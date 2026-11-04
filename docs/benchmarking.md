# Performance benchmark (Result 1 and Result 2)

**Workload:** each transaction is one authorized `update_marks` HTTP request by the course's faculty on an `Entered` record. Same business rules and checks in both systems
(JWT auth, role, course scope, state machine, DB update, version row, audit log). System B additionally does one integrity read from Besu, hashing, and one Besu transaction that
must be confirmed (one QBFT block) before the DB transaction commits.
**Design:** closed-loop clients (default 8 concurrent workers), identical request sequence for A and B (seeded), A/B order alternated between runs, 30 warm-up requests per system
(not recorded), fresh isolated database copy + fresh contract per benchmark execution, workloads 100/500/1000/2500/5000, 10 runs each.
**Per-transaction measurements (raw CSV):** `e2e_ms` (client-side end-to-end), `server_total_ms`, `db_ms` (server time excluding chain calls), `verify_ms` (on-chain integrity read),
`submit_ms` (transaction accepted by the node), `confirm_ms` (submit + wait for the receipt, i.e. block inclusion), `http_status`.
**Aggregates:** average latency = mean of per-run means; error bars/std = standard deviation across runs; TPS = successful transactions / wall time of the run; success rate = HTTP 200 share.

## Run it (on your machine, with Besu and PostgreSQL running)
```bash
python3 experiments/benchmark/run_benchmark.py            # full spec: 5 workloads x 10 runs x 2 systems (long: System B is bounded by block time)
python3 experiments/benchmark/analyze_performance.py      # -> experiments/results/performance_summary.csv, experiments/figures/Fig_Performance.png (300 DPI)
```
Quick check: `run_benchmark.py --workloads 50,100 --runs 2 --tag smoke && analyze_performance.py --tag smoke`.
Raw files go to `experiments/results/raw/` (git-ignored because of size; keep them with your results). `<tag>_config.json` records hardware, software versions, dataset SHA-256 and Besu config.

## Smoke test status (NOT paper results)
`performance_summary_smoke.csv` and the `*_smoke.png` figures come from a tiny run (workloads 50 and 100, 2 runs) on the 1-CPU / 4 GB development sandbox with the load generator, API, PostgreSQL and
four Besu validators on the same CPU. They only prove the pipeline works. Do not cite them. Run the full benchmark on your machine and report that hardware.
Observed in the smoke run: System A ~30 TPS and ~250 ms; System B ~3-4 TPS and ~2 s, dominated by blockchain confirmation (one 2 s block period). This is the expected cost of waiting for a confirmed block per transaction.
