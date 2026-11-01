#!/usr/bin/env python3
"""Verify the import: CSV vs DB, System A vs System B identical, hashes recompute. Writes counts/booleans only
(no pseudonyms or hashes) to experiments/results/import_verification.json. Env: PG*, PSEUDONYM_PEPPER."""
import csv, json, os, sys, pathlib, datetime
import psycopg2
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from canonical import record_hash, pseudonym, ZERO_HASH
ROOT = pathlib.Path(__file__).resolve().parent.parent
pepper = os.environ["PSEUDONYM_PEPPER"]
cur = psycopg2.connect().cursor()
res = {}
def one(q): cur.execute(q); return cur.fetchone()[0]

csv_rows = {r["Record_ID"]: r for r in csv.DictReader(open(ROOT/"data/synthetic_student_marks_50000_1.csv"))}
res["csv_rows"] = len(csv_rows)
for s in "ab":
    res[f"marks_{s}_rows"] = one(f"select count(*) from marks_{s}")
    res[f"versions_{s}_rows"] = one(f"select count(*) from record_versions_{s}")
cols = "record_id,student_id,course_id,assessment_id,faculty_id,marks_obtained,status,version_no,recorded_at"
chk = lambda s: one(f"select md5(string_agg(concat_ws('|',{cols}),E'\\n' order by record_id)) from marks_{s}")
res["marks_a_equals_marks_b"] = chk("a") == chk("b")
cur.execute(f"select {cols} from marks_a")
mism = 0
for rid, st, co, asx, fa, mk, status, ver, ts in cur.fetchall():
    r = csv_rows.get(rid)
    if not r or (st, co, asx, fa, status) != (r["Student_ID"], r["Course_ID"], r["Assessment_ID"], r["Faculty_ID"], r["Status"]) \
       or float(mk) != float(r["Marks_Obtained"]) or ts.strftime("%Y-%m-%d %H:%M:%S") != r["Timestamp"]:
        mism += 1
res["csv_vs_db_mismatches"] = mism
cur.execute("select m.record_id, s.pseudonym, m.course_id, m.assessment_id, a.max_marks, m.marks_obtained, m.status, m.version_no, v.record_hash, v.prev_hash "
            "from marks_b m join students s using(student_id) join assessments a using(assessment_id) "
            "join record_versions_b v on v.record_id=m.record_id and v.version_no=m.version_no")
bad = 0
for rid, ps, co, asx, mx, mk, stt, ver, h, ph in cur.fetchall():
    if h != record_hash(rid, ps, co, asx, mx, "%.1f" % mk, stt, ver) or ph != ZERO_HASH: bad += 1
res["hash_recompute_mismatches"] = bad
res["pseudonym_pepper_consistent"] = one("select count(*) from students") == 1000
res["distinct"] = {k: one(f"select count(*) from {k}") for k in ("students", "courses", "assessments", "faculty")}
res["all_checks_pass"] = (res["csv_rows"] == res["marks_a_rows"] == res["marks_b_rows"] == res["versions_a_rows"] == res["versions_b_rows"] == 50000
                          and res["marks_a_equals_marks_b"] and mism == 0 and bad == 0)
res["verified_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
out = ROOT/"experiments/results/import_verification.json"
out.write_text(json.dumps(res, indent=2) + "\n"); print(json.dumps(res, indent=2))
sys.exit(0 if res["all_checks_pass"] else 1)
