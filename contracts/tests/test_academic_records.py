import pytest
from conftest import ROLE, STATUS, b32, h, reverts

def new_record(env, key, course="CS101", fac=None, marks="72.0", status_fac=None):
    fac = fac or env.fac1
    ch = h(f"{key}|v1|{marks}")
    env.chain.send(fac, env.c.functions.createRecord(b32(key), h("stu-" + key), b32(course), b32("MidTerm"), h("m|" + marks), ch))
    return ch

def step(env, who, fn_name, key, prev, marks, ver):
    """Apply a workflow step; returns the new record hash."""
    cur = h(f"{key}|v{ver}|{marks}|{fn_name}")
    env.chain.send(who, getattr(env.c.functions, fn_name)(b32(key), prev, h("m|" + marks), cur))
    return cur

def test_deploy_and_owner(env):
    assert env.c.functions.owner().call() == env.owner.address
    assert env.c.functions.roles(env.owner.address).call() == ROLE["EXAM_ADMIN"]
    assert env.c.functions.courseFaculty(b32("CS101")).call() == env.fac1.address

def test_only_owner_sets_roles(env):
    reverts(env.c.functions.setRole(env.stranger.address, 1), env.mod, "owner")
    reverts(env.c.functions.assignCourse(b32("CS103"), env.fac1.address), env.fac1, "role")
    reverts(env.c.functions.assignCourse(b32("CS103"), env.stranger.address), env.owner, "not faculty")

def test_create_requires_assigned_faculty(env):
    args = (b32("R-x"), h("s"), b32("CS101"), b32("Quiz1"), h("m"), h("c"))
    reverts(env.c.functions.createRecord(*args), env.fac2, "course")       # other course's faculty
    reverts(env.c.functions.createRecord(*args), env.mod, "role")
    reverts(env.c.functions.createRecord(*args), env.stranger, "role")

def test_full_workflow_hash_chain_and_events(env):
    key = "R-flow"; f, m, a = env.fac1, env.mod, env.owner
    hs = [new_record(env, key, marks="72.0")]
    seq = [(f, "updateMarks", "72.0"), (f, "submit", "72.0"), (m, "moderate", "72.0"), (m, "approve", "72.0"), (a, "lock", "72.0"),
           (f, "requestCorrection", "72.0"), (a, "authorizeCorrection", "72.0"), (f, "applyCorrection", "76.0"),
           (m, "moderate", "76.0"), (m, "approve", "76.0"), (a, "lock", "76.0")]
    for i, (who, fn, marks) in enumerate(seq, start=2):
        hs.append(step(env, who, fn, key, hs[-1], marks, i))
    k = b32(key)
    assert env.c.functions.historyLength(k).call() == 1 + len(seq)
    rec = env.c.functions.getRecord(k).call()
    assert rec[3] == STATUS["LOCKED"] and rec[4] == 1 + len(seq)
    zero = b"\0" * 32
    for i in range(len(hs)):
        e = env.c.functions.getEntry(k, i).call()
        assert e[2] == hs[i]                              # currHash
        assert e[1] == (zero if i == 0 else hs[i - 1])    # prevHash = previous version of the SAME record
    assert env.c.functions.getEntry(k, 0).call()[0] == h("m|72.0") and env.c.functions.getEntry(k, 8).call()[0] == h("m|76.0")
    assert env.c.functions.verify(k, hs[-1]).call() is True
    assert env.c.functions.verify(k, hs[0]).call() is False          # old version is not the latest
    assert env.c.functions.latestHash(k).call() == hs[-1]

def test_receipt_event_decodes_and_matches_chain(env):
    key = "R-evt"; ch = new_record(env, key)
    r = env.chain.send(env.fac1, env.c.functions.submit(b32(key), ch, h("m|72.0"), h("R-evt|v2")))
    ev = env.c.events.RecordEvent().process_receipt(r)[0]["args"]
    assert ev["key"] == b32(key) and ev["actor"] == env.fac1.address and ev["version"] == 2
    assert ev["prevHash"] == ch and ev["currHash"] == h("R-evt|v2") and ev["courseId"] == b32("CS101")
    blk = env.chain.w3.eth.get_block(r["blockNumber"])
    assert ev["timestamp"] == blk["timestamp"]                       # event time = block time on Besu

def test_wrong_prev_hash_rejected(env):
    key, other = "R-prev", "R-prev-other"
    ch = new_record(env, key); och = new_record(env, other)
    reverts(env.c.functions.submit(b32(key), och, h("m|72.0"), h("n")), env.fac1, "prev")   # link to ANOTHER record's hash
    reverts(env.c.functions.submit(b32(key), h("garbage"), h("m|72.0"), h("n")), env.fac1, "prev")

def test_state_machine_cannot_be_skipped(env):
    key = "R-skip"; ch = new_record(env, key); m = h("m|72.0")
    reverts(env.c.functions.moderate(b32(key), ch, m, h("n")), env.mod, "state")      # not submitted yet
    reverts(env.c.functions.lock(b32(key), ch, m, h("n")), env.owner, "state")
    reverts(env.c.functions.requestCorrection(b32(key), ch, m, h("n")), env.fac1, "state")
    reverts(env.c.functions.applyCorrection(b32(key), ch, m, h("n")), env.fac1, "state")
    ch = step(env, env.fac1, "submit", key, ch, "72.0", 2)
    reverts(env.c.functions.approve(b32(key), ch, m, h("n")), env.mod, "state")       # must moderate first
    reverts(env.c.functions.updateMarks(b32(key), ch, m, h("n")), env.fac1, "state")   # no edits after submission
    ch = step(env, env.mod, "moderate", key, ch, "72.0", 3)
    reverts(env.c.functions.lock(b32(key), ch, m, h("n")), env.owner, "state")         # must be approved first
    ch = step(env, env.mod, "approve", key, ch, "72.0", 4)
    ch = step(env, env.owner, "lock", key, ch, "72.0", 5)
    for fn in ("updateMarks", "submit", "applyCorrection"):                           # locked: no bypass of the correction path
        reverts(getattr(env.c.functions, fn)(b32(key), ch, h("m|99.0"), h("n")), env.fac1, "state")

def test_wrong_role_or_course_rejected(env):
    key = "R-role"; ch = new_record(env, key); m = h("m|72.0")
    reverts(env.c.functions.submit(b32(key), ch, m, h("n")), env.mod, "role")
    reverts(env.c.functions.submit(b32(key), ch, m, h("n")), env.owner, "role")
    reverts(env.c.functions.submit(b32(key), ch, m, h("n")), env.stranger, "role")
    reverts(env.c.functions.submit(b32(key), ch, m, h("n")), env.fac2, "course")       # faculty of ANOTHER course
    reverts(env.c.functions.updateMarks(b32(key), ch, h("m|1.0"), h("n")), env.fac2, "course")

def test_non_marks_actions_cannot_change_marks(env):
    key = "R-marks"; ch = new_record(env, key)
    reverts(env.c.functions.submit(b32(key), ch, h("m|95.0"), h("n")), env.fac1, "marks")   # marks tampering inside a status change
    env.chain.send(env.fac1, env.c.functions.updateMarks(b32(key), ch, h("m|80.0"), h("n2")))   # allowed: marks-changing action

def test_import_batch_admin_only_and_no_duplicates(env):
    items = [(b32(f"R-imp{i}"), h(f"s{i}"), b32("CS101"), b32("Quiz1"), h(f"m{i}"), h(f"c{i}"), STATUS["LOCKED"]) for i in range(5)]
    reverts(env.c.functions.importRecords(items), env.fac1, "role")
    r = env.chain.send(env.owner, env.c.functions.importRecords(items))
    assert len(env.c.events.RecordEvent().process_receipt(r)) == 5
    assert env.c.functions.getRecord(b32("R-imp3")).call()[3] == STATUS["LOCKED"]
    reverts(env.c.functions.importRecords(items), env.owner, "exists")

def test_failed_transaction_changes_nothing_on_chain(env):
    key = "R-fail"; ch = new_record(env, key); n = env.c.functions.historyLength(b32(key)).call()
    tx = env.c.functions.moderate(b32(key), ch, h("m|72.0"), h("n")).build_transaction(
        {"from": env.mod.address, "nonce": env.chain.w3.eth.get_transaction_count(env.mod.address), "gas": 500_000, "gasPrice": 0, "chainId": env.chain.chain_id})
    r = env.chain.w3.eth.wait_for_transaction_receipt(env.chain.w3.eth.send_raw_transaction(env.mod.sign_transaction(tx).raw_transaction), timeout=60)
    assert r["status"] == 0                                                   # real reverted tx on Besu
    assert env.c.functions.historyLength(b32(key)).call() == n and env.c.functions.getRecord(b32(key)).call()[3] == STATUS["ENTERED"]

def test_history_is_append_only(env):
    names = [x["name"].lower() for x in env.c.abi if x["type"] == "function"]
    assert not any(w in n for n in names for w in ("delete", "remove", "overwrite", "erase", "reset"))
    key = "R-app"; ch = new_record(env, key)
    first = env.c.functions.getEntry(b32(key), 0).call()
    ch2 = step(env, env.fac1, "submit", key, ch, "72.0", 2)
    assert env.c.functions.getEntry(b32(key), 0).call() == first             # earlier entry untouched
    assert env.c.functions.historyLength(b32(key)).call() == 2
