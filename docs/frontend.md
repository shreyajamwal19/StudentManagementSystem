# Dashboard (React + Vite + Tailwind)

Minimal research dashboard in `frontend/`. Sections: Dashboard, Student records (search), Marks entry & correction, Blockchain transaction history,
Integrity verification (+ database-tampering demo), Experiment results (T1-T6 and the performance summary).

```bash
# terminal 1: backend (env: PG*, JWT_SECRET, ACCOUNTS_PASSWORD, PSEUDONYM_PEPPER; add DEMO_MODE=1 to enable the tamper demo)
cd backend && uvicorn app.main:app --port 8000
# terminal 2
cd frontend && npm install && npm run dev        # http://localhost:5173 (proxies /api and /auth to :8000; VITE_API overrides)
npm test                                         # render tests with a mocked API
```
Notes: the JWT is kept in memory only. Buttons are only a convenience; permissions are enforced by the backend and the smart contract.
The tamper demo (`POST /api/{a|b}/demo/tamper`) exists only for demonstration, is disabled unless `DEMO_MODE=1`, and requires EXAM_ADMIN.
Sign in with the seeded demo users (`python3 scripts/seed_users.py`), e.g. `fac01`, `moderator1`, `admin1`, `st0001`.
Tested here: production build succeeds and 2 render tests pass; it was not exercised in a real browser in the development sandbox.
