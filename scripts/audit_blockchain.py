import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import psycopg2
from psycopg2.extras import RealDictCursor
from web3 import Web3
from app.chain import get_chain
from app.hashing import record_hash, ZERO_HASH

EXPECTED_ADDRESS = Web3.to_checksum_address(
    "0xc04C728eAA5914060DeB231628751A7292D317E1"
)
EXPECTED_CHAIN_ID = 20260
EXPECTED_RECORDS = 50000


def clean_hash(value):
    return str(value).lower().removeprefix("0x")


def retry_rpc(function, *args, attempts=3):
    """Retry temporary RPC read failures without hiding persistent errors."""
    for attempt in range(attempts):
        try:
            return function(*args)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(attempt + 1)


def main():
    print("Starting READ-ONLY audit of the main Besu deployment...")

    db = psycopg2.connect()
    db.set_session(readonly=True, autocommit=False)
    cur = db.cursor(cursor_factory=RealDictCursor)

    try:
        chain = get_chain()
        actual_address = Web3.to_checksum_address(chain.c.address)

        print("Besu chain ID:", chain.w3.eth.chain_id)
        print("Contract address:", actual_address)

        if chain.w3.eth.chain_id != EXPECTED_CHAIN_ID:
            raise RuntimeError("Wrong Besu chain ID; refusing to audit.")
        if actual_address != EXPECTED_ADDRESS:
            raise RuntimeError("Wrong contract address; refusing to audit.")

        cur.execute("""
            SELECT m.record_id, m.student_id, m.course_id, m.assessment_id,
                   m.marks_obtained, m.status, m.version_no, a.max_marks,
                   s.pseudonym
            FROM marks_b m
            JOIN students s ON s.student_id = m.student_id
            JOIN assessments a ON a.assessment_id = m.assessment_id
            ORDER BY m.record_id
        """)
        records = cur.fetchall()
        expected_count = len(records)

        cur.execute("""
            SELECT record_id, version_no, marks_obtained, status,
                   record_hash, prev_hash
            FROM record_versions_b
            ORDER BY record_id, version_no
        """)
        versions_by_record = {}
        for row in cur.fetchall():
            versions_by_record.setdefault(row["record_id"], []).append(row)

        cur.execute("""
            SELECT record_id, version_no, record_hash, prev_hash,
                   tx_hash, block_number
            FROM chain_anchor
            ORDER BY record_id, version_no
        """)
        anchors = {
            (row["record_id"], row["version_no"]): row
            for row in cur.fetchall()
        }

        print("Database current records:", expected_count)
        print("Database historical versions:", sum(map(len, versions_by_record.values())))
        print("Database chain anchors:", len(anchors))
        print("Besu current block:", chain.w3.eth.block_number)
        print("\nChecking current hashes and complete histories...")

        checked = 0
        latest_matches = 0
        histories_checked = 0
        history_matches = 0
        missing_anchors = 0
        mismatches = []
        errors = []

        for rec in records:
            record_id = rec["record_id"]
            key = Web3.keccak(text=record_id)
            versions = versions_by_record.get(record_id, [])

            try:
                current_db_hash = record_hash(
                    record_id, rec["pseudonym"], rec["course_id"],
                    rec["assessment_id"], rec["max_marks"],
                    rec["marks_obtained"], rec["status"], rec["version_no"]
                )

                current_chain_hash = clean_hash(retry_rpc(chain.latest_hash, key).hex())
                checked += 1

                if current_db_hash == current_chain_hash:
                    latest_matches += 1
                else:
                    mismatches.append(f"{record_id}: latest hash mismatch")

                chain_versions = retry_rpc(chain.history_length, key)

                if chain_versions != len(versions):
                    mismatches.append(
                        f"{record_id}: DB versions={len(versions)}, chain versions={chain_versions}"
                    )

                if rec["version_no"] != len(versions):
                    mismatches.append(
                        f"{record_id}: current version={rec['version_no']}, history rows={len(versions)}"
                    )

                for i, version in enumerate(versions):
                    version_no = i + 1
                    histories_checked += 1

                    expected_prev = (
                        ZERO_HASH if i == 0
                        else clean_hash(versions[i - 1]["record_hash"])
                    )
                    stored_hash = clean_hash(version["record_hash"])
                    stored_prev = clean_hash(version["prev_hash"])

                    recomputed_hash = record_hash(
                        record_id, rec["pseudonym"], rec["course_id"],
                        rec["assessment_id"], rec["max_marks"],
                        version["marks_obtained"], version["status"],
                        version["version_no"]
                    )

                    if i >= chain_versions:
                        mismatches.append(
                            f"{record_id} v{version_no}: missing on-chain entry"
                        )
                        continue

                    entry = retry_rpc(chain.entry, key, i)
                    entry_hash = clean_hash(entry["curr_hash"])
                    entry_prev = clean_hash(entry["prev_hash"])

                    if (
                        recomputed_hash != stored_hash
                        or stored_hash != entry_hash
                        or stored_prev != entry_prev
                        or stored_prev != expected_prev
                    ):
                        mismatches.append(
                            f"{record_id} v{version_no}: history/hash mismatch"
                        )
                    else:
                        history_matches += 1

                    if (record_id, version_no) not in anchors:
                        missing_anchors += 1

            except Exception as exc:
                errors.append((record_id, str(exc)))

            if checked and checked % 500 == 0:
                print(
                    f"Progress: {checked}/{expected_count} records | "
                    f"Latest matches: {latest_matches} | "
                    f"History entries matched: {history_matches}"
                )

        print("\n========== BLOCKCHAIN AUDIT REPORT ==========")
        print("Expected records:", EXPECTED_RECORDS)
        print("Database records:", expected_count)
        print("Current records checked:", checked)
        print("Latest hashes matching:", latest_matches)
        print("Historical versions checked:", histories_checked)
        print("Historical entries matching:", history_matches)
        print("Missing database anchors:", missing_anchors)
        print("Hash/history mismatches:", len(mismatches))
        print("RPC or processing errors:", len(errors))

        if mismatches:
            print("\nMismatches (first 20):")
            for item in mismatches[:20]:
                print("-", item)

        if errors:
            print("\nErrors (first 10):")
            for item in errors[:10]:
                print("-", item)

        passed = (
            expected_count == EXPECTED_RECORDS
            and checked == expected_count
            and latest_matches == expected_count
            and histories_checked == history_matches
            and len(anchors) == histories_checked
            and missing_anchors == 0
            and not mismatches
            and not errors
        )

        print("\nFINAL RESULT:", "PASS" if passed else "FAIL")

    finally:
        cur.close()
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
