#!/usr/bin/env python3
"""Security & integrity experiments T1-T6 on System A (conventional) and System B (blockchain), via the real HTTP API,
real PostgreSQL and the real Besu network, in an isolated environment (experiments/common.py).
Outputs: experiments/results/security_results.{csv,json,md}. Outcome vocabulary: Prevented | Detected | Not Detected | Allowed."""
import csv, datetime, json, pathlib, sys
import httpx
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import ExperimentEnv
from app.hashing import record_key
from app.security import User

OUT = HERE.parent / "results"
rows = []

def add(test, desc, system, outcome, evidence):
    rows.append({"test": test, "description": desc, "system": system, "outcome": outcome, "evidence": evidence})
    print(f"{test} [{system}] {outcome}: {evidence}", flush=True)

def main():
    # same record ids are used for System A and System B (identical datasets)
    import psycopg2, os
    probe = psycopg2.connect(); c = probe.cursor()
    def ids(status, same, n, off=0):
        op = "=" if same else "<>"
        c.execute(f"SELECT m.record_id FROM marks_a m JOIN courses c USING(course_id) WHERE m.status=%s AND c.faculty_id {op} 'FAC01' ORDER BY m.record_id OFFSET %s LIMIT %s", (status, off, n))
        return [r[0] for r in c.fetchall()]
    t1 = ids("Entered", False, 1)[0]; t2 = ids("Locked", True, 1)[0]; t3 = ids("Locked", True, 1, 1)[0]
    t4 = ids("Locked", True, 1, 2)[0]; t5 = ids("Entered", True, 1)[0]; t6 = ids("Entered", True, 1, 1)[0]
    probe.close()
    plan = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}

    with ExperimentEnv(anchor_records=list(plan.values())) as env:
        tok = {u: env.token(u) for u in ("fac01", "fac02", "moderator1", "admin1")}
        db = env.db.cursor()
        def q(sql, *a): db.execute(sql, a); return db
        def state(sysx, rid): return tuple(q(f"SELECT marks_obtained, status, version_no FROM marks_{sysx} WHERE record_id=%s", rid).fetchone())
        def act(sysx, who, rid, action, **body): return httpx.post(f"{env.base}/api/{sysx}/records/{rid}/actions/{action}", json=body, headers=tok[who], timeout=120)
        def chain_len(rid): return env.chain.history_length(record_key(rid))
        def verify(rid): return httpx.get(f"{env.base}/api/b/records/{rid}/verify", headers=tok["moderator1"], timeout=60).json()
        other_fac = "fac02"   # t1 record belongs to a course not assigned to fac01; use fac01 as the unauthorized actor

        for s in "ab":
            S = s.upper()
            # T1 unauthorized marks modification (faculty not assigned to the course)
            before = state(s, t1); n0 = chain_len(t1) if s == "b" else None
            r = act(s, "fac01", t1, "update_marks", marks="1.0")
            ok = r.status_code == 403 and state(s, t1) == before and (s == "a" or chain_len(t1) == n0)
            add("T1", "Faculty not assigned to the course tries to change marks", S, "Prevented" if ok else "Allowed",
                f"HTTP {r.status_code}; DB unchanged={state(s, t1) == before}" + (f"; chain events {n0}->{chain_len(t1)}" if s == "b" else ""))
            # T2 modification after locking
            before = state(s, t2); n0 = chain_len(t2) if s == "b" else None
            r1 = act(s, "fac01", t2, "update_marks", marks="1.0"); r2 = act(s, "fac01", t2, "apply_correction", marks="1.0")
            ok = r1.status_code == 409 and r2.status_code == 409 and state(s, t2) == before and (s == "a" or chain_len(t2) == n0)
            add("T2", "Assigned faculty edits marks of a LOCKED record (direct edit and correction bypass)", S, "Prevented" if ok else "Allowed",
                f"HTTP {r1.status_code}/{r2.status_code}; DB unchanged={state(s, t2) == before}" + (f"; chain events {n0}->{chain_len(t2)}" if s == "b" else ""))
            # T3 manual database alteration (insider / compromised DB credentials, bypassing the application)
            orig = state(s, t3)
            q(f"UPDATE marks_{s} SET marks_obtained = CASE WHEN marks_obtained < 5 THEN marks_obtained + 1 ELSE marks_obtained - 1 END WHERE record_id=%s", t3)
            tampered = state(s, t3)
            aud = q("SELECT count(*) FROM audit_log WHERE record_id=%s AND system=%s", t3, S).fetchone()[0]
            if s == "a":
                rv = httpx.get(f"{env.base}/api/a/records/{t3}/verify", headers=tok["moderator1"], timeout=30)
                add("T3", "Manual SQL alteration of marks of a locked record", S, "Not Detected",
                    f"DB write allowed ({orig[0]} -> {tampered[0]}); no audit_log entry ({aud} rows); no integrity check exists (verify endpoint HTTP {rv.status_code})")
            else:
                v = verify(t3); blocked = act("b", "fac01", t3, "request_correction", reason="x")
                add("T3", "Manual SQL alteration of marks of a locked record", S, "Detected" if v["result"] == "INTEGRITY_MISMATCH" else "Not Detected",
                    f"DB write allowed ({orig[0]} -> {tampered[0]}); verify={v['result']} db_hash!=chain_hash={v['db_hash'] != v['chain_hash']}; "
                    f"legit follow-up action HTTP {blocked.status_code}")
            # T4 attempted modification of historical records (version history row)
            q(f"UPDATE record_versions_{s} SET marks_obtained = marks_obtained - 0.1 WHERE record_id=%s AND version_no=1", t4)
            aud = q("SELECT count(*) FROM audit_log WHERE record_id=%s AND system=%s", t4, S).fetchone()[0]
            if s == "a":
                add("T4", "Manual SQL alteration of a historical version row", S, "Not Detected",
                    f"history row edited; no audit_log entry ({aud} rows); no integrity check exists")
            else:
                v = verify(t4)
                add("T4", "Manual SQL alteration of a historical version row", S, "Detected" if not v["history_consistent"] else "Not Detected",
                    f"verify={v['result']} history_consistent={v['history_consistent']} mismatched_versions={v['mismatched_versions']}")
            # T5 unauthorized role transaction
            before = state(s, t5); n0 = chain_len(t5) if s == "b" else None
            r1 = act(s, "moderator1", t5, "submit"); r2 = act(s, "admin1", t5, "update_marks", marks="2.0")
            ev = f"moderator submit HTTP {r1.status_code}, admin update HTTP {r2.status_code}; DB unchanged={state(s, t5) == before}"
            ok = r1.status_code == 403 and r2.status_code == 403 and state(s, t5) == before
            if s == "b":
                from app.chain import ChainError
                try:
                    env.chain.send_action(User("m", "MODERATOR"), "submit", record_key(t5), env.chain.latest_hash(record_key(t5)), b"\0" * 32, b"\1" * 32)
                    direct = "accepted"
                except ChainError as e:
                    direct = "reverted"
                ev += f"; direct contract call by moderator signer {direct}; chain events {n0}->{chain_len(t5)}"
                ok = ok and direct == "reverted" and chain_len(t5) == n0
            add("T5", "Wrong-role users attempt faculty actions (and, for B, call the contract directly)", S, "Prevented" if ok else "Allowed", ev)
            # T6 valid authorized correction (full workflow with moderation, approval and locking)
            f, m, a = "fac01", "moderator1", "admin1"
            steps = [(f, "update_marks", {"marks": "10.0"}), (f, "submit", {}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {}),
                     (f, "request_correction", {"reason": "re-evaluation"}), (a, "authorize_correction", {}), (f, "apply_correction", {"marks": "12.0"}),
                     (m, "moderate", {}), (m, "approve", {}), (a, "lock", {})]
            codes = [act(s, who, t6, action, **body).status_code for who, action, body in steps]
            fin = state(s, t6)
            ok = all(c == 200 for c in codes) and float(fin[0]) == 12.0 and fin[1] == "Locked"
            ev = f"{sum(c == 200 for c in codes)}/{len(codes)} steps HTTP 200; final marks={fin[0]} status={fin[1]} version={fin[2]}"
            if s == "b":
                v = verify(t6); ev += f"; chain events={chain_len(t6)}; verify={v['result']}"
                ok = ok and v["result"] == "MATCH" and chain_len(t6) == 12
            add("T6", "Authorized correction passes moderation, approval and locking again", S, "Allowed" if ok else "Prevented", ev)

        info = dict(env.deploy_info, records=plan)
    OUT.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(OUT / "security_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["test", "description", "system", "outcome", "evidence"]); w.writeheader(); w.writerows(rows)
    (OUT / "security_results.json").write_text(json.dumps({"run_at_utc": stamp, "environment": info, "results": rows}, indent=2) + "\n")
    md = ["| Test | Description | System A | System B |", "|---|---|---|---|"]
    for t in sorted({r["test"] for r in rows}):
        a = next(r for r in rows if r["test"] == t and r["system"] == "A"); b = next(r for r in rows if r["test"] == t and r["system"] == "B")
        md.append(f"| {t} | {a['description']} | {a['outcome']} | {b['outcome']} |")
    (OUT / "security_results.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))

if __name__ == "__main__":
    main()
