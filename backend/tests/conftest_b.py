"""Fixtures for System B tests: a FRESH contract deployment on the real Besu network + temp encrypted keystores."""
import json, os, pathlib, tempfile
import psycopg2, pytest
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

KS_PASS = "TestKeystorePass#1"

@pytest.fixture(scope="session")
def b_env(_db):
    tmp = pathlib.Path(tempfile.mkdtemp())
    ks = tmp / "keystore"; ks.mkdir()
    names = ["admin1", "moderator1"] + [f"fac{i:02d}" for i in range(1, 11)]
    accts = {n: Account.create() for n in names}
    for n, a in accts.items():
        (ks / f"{n}.json").write_text(json.dumps(Account.encrypt(a.key, KS_PASS, kdf="pbkdf2", iterations=1000)))
    os.environ.update(KEYSTORE_DIR=str(ks), ACCOUNTS_PASSWORD=KS_PASS, DEPLOYMENT_FILE=str(tmp / "deployment.json"),
                      PSEUDONYM_PEPPER="test-pepper-test-pepper-test-pepper")
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 60}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    assert w3.is_connected(), "Besu is not running (besu-network/start.sh)"
    cid = w3.eth.chain_id
    art = json.loads((pathlib.Path(__file__).resolve().parents[2] / "contracts/build/AcademicRecords.json").read_text())
    admin = accts["admin1"]

    def send(fn=None, ctor=None):
        src = ctor.constructor() if ctor else fn
        tx = src.build_transaction({"from": admin.address, "nonce": w3.eth.get_transaction_count(admin.address), "gas": 5_000_000, "gasPrice": 0, "chainId": cid})
        r = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(admin.sign_transaction(tx).raw_transaction), timeout=60)
        assert r["status"] == 1
        return r
    r = send(ctor=w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]))
    c = w3.eth.contract(address=r["contractAddress"], abi=art["abi"])
    for n, a in accts.items():
        if n == "moderator1": send(c.functions.setRole(a.address, 2))
        elif n.startswith("fac"): send(c.functions.setRole(a.address, 1))
    db = psycopg2.connect(dbname=os.environ["PGDATABASE"]); db.autocommit = True
    cur = db.cursor(); cur.execute("SELECT course_id, faculty_id FROM courses")
    for course, fac in cur.fetchall():
        send(c.functions.assignCourse(course.encode().ljust(32, b"\0"), accts[fac.lower()].address))
    (tmp / "deployment.json").write_text(json.dumps({"address": c.address, "chain_id": cid}))

    # anchor a controlled subset of System B records (batch import, as in the real initial anchoring)
    from app.chain import Chain, STATUS_ID
    from app.hashing import marks_hash, record_key, b32_ascii
    chain = Chain()
    picks, plan = {}, [("Entered", 8, "=", "FAC01"), ("Submitted", 3, "=", "FAC01"), ("Moderated", 3, "=", "FAC01"),
                       ("Approved", 3, "=", "FAC01"), ("Locked", 5, "=", "FAC01"), ("Entered", 3, "<>", "FAC01")]
    items = []
    for status, n, op, fac in plan:
        cur.execute(f"SELECT m.record_id, m.student_id, m.course_id, m.assessment_id, m.marks_obtained, s.pseudonym, v.record_hash "
                    f"FROM marks_b m JOIN courses c USING(course_id) JOIN students s USING(student_id) "
                    f"JOIN record_versions_b v ON v.record_id=m.record_id AND v.version_no=1 "
                    f"WHERE m.status=%s AND c.faculty_id {op} %s ORDER BY m.record_id LIMIT %s", (status, fac, n))
        rows = cur.fetchall()
        picks[(status, op)] = [r[0] for r in rows]
        for rid, st, co, asx, mk, ps, rh in rows:
            items.append((record_key(rid), bytes.fromhex(ps), b32_ascii(co), b32_ascii(asx),
                          bytes.fromhex(marks_hash(os.environ["PSEUDONYM_PEPPER"], rid, mk)), bytes.fromhex(rh), STATUS_ID[status]))
    chain.import_batch(items)
    return type("BEnv", (), dict(picks=picks, db=db, chain=chain, accts=accts, contract=c))
