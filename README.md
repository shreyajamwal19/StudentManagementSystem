# Blockchain-Based Secure Academic Records Management Framework (Research Prototype)

A proof of concept comparing a **conventional database-only system (System A)** with a **PostgreSQL + Hyperledger Besu system (System B)**
for tamper-evident academic records. Not a production university ERP. Blockchain complements cloud/database storage; marks never go on-chain, only hashes.

## What is implemented (all verified by tests/experiments run in the development sandbox)
| Part | Status |
|---|---|
| PostgreSQL schema + import of the 50,000-record CSV into identical System A / System B tables | done, verified (`experiments/results/import_verification.json`) |
| System A: JWT auth, 4 roles, course-scoped faculty, state machine, audit log | done, tests pass |
| Hyperledger Besu QBFT network (4 validators, chainId 20260) | done, verified incl. fault-tolerance test |
| Solidity contract (roles, course assignment, state machine, prevHash linkage, append-only) | done, 12 tests on Besu |
| System B: SHA-256 canonical hashing, web3.py anchoring, verification API, tamper detection | done, 10 tests on Besu (31 backend tests total) |
| Security experiments T1-T6 on both systems | done (`experiments/results/security_results.*`) |
| Provenance experiment + diagram (`Fig_Provenance.png`) | done |
| Benchmark harness, analysis, `Fig_Performance.png` generator | done, smoke-tested only |
| Minimal React dashboard | done (build + render tests; not browser-tested) |
| Anchoring all 50,000 records, full benchmark, cloud demo, Docker packaging | **pending, needs your machine** (see `docs/reproducibility.md`) |

Deviation from the original plan: the backend is Python/FastAPI with web3.py (instead of Spring Boot/Web3j) because Maven Central was unreachable in the development sandbox. Confirm with your supervisor and state it in the paper.

## Layout
`backend/` FastAPI app + tests · `contracts/` Solidity, compile/deploy, tests · `besu-network/` QBFT config and scripts · `frontend/` dashboard ·
`experiments/` security, provenance, benchmark, results, figures · `scripts/` import, anchoring, accounts, `run_all.sh` · `docs/` design notes · `data/` dataset (CSV not tracked, checksum tracked)

## Quick start
```bash
cp .env.example .env && docker compose up -d postgres      # PostgreSQL (compose file not yet tested by the author)
./scripts/install_hooks.sh                                  # secret scan before commits
pip install -r backend/requirements.txt && pip install web3 pandas matplotlib
export BESU_BIN=/path/to/besu-26.10.2/bin/besu              # Java 25 required
(cd besu-network && ./setup.sh && ./start.sh)
export PGHOST=localhost PGDATABASE=academic_records PGUSER=academic_app PGPASSWORD=... \
       PSEUDONYM_PEPPER=$(python3 -c "import secrets;print(secrets.token_hex(32))") ACCOUNTS_PASSWORD=... JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
./scripts/run_all.sh --smoke                                # import, deploy, anchor, tests, T1-T6, provenance, smoke benchmark
```
Then `scripts/seed_users.py`, `uvicorn app.main:app` (in `backend/`), and `cd frontend && npm install && npm run dev`.

## Security rules
No secrets, keys, `.env` files or tokens are committed (`.gitignore` + pre-commit scan). Authenticate to GitHub with `gh auth login` or a credential manager, never a token in a remote URL.

## Docs
`docs/architecture.md` · `docs/database-schema.md` · `docs/besu.md` · `docs/smart-contract.md` · `docs/security-experiments.md` · `docs/provenance.md` · `docs/benchmarking.md` ·
`docs/frontend.md` · `docs/privacy-and-limitations.md` · `docs/reproducibility.md` · `docs/cloud-deployment.md`
