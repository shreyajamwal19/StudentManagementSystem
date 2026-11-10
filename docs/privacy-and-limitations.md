# Privacy, trust and limitations

**What goes on the blockchain:** only hashes and metadata: record key (SHA-256 of the record id), student pseudonym (HMAC-SHA256 of the student id with a secret pepper), course id, assessment id,
keyed marks hash, previous/current record hash, action, status, signer address, block timestamp. No marks, names or real student ids.
**Privacy limits (be explicit in the paper):**
- Course/assessment ids, actions, timing and signer addresses are visible to everyone with chain access and are linkable (e.g. "this pseudonym had a correction in CS101 at time T"). Pseudonyms are stable per student, so activity patterns can be linked.
- If the pepper leaks, pseudonyms and marks hashes can be brute-forced (small value spaces), so the pepper must be a managed secret (secret manager/HSM in the cloud deployment).
- Immutability conflicts with erasure requests (e.g. GDPR right to erasure): hashes cannot be deleted. Keep personal data off-chain (as here) and treat the hashes as non-reversible pseudonymous data.
- A private permissioned network limits who can read the chain, but members (validators, auditors) still see the metadata.

**Security limits:**
- The blockchain DETECTS tampering; it does not PREVENT database writes. Prevention comes from access control, in both systems.
- An attacker controlling an authorized signer key (or a majority of validators) can append fraudulent but validly signed events; mitigations: HSM/key custody, multi-party approval, external anchoring.
- System B refuses to build on a tampered record, but a restore from backup after tampering needs a documented reconciliation procedure (not implemented).
- The prototype uses one signer per faculty and one each for moderator/admin; real deployments need per-user keys.
- Anchoring is synchronous inside the DB transaction: a Besu outage blocks writes in System B (by design here; production needs queueing and reconciliation).
- Prototype scale only: 4 local validators, free gas, no node permissioning/allow-listing yet, no TLS on RPC.
