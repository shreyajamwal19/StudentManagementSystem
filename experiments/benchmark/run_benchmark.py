#!/usr/bin/env python3
"""Performance benchmark: System A (DB only) vs System B (DB + Besu). Same records, same request sequence, same hardware.
Each transaction = one authorized 'update_marks' HTTP request by the course's faculty (the same business rule in both systems).
Per transaction we store: end-to-end latency (client side), and the server-reported split into database time, blockchain
verification read, blockchain submission time and blockchain confirmation time.
Usage: run_benchmark.py [--workloads 100,500,1000,2500,5000] [--runs 10] [--concurrency 8] [--seed 42] [--tag name]
Output: experiments/results/raw/<tag>_raw.csv (every transaction), <tag>_runs.csv (one row per run), <tag>_config.json."""
import argparse, csv, datetime, json, pathlib, random, sys, time
from concurrent.futures import ThreadPoolExecutor
import httpx
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
from common import ExperimentEnv
from collect_environment import collect

ap = argparse.ArgumentParser()
ap.add_argument("--workloads", default="100,500,1000,2500,5000"); ap.add_argument("--runs", type=int, default=10)
ap.add_argument("--concurrency", type=int, default=8); ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--warmup", type=int, default=30); ap.add_argument("--tag", default="benchmark")
a = ap.parse_args()
workloads = [int(x) for x in a.workloads.split(",")]
OUT = HERE.parent / "results" / "raw"; OUT.mkdir(parents=True, exist_ok=True)

def main():
    import psycopg2
    p = psycopg2.connect(); c = p.cursor()
    c.execute("SELECT m.record_id, c.faculty_id, a.max_marks FROM marks_a m JOIN courses c USING(course_id) JOIN assessments a USING(assessment_id) "
              "WHERE m.status='Entered' ORDER BY m.record_id")
    recs = c.fetchall(); p.close()          # eligible: records that allow update_marks (status Entered)
    print(f"{len(recs)} Entered records; workloads {workloads}; runs {a.runs}; concurrency {a.concurrency}", flush=True)
    raw_f = open(OUT / f"{a.tag}_raw.csv", "w", newline=""); runs_f = open(OUT / f"{a.tag}_runs.csv", "w", newline="")
    raw = csv.writer(raw_f); runs = csv.writer(runs_f)
    raw.writerow(["system", "workload", "run", "tx_index", "record_id", "http_status", "e2e_ms", "server_total_ms", "db_ms", "verify_ms", "submit_ms", "confirm_ms"])
    runs.writerow(["system", "workload", "run", "transactions", "successes", "wall_seconds", "tps", "mean_e2e_ms", "std_e2e_ms"])
    with ExperimentEnv(anchor_records=[r[0] for r in recs]) as env:
        tokens = {f: env.token(f.lower()) for f in sorted({r[1] for r in recs})}
        clients = {}
        def client_for(tid):
            import threading
            k = threading.get_ident()
            if k not in clients: clients[k] = httpx.Client(timeout=300, limits=httpx.Limits(max_connections=4))
            return clients[k]
        def one(args):
            system, k, rec, marks = args
            rid, fac, _ = rec
            t0 = time.perf_counter()
            try:
                r = client_for(0).post(f"{env.base}/api/{system}/records/{rid}/actions/update_marks", json={"marks": marks}, headers=tokens[fac])
                e2e = (time.perf_counter() - t0) * 1000
                tm = r.json().get("timings_ms", {}) if r.status_code == 200 else {}
                return (k, rid, r.status_code, e2e, tm.get("total_ms"), tm.get("db_ms"), tm.get("verify_ms"), tm.get("submit_ms"), tm.get("confirm_ms"))
            except Exception:
                return (k, rid, 0, (time.perf_counter() - t0) * 1000, None, None, None, None, None)
        def make_requests(system, n, seed):
            rng = random.Random(seed); order = list(range(len(recs))); rng.shuffle(order)
            out = []
            for k in range(n):
                rec = recs[order[k % len(order)]]
                out.append((system, k, rec, f"{rng.randint(0, rec[2] * 10) / 10:.1f}"))
            return out
        # warm-up (not recorded): JIT, connection pools, keystore decryption
        for system in ("a", "b"):
            with ThreadPoolExecutor(a.concurrency) as ex: list(ex.map(one, make_requests(system, a.warmup, a.seed - 1)))
        for w in workloads:
            for run in range(1, a.runs + 1):
                for system in (("a", "b") if run % 2 else ("b", "a")):     # alternate order to avoid time-drift bias
                    reqs = make_requests(system, w, a.seed * 1000 + w * 10 + run)
                    t0 = time.perf_counter()
                    with ThreadPoolExecutor(a.concurrency) as ex: res = list(ex.map(one, reqs))
                    wall = time.perf_counter() - t0
                    ok = [r for r in res if r[2] == 200]
                    lat = [r[3] for r in ok]
                    mean = sum(lat) / len(lat) if lat else float("nan")
                    std = (sum((x - mean) ** 2 for x in lat) / (len(lat) - 1)) ** 0.5 if len(lat) > 1 else 0.0
                    for r in res: raw.writerow([system.upper(), w, run, r[0], r[1], r[2]] + [("" if v is None else round(v, 3)) for v in r[3:]])
                    runs.writerow([system.upper(), w, run, w, len(ok), round(wall, 3), round(len(ok) / wall, 3), round(mean, 3), round(std, 3)])
                    raw_f.flush(); runs_f.flush()
                    print(f"workload {w} run {run} {system.upper()}: ok {len(ok)}/{w} wall {wall:.1f}s tps {len(ok)/wall:.1f} mean {mean:.0f} ms", flush=True)
        cfg = collect({"run_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "workloads": workloads, "runs": a.runs,
                       "concurrency": a.concurrency, "seed": a.seed, "warmup_requests": a.warmup, "eligible_records": len(recs),
                       "operation": "authorized update_marks on an Entered record (same rules in A and B)",
                       "contract": env.deploy_info, "note": "System B includes an on-chain integrity pre-check read before each write, one chain transaction per request, DB commit after confirmation."})
        (OUT / f"{a.tag}_config.json").write_text(json.dumps(cfg, indent=2, default=str) + "\n")
    raw_f.close(); runs_f.close()

if __name__ == "__main__":
    main()
