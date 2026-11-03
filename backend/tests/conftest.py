"""Tests run against a throw-away copy of the imported database (CREATE DATABASE ... TEMPLATE).
Requires: dataset already imported into $PGDATABASE and a role allowed to CREATE DATABASE."""
import os
import bcrypt, psycopg2, pytest

SRC_DB = os.environ.get("PGDATABASE", "academic_records")
TEST_DB = "academic_records_test"
PW = "TestPass#12345"
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

@pytest.fixture(scope="session")
def _db():
    admin = psycopg2.connect(dbname="postgres"); admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cur.execute(f"CREATE DATABASE {TEST_DB} TEMPLATE {SRC_DB}")
    os.environ["PGDATABASE"] = TEST_DB
    conn = psycopg2.connect(dbname=TEST_DB); c = conn.cursor()
    h = bcrypt.hashpw(PW.encode(), bcrypt.gensalt(4)).decode()
    c.execute("DELETE FROM users")
    c.execute("INSERT INTO users (username,password_hash,role,faculty_id) VALUES ('fac01',%s,'FACULTY','FAC01'),('fac02',%s,'FACULTY','FAC02')", (h, h))
    c.execute("INSERT INTO users (username,password_hash,role) VALUES ('mod1',%s,'MODERATOR'),('admin1',%s,'EXAM_ADMIN')", (h, h))
    c.execute("SELECT DISTINCT student_id FROM marks_a WHERE status='Locked' ORDER BY 1 LIMIT 2")
    s1, s2 = [r[0] for r in c.fetchall()]
    c.execute("INSERT INTO users (username,password_hash,role,student_id) VALUES ('stu1',%s,'STUDENT',%s),('stu2',%s,'STUDENT',%s)", (h, s1, h, s2))
    conn.commit(); conn.close()
    yield
    admin.close()

@pytest.fixture(scope="session")
def client(_db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)

@pytest.fixture(scope="session")
def db(_db):
    conn = psycopg2.connect(dbname=TEST_DB); conn.autocommit = True
    yield conn
    conn.close()

def login(client, username):
    r = client.post("/auth/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}

@pytest.fixture(scope="session")
def tok(client):
    return {u: login(client, u) for u in ("fac01", "fac02", "mod1", "admin1", "stu1", "stu2")}

def pick(db, status, faculty, offset=0, table="marks_a"):
    """Fetch a record id with given status in a course assigned to `faculty` (or NOT assigned if faculty startswith '!')."""
    op = "<>" if faculty.startswith("!") else "="
    c = db.cursor()
    c.execute(f"SELECT m.record_id FROM {table} m JOIN courses c USING(course_id) WHERE m.status=%s AND c.faculty_id {op} %s "
              f"ORDER BY m.record_id OFFSET %s LIMIT 1", (status, faculty.lstrip("!"), offset))
    return c.fetchone()[0]

def row(db, rid, table="marks_a"):
    c = db.cursor(); c.execute(f"SELECT marks_obtained, status, version_no FROM {table} WHERE record_id=%s", (rid,))
    return c.fetchone()

from conftest_b import b_env  # noqa: E402,F401  (fixture for System B tests)
