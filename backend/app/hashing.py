"""Canonical record hashing and privacy-preserving identifiers (single source of truth; scripts/canonical.py re-exports it).
Canonical form: v1|record_id|student_pseudonym|course|assessment|max|marks(1dp)|status|version_no  (UTF-8, SHA-256)."""
import hashlib, hmac, os
from decimal import Decimal, ROUND_HALF_UP

ZERO_HASH = "0" * 64

def canonical(record_id, pseudonym, course, assessment, max_marks, marks, status, version_no):
    m = Decimal(str(marks)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"v1|{record_id}|{pseudonym}|{course}|{assessment}|{int(max_marks)}|{m}|{status}|{int(version_no)}"

def record_hash(*args):
    return hashlib.sha256(canonical(*args).encode("utf-8")).hexdigest()

def pseudonym(pepper: str, student_id: str) -> str:
    return hmac.new(pepper.encode(), student_id.encode(), hashlib.sha256).hexdigest()

def marks_hash(pepper: str, record_id: str, marks) -> str:
    """Keyed hash of the marks alone (marks have a tiny value space, so a plain hash would be brute-forceable)."""
    m = Decimal(str(marks)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return hmac.new(pepper.encode(), f"marks|{record_id}|{m}".encode(), hashlib.sha256).hexdigest()

def record_key(record_id: str) -> bytes:
    """On-chain key of a record: SHA-256(record_id) as bytes32."""
    return hashlib.sha256(record_id.encode()).digest()

def b32_ascii(s: str) -> bytes:
    return s.encode().ljust(32, b"\0")

def pepper() -> str:
    p = os.environ.get("PSEUDONYM_PEPPER")
    if not p:
        raise RuntimeError("PSEUDONYM_PEPPER is not set")
    return p
