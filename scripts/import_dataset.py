#!/usr/bin/env python3
"""Import the original CSV (read-only) into PostgreSQL: reference tables, then marks_a and marks_b from the SAME
parsed rows in ONE transaction, plus version-1 history rows. System B version rows carry canonical SHA-256 hashes.
Env: PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD, PSEUDONYM_PEPPER. Use --reset to truncate (destructive, local only)."""
import csv, hashlib, io, os, sys, pathlib
import psycopg2
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from canonical import record_hash, pseudonym, ZERO_HASH

ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "synthetic_student_marks_50000_1.csv"
SCHEMA = ROOT / "backend/src/main/resources/db/migration/V1__schema.sql"
LEGAL = {"Entered", "Submitted", "Moderated", "Approved", "Locked"}

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def main():
    pepper = os.environ.get("PSEUDONYM_PEPPER")
    if not pepper: sys.exit("Set PSEUDONYM_PEPPER (secret, not committed).")
    expected = (ROOT / "data/DATASET.sha256").read_text().split()[0]
    if sha256_file(CSV) != expected: sys.exit("CSV checksum mismatch: dataset was modified.")
    with open(CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 50000, len(rows)

    conn = psycopg2.connect()  # uses PG* env vars
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.marks_a')")
    if cur.fetchone()[0] is None:
        cur.execute(SCHEMA.read_text())
    cur.execute("SELECT count(*) FROM marks_a")
    if cur.fetchone()[0] > 0:
        if "--reset" not in sys.argv: sys.exit("Tables not empty. Re-run with --reset to truncate (destructive).")
        cur.execute("TRUNCATE chain_anchor, audit_log, record_versions_a, record_versions_b, marks_a, marks_b, "
                    "users, students, courses, assessments, faculty RESTART IDENTITY CASCADE")

    fac = sorted({r["Faculty_ID"] for r in rows})
    course_fac = {}
    for r in rows: course_fac.setdefault(r["Course_ID"], r["Faculty_ID"])
    assert all(course_fac[r["Course_ID"]] == r["Faculty_ID"] for r in rows), "course->faculty not unique"
    maxm = {}
    for r in rows: maxm.setdefault(r["Assessment_ID"], int(r["Max_Marks"]))
    assert all(maxm[r["Assessment_ID"]] == int(r["Max_Marks"]) for r in rows)
    assert all(r["Status"] in LEGAL for r in rows)
    students = sorted({r["Student_ID"] for r in rows})
    pseud = {s: pseudonym(pepper, s) for s in students}

    cur.executemany("INSERT INTO faculty VALUES (%s)", [(x,) for x in fac])
    cur.executemany("INSERT INTO courses VALUES (%s,%s)", sorted(course_fac.items()))
    cur.executemany("INSERT INTO assessments VALUES (%s,%s)", sorted(maxm.items()))
    cur.executemany("INSERT INTO students VALUES (%s,%s)", [(s, pseud[s]) for s in students])

    def buf(lines):
        b = io.StringIO()
        w = csv.writer(b); w.writerows(lines); b.seek(0); return b
    marks, va, vb = [], [], []
    for r in rows:
        m = ("%.1f" % float(r["Marks_Obtained"]))
        marks.append([r["Record_ID"], r["Student_ID"], r["Course_ID"], r["Assessment_ID"], r["Faculty_ID"], m,
                      r["Status"], 1, r["Timestamp"]])
        va.append([r["Record_ID"], 1, "IMPORT", m, r["Status"], "dataset-import", "", "", r["Timestamp"]])
        h = record_hash(r["Record_ID"], pseud[r["Student_ID"]], r["Course_ID"], r["Assessment_ID"],
                        r["Max_Marks"], m, r["Status"], 1)
        vb.append([r["Record_ID"], 1, "IMPORT", m, r["Status"], "dataset-import", h, ZERO_HASH, r["Timestamp"]])
    cols = "(record_id,student_id,course_id,assessment_id,faculty_id,marks_obtained,status,version_no,recorded_at)"
    vcols = "(record_id,version_no,action,marks_obtained,status,actor,record_hash,prev_hash,created_at)"
    for t in ("marks_a", "marks_b"):
        cur.copy_expert(f"COPY {t} {cols} FROM STDIN WITH CSV", buf(marks))
    cur.copy_expert(f"COPY record_versions_a {vcols} FROM STDIN WITH CSV", buf(va))
    cur.copy_expert(f"COPY record_versions_b {vcols} FROM STDIN WITH CSV", buf(vb))
    conn.commit()
    print("Imported", len(rows), "rows into marks_a and marks_b (single transaction).")

if __name__ == "__main__":
    main()
