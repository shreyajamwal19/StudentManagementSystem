#!/usr/bin/env python3
"""Create encrypted Besu signer keystores: admin1 (contract owner/EXAM_ADMIN), moderator1, fac01..fac10.
Output: secrets/keystore/<name>.json (encrypted) + secrets/addresses.json (public addresses). Both are gitignored.
Env: ACCOUNTS_PASSWORD (min 12 chars). Refuses to overwrite existing keystores."""
import json, os, pathlib, sys
from eth_account import Account
ROOT = pathlib.Path(__file__).resolve().parent.parent
pw = os.environ.get("ACCOUNTS_PASSWORD", "")
if len(pw) < 12: sys.exit("Set ACCOUNTS_PASSWORD (min 12 chars).")
ks = ROOT / "secrets/keystore"; ks.mkdir(parents=True, exist_ok=True)
os.chmod(ROOT / "secrets", 0o700)
names = ["admin1", "moderator1"] + [f"fac{i:02d}" for i in range(1, 11)]
addrs = {}
for n in names:
    p = ks / f"{n}.json"
    if p.exists():
        addrs[n] = "0x" + json.loads(p.read_text())["address"]; continue
    a = Account.create()
    p.write_text(json.dumps(Account.encrypt(a.key, pw))); os.chmod(p, 0o600)
    addrs[n] = a.address
(ROOT / "secrets/addresses.json").write_text(json.dumps(addrs, indent=2) + "\n")
print("Accounts ready:", len(addrs))
