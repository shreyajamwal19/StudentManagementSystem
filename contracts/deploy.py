#!/usr/bin/env python3
"""Deploy AcademicRecords to Besu with the admin1 keystore, grant roles, assign courses to faculty.
Env: ACCOUNTS_PASSWORD, PG* (reads courses table), optional BESU_RPC (default http://127.0.0.1:8545).
Writes besu-network/deployment.json (gitignored) and experiments/results/contract_deployment_verification.json."""
import json, os, pathlib, sys, datetime
import psycopg2
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
ROOT = pathlib.Path(__file__).resolve().parent.parent
pw = os.environ["ACCOUNTS_PASSWORD"]
w3 = Web3(Web3.HTTPProvider(os.environ.get("BESU_RPC", "http://127.0.0.1:8545"), request_kwargs={"timeout": 30}))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
CID = w3.eth.chain_id
art = json.loads((ROOT / "contracts/build/AcademicRecords.json").read_text())
addrs = json.loads((ROOT / "secrets/addresses.json").read_text())
admin = Account.from_key(Account.decrypt(json.loads((ROOT / "secrets/keystore/admin1.json").read_text()), pw))
assert admin.address.lower() == addrs["admin1"].lower()
b32 = lambda s: s.encode().ljust(32, b"\0")

def send(fn=None, deploy=None):
    tx_args = {"from": admin.address, "nonce": w3.eth.get_transaction_count(admin.address), "gas": 5_000_000, "gasPrice": 0, "chainId": CID}
    tx = (deploy.constructor() if deploy else fn).build_transaction(tx_args)
    r = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(admin.sign_transaction(tx).raw_transaction), timeout=60)
    assert r["status"] == 1, "transaction failed"
    return r

factory = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
r = send(deploy=factory)
c = w3.eth.contract(address=r["contractAddress"], abi=art["abi"])
for n, a in addrs.items():
    if n.startswith("moderator"): send(c.functions.setRole(a, 2))
    elif n.startswith("fac"): send(c.functions.setRole(a, 1))
cur = psycopg2.connect().cursor(); cur.execute("SELECT course_id, faculty_id FROM courses ORDER BY 1")
courses = cur.fetchall()
for course, fac in courses:
    send(c.functions.assignCourse(b32(course), addrs[fac.lower()]))

dep = {"address": c.address, "deploy_tx": r["transactionHash"].hex(), "block": r["blockNumber"], "chain_id": CID,
       "solc": art["solc"], "deployer": "admin1"}
(ROOT / "besu-network/deployment.json").write_text(json.dumps(dep, indent=2) + "\n")
ok_roles = all(c.functions.roles(a).call() == (2 if n.startswith("moderator") else 1 if n.startswith("fac") else 3) for n, a in addrs.items())
ok_courses = all(c.functions.courseFaculty(b32(co)).call() == addrs[f.lower()] for co, f in courses)
ver = {"verified_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "chain_id": CID,
       "deploy_tx": dep["deploy_tx"], "deploy_block": dep["block"], "runtime_bytecode_bytes": len(w3.eth.get_code(c.address)),
       "accounts_with_correct_role": ok_roles, "courses_assigned_correctly": ok_courses, "courses": len(courses), "solc": art["solc"]}
(ROOT / "experiments/results/contract_deployment_verification.json").write_text(json.dumps(ver, indent=2) + "\n")
print(json.dumps(ver, indent=2)); sys.exit(0 if ok_roles and ok_courses else 1)
