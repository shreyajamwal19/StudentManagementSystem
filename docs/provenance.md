# Auditability and marks provenance (Result 4)

Run: `python3 experiments/provenance/run_provenance.py` (Besu + PostgreSQL running). Outputs: `experiments/results/provenance.{json,csv}`, `experiments/figures/Fig_Provenance.png`.
It drives the real System B API through the full workflow on one EndTerm record and reads the history back from Besu:
imported 46.6, entered 42.0, submitted, moderated, approved, locked, correction requested, authorized, corrected to 46.0, moderated, approved, locked again (12 on-chain events).

For every version the output shows: marks (from the database; the chain holds only a keyed marks hash, which the script recomputes and matches), previous record hash, current record hash,
actor (role-specific Besu signer), block timestamp, Besu transaction id, and the approval history (moderate/approve/lock events). Checks enforced by the script: verification = MATCH,
each `prevHash` equals the previous version's hash of the same record, all 12 transaction ids are distinct.

Note: the spec's 72 -> 76 example exceeds the dataset's maximum marks (at most 50), so the same +4 correction is shown as 42.0 -> 46.0.
