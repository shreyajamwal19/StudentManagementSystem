"""Marks service (the shared 'marks-core'). System A uses it as-is; System B will subclass it and override
_after_apply() to hash and anchor each event on Besu. Order of checks: role -> record exists -> course scope -> state -> input."""
import time
from decimal import Decimal
from typing import Optional
from psycopg2.extras import RealDictCursor
from .db import connection
from .security import User
from .workflow import ACTIONS, LOCKED


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class MarksService:
    def __init__(self, system: str):
        if system not in ("a", "b"):
            raise ValueError("system must be 'a' or 'b'")
        self.sys = system
        self.marks_t = f"marks_{system}"
        self.versions_t = f"record_versions_{system}"

    # ---- reads ----------------------------------------------------------
    _SELECT = ("SELECT m.record_id, m.student_id, m.course_id, m.assessment_id, m.marks_obtained, m.status, "
               "m.version_no, m.recorded_at, c.faculty_id AS course_faculty, a.max_marks "
               "FROM {t} m JOIN courses c ON c.course_id = m.course_id "
               "JOIN assessments a ON a.assessment_id = m.assessment_id ")

    def _fetch(self, cur, record_id: str, lock: bool = False):
        cur.execute(self._SELECT.format(t=self.marks_t) + "WHERE m.record_id = %s" + (" FOR UPDATE OF m" if lock else ""),
                    (record_id,))
        return cur.fetchone()

    @staticmethod
    def _can_view(u: User, rec) -> bool:
        if u.role in ("MODERATOR", "EXAM_ADMIN"):
            return True
        if u.role == "FACULTY":
            return u.faculty_id is not None and u.faculty_id == rec["course_faculty"]
        if u.role == "STUDENT":
            return u.student_id == rec["student_id"] and rec["status"] == LOCKED
        return False

    def get(self, u: User, record_id: str):
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            rec = self._fetch(cur, record_id)
        if rec is None:
            raise ApiError(404, "Record not found")
        if not self._can_view(u, rec):
            raise ApiError(403, "Not allowed to view this record")
        return rec

    def list(self, u: User, student_id: Optional[str], course_id: Optional[str], status: Optional[str], limit: int, offset: int):
        where, args = [], []
        if u.role == "FACULTY":
            where.append("c.faculty_id = %s"); args.append(u.faculty_id)
        elif u.role == "STUDENT":
            where += ["m.student_id = %s", "m.status = %s"]; args += [u.student_id, LOCKED]
        for col, val in (("m.student_id", student_id), ("m.course_id", course_id), ("m.status", status)):
            if val:
                where.append(f"{col} = %s"); args.append(val)
        sql = self._SELECT.format(t=self.marks_t) + ("WHERE " + " AND ".join(where) + " " if where else "") + \
              "ORDER BY m.record_id LIMIT %s OFFSET %s"
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, args + [limit, offset])
            return cur.fetchall()

    def history(self, u: User, record_id: str):
        self.get(u, record_id)  # same visibility rules
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT record_id, version_no, action, marks_obtained, status, actor, record_hash, prev_hash, created_at "
                        f"FROM {self.versions_t} WHERE record_id = %s ORDER BY version_no", (record_id,))
            return cur.fetchall()

    def audit(self, record_id: Optional[str], limit: int):
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, system, record_id, action, actor, old_value, new_value, created_at FROM audit_log "
                        "WHERE system = %s AND (%s::text IS NULL OR record_id = %s) ORDER BY id DESC LIMIT %s",
                        (self.sys.upper(), record_id, record_id, limit))
            return cur.fetchall()

    # ---- writes ---------------------------------------------------------
    @staticmethod
    def _validate_marks(marks: Optional[Decimal], max_marks: int) -> Decimal:
        if marks is None:
            raise ApiError(422, "marks is required for this action")
        if not marks.is_finite() or marks.as_tuple().exponent < -1:
            raise ApiError(422, "marks must be a number with at most one decimal place")
        if marks < 0 or marks > max_marks:
            raise ApiError(422, f"marks must be between 0 and {max_marks}")
        return marks.quantize(Decimal("0.1"))

    def perform(self, u: User, record_id: str, action: str, marks: Optional[Decimal] = None, reason: Optional[str] = None):
        t0 = time.perf_counter()
        spec = ACTIONS.get(action)
        if spec is None:
            raise ApiError(404, "Unknown action")
        if u.role != spec.role:
            raise ApiError(403, f"Action '{action}' requires role {spec.role}")
        t = {"submit_ms": 0.0, "confirm_ms": 0.0, "verify_ms": 0.0}   # chain timings (System B); confirm_ms includes submit_ms
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            rec = self._fetch(cur, record_id, lock=True)
            if rec is None:
                raise ApiError(404, "Record not found")
            if spec.course_scoped and (u.faculty_id is None or u.faculty_id != rec["course_faculty"]):
                raise ApiError(403, "Faculty is not assigned to this course")
            if rec["status"] not in spec.from_status:
                raise ApiError(409, f"Illegal transition: '{action}' not allowed from status {rec['status']}")
            new_marks = rec["marks_obtained"]
            if spec.needs_marks:
                new_marks = self._validate_marks(marks, rec["max_marks"])
            if spec.needs_reason and not (reason and reason.strip()):
                raise ApiError(422, "reason is required for this action")
            self._precheck(cur, rec, action, u, t)
            new_version = rec["version_no"] + 1
            after = dict(rec, marks_obtained=new_marks, status=spec.to_status, version_no=new_version)
            cur.execute(f"UPDATE {self.marks_t} SET marks_obtained=%s, status=%s, version_no=%s WHERE record_id=%s",
                        (new_marks, spec.to_status, new_version, record_id))
            rhash, phash = self._hashes(cur, after)
            cur.execute(f"INSERT INTO {self.versions_t} (record_id, version_no, action, marks_obtained, status, actor, record_hash, prev_hash, created_at) "
                        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())",
                        (record_id, new_version, action.upper(), new_marks, spec.to_status, u.username, rhash, phash))
            old = f"status={rec['status']};marks={rec['marks_obtained']};v={rec['version_no']}"
            new = f"status={spec.to_status};marks={new_marks};v={new_version}" + (f";reason={reason.strip()}" if reason else "")
            cur.execute("INSERT INTO audit_log (system, record_id, action, actor, old_value, new_value) VALUES (%s,%s,%s,%s,%s,%s)",
                        (self.sys.upper(), record_id, action.upper(), u.username, old, new))
            extra = self._after_apply(cur, after, action, u, (rhash, phash), t) or {}
        total = (time.perf_counter() - t0) * 1000
        out = dict(after, **extra)
        out["timings_ms"] = {"total_ms": round(total, 2), "db_ms": round(total - t["confirm_ms"] - t["verify_ms"], 2),
                             "verify_ms": round(t["verify_ms"], 2), "submit_ms": round(t["submit_ms"], 2),
                             "confirm_ms": round(t["confirm_ms"], 2)}
        return out

    # ---- hooks (System A: no-ops; System B overrides them) ------------------
    def _precheck(self, cur, rec, action: str, u: User, t: dict) -> None:
        return None

    def _hashes(self, cur, after):
        return (None, None)

    def _after_apply(self, cur, after, action: str, u: User, hashes, t: dict):
        return None
