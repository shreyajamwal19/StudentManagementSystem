from conftest import pick, row, login, PW

def act(client, h, rid, action, **body):
    return client.post(f"/api/a/records/{rid}/actions/{action}", json=body, headers=h)

# ---------- authentication ----------
def test_login_wrong_password(client):
    assert client.post("/auth/login", json={"username": "fac01", "password": "nope"}).status_code == 401

def test_unauthenticated_rejected(client, db):
    rid = pick(db, "Entered", "FAC01")
    assert client.get(f"/api/a/records/{rid}").status_code == 401
    assert client.post(f"/api/a/records/{rid}/actions/submit").status_code == 401

def test_forged_token_rejected(client, db):
    import jwt
    rid = pick(db, "Entered", "FAC01")
    forged = jwt.encode({"sub": "fac01", "role": "EXAM_ADMIN", "exp": 9999999999}, "x" * 40, algorithm="HS256")
    r = client.get(f"/api/a/records/{rid}", headers={"Authorization": "Bearer " + forged})
    assert r.status_code == 401

def test_user_supplied_role_in_body_or_header_is_ignored(client, tok, db):
    rid = pick(db, "Moderated", "FAC01")
    h = dict(tok["fac01"], **{"X-Role": "MODERATOR"})
    r = act(client, h, rid, "approve", role="MODERATOR")
    assert r.status_code == 403 and row(db, rid)[1] == "Moderated"

# ---------- T1 / course-specific authorization ----------
def test_T1_faculty_cannot_modify_other_course(client, tok, db):
    rid = pick(db, "Entered", "!FAC01")          # a course not assigned to fac01
    before = row(db, rid)
    r = act(client, tok["fac01"], rid, "update_marks", marks="1.0")
    assert r.status_code == 403 and row(db, rid) == before

def test_faculty_cannot_view_other_course(client, tok, db):
    rid = pick(db, "Entered", "!FAC01")
    assert client.get(f"/api/a/records/{rid}", headers=tok["fac01"]).status_code == 403

def test_faculty_list_limited_to_own_course(client, tok):
    recs = client.get("/api/a/records?limit=200", headers=tok["fac01"]).json()
    assert recs and {r["course_faculty"] for r in recs} == {"FAC01"}

# ---------- T2 / state machine ----------
def test_T2_cannot_modify_locked_record(client, tok, db):
    rid = pick(db, "Locked", "FAC01")
    before = row(db, rid)
    assert act(client, tok["fac01"], rid, "update_marks", marks="1.0").status_code == 409
    assert act(client, tok["fac01"], rid, "apply_correction", marks="1.0").status_code == 409  # no correction bypass
    assert act(client, tok["fac01"], rid, "submit").status_code == 409
    assert row(db, rid) == before

def test_cannot_skip_states(client, tok, db):
    sub = pick(db, "Submitted", "FAC01")
    assert act(client, tok["mod1"], sub, "approve").status_code == 409      # must moderate first
    assert act(client, tok["admin1"], sub, "lock").status_code == 409
    mod = pick(db, "Moderated", "FAC01")
    assert act(client, tok["admin1"], mod, "lock").status_code == 409       # must be approved first
    ent = pick(db, "Entered", "FAC01")
    assert act(client, tok["mod1"], ent, "moderate").status_code == 409     # must be submitted first
    assert act(client, tok["admin1"], ent, "authorize_correction").status_code == 409

def test_T5_wrong_role_rejected(client, tok, db):
    ent = pick(db, "Entered", "FAC01", 1)
    assert act(client, tok["mod1"], ent, "update_marks", marks="2.0").status_code == 403
    assert act(client, tok["admin1"], ent, "submit").status_code == 403
    appr = pick(db, "Approved", "FAC01")
    assert act(client, tok["fac01"], appr, "lock").status_code == 403
    assert act(client, tok["stu1"], appr, "lock").status_code == 403
    assert row(db, appr)[1] == "Approved"

def test_marks_validation(client, tok, db):
    rid = pick(db, "Entered", "FAC01", 2)
    mx = db.cursor(); mx.execute("SELECT max_marks FROM assessments a JOIN marks_a m USING(assessment_id) WHERE record_id=%s", (rid,))
    mx = mx.fetchone()[0]
    before = row(db, rid)
    for bad in (str(mx + 1), "-1", "17.25", None):
        body = {} if bad is None else {"marks": bad}
        assert act(client, tok["fac01"], rid, "update_marks", **body).status_code == 422, bad
    assert row(db, rid) == before

# ---------- T6 / full workflow incl. authorized correction + provenance ----------
def test_T6_full_workflow_and_correction(client, tok, db):
    rid = pick(db, "Entered", "FAC01", 3)
    f, m, a = tok["fac01"], tok["mod1"], tok["admin1"]
    steps = [(f, "update_marks", {"marks": "10.0"}), (f, "submit", {}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {}),
             (f, "request_correction", {"reason": "re-evaluation"}), (a, "authorize_correction", {}),
             (f, "apply_correction", {"marks": "12.0"}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {})]
    for h, action, body in steps:
        r = act(client, h, rid, action, **body)
        assert r.status_code == 200, (action, r.text)
    marks, status, ver = row(db, rid)
    assert float(marks) == 12.0 and status == "Locked" and ver == 1 + len(steps)
    hist = client.get(f"/api/a/records/{rid}/history", headers=f).json()
    assert [h["version_no"] for h in hist] == list(range(1, ver + 1))
    assert [h["action"] for h in hist][1:] == [s[1].upper() for s in steps]
    assert float(hist[5]["marks_obtained"]) == 10.0 and float(hist[-1]["marks_obtained"]) == 12.0
    aud = client.get(f"/api/a/audit?record_id={rid}", headers=a).json()
    assert len(aud) == len(steps) and all(x["system"] == "A" for x in aud)
    assert "reason=re-evaluation" in [x["new_value"] for x in aud if x["action"] == "REQUEST_CORRECTION"][0]

def test_reject_returns_to_entered(client, tok, db):
    rid = pick(db, "Moderated", "FAC01", 1)
    assert act(client, tok["mod1"], rid, "reject").status_code == 422   # reason required
    assert act(client, tok["mod1"], rid, "reject", reason="check marks").status_code == 200
    assert row(db, rid)[1] == "Entered"

# ---------- students / audit access ----------
def test_student_sees_only_own_locked(client, tok, db):
    recs = client.get("/api/a/records?limit=1000", headers=tok["stu1"]).json()
    assert recs and all(r["status"] == "Locked" for r in recs)
    assert len({r["student_id"] for r in recs}) == 1
    other = pick(db, "Locked", "FAC01")  # some record; ensure not stu1's
    c = db.cursor(); c.execute("SELECT student_id FROM marks_a WHERE record_id=%s", (other,)); owner = c.fetchone()[0]
    mine = recs[0]["student_id"]
    if owner != mine:
        assert client.get(f"/api/a/records/{other}", headers=tok["stu1"]).status_code == 403
    nonlocked = pick(db, "Submitted", "FAC01")
    c.execute("SELECT student_id FROM marks_a WHERE record_id=%s", (nonlocked,))
    assert client.get(f"/api/a/records/{nonlocked}", headers=tok["stu1"]).status_code == 403

def test_audit_requires_privileged_role(client, tok):
    assert client.get("/api/a/audit", headers=tok["fac01"]).status_code == 403
    assert client.get("/api/a/audit", headers=tok["stu1"]).status_code == 403
    assert client.get("/api/a/audit", headers=tok["mod1"]).status_code == 200
