"""System B: same business rules as System A (inherited), plus SHA-256 hashing and a Besu transaction per event.
Order inside one DB transaction: integrity pre-check -> DB write -> chain transaction (waits for confirmation) -> commit.
If the chain rejects the transaction the DB write is rolled back, so both stay consistent."""
import time
from typing import Optional
from psycopg2.extras import RealDictCursor
from .chain import ChainError, STATUS_ID, get_chain
from .db import connection
from .hashing import ZERO_HASH, b32_ascii, marks_hash, pepper, pseudonym, record_hash, record_key
from .security import User
from .service import ApiError, MarksService
from .workflow import LOCKED  # noqa: F401


class MarksServiceB(MarksService):
    def __init__(self):
        super().__init__("b")

    # ---- helpers ---------------------------------------------------------
    def _hash_of(self, cur, row) -> str:
        cur.execute("SELECT pseudonym FROM students WHERE student_id=%s", (row["student_id"],))
        ps = cur.fetchone()["pseudonym"]
        return record_hash(row["record_id"], ps, row["course_id"], row["assessment_id"], row["max_marks"],
                           row["marks_obtained"], row["status"], row["version_no"])

    # ---- hooks -----------------------------------------------------------
    def _precheck(self, cur, rec, action, u, t):
        """The database row must still match the hash anchored on Besu; otherwise refuse to build on a tampered record."""
        t0 = time.perf_counter()
        db_hash = self._hash_of(cur, rec)
        chain_hash = get_chain().latest_hash(record_key(rec["record_id"])).hex()
        t["verify_ms"] += (time.perf_counter() - t0) * 1000
        if db_hash != chain_hash:
            raise ApiError(409, "INTEGRITY MISMATCH DETECTED: database record differs from the version anchored on the blockchain")

    def _hashes(self, cur, after):
        cur.execute("SELECT record_hash FROM record_versions_b WHERE record_id=%s AND version_no=%s",
                    (after["record_id"], after["version_no"] - 1))
        row = cur.fetchone()
        return (self._hash_of(cur, after), row["record_hash"] if row else ZERO_HASH)

    def _after_apply(self, cur, after, action, u, hashes, t):
        rhash, phash = hashes
        try:
            r = get_chain().send_action(u, action, record_key(after["record_id"]), bytes.fromhex(phash),
                                        bytes.fromhex(marks_hash(pepper(), after["record_id"], after["marks_obtained"])), bytes.fromhex(rhash))
        except ChainError as e:
            raise ApiError(409, f"Blockchain rejected the transaction: {e}")
        t["submit_ms"] += r["submit_ms"]; t["confirm_ms"] += r["confirm_ms"]
        cur.execute("INSERT INTO chain_anchor (record_id, version_no, action, record_hash, prev_hash, tx_hash, block_number, actor_address, submit_ms, confirm_ms) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (after["record_id"], after["version_no"], action.upper(), rhash, phash, r["tx_hash"], r["block_number"],
                     r["actor_address"], r["submit_ms"], r["confirm_ms"]))
        return {"tx_hash": r["tx_hash"], "block_number": r["block_number"], "record_hash": rhash, "prev_hash": phash}

    # ---- verification & provenance ---------------------------------------
    def verify(self, u: User, record_id: str) -> dict:
        self.get(u, record_id)                                     # same visibility rules as reads
        t0 = time.perf_counter()
        chain = get_chain(); key = record_key(record_id)
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            rec = self._fetch(cur, record_id)
            db_hash = self._hash_of(cur, rec)
            cur.execute("SELECT version_no, marks_obtained, status, record_hash, prev_hash FROM record_versions_b WHERE record_id=%s ORDER BY version_no", (record_id,))
            versions = cur.fetchall()
            cur.execute("SELECT pseudonym FROM students WHERE student_id=%s", (rec["student_id"],))
            ps = cur.fetchone()["pseudonym"]
        n = chain.history_length(key)
        chain_hash = chain.latest_hash(key).hex()
        bad = []
        for i in range(max(n, len(versions))):
            if i >= n or i >= len(versions):
                bad.append(i + 1); continue
            e = chain.entry(key, i); v = versions[i]
            exp_prev = ZERO_HASH if i == 0 else versions[i - 1]["record_hash"]
            # recompute the hash from the stored version row (detects edits to historical marks/status) and compare to chain
            vh = record_hash(record_id, ps, rec["course_id"], rec["assessment_id"], rec["max_marks"], v["marks_obtained"], v["status"], v["version_no"])
            if vh != e["curr_hash"] or e["curr_hash"] != v["record_hash"] or e["prev_hash"] != v["prev_hash"] or v["prev_hash"] != exp_prev:
                bad.append(i + 1)
        match = (n > 0 and db_hash == chain_hash and rec["version_no"] == n)
        return {"record_id": record_id,
                "result": "MATCH" if match and not bad else "INTEGRITY_MISMATCH",
                "message": ("Record matches the anchored version." if match and not bad else "INTEGRITY MISMATCH DETECTED"),
                "current_record_matches_chain": match, "db_version": rec["version_no"], "chain_versions": n,
                "db_hash": db_hash, "chain_hash": chain_hash, "history_consistent": not bad, "mismatched_versions": bad,
                "verify_ms": round((time.perf_counter() - t0) * 1000, 2)}

    def chain_history(self, u: User, record_id: str) -> list:
        self.get(u, record_id)
        chain = get_chain(); key = record_key(record_id)
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT version_no, tx_hash, block_number, actor_address FROM chain_anchor WHERE record_id=%s", (record_id,))
            anchors = {r["version_no"]: r for r in cur.fetchall()}
            cur.execute("SELECT version_no, action, marks_obtained, actor FROM record_versions_b WHERE record_id=%s", (record_id,))
            dbv = {r["version_no"]: r for r in cur.fetchall()}
        out = []
        for i in range(chain.history_length(key)):
            e = chain.entry(key, i); a = anchors.get(i + 1, {}); d = dbv.get(i + 1, {})
            out.append(dict(e, version_no=i + 1, tx_hash=a.get("tx_hash"), block_number=a.get("block_number"),
                            db_action=d.get("action"), db_actor=d.get("actor")))
        return out
