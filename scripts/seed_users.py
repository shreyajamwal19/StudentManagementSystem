#!/usr/bin/env python3
"""Seed demo users: one faculty login per faculty ID, moderator1, admin1, and N student logins.
Env: PG*, SEED_PASSWORD (demo password, not committed). Usage: seed_users.py [N_students=20]"""
import os, sys, pathlib
import psycopg2
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from app.security import hash_password

pw = os.environ.get("SEED_PASSWORD")
if not pw or len(pw) < 10: sys.exit("Set SEED_PASSWORD (min 10 chars).")
n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
conn = psycopg2.connect(); cur = conn.cursor()
h = hash_password(pw)  # same demo password for all demo users
cur.execute("SELECT faculty_id FROM faculty ORDER BY 1"); fac = [r[0] for r in cur.fetchall()]
cur.execute("SELECT student_id FROM students ORDER BY 1 LIMIT %s", (n,)); stu = [r[0] for r in cur.fetchall()]
rows = [(f.lower(), h, "FACULTY", f, None) for f in fac] + [("moderator1", h, "MODERATOR", None, None), ("admin1", h, "EXAM_ADMIN", None, None)] \
     + [(s.lower(), h, "STUDENT", None, s) for s in stu]
for r in rows:
    cur.execute("INSERT INTO users (username,password_hash,role,faculty_id,student_id) VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (username) DO NOTHING", r)
conn.commit(); print("Seeded", len(rows), "users (existing usernames skipped).")
