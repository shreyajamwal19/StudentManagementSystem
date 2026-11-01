#!/usr/bin/env python3
"""Checks canonical hashing against fixed vectors (shared with the future Java tests)."""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from canonical import canonical, record_hash
V = [
 ("REC000001","p"*64,"CS101","Quiz1",20,17.1,"Entered",1),
 ("REC000002","q"*64,"CS102","EndTerm",50,"22.30","Locked",3),
 ("REC000003","r"*64,"CS103","MidTerm",30,0.4,"Submitted",2),
]
out = [{"args": list(v), "canonical": canonical(*v), "sha256": record_hash(*v)} for v in V]
p = pathlib.Path(__file__).resolve().parent.parent / "docs/canonical_hash_vectors.json"
if p.exists():
    assert json.loads(p.read_text()) == out, "canonical vectors changed!"
else:
    p.write_text(json.dumps(out, indent=2) + "\n")
assert out[1]["canonical"].split("|")[6] == "22.3" and out[0]["canonical"] == record_hash.__globals__["canonical"](*V[0])
assert record_hash(*V[0]) != record_hash("REC000001","p"*64,"CS101","Quiz1",20,17.2,"Entered",1)
print("canonical tests ok")
