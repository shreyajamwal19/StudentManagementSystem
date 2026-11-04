#!/usr/bin/env python3
"""Summarize initial batch anchoring from chain_anchor (real recorded receipts) -> experiments/results/initial_anchoring.json."""
import datetime, json, pathlib, psycopg2, statistics
ROOT = pathlib.Path(__file__).resolve().parent.parent
cur = psycopg2.connect().cursor()
cur.execute("SELECT count(*) FROM marks_b"); total = cur.fetchone()[0]
cur.execute("SELECT tx_hash, count(*), max(confirm_ms), max(block_number) FROM chain_anchor WHERE action='IMPORT' GROUP BY tx_hash")
rows = cur.fetchall()
conf = [r[2] for r in rows if r[2] is not None]
out = {"summarized_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
       "records_in_dataset": total, "records_anchored": sum(r[1] for r in rows), "anchoring_complete": sum(r[1] for r in rows) == total,
       "import_transactions": len(rows), "records_per_tx_mean": round(sum(r[1] for r in rows) / max(len(rows), 1), 1),
       "confirm_ms_per_tx": {"mean": round(statistics.mean(conf), 1), "median": round(statistics.median(conf), 1), "max": round(max(conf), 1)} if conf else None,
       "first_block": min(r[3] for r in rows) if rows else None, "last_block": max(r[3] for r in rows) if rows else None}
(ROOT / "experiments/results/initial_anchoring.json").write_text(json.dumps(out, indent=2) + "\n"); print(json.dumps(out, indent=2))
