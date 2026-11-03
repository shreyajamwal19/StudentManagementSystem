"""Contract tests run against the REAL local Besu QBFT network (no simulator). Start it first: besu-network/start.sh.
Test accounts are ephemeral (created per run, never stored); gas is free on this private network."""
import hashlib, json, pathlib, time
import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.middleware import ExtraDataToPOAMiddleware

BUILD = pathlib.Path(__file__).resolve().parent.parent / "build/AcademicRecords.json"
ROLE = {"NONE": 0, "FACULTY": 1, "MODERATOR": 2, "EXAM_ADMIN": 3}
STATUS = {"NONE": 0, "ENTERED": 1, "SUBMITTED": 2, "MODERATED": 3, "APPROVED": 4, "LOCKED": 5, "CORR_REQ": 6, "CORR_AUTH": 7}

def b32(s: str) -> bytes:
    return s.encode().ljust(32, b"\0")

def h(s: str) -> bytes:
    return hashlib.sha256(s.encode()).digest()

class Chain:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 30}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        assert self.w3.is_connected(), "Besu is not running (besu-network/start.sh)"
        self.chain_id = self.w3.eth.chain_id
        art = json.loads(BUILD.read_text())
        self.abi, self.bytecode = art["abi"], art["bytecode"]

    def send(self, acct, fn, expect_ok=True):
        tx = fn.build_transaction({"from": acct.address, "nonce": self.w3.eth.get_transaction_count(acct.address),
                                   "gas": 5_000_000, "gasPrice": 0, "chainId": self.chain_id})
        txh = self.w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
        r = self.w3.eth.wait_for_transaction_receipt(txh, timeout=60)
        if expect_ok: assert r["status"] == 1, "transaction reverted"
        return r

    def deploy(self, owner):
        c = self.w3.eth.contract(abi=self.abi, bytecode=self.bytecode)
        tx = c.constructor().build_transaction({"from": owner.address, "nonce": 0, "gas": 5_000_000, "gasPrice": 0, "chainId": self.chain_id})
        r = self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_raw_transaction(owner.sign_transaction(tx).raw_transaction), timeout=60)
        assert r["status"] == 1
        return self.w3.eth.contract(address=r["contractAddress"], abi=self.abi)

def reverts(fn, sender, reason):
    """eth_call must revert with the given reason string."""
    with pytest.raises(ContractLogicError) as e:
        fn.call({"from": sender.address})
    assert reason in str(e.value), str(e.value)

@pytest.fixture(scope="session")
def chain():
    return Chain()

@pytest.fixture(scope="session")
def env(chain):
    owner, fac1, fac2, mod, stranger = (Account.create() for _ in range(5))
    c = chain.deploy(owner)
    for a, role in ((fac1, "FACULTY"), (fac2, "FACULTY"), (mod, "MODERATOR")):
        chain.send(owner, c.functions.setRole(a.address, ROLE[role]))
    chain.send(owner, c.functions.assignCourse(b32("CS101"), fac1.address))
    chain.send(owner, c.functions.assignCourse(b32("CS102"), fac2.address))
    return type("Env", (), dict(c=c, owner=owner, fac1=fac1, fac2=fac2, mod=mod, stranger=stranger, chain=chain))
