# Reproducibility

**Software (tested in development):** Python 3.12, FastAPI, psycopg2, web3.py 8, PostgreSQL 16, Besu 26.10.2 (needs Java 25), solc 0.8.38 (solc-js, EVM shanghai), Node 22 (frontend/contracts compile), pandas/matplotlib.
Besu tarball SHA-256 used: `8cc633e19cb23cd38b5d6ad988b725c8533389a773aea65782fd16d37946825b`. Dataset: `data/DATASET.sha256` (verified by the import script).
**Besu configuration:** `besu-network/qbftConfigFile.json` (chainId 20260, QBFT, 2 s blocks, 4 validators, free gas); each benchmark/security run deploys a fresh contract and fresh signer keys.
**Hardware:** each run writes `experiments/results/raw/<tag>_config.json` (CPU, RAM, OS, versions, dataset hash, config). The numbers in this repository so far come from a 1-CPU / 4 GB sandbox and are NOT paper results; only the security (T1-T6) and provenance outcomes are logical results that do not depend on hardware.
**Dataset:** 50,000 rows, 1,000 students, 10 courses, 5 assessments (max 20/20/20/30/50), 10 faculty (one per course), no missing values or duplicates. Statuses are random per row.
**Workload generation:** seeded random record order and marks, identical request sequence for A and B (see `docs/benchmarking.md`). **Measurement:** client-side end-to-end latency plus server-reported database, chain-read, submit and confirmation times.

**Run everything:** `scripts/run_all.sh` (add `--smoke` for a quick check, `--dry-run` to print the steps). Tests: `cd backend && pytest`, `cd contracts && pytest`, `cd frontend && npm test`.
**Not yet done / needs your machine:** anchoring all 50,000 records, the full 10-run benchmark, Docker Compose packaging of Besu/PostgreSQL (the PostgreSQL compose file is untested), a cloud demonstration (see `docs/cloud-deployment.md`), browser testing of the dashboard.
