#!/usr/bin/env python3
"""Batch-anchor version 1 of every System B record on Besu (importRecords, signed by admin1). Resumable: records already in
chain_anchor are skipped. Env: PG*, PSEUDONYM_PEPPER, ACCOUNTS_PASSWORD (+ BESU_RPC, DEPLOYMENT_FILE, KEYSTORE_DIR).
Usage: anchor_initial.py [--batch-size 100] [--limit N]"""
import argparse, datetime, json, pathlib, sys, time
import psycopg2
from psycopg2.extras import execute_values
from web3 import Web3
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.chain import Chain, STATUS_ID
from app.hashing import ZERO_HASH, b32_ascii, marks_hash, pepper, record_key

ap = argparse.ArgumentParser(); ap.add_argument("--batch-size", type=int, default=100); ap.add_argument("--limit", type=int, default=None)
ap.add_argument("--max-batches", type=int, default=None)
a = ap.parse_args()
pep = pepper(); chain = Chain()
conn = psycopg2.connect(); cur = conn.cursor()
cur.execute("""SELECT m.record_id, s.pseudonym, m.course_id, m.assessment_id, m.marks_obtained, m.status, v.record_hash
               FROM marks_b m JOIN students s USING(student_id) JOIN record_versions_b v ON v.record_id=m.record_id AND v.version_no=1
               WHERE m.version_no = 1 AND NOT EXISTS (SELECT 1 FROM chain_anchor c WHERE c.record_id=m.record_id AND c.version_no=1)
               ORDER BY m.record_id""" + (f" LIMIT {int(a.limit)}" if a.limit else ""))
rows = cur.fetchall()
print(f"{len(rows)} records to anchor, batch size {a.batch_size}", flush=True)
t_start = time.time(); stats = []; first_block = last_block = None
def reconcile(chunk):
    """Crash safety: if a previous run was killed after the chain transaction but before the DB insert, the records are already on
    chain. Recover their tx hash/block from the RecordEvent logs instead of re-importing (which would revert with 'exists')."""
    done = [r for r in chunk if chain.history_length(record_key(r[0])) > 0]
    for r in done:
        ev = chain.c.events.RecordEvent().get_logs(from_block=0, argument_filters={"key": record_key(r[0])})[0]
        tx = chain.w3.eth.get_transaction_receipt(ev["transactionHash"])
        cur.execute("INSERT INTO chain_anchor (record_id, version_no, action, record_hash, prev_hash, tx_hash, block_number, actor_address, batch_id) "
                    "VALUES (%s,1,'IMPORT',%s,%s,%s,%s,%s,'reconciled')", (r[0], r[6], ZERO_HASH, Web3.to_hex(ev["transactionHash"]), ev["blockNumber"], tx["from"]))
    conn.commit()
    return [r for r in chunk if r not in done]

for bi in range(0, len(rows), a.batch_size):
    if a.max_batches is not None and bi // a.batch_size >= a.max_batches:
        break
    chunk = rows[bi:bi + a.batch_size]
    if chain.history_length(record_key(chunk[0][0])) > 0 or chain.history_length(record_key(chunk[-1][0])) > 0:
        chunk = reconcile(chunk)
        if not chunk:
            print("reconciled a batch that was already on chain", flush=True); continue
    items = [(record_key(r[0]), bytes.fromhex(r[1]), b32_ascii(r[2]), b32_ascii(r[3]), bytes.fromhex(marks_hash(pep, r[0], r[4])),
              bytes.fromhex(r[6]), STATUS_ID[r[5]]) for r in chunk]
    res = chain.import_batch(items)
    batch_id = f"import-{res['block_number']}-{bi // a.batch_size}"
    execute_values(cur, "INSERT INTO chain_anchor (record_id, version_no, action, record_hash, prev_hash, tx_hash, block_number, actor_address, batch_id, submit_ms, confirm_ms) VALUES %s",
                   [(r[0], 1, "IMPORT", r[6], ZERO_HASH, res["tx_hash"], res["block_number"], res["actor_address"], batch_id, res["submit_ms"], res["confirm_ms"]) for r in chunk])
    conn.commit()
    first_block = first_block or res["block_number"]; last_block = res["block_number"]
    stats.append({"records": len(chunk), "confirm_ms": res["confirm_ms"], "gas_used": res["receipt"]["gasUsed"]})
    print(f"batch {bi // a.batch_size + 1}/{-(-len(rows) // a.batch_size)}: {len(chunk)} records, block {res['block_number']}, "
          f"confirm {res['confirm_ms']:.0f} ms, gas {res['receipt']['gasUsed']}", flush=True)
print(f"done in {time.time() - t_start:.0f}s; run scripts/summarize_anchoring.py for the summary", flush=True)
