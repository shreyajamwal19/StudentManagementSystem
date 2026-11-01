# Architecture and Business Rules

> **Implementation note:** the backend is Python (FastAPI) instead of the originally planned Java/Spring Boot, because Maven Central
> was unreachable in the development sandbox. Blockchain integration will use web3.py instead of Web3j. This deviates from the
> original stack; confirm with the supervisor and state it in the paper.

## Two systems, one core
Both systems call the same `marks-core` service (same JPA entities, validators, state machine, RBAC checks).
- **System A (conventional):** PostgreSQL + JWT/RBAC + ordinary application audit log (`audit_log`).
- **System B (proposed):** identical core, plus SHA-256 record hashing and a Hyperledger Besu transaction per event.

Fairness rules:
1. **Identical starting data.** The CSV is imported once into a staging table, then copied to `marks_a` and `marks_b`
   in a single DB transaction. A script compares row counts and a table-content checksum of both before any experiment.
2. **Equivalent business rules.** Same state machine, same course-specific authorization, same validation (marks within 0..Max_Marks).
3. **Equivalent application security.** Both have authentication, RBAC and audit logging. System A is not made insecure.
4. Same hardware, same workload generator, same DB engine and configuration.

## Per-record version history (provenance)
Each academic record has an append-only `record_versions` table (one row per event):
`record_id, version_no, action, marks, status, actor_user_id, record_hash, prev_hash, created_at`.
- `prev_hash` is the `record_hash` of the **previous version of the same record** (`version_no - 1`); version 1 uses a zero hash.
- The contract stores the same chain per `recordKey` (hash of record id). It rejects any event whose `prevHash`
  differs from the latest `currHash` for that record, so a link to another record's hash is impossible.
- Hash input (canonical, UTF-8): `v1|record_id|student_pseudonym|course|assessment|max|marks(1 dp)|status|version_no`.

## Workflow state machine
`ENTERED -> SUBMITTED -> MODERATED -> APPROVED -> LOCKED`

| Transition | Who | Rule |
|---|---|---|
| create / update marks (ENTERED) | Faculty | only for an **assigned course**; before submission |
| ENTERED -> SUBMITTED | Faculty | assigned course |
| SUBMITTED -> MODERATED | Moderator | reviews marks |
| MODERATED -> APPROVED, or back to ENTERED (reject) | Moderator | |
| APPROVED -> LOCKED | Exam Admin | finalizes |
| LOCKED -> CORRECTION_REQUESTED | Faculty | assigned course, reason required |
| CORRECTION_REQUESTED -> CORRECTION_AUTHORIZED | Exam Admin | |
| CORRECTION_AUTHORIZED -> SUBMITTED (new marks) | Faculty | assigned course; then MODERATED, APPROVED, LOCKED again |

Any other transition is rejected. There is no path that changes marks of a LOCKED record without passing
moderation, approval and locking again. Students may only read their own LOCKED records.
*Design decision:* the corrected marks re-enter at SUBMITTED so the 72 -> 76 provenance example passes through
Moderated, Approved, Locked. Tell me if your supervisor expects a different flow.

## Course-specific faculty authorization
`courses.faculty_id` (from the dataset: one faculty per course) is the assignment. `users.faculty_id` links a login to a faculty.
- **Backend:** every faculty action checks `record.course.faculty_id == current_user.faculty_id`; identity comes from the JWT, never from the request body.
- **Contract (System B):** admin maps `courseKey -> faculty address`; faculty functions revert unless `msg.sender` is the assigned address, and role functions check the signer's role.
Both layers are enforced; the frontend is not trusted.

## Initial import vs experiments
- **Initial 50,000 records:** anchored in batches (about 100 records per transaction) as version-1 genesis events.
- **Benchmarks:** each workload transaction is an **individual** Besu transaction. Submission time and confirmation time are measured separately from DB time and end-to-end time.
- Receipts are stored in `chain_anchor`, but verification always re-reads the transaction receipt and contract state from Besu; the DB copy is never the source of truth.

## What blockchain does and does not do here
It **detects** alteration (hash mismatch) and gives an append-only, verifiable history; it does not **prevent** a DBA from
editing the database. Limitation: if the attacker also controls an authorized signer key, they can append a fraudulent but
validly-signed event; key management and multi-party approval are needed on top.
