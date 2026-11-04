# Security and integrity experiments (T1-T6)

Run: `python3 experiments/security/run_security_experiments.py` (needs Besu running, imported dataset, no other sessions on the source DB).
Each run builds an isolated copy of the database, a fresh contract on Besu with fresh signer keys, anchors only the records it needs,
starts the API, runs all tests through HTTP against System A and System B with the SAME record ids, then removes the copy.
Results: `experiments/results/security_results.{csv,json,md}` (includes the evidence for every outcome).

| Test | System A | System B |
|---|---|---|
| T1 unauthorized marks modification | Prevented | Prevented (no chain transaction created) |
| T2 modification after locking (incl. correction bypass) | Prevented | Prevented |
| T3 manual database alteration | Not Detected | Detected (hash mismatch) |
| T4 historical version row alteration | Not Detected | Detected |
| T5 wrong-role transaction | Prevented | Prevented (also reverted by the contract when called directly) |
| T6 valid authorized correction | Allowed | Allowed (12 on-chain events, verify = MATCH) |

How to read this honestly:
- T1, T2, T5 are prevented by the application's access control in BOTH systems; the blockchain adds a second, independent check (contract), not the first.
- T3 and T4: the database write itself succeeds in both systems (the blockchain does not prevent it). System A has ordinary application audit logging, but a direct SQL edit
  bypasses the application and leaves no audit row, and A has no integrity check, so "Not Detected" is a statement about A's design, not a failure of its access control.
  System B detects the change by recomputing hashes and comparing them with Besu. B also refuses to build on a tampered record (follow-up actions return HTTP 409).
- Limitation: an attacker who controls an authorized signer key can append a validly signed fraudulent version; that is not covered here.
- Notes: the trigger-based marks <= max check means in-range tampering values are used (e.g. 14.7 -> 13.7), not 75 -> 95.

## Initial batch anchoring (`scripts/anchor_initial.py`, `scripts/summarize_anchoring.py`)
Resumable and crash-safe (reconciles a batch that reached the chain but was not recorded in the DB). In the 4 GB / 1 CPU development sandbox only
part of the dataset was anchored (see `experiments/results/initial_anchoring.json`, field `anchoring_complete`); run the script on your machine to anchor all 50,000 records
and re-run the summarizer. Sandbox timings are not benchmark numbers.
