#!/usr/bin/env python3
"""Verify the local Besu QBFT network with real chain data and a real signed transaction.
Usage: verify_network.py [--fault-test]   (fault test stops/starts validators using ./stop-node.sh style pid files)
Writes experiments/results/besu_network_verification.json (no keys, no secrets)."""
import json, os, pathlib, subprocess, sys, time, datetime
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware  # QBFT extraData is longer than 32 bytes
from eth_account import Account

HERE = pathlib.Path(__file__).resolve().parent
RPC = [f"http://127.0.0.1:{8545+i}" for i in range(4)]
w3s = [Web3(Web3.HTTPProvider(u, request_kwargs={"timeout": 10})) for u in RPC]
for _w in w3s: _w.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
w3 = w3s[0]
res = {"checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}

def wait_blocks(n, timeout=60, node=None):
    node = node or w3
    start = node.eth.block_number; t0 = time.time()
    while node.eth.block_number < start + n:
        if time.time() - t0 > timeout: return False
        time.sleep(0.5)
    return True

def validators():
    return w3.provider.make_request("qbft_getValidatorsByBlockNumber", ["latest"])["result"]

res["chain_id"] = w3.eth.chain_id
res["client_version"] = w3.client_version
res["validators"] = len(validators())
res["peer_counts"] = [x.net.peer_count for x in w3s]
assert res["chain_id"] == 20260 and res["validators"] == 4

assert wait_blocks(8), "chain is not producing blocks"
head = w3.eth.block_number
blocks = [w3.eth.get_block(n) for n in range(max(1, head - 11), head + 1)]
res["recent_block_proposers"] = sorted({b["miner"].lower() for b in blocks})
deltas = [blocks[i + 1]["timestamp"] - blocks[i]["timestamp"] for i in range(len(blocks) - 1)]
res["block_time_seconds"] = {"min": min(deltas), "max": max(deltas), "mean": round(sum(deltas) / len(deltas), 2)}
res["distinct_proposers_in_last_12_blocks"] = len(res["recent_block_proposers"])
assert set(res["recent_block_proposers"]) <= set(v.lower() for v in validators())

# real signed transaction from an ephemeral throw-away account (key never stored)
acct = Account.create()
tx = {"to": acct.address, "value": 0, "data": b"qbft-verification", "gas": 60000, "gasPrice": 0,
      "nonce": 0, "chainId": res["chain_id"]}
signed = acct.sign_transaction(tx)
t0 = time.time(); txh = w3.eth.send_raw_transaction(signed.raw_transaction); t_submit = time.time() - t0
rcpt = w3.eth.wait_for_transaction_receipt(txh, timeout=60); t_confirm = time.time() - t0
res["tx"] = {"hash": txh.hex(), "status": rcpt["status"], "block_number": rcpt["blockNumber"], "gas_used": rcpt["gasUsed"],
             "submit_seconds": round(t_submit, 3), "confirm_seconds": round(t_confirm, 3)}
assert rcpt["status"] == 1
blk = w3.eth.get_block(rcpt["blockNumber"])
res["tx"]["included_in_block_hash"] = blk["hash"].hex()
res["tx"]["tx_listed_in_block"] = txh in [t for t in blk["transactions"]]
# same transaction visible on another validator (replication)
time.sleep(3)
other = w3s[3].eth.get_transaction_receipt(txh)
res["tx"]["receipt_matches_on_node4"] = other["blockHash"] == rcpt["blockHash"] and other["status"] == 1
assert res["tx"]["tx_listed_in_block"] and res["tx"]["receipt_matches_on_node4"]

if "--fault-test" in sys.argv:
    def pid(i): return int((HERE / f"pids/node{i}.pid").read_text())
    def kill(i): os.kill(pid(i), 15); (HERE / f"pids/node{i}.pid").unlink()
    ft = {}
    kill(4); time.sleep(3)
    ft["one_validator_down_blocks_continue"] = wait_blocks(3, 40)       # f = 1 tolerated
    kill(3); time.sleep(3)
    h = w3.eth.block_number; time.sleep(20)
    ft["two_validators_down_chain_halts"] = (w3.eth.block_number - h) <= 1  # < 2f+1 validators: no finality
    subprocess.run([str(HERE / "start.sh")], check=True, capture_output=True)
    ft["resumes_after_restart"] = wait_blocks(3, 120)
    res["fault_tolerance"] = ft
    print(json.dumps(ft, indent=2))

out = HERE.parent / "experiments/results/besu_network_verification.json"
out.write_text(json.dumps(res, indent=2) + "\n")
print(json.dumps(res, indent=2))
