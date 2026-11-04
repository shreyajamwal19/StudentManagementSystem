| Test | Description | System A | System B |
|---|---|---|---|
| T1 | Faculty not assigned to the course tries to change marks | Prevented | Prevented |
| T2 | Assigned faculty edits marks of a LOCKED record (direct edit and correction bypass) | Prevented | Prevented |
| T3 | Manual SQL alteration of marks of a locked record | Not Detected | Detected |
| T4 | Manual SQL alteration of a historical version row | Not Detected | Detected |
| T5 | Wrong-role users attempt faculty actions (and, for B, call the contract directly) | Prevented | Prevented |
| T6 | Authorized correction passes moderation, approval and locking again | Allowed | Allowed |
