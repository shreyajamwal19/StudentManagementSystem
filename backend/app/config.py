import os

def jwt_secret() -> str:
    s = os.environ.get("JWT_SECRET", "")
    if len(s) < 32:
        raise RuntimeError("Set JWT_SECRET (at least 32 chars) in the environment; it is never committed.")
    return s

JWT_ALG = "HS256"
def jwt_expire_minutes() -> int:
    return int(os.environ.get("JWT_EXPIRE_MIN", "60"))
