# Smart contract: `contracts/AcademicRecords.sol`

Stores **only hashes** and metadata; marks never go on-chain. Every version of a record is an append-only `Entry`
(marksHash, prevHash, currHash, action, status, actor address, block timestamp). `prevHash` must equal the latest
`currHash` of the SAME record, so history cannot be re-linked to another record. No function edits or deletes an entry.

| Function | Who | Purpose |
|---|---|---|
| `setRole(account, role)` | owner | grant FACULTY / MODERATOR / EXAM_ADMIN (or NONE to revoke) |
| `assignCourse(courseId, faculty)` | EXAM_ADMIN | course-specific faculty assignment |
| `importRecords(items[])` | EXAM_ADMIN | batch-anchor the initial dataset (version 1 per record) |
| `createRecord(...)` | assigned FACULTY | new record in status Entered |
| `updateMarks` | assigned FACULTY | Entered -> Entered with new marksHash |
| `submit` | assigned FACULTY | Entered -> Submitted |
| `moderate` / `approve` / `reject` | MODERATOR | Submitted -> Moderated -> Approved; reject: Moderated -> Entered |
| `lock` | EXAM_ADMIN | Approved -> Locked |
| `requestCorrection` | assigned FACULTY | Locked -> CorrectionRequested |
| `authorizeCorrection` | EXAM_ADMIN | CorrectionRequested -> CorrectionAuthorized |
| `applyCorrection` | assigned FACULTY | CorrectionAuthorized -> Submitted with new marksHash (then moderate, approve, lock again) |
| `getRecord`, `historyLength`, `getEntry`, `latestHash`, `verify(key, hash)` | anyone (views) | read history and compare hashes |

Rules enforced on-chain: caller role, course assignment, legal state transition, `prevHash` linkage, and marksHash may only change in
`updateMarks` / `applyCorrection`. Event `RecordEvent` logs key, action, actor, version, studentHash, courseId, assessmentId, marksHash,
prevHash, currHash, timestamp. The blockchain transaction ID is the Besu transaction hash (stored in `chain_anchor`).
Course and assessment IDs are stored as `bytes32` (ASCII padded).

## Build, test, deploy
```bash
cd contracts && npm install && node compile.js            # solc 0.8.38 (solc-js), EVM shanghai, optimizer on
python3 -m pytest -q tests                                # 12 tests on the REAL Besu network (start it first)
export ACCOUNTS_PASSWORD=... && python3 scripts/make_accounts.py   # encrypted keystores in secrets/ (gitignored)
python3 contracts/deploy.py                               # deploys, sets roles, assigns the 10 courses
```
Tested: 12/12 contract tests pass on Besu; deployment verified (`experiments/results/contract_deployment_verification.json`).

## Limits
Signer keys live in encrypted local keystores for this prototype; production needs a secret manager/HSM. A compromised authorized signer
can still append a validly-signed fraudulent version; the contract detects history tampering, it does not stop a legitimate key from acting.
