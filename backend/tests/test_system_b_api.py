"""System B tests on the REAL Besu network: anchoring, provenance, tamper detection, on-chain enforcement."""
import pytest
from conftest import row
from app.chain import ChainError
from app.hashing import b32_ascii, marks_hash, record_key
from app.security import User

H0 = "0" * 64

def act(client, h, rid, action, **body):
    return client.post(f"/api/b/records/{rid}/actions/{action}", json=body, headers=h)

def verify(client, tok, rid, who="mod1"):
    r = client.get(f"/api/b/records/{rid}/verify", headers=tok[who]); assert r.status_code == 200, r.text
    return r.json()

def hist_len(b_env, rid):
    return b_env.chain.history_length(record_key(rid))

def sql(b_env, q, *a):
    c = b_env.db.cursor(); c.execute(q, a); return c

def rid_of(b_env, status, op="=", i=0):
    return b_env.picks[(status, op)][i]

# ---------- anchoring and verification ----------
def test_initial_records_verify_match(client, tok, b_env):
    for st in ("Entered", "Locked"):
        v = verify(client, tok, rid_of(b_env, st))
        assert v["result"] == "MATCH" and v["history_consistent"] and v["chain_versions"] == 1

def test_update_is_anchored_with_prev_hash_link_and_timings(client, tok, b_env):
    rid = rid_of(b_env, "Entered", i=0)
    before = b_env.chain.latest_hash(record_key(rid)).hex()
    r = act(client, tok["fac01"], rid, "update_marks", marks="11.0")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tx_hash"].startswith("0x") and len(j["tx_hash"]) == 66
    assert j["prev_hash"] == before and j["record_hash"] != before
    assert b_env.chain.latest_hash(record_key(rid)).hex() == j["record_hash"]
    t = j["timings_ms"]; assert t["confirm_ms"] > 0 and t["submit_ms"] > 0 and t["total_ms"] >= t["confirm_ms"]
    assert hist_len(b_env, rid) == 2
    h = client.get(f"/api/b/records/{rid}/chain-history", headers=tok["fac01"]).json()
    assert h[1]["prev_hash"] == h[0]["curr_hash"] and h[1]["tx_hash"] == j["tx_hash"]
    assert verify(client, tok, rid)["result"] == "MATCH"

# ---------- T6 + provenance: authorized correction, every step on-chain ----------
def test_T6_full_workflow_correction_provenance(client, tok, b_env):
    rid = rid_of(b_env, "Entered", i=1)
    f, m, a = tok["fac01"], tok["mod1"], tok["admin1"]
    steps = [(f, "update_marks", {"marks": "10.0"}), (f, "submit", {}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {}),
             (f, "request_correction", {"reason": "re-evaluation"}), (a, "authorize_correction", {}),
             (f, "apply_correction", {"marks": "12.0"}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {})]
    txs = []
    for h, action, body in steps:
        r = act(client, h, rid, action, **body); assert r.status_code == 200, (action, r.text)
        txs.append(r.json()["tx_hash"])
    assert len(set(txs)) == len(txs)
    assert hist_len(b_env, rid) == 1 + len(steps)
    hist = client.get(f"/api/b/records/{rid}/chain-history", headers=m).json()
    for i in range(1, len(hist)):
        assert hist[i]["prev_hash"] == hist[i - 1]["curr_hash"]        # links to previous version of the SAME record
    assert hist[0]["marks_hash"] != hist[-1]["marks_hash"] and hist[2]["marks_hash"] == hist[1]["marks_hash"]
    # actors on-chain are the role-specific signers chosen by the backend
    exp = {"update_marks": "fac01", "submit": "fac01", "moderate": "moderator1", "approve": "moderator1", "lock": "admin1",
           "request_correction": "fac01", "authorize_correction": "admin1", "apply_correction": "fac01"}
    for (h_, action, _), e in zip(steps, hist[1:]):
        assert e["actor"] == b_env.accts[exp[action]].address, action
    assert verify(client, tok, rid)["result"] == "MATCH"

# ---------- T1 / T2 / T5 ----------
def test_unauthorized_actions_create_no_chain_transaction(client, tok, b_env):
    other = rid_of(b_env, "Entered", "<>")
    n = hist_len(b_env, other)
    assert act(client, tok["fac01"], other, "update_marks", marks="1.0").status_code == 403           # T1 other course
    locked = rid_of(b_env, "Locked", i=0); nl = hist_len(b_env, locked)
    assert act(client, tok["fac01"], locked, "update_marks", marks="1.0").status_code == 409          # T2 locked
    assert act(client, tok["fac01"], locked, "apply_correction", marks="1.0").status_code == 409
    ent = rid_of(b_env, "Entered", i=2); ne = hist_len(b_env, ent)
    assert act(client, tok["mod1"], ent, "submit").status_code == 403                                 # T5 wrong role
    assert act(client, tok["stu1"], ent, "submit").status_code == 403
    assert (hist_len(b_env, other), hist_len(b_env, locked), hist_len(b_env, ent)) == (n, nl, ne)

def test_contract_enforces_rules_even_if_backend_were_bypassed(b_env):
    rid = rid_of(b_env, "Entered", i=3)
    key = record_key(rid); prev = b_env.chain.latest_hash(key)
    wrong_fac = User("x", "FACULTY", "FAC02")
    with pytest.raises(ChainError):
        b_env.chain.send_action(wrong_fac, "submit", key, prev, bytes.fromhex(marks_hash("test-pepper-test-pepper-test-pepper", rid, 0)), b"\x01" * 32)
    assert hist_len(b_env, rid) == 1

# ---------- T3 / T4: tampering is DETECTED ----------
def test_T3_marks_tamper_detected_and_blocks_progress(client, tok, b_env):
    rid = rid_of(b_env, "Locked", i=1)
    assert verify(client, tok, rid)["result"] == "MATCH"
    sql(b_env, "UPDATE marks_b SET marks_obtained = CASE WHEN marks_obtained < 5 THEN marks_obtained + 1 ELSE marks_obtained - 1 END WHERE record_id=%s", rid)
    v = verify(client, tok, rid)
    assert v["result"] == "INTEGRITY_MISMATCH" and v["current_record_matches_chain"] is False
    assert v["db_hash"] != v["chain_hash"] and "INTEGRITY MISMATCH DETECTED" in v["message"]
    n = hist_len(b_env, rid)
    r = act(client, tok["fac01"], rid, "request_correction", reason="x")
    assert r.status_code == 409 and "INTEGRITY MISMATCH" in r.text and hist_len(b_env, rid) == n
    # the baseline-style read still returns the tampered value silently: only verification reveals it
    assert client.get(f"/api/b/records/{rid}", headers=tok["fac01"]).status_code == 200

def test_T3_status_tamper_detected(client, tok, b_env):
    rid = rid_of(b_env, "Entered", i=4)
    sql(b_env, "UPDATE marks_b SET status='Approved' WHERE record_id=%s", rid)
    assert verify(client, tok, rid)["result"] == "INTEGRITY_MISMATCH"

def test_T4_history_row_tamper_detected(client, tok, b_env):
    rid = rid_of(b_env, "Locked", i=2)
    assert verify(client, tok, rid)["result"] == "MATCH"
    sql(b_env, "UPDATE record_versions_b SET marks_obtained = marks_obtained - 0.1 WHERE record_id=%s AND version_no=1", rid)
    v = verify(client, tok, rid)
    assert v["result"] == "INTEGRITY_MISMATCH" and v["history_consistent"] is False and v["mismatched_versions"] == [1]
    assert v["current_record_matches_chain"] is True      # current row untouched; the history edit alone is caught
    rid2 = rid_of(b_env, "Locked", i=3)
    sql(b_env, "UPDATE record_versions_b SET record_hash = repeat('a',64) WHERE record_id=%s AND version_no=1", rid2)
    assert verify(client, tok, rid2)["history_consistent"] is False

def test_deleted_history_row_detected(client, tok, b_env):
    rid = rid_of(b_env, "Submitted", i=0)
    r = act(client, tok["fac01"], rid, "unknown_action"); assert r.status_code == 404
    # advance once so there are 2 versions, then delete version 2 from the DB history
    assert act(client, tok["mod1"], rid, "moderate").status_code == 200
    sql(b_env, "DELETE FROM chain_anchor WHERE record_id=%s AND version_no=2", rid)       # FK: attacker must remove the mirror row too
    sql(b_env, "DELETE FROM record_versions_b WHERE record_id=%s AND version_no=2", rid)
    v = verify(client, tok, rid)
    assert v["result"] == "INTEGRITY_MISMATCH" and 2 in v["mismatched_versions"]

# ---------- atomicity ----------
def test_chain_failure_rolls_back_database(client, tok, b_env, monkeypatch):
    rid = rid_of(b_env, "Entered", i=5)
    before = row(b_env.db, rid, "marks_b")
    monkeypatch.setattr(b_env.chain.__class__, "send_action", lambda *a, **k: (_ for _ in ()).throw(ChainError("simulated outage")))
    r = act(client, tok["fac01"], rid, "update_marks", marks="3.0")
    assert r.status_code == 409 and "Blockchain rejected" in r.text
    assert row(b_env.db, rid, "marks_b") == before
    assert sql(b_env, "SELECT count(*) FROM record_versions_b WHERE record_id=%s", rid).fetchone()[0] == 1

# ---------- dashboard support endpoints ----------
def test_overview_and_results_endpoints(client, tok, b_env):
    r = client.get("/api/overview", headers=tok["mod1"]); assert r.status_code == 200
    j = r.json(); assert sum(j["status_a"].values()) == 50000 and j["chain"]["chain_id"] == 20260
    assert client.get("/api/overview", headers=tok["stu1"]).status_code == 403
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/experiments/security", headers=tok["mod1"]).status_code in (200, 404)

def test_demo_tamper_is_off_by_default_then_detected_when_enabled(client, tok, b_env, monkeypatch):
    rid = rid_of(b_env, "Locked", i=4)
    body = {"record_id": rid, "marks": "1.0"}
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert client.post("/api/b/demo/tamper", json=body, headers=tok["admin1"]).status_code == 404
    monkeypatch.setenv("DEMO_MODE", "1")
    assert client.post("/api/b/demo/tamper", json=body, headers=tok["fac01"]).status_code == 403          # only EXAM_ADMIN
    assert client.post("/api/b/demo/tamper", json={"record_id": rid, "marks": "9999"}, headers=tok["admin1"]).status_code == 422   # DB constraint
    r = client.post("/api/b/demo/tamper", json=body, headers=tok["admin1"]); assert r.status_code == 200, r.text
    assert sql(b_env, "SELECT count(*) FROM audit_log WHERE record_id=%s AND system='B'", rid).fetchone()[0] == 0    # leaves no trace in the app
    assert verify(client, tok, rid)["result"] == "INTEGRITY_MISMATCH"
