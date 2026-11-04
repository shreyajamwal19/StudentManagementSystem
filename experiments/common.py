"""Isolated, reproducible experiment environment (used by the security and benchmark runners).
Creates: a throw-away copy of the imported database (CREATE DATABASE .. TEMPLATE), fresh encrypted signer keystores,
a FRESH AcademicRecords contract on the real Besu network (roles + course assignments), anchors the requested records,
seeds demo users, and starts the API (uvicorn) pointing at all of it. Nothing here touches the main database or main contract.
Requirements: Besu running (besu-network/start.sh), imported dataset in $PGDATABASE, no other sessions on that database."""
import json, os, pathlib, secrets, subprocess, sys, tempfile, time
import bcrypt, httpx, psycopg2
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
PASSWORD = "ExperimentPass#2026"
KS_PASS = "ExperimentKeystore#2026"


class ExperimentEnv:
    def __init__(self, anchor_records=(), port=8010, exp_db="academic_records_exp"):
        self.anchor_records, self.port, self.exp_db = list(anchor_records), port, exp_db
        self.src_db = os.environ.get("PGDATABASE", "academic_records")
        self.base = f"http://127.0.0.1:{port}"
        self.proc = None

    # ---- setup -----------------------------------------------------------
    def __enter__(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="exp_"))
        self._make_db(); self._make_accounts_and_contract(); self._seed_users(); self._anchor(); self._start_server()
        return self

    def _make_db(self):
        adm = psycopg2.connect(dbname="postgres"); adm.autocommit = True
        c = adm.cursor()
        c.execute(f"DROP DATABASE IF EXISTS {self.exp_db}")
        c.execute(f"CREATE DATABASE {self.exp_db} TEMPLATE {self.src_db}")
        adm.close()
        self.db = psycopg2.connect(dbname=self.exp_db); self.db.autocommit = True

    def _make_accounts_and_contract(self):
        ks = self.tmp / "keystore"; ks.mkdir()
        self.accts = {n: Account.create() for n in ["admin1", "moderator1"] + [f"fac{i:02d}" for i in range(1, 11)]}
        for n, a in self.accts.items():
            (ks / f"{n}.json").write_text(json.dumps(Account.encrypt(a.key, KS_PASS, kdf="pbkdf2", iterations=1000)))
        self.w3 = Web3(Web3.HTTPProvider(os.environ.get("BESU_RPC", "http://127.0.0.1:8545"), request_kwargs={"timeout": 60}))
        self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        assert self.w3.is_connected(), "Besu is not running (besu-network/start.sh)"
        cid = self.w3.eth.chain_id
        art = json.loads((ROOT / "contracts/build/AcademicRecords.json").read_text())
        admin = self.accts["admin1"]
        def send(fn=None, ctor=None):
            src = ctor.constructor() if ctor else fn
            tx = src.build_transaction({"from": admin.address, "nonce": self.w3.eth.get_transaction_count(admin.address), "gas": 5_000_000, "gasPrice": 0, "chainId": cid})
            r = self.w3.eth.wait_for_transaction_receipt(self.w3.eth.send_raw_transaction(admin.sign_transaction(tx).raw_transaction), timeout=60)
            assert r["status"] == 1; return r
        r = send(ctor=self.w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]))
        self.contract = self.w3.eth.contract(address=r["contractAddress"], abi=art["abi"])
        for n, a in self.accts.items():
            if n == "moderator1": send(self.contract.functions.setRole(a.address, 2))
            elif n.startswith("fac"): send(self.contract.functions.setRole(a.address, 1))
        cur = self.db.cursor(); cur.execute("SELECT course_id, faculty_id FROM courses")
        for course, fac in cur.fetchall():
            send(self.contract.functions.assignCourse(course.encode().ljust(32, b"\0"), self.accts[fac.lower()].address))
        (self.tmp / "deployment.json").write_text(json.dumps({"address": self.contract.address, "chain_id": cid}))
        self.deploy_info = {"contract_address": self.contract.address, "chain_id": cid, "deploy_block": r["blockNumber"], "deploy_tx": Web3.to_hex(r["transactionHash"])}
        self.env = dict(os.environ, PGDATABASE=self.exp_db, KEYSTORE_DIR=str(ks), ACCOUNTS_PASSWORD=KS_PASS,
                        DEPLOYMENT_FILE=str(self.tmp / "deployment.json"), JWT_SECRET=secrets.token_hex(32),
                        PSEUDONYM_PEPPER=os.environ.get("PSEUDONYM_PEPPER") or secrets.token_hex(16))

    def _seed_users(self):
        h = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode()
        c = self.db.cursor(); c.execute("DELETE FROM users")
        c.execute("SELECT faculty_id FROM faculty ORDER BY 1")
        for (f,) in c.fetchall():
            self.db.cursor().execute("INSERT INTO users (username,password_hash,role,faculty_id) VALUES (%s,%s,'FACULTY',%s)", (f.lower(), h, f))
        for u, r in (("moderator1", "MODERATOR"), ("admin1", "EXAM_ADMIN")):
            self.db.cursor().execute("INSERT INTO users (username,password_hash,role) VALUES (%s,%s,%s)", (u, h, r))

    def _anchor(self):
        os.environ.update({k: self.env[k] for k in ("KEYSTORE_DIR", "ACCOUNTS_PASSWORD", "DEPLOYMENT_FILE", "PSEUDONYM_PEPPER")})
        from app.chain import Chain, STATUS_ID
        from app.hashing import b32_ascii, marks_hash, record_key
        self.chain = Chain()
        if not self.anchor_records:
            return
        items, cur = [], self.db.cursor()
        for i in range(0, len(self.anchor_records), 200):
            ids = self.anchor_records[i:i + 200]
            cur.execute("SELECT m.record_id, s.pseudonym, m.course_id, m.assessment_id, m.marks_obtained, m.status, v.record_hash FROM marks_b m "
                        "JOIN students s USING(student_id) JOIN record_versions_b v ON v.record_id=m.record_id AND v.version_no=1 "
                        "WHERE m.record_id = ANY(%s) AND m.version_no=1", (ids,))
            items = [(record_key(r[0]), bytes.fromhex(r[1]), b32_ascii(r[2]), b32_ascii(r[3]),
                      bytes.fromhex(marks_hash(self.env["PSEUDONYM_PEPPER"], r[0], r[4])), bytes.fromhex(r[6]), STATUS_ID[r[5]]) for r in cur.fetchall()]
            self.chain.import_batch(items)
        self.anchored = len(self.anchor_records)

    def _start_server(self):
        self.log = open(self.tmp / "server.log", "w")
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(ROOT / "backend"), "--port", str(self.port),
                                      "--log-level", "warning"], env=self.env, stdout=self.log, stderr=subprocess.STDOUT)
        for _ in range(60):
            try:
                if httpx.get(self.base + "/openapi.json", timeout=2).status_code == 200: return
            except Exception: time.sleep(0.5)
        raise RuntimeError("API did not start; see " + str(self.tmp / "server.log"))

    # ---- helpers ---------------------------------------------------------
    def token(self, username):
        r = httpx.post(self.base + "/auth/login", json={"username": username, "password": PASSWORD}, timeout=30); r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["access_token"]}

    def pick(self, status, faculty, n=1, offset=0, same=True):
        op = "=" if same else "<>"
        c = self.db.cursor()
        c.execute(f"SELECT m.record_id FROM marks_a m JOIN courses c USING(course_id) WHERE m.status=%s AND c.faculty_id {op} %s ORDER BY m.record_id OFFSET %s LIMIT %s",
                  (status, faculty, offset, n))
        return [r[0] for r in c.fetchall()]

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try: self.proc.wait(10)
            except Exception: self.proc.kill()
        try: self.db.close()
        except Exception: pass
        adm = psycopg2.connect(dbname="postgres"); adm.autocommit = True
        adm.cursor().execute(f"DROP DATABASE IF EXISTS {self.exp_db} WITH (FORCE)"); adm.close()
