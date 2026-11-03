"""Re-export of backend/app/hashing.py so scripts and the backend can never drift apart."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from app.hashing import canonical, record_hash, pseudonym, marks_hash, ZERO_HASH  # noqa: F401
