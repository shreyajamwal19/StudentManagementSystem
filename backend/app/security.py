"""Authentication: bcrypt password hashes and signed JWTs. Identity and role come ONLY from the verified token."""
import datetime
from dataclasses import dataclass
from typing import Optional
import bcrypt, jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import JWT_ALG, jwt_secret, jwt_expire_minutes
from .workflow import ROLES

_bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class User:
    username: str
    role: str
    faculty_id: Optional[str] = None
    student_id: Optional[str] = None

def hash_password(pw: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds)).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False

def create_token(u: User) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    claims = {"sub": u.username, "role": u.role, "faculty_id": u.faculty_id, "student_id": u.student_id,
              "iat": now, "exp": now + datetime.timedelta(minutes=jwt_expire_minutes())}
    return jwt.encode(claims, jwt_secret(), algorithm=JWT_ALG)

def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(401, "Authentication required")
    try:
        p = jwt.decode(creds.credentials, jwt_secret(), algorithms=[JWT_ALG], options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    if p["role"] not in ROLES:
        raise HTTPException(401, "Invalid token")
    return User(p["sub"], p["role"], p.get("faculty_id"), p.get("student_id"))
