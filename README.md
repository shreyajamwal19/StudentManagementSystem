# Blockchain-Based Secure Academic Records Management Framework (Research Prototype)

A research proof of concept comparing a **conventional database-only system (System A)** with a
**PostgreSQL + Hyperledger Besu system (System B)** for tamper-evident academic records.
Not a production university ERP.

## Status
| Milestone | State |
|---|---|
| 1. Project setup, Git, PostgreSQL Docker Compose, docs | done |
| 2. Schema + dataset import | done (verified; see experiments/results/import_verification.json) |
| 3. System A (conventional baseline) | pending |
| 4+. Besu, contract, Web3j, experiments, frontend | pending |

## Stack
Java 17 / Spring Boot 3 / PostgreSQL / Hyperledger Besu (QBFT) / Solidity / Web3j / React + Vite + Tailwind / Python (pandas, matplotlib).

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

## Security rules
No secrets, keys, `.env` files or tokens are ever committed. Authenticate to GitHub with `gh auth login`
or your OS credential manager, never by embedding a token in the remote URL.

## Docs
- `docs/architecture.md` design and business rules
- `docs/database-schema.md` schema and import
- `docs/cloud-deployment.md` cloud deployment plan
