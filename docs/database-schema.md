# Database schema (V1__schema.sql)

Reference tables: `faculty` <- `courses` (course -> assigned faculty), `assessments` (max_marks), `students` (pseudonym = HMAC-SHA256(pepper, student_id)).
`users` links a login to a role, plus `faculty_id` (FACULTY) or `student_id` (STUDENT).

| System A | System B |
|---|---|
| `marks_a` current state of each record | `marks_b` same structure and constraints |
| `record_versions_a` per-record history (hash columns NULL) | `record_versions_b` per-record history; `record_hash` = SHA-256 of canonical record, `prev_hash` = hash of version_no-1 of the SAME record (zeros for v1) |

Shared: `audit_log` (ordinary app audit, column `system` A/B), `chain_anchor` (mirror of Besu receipts: tx hash, block, submit/confirm ms; Besu stays the source of truth).

Constraints (identical in A and B): unique (student, course, assessment); FKs; marks >= 0; trigger rejects marks > max_marks; status check.
Import: CSV (checksum-verified, unchanged) -> one transaction fills marks_a and marks_b from the same parsed rows.
Note: the DB trigger also limits tampering to valid ranges, so tamper experiments use in-range values (e.g. 15.0 -> 19.5), not 75 -> 95.

Canonical hash: `v1|record_id|pseudonym|course|assessment|max|marks(1dp)|status|version_no`; test vectors in `canonical_hash_vectors.json`.

Rerun: `python3 scripts/import_dataset.py` then `python3 scripts/verify_import.py` (env: PG*, PSEUDONYM_PEPPER).
