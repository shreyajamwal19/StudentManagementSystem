"""System A (conventional baseline) REST API. Run: uvicorn app.main:app --app-dir backend"""
import csv, json, os, pathlib
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from .db import connection
from .security import User, create_token, current_user, verify_password
from .service import ApiError, MarksService
from .service_b import MarksServiceB

app = FastAPI(title="Academic Records - System A (baseline) and System B (blockchain)", version="0.6.0")

class LoginRequest(BaseModel):
    username: str
    password: str

ROOT = pathlib.Path(__file__).resolve().parents[2]

class TamperRequest(BaseModel):
    record_id: str
    marks: Decimal

class ActionRequest(BaseModel):
    marks: Optional[Decimal] = None
    reason: Optional[str] = None

@app.exception_handler(ApiError)
async def _api_error(_, exc: ApiError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})

@app.post("/auth/login")
def login(body: LoginRequest):
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT username, password_hash, role, faculty_id, student_id FROM users WHERE username = %s", (body.username,))
        row = cur.fetchone()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    u = User(row["username"], row["role"], row["faculty_id"], row["student_id"])
    return {"access_token": create_token(u), "token_type": "bearer", "role": u.role}

@app.get("/api/overview")
def overview(u: User = Depends(current_user)):
    if u.role == "STUDENT":
        raise HTTPException(403, "Not available for students")
    out = {}
    with connection() as conn, conn.cursor() as cur:
        for sx in ("a", "b"):
            cur.execute(f"SELECT status, count(*) FROM marks_{sx} GROUP BY status ORDER BY status")
            out[f"status_{sx}"] = {k: v for k, v in cur.fetchall()}
        cur.execute("SELECT count(DISTINCT record_id) FROM chain_anchor"); out["records_anchored"] = cur.fetchone()[0]
    out["demo_mode"] = os.environ.get("DEMO_MODE") == "1"
    try:
        from .chain import get_chain
        ch = get_chain()
        out["chain"] = {"block_number": ch.w3.eth.block_number, "chain_id": ch.chain_id, "contract": ch.c.address}
    except Exception:
        out["chain"] = None
    return out

@app.get("/api/experiments/security")
def exp_security(u: User = Depends(current_user)):
    f = ROOT / "experiments/results/security_results.json"
    if not f.exists():
        raise HTTPException(404, "Run experiments/security/run_security_experiments.py first")
    return json.loads(f.read_text())

@app.get("/api/experiments/performance")
def exp_performance(u: User = Depends(current_user)):
    f = ROOT / "experiments/results/performance_summary.csv"
    smoke = False
    if not f.exists():
        f = ROOT / "experiments/results/performance_summary_smoke.csv"; smoke = True
    if not f.exists():
        raise HTTPException(404, "Run experiments/benchmark first")
    return {"smoke_test_only": smoke, "rows": list(csv.DictReader(f.open()))}

def build_router(system: str, svc: Optional[MarksService] = None) -> APIRouter:
    svc = svc or MarksService(system)
    r = APIRouter(prefix=f"/api/{system}", tags=[f"system-{system}"])

    @r.get("/records")
    def list_records(student_id: Optional[str] = None, course_id: Optional[str] = None, status: Optional[str] = None,
                     limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), u: User = Depends(current_user)):
        return jsonable_encoder(svc.list(u, student_id, course_id, status, limit, offset))

    @r.get("/records/{record_id}")
    def get_record(record_id: str, u: User = Depends(current_user)):
        return jsonable_encoder(svc.get(u, record_id))

    @r.get("/records/{record_id}/history")
    def history(record_id: str, u: User = Depends(current_user)):
        return jsonable_encoder(svc.history(u, record_id))

    @r.post("/records/{record_id}/actions/{action}")
    def act(record_id: str, action: str, body: ActionRequest = ActionRequest(), u: User = Depends(current_user)):
        return jsonable_encoder(svc.perform(u, record_id, action, body.marks, body.reason))

    @r.get("/audit")
    def audit(record_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000), u: User = Depends(current_user)):
        if u.role not in ("MODERATOR", "EXAM_ADMIN"):
            raise HTTPException(403, "Audit log requires MODERATOR or EXAM_ADMIN")
        return jsonable_encoder(svc.audit(record_id, limit))

    @r.post("/demo/tamper")
    def demo_tamper(body: TamperRequest, u: User = Depends(current_user)):
        """DEMO ONLY (DEMO_MODE=1, EXAM_ADMIN): simulates an insider editing the database directly, bypassing the application,
        its audit log and its version history. Used to demonstrate tamper detection."""
        if os.environ.get("DEMO_MODE") != "1":
            raise HTTPException(404, "Demo mode is disabled")
        if u.role != "EXAM_ADMIN":
            raise HTTPException(403, "Requires EXAM_ADMIN")
        try:
            with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT marks_obtained FROM {svc.marks_t} WHERE record_id=%s FOR UPDATE", (body.record_id,))
                row = cur.fetchone()
                if row is None:
                    raise HTTPException(404, "Record not found")
                cur.execute(f"UPDATE {svc.marks_t} SET marks_obtained=%s WHERE record_id=%s", (body.marks, body.record_id))
        except psycopg2.Error as e:
            raise HTTPException(422, f"Database rejected the value: {str(e).splitlines()[0]}")
        return jsonable_encoder({"record_id": body.record_id, "system": system.upper(), "marks_before": row["marks_obtained"], "marks_after": body.marks,
                                 "note": "Written directly to the database: no audit_log entry, no version row, no blockchain transaction."})

    if system == "b":
        @r.get("/records/{record_id}/verify")
        def verify(record_id: str, u: User = Depends(current_user)):
            if u.role == "STUDENT":
                raise HTTPException(403, "Verification requires FACULTY, MODERATOR or EXAM_ADMIN")
            return jsonable_encoder(svc.verify(u, record_id))

        @r.get("/records/{record_id}/chain-history")
        def chain_history(record_id: str, u: User = Depends(current_user)):
            return jsonable_encoder(svc.chain_history(u, record_id))
    return r

app.include_router(build_router("a"))
app.include_router(build_router("b", MarksServiceB()))
