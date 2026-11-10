# Blockchain-Based Secure Academic Records Management Framework (Research Prototype)

A research proof of concept comparing a **conventional database-only system (System A)** with a
**PostgreSQL + Hyperledger Besu system (System B)** for tamper-evident academic records.
Not a production university ERP.

## Status
| Milestone | State |
|---|---|
| 1. Project setup, Git, PostgreSQL Docker Compose, docs | done |
| 2. Schema + dataset import | done (verified; see experiments/results/import_verification.json) |
| 3. System A (conventional baseline: JWT, RBAC, state machine, audit log) | done, 19 tests pass |
| 4. Besu QBFT network (4 validators) | done, verified |
| 5. Solidity contract, signer accounts, deployment | done, 12 tests pass on Besu |
| 6. System B: web3.py anchoring, verification API, tamper detection | done, 29 backend tests pass |
| 7-8. Security experiments T1-T6 (both systems) | done, results in experiments/results |
| 9. Benchmark harness + analysis + figures (smoke-tested only; full run on your machine) | done, results pending |
| 10. Provenance experiment + diagram (Result 4) | done, verified on Besu |
| 11. Minimal React dashboard | done (build + render tests pass; not browser-tested) |
| 12. Full 50,000-record anchoring, full benchmark, final docs and rerun script | pending (needs your machine) |

## Stack
Python 3.12 / FastAPI (instead of Spring Boot, see docs/architecture.md) / PostgreSQL / Hyperledger Besu (QBFT) / Solidity / web3.py / React + Vite + Tailwind / Python (pandas, matplotlib).

## Layout
`backend/` Spring Boot · `contracts/` Solidity · `besu-network/` QBFT network · `frontend/` dashboard ·
`experiments/` benchmarks, security tests, results · `docs/` design notes · `data/` dataset (CSV not tracked) · `scripts/` helpers

## Quick start (so far)
```bash
cp .env.example .env          # then edit POSTGRES_PASSWORD
docker compose up -d postgres
docker compose ps             # wait for "healthy"
./scripts/install_hooks.sh    # enable secret scan before commits
```
Place `synthetic_student_marks_50000_1.csv` in `data/` and verify: `cd data && sha256sum -c DATASET.sha256`

## Import dataset
```bash
pip install psycopg2-binary
export PGHOST=localhost PGDATABASE=academic_records PGUSER=academic_app PGPASSWORD=... PSEUDONYM_PEPPER=...
python3 scripts/import_dataset.py && python3 scripts/verify_import.py
```

## Run System A
```bash
pip install -r backend/requirements.txt
export JWT_SECRET=<32+ random chars> SEED_PASSWORD=<demo password>   # plus PGHOST/PGDATABASE/PGUSER/PGPASSWORD
python3 scripts/seed_users.py 20
cd backend && uvicorn app.main:app --port 8000     # API docs at /docs
cd backend && python3 -m pytest -q                  # uses a throw-away DB copy (role needs CREATEDB)
```

## Security rules
No secrets, keys, `.env` files or tokens are ever committed. Authenticate to GitHub with `gh auth login`
or your OS credential manager, never by embedding a token in the remote URL.

## Docs
- `docs/architecture.md` design and business rules
- `docs/database-schema.md` schema and import
- `docs/besu.md` Besu QBFT network
- `docs/frontend.md` dashboard
- `docs/provenance.md` provenance experiment
- `docs/benchmarking.md` benchmark method and how to run
- `docs/security-experiments.md` T1-T6 method and results
- `docs/smart-contract.md` contract design, functions, deployment
- `docs/cloud-deployment.md` cloud deployment plan
