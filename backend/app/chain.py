"""Besu / Web3 integration for System B.
- Signer is chosen by the BACKEND from the verified JWT role (never from client input).
- Signer keys come from encrypted keystores (KEYSTORE_DIR, ACCOUNTS_PASSWORD); nothing is hard-coded.
- Nonces are allocated locally per signer so many transactions can be pipelined into the same block."""
import json, os, pathlib, threading, time
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
from .security import User

ROOT = pathlib.Path(__file__).resolve().parents[2]
FN = {"update_marks": "updateMarks", "submit": "submit", "moderate": "moderate", "approve": "approve", "reject": "reject",
      "lock": "lock", "request_correction": "requestCorrection", "authorize_correction": "authorizeCorrection",
      "apply_correction": "applyCorrection"}
STATUS_ID = {"Entered": 1, "Submitted": 2, "Moderated": 3, "Approved": 4, "Locked": 5, "CorrectionRequested": 6, "CorrectionAuthorized": 7}


class ChainError(Exception):
    pass


class Chain:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(os.environ.get("BESU_RPC", "http://127.0.0.1:8545"), request_kwargs={"timeout": 60}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        dep = pathlib.Path(os.environ.get("DEPLOYMENT_FILE", ROOT / "besu-network/deployment.json"))
        art = pathlib.Path(os.environ.get("CONTRACT_ARTIFACT", ROOT / "contracts/build/AcademicRecords.json"))
        d = json.loads(dep.read_text())
        self.chain_id = d["chain_id"]
        self.c = self.w3.eth.contract(address=d["address"], abi=json.loads(art.read_text())["abi"])
        self.keystore_dir = pathlib.Path(os.environ.get("KEYSTORE_DIR", ROOT / "secrets/keystore"))
        self._accounts, self._nonce, self._lock = {}, {}, threading.Lock()

    # ---- signers -------------------------------------------------------
    @staticmethod
    def signer_name(u: User) -> str:
        if u.role == "FACULTY":
            return u.faculty_id.lower()          # FAC01 -> fac01 (course-specific signer)
        return {"MODERATOR": "moderator1", "EXAM_ADMIN": "admin1"}[u.role]

    def _account(self, name: str):
        with self._lock:
            if name not in self._accounts:
                pw = os.environ.get("ACCOUNTS_PASSWORD")
                if not pw:
                    raise ChainError("ACCOUNTS_PASSWORD is not set")
                ks = json.loads((self.keystore_dir / f"{name}.json").read_text())
                self._accounts[name] = Account.from_key(Account.decrypt(ks, pw))
            return self._accounts[name]

    def _next_nonce(self, acct) -> int:
        with self._lock:
            if acct.address not in self._nonce:
                self._nonce[acct.address] = self.w3.eth.get_transaction_count(acct.address, "pending")
            n = self._nonce[acct.address]
            self._nonce[acct.address] = n + 1
            return n

    def _resync(self, acct):
        with self._lock:
            self._nonce.pop(acct.address, None)

    # ---- writes --------------------------------------------------------
    def _send(self, acct, fn, gas: int):
        tx = fn.build_transaction({"from": acct.address, "nonce": self._next_nonce(acct), "gas": gas, "gasPrice": 0, "chainId": self.chain_id})
        raw = acct.sign_transaction(tx).raw_transaction
        t0 = time.perf_counter()
        try:
            txh = self.w3.eth.send_raw_transaction(raw)
        except Exception as e:
            self._resync(acct)
            raise ChainError(f"submit failed: {e}")
        submit_ms = (time.perf_counter() - t0) * 1000
        r = self.w3.eth.wait_for_transaction_receipt(txh, timeout=120, poll_latency=0.1)
        confirm_ms = (time.perf_counter() - t0) * 1000
        if r["status"] != 1:
            raise ChainError("transaction reverted on Besu (contract rule rejected it)")
        return {"tx_hash": Web3.to_hex(txh), "block_number": r["blockNumber"], "submit_ms": submit_ms, "confirm_ms": confirm_ms, "receipt": r}

    def send_action(self, u: User, action: str, key: bytes, prev: bytes, marks: bytes, curr: bytes):
        acct = self._account(self.signer_name(u))
        fn = getattr(self.c.functions, FN[action])(key, prev, marks, curr)
        out = self._send(acct, fn, 1_000_000)
        out["actor_address"] = acct.address
        return out

    def import_batch(self, items):
        """items: tuples (key, studentHash, courseId, assessmentId, marksHash, currHash, statusId); signed by admin1."""
        acct = self._account("admin1")
        out = self._send(acct, self.c.functions.importRecords(items), 60_000_000)
        out["actor_address"] = acct.address
        return out

    # ---- reads ---------------------------------------------------------
    def latest_hash(self, key: bytes) -> bytes:
        return self.c.functions.latestHash(key).call()

    def history_length(self, key: bytes) -> int:
        return self.c.functions.historyLength(key).call()

    def entry(self, key: bytes, i: int) -> dict:
        marks, prev, curr, action, status, actor, ts = self.c.functions.getEntry(key, i).call()
        return {"marks_hash": marks.hex(), "prev_hash": prev.hex(), "curr_hash": curr.hex(), "action": int(action),
                "status": int(status), "actor": actor, "timestamp": int(ts)}


_chain = None
_chain_lock = threading.Lock()

def get_chain() -> Chain:
    global _chain
    with _chain_lock:
        if _chain is None:
            _chain = Chain()
        return _chain
