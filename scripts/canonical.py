"""Canonical record serialization and SHA-256 hashing. The Java backend must produce identical output
(see docs/canonical_hash_vectors.json). Marks are rendered with exactly one decimal place."""
import hashlib, hmac
from decimal import Decimal, ROUND_HALF_UP

ZERO_HASH = "0" * 64

def canonical(record_id, pseudonym, course, assessment, max_marks, marks, status, version_no):
    m = Decimal(str(marks)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"v1|{record_id}|{pseudonym}|{course}|{assessment}|{int(max_marks)}|{m}|{status}|{int(version_no)}"

def record_hash(*args):
    return hashlib.sha256(canonical(*args).encode("utf-8")).hexdigest()

def pseudonym(pepper: str, student_id: str) -> str:
    return hmac.new(pepper.encode(), student_id.encode(), hashlib.sha256).hexdigest()
