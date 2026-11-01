"""System A (conventional baseline) REST API. Run: uvicorn app.main:app --app-dir backend"""
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from .db import connection
from .security import User, create_token, current_user, verify_password
from .service import ApiError, MarksService

app = FastAPI(title="Academic Records - System A (conventional baseline)", version="0.3.0")

class LoginRequest(BaseModel):
    username: str
    password: str

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

def build_router(system: str) -> APIRouter:
    svc = MarksService(system)
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
    return r

app.include_router(build_router("a"))
