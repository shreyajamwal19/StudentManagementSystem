#!/usr/bin/env bash
# One-command pipeline to reproduce the experiments. Prerequisites (see docs/reproducibility.md):
#   PostgreSQL running with schema access, Besu QBFT network running (besu-network/start.sh), data/*.csv in place,
#   env: PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PSEUDONYM_PEPPER ACCOUNTS_PASSWORD JWT_SECRET
# Usage: scripts/run_all.sh [--smoke] [--skip-tests] [--dry-run]
#   --smoke       tiny benchmark (workloads 50,100 x 2 runs) to check the pipeline; full spec benchmark otherwise
set -euo pipefail
cd "$(dirname "$0")/.."
SMOKE=0; TESTS=1; DRY=0
for a in "$@"; do case "$a" in --smoke) SMOKE=1;; --skip-tests) TESTS=0;; --dry-run) DRY=1;; *) echo "unknown option $a"; exit 2;; esac; done
run() { echo; echo ">>> $*"; if [ "$DRY" = 0 ]; then "$@"; fi; }

for v in PGHOST PGDATABASE PGUSER PGPASSWORD PSEUDONYM_PEPPER ACCOUNTS_PASSWORD JWT_SECRET; do
  [ -n "${!v:-}" ] || { echo "Missing env var $v"; [ "$DRY" = 1 ] || exit 1; }
done
[ "$DRY" = 1 ] || curl -s -m 5 -X POST "${BESU_RPC:-http://127.0.0.1:8545}" -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | grep -q result || { echo "Besu RPC not reachable"; exit 1; }

run python3 scripts/import_dataset.py || true        # refuses if tables are not empty (safe to re-run)
run python3 scripts/verify_import.py
run bash -c 'cd contracts && npm install --silent && node compile.js'
[ -f secrets/addresses.json ] || run python3 scripts/make_accounts.py
[ -f besu-network/deployment.json ] || run python3 contracts/deploy.py
run python3 scripts/anchor_initial.py --batch-size 250      # resumable; anchors all 50,000 version-1 records
run python3 scripts/summarize_anchoring.py
if [ "$TESTS" = 1 ]; then
  run bash -c 'cd backend && python3 -m pytest -q tests'
  run bash -c 'cd contracts && python3 -m pytest -q tests'
fi
run python3 experiments/security/run_security_experiments.py
run python3 experiments/provenance/run_provenance.py
if [ "$SMOKE" = 1 ]; then
  run python3 experiments/benchmark/run_benchmark.py --workloads 50,100 --runs 2 --warmup 10 --tag smoke
  run python3 experiments/benchmark/analyze_performance.py --tag smoke
else
  run python3 experiments/benchmark/run_benchmark.py
  run python3 experiments/benchmark/analyze_performance.py
fi
echo; echo "Done. Results: experiments/results, figures: experiments/figures"
