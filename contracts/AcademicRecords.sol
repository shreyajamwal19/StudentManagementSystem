// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AcademicRecords - append-only, role-restricted anchor of academic record versions (research prototype).
/// No marks are stored: only hashes. Each event links to the previous version of the SAME record via prevHash.
contract AcademicRecords {
    enum Role { NONE, FACULTY, MODERATOR, EXAM_ADMIN }
    enum Status { NONE, ENTERED, SUBMITTED, MODERATED, APPROVED, LOCKED, CORRECTION_REQUESTED, CORRECTION_AUTHORIZED }
    enum Action { IMPORT, CREATE, UPDATE_MARKS, SUBMIT, MODERATE, APPROVE, REJECT, LOCK,
                  REQUEST_CORRECTION, AUTHORIZE_CORRECTION, APPLY_CORRECTION }

    struct Record { bytes32 studentHash; bytes32 courseId; bytes32 assessmentId; Status status; uint32 version; }
    struct Entry  { bytes32 marksHash; bytes32 prevHash; bytes32 currHash; Action action; Status status; address actor; uint64 timestamp; }
    struct ImportItem { bytes32 key; bytes32 studentHash; bytes32 courseId; bytes32 assessmentId; bytes32 marksHash; bytes32 currHash; Status status; }

    address public immutable owner;
    mapping(address => Role) public roles;
    mapping(bytes32 => address) public courseFaculty;          // course-specific faculty assignment
    mapping(bytes32 => Record) private records;
    mapping(bytes32 => Entry[]) private history;               // append-only; nothing ever deletes or edits an entry

    event RoleSet(address indexed account, Role role);
    event CourseAssigned(bytes32 indexed courseId, address indexed faculty);
    event RecordEvent(bytes32 indexed key, Action indexed action, address indexed actor, uint32 version,
                      bytes32 studentHash, bytes32 courseId, bytes32 assessmentId,
                      bytes32 marksHash, bytes32 prevHash, bytes32 currHash, uint64 timestamp);

    modifier onlyOwner() { require(msg.sender == owner, "owner"); _; }
    modifier onlyRole(Role r) { require(roles[msg.sender] == r, "role"); _; }

    constructor() { owner = msg.sender; roles[msg.sender] = Role.EXAM_ADMIN; emit RoleSet(msg.sender, Role.EXAM_ADMIN); }

    // ---------------- administration ----------------
    function setRole(address account, Role role) external onlyOwner { roles[account] = role; emit RoleSet(account, role); }

    function assignCourse(bytes32 courseId, address faculty) external onlyRole(Role.EXAM_ADMIN) {
        require(roles[faculty] == Role.FACULTY, "not faculty");
        courseFaculty[courseId] = faculty;
        emit CourseAssigned(courseId, faculty);
    }

    // ---------------- creation ----------------
    /// Batch anchoring of the initial dataset (version 1 of every record). Exam admin only.
    function importRecords(ImportItem[] calldata items) external onlyRole(Role.EXAM_ADMIN) {
        for (uint256 i = 0; i < items.length; i++) {
            ImportItem calldata it = items[i];
            require(records[it.key].version == 0, "exists");
            require(it.status >= Status.ENTERED && it.status <= Status.LOCKED, "status");
            require(it.currHash != bytes32(0), "hash");
            records[it.key] = Record(it.studentHash, it.courseId, it.assessmentId, it.status, 1);
            _push(it.key, Action.IMPORT, it.status, 1, it.marksHash, bytes32(0), it.currHash);
        }
    }

    /// New record entered by the faculty assigned to the course.
    function createRecord(bytes32 key, bytes32 studentHash, bytes32 courseId, bytes32 assessmentId,
                          bytes32 marksHash, bytes32 currHash) external onlyRole(Role.FACULTY) {
        require(courseFaculty[courseId] == msg.sender, "course");
        require(records[key].version == 0, "exists");
        require(currHash != bytes32(0), "hash");
        records[key] = Record(studentHash, courseId, assessmentId, Status.ENTERED, 1);
        _push(key, Action.CREATE, Status.ENTERED, 1, marksHash, bytes32(0), currHash);
    }

    // ---------------- workflow (same state machine as the backend) ----------------
    function updateMarks(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)          external { _apply(k, Action.UPDATE_MARKS, prev, m, h); }
    function submit(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)               external { _apply(k, Action.SUBMIT, prev, m, h); }
    function moderate(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)             external { _apply(k, Action.MODERATE, prev, m, h); }
    function approve(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)              external { _apply(k, Action.APPROVE, prev, m, h); }
    function reject(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)               external { _apply(k, Action.REJECT, prev, m, h); }
    function lock(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)                 external { _apply(k, Action.LOCK, prev, m, h); }
    function requestCorrection(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)    external { _apply(k, Action.REQUEST_CORRECTION, prev, m, h); }
    function authorizeCorrection(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)  external { _apply(k, Action.AUTHORIZE_CORRECTION, prev, m, h); }
    function applyCorrection(bytes32 k, bytes32 prev, bytes32 m, bytes32 h)      external { _apply(k, Action.APPLY_CORRECTION, prev, m, h); }

    function _rule(Action a) private pure returns (Role role, bool scoped, Status from, Status to, bool changesMarks) {
        if (a == Action.UPDATE_MARKS)         return (Role.FACULTY,    true,  Status.ENTERED,  Status.ENTERED,  true);
        if (a == Action.SUBMIT)               return (Role.FACULTY,    true,  Status.ENTERED,  Status.SUBMITTED, false);
        if (a == Action.MODERATE)             return (Role.MODERATOR,  false, Status.SUBMITTED, Status.MODERATED, false);
        if (a == Action.APPROVE)              return (Role.MODERATOR,  false, Status.MODERATED, Status.APPROVED,  false);
        if (a == Action.REJECT)               return (Role.MODERATOR,  false, Status.MODERATED, Status.ENTERED,   false);
        if (a == Action.LOCK)                 return (Role.EXAM_ADMIN, false, Status.APPROVED,  Status.LOCKED,    false);
        if (a == Action.REQUEST_CORRECTION)   return (Role.FACULTY,    true,  Status.LOCKED,    Status.CORRECTION_REQUESTED, false);
        if (a == Action.AUTHORIZE_CORRECTION) return (Role.EXAM_ADMIN, false, Status.CORRECTION_REQUESTED, Status.CORRECTION_AUTHORIZED, false);
        if (a == Action.APPLY_CORRECTION)     return (Role.FACULTY,    true,  Status.CORRECTION_AUTHORIZED, Status.SUBMITTED, true);
        revert("action");
    }

    function _apply(bytes32 key, Action act, bytes32 expectedPrev, bytes32 marksHash, bytes32 currHash) private {
        (Role role, bool scoped, Status from, Status to, bool changesMarks) = _rule(act);
        require(roles[msg.sender] == role, "role");
        Record storage rec = records[key];
        require(rec.version != 0, "no record");
        if (scoped) require(courseFaculty[rec.courseId] == msg.sender, "course");
        require(rec.status == from, "state");
        Entry storage last = history[key][history[key].length - 1];
        require(last.currHash == expectedPrev, "prev");        // must link to the previous version of THIS record
        require(currHash != bytes32(0) && currHash != expectedPrev, "hash");
        if (!changesMarks) require(marksHash == last.marksHash, "marks");   // marks may only change in marks-changing actions
        rec.status = to;
        rec.version += 1;
        _push(key, act, to, rec.version, marksHash, expectedPrev, currHash);
    }

    function _push(bytes32 key, Action act, Status st, uint32 version, bytes32 marksHash, bytes32 prev, bytes32 curr) private {
        history[key].push(Entry(marksHash, prev, curr, act, st, msg.sender, uint64(block.timestamp)));
        Record storage r = records[key];
        emit RecordEvent(key, act, msg.sender, version, r.studentHash, r.courseId, r.assessmentId,
                         marksHash, prev, curr, uint64(block.timestamp));
    }

    // ---------------- views ----------------
    function getRecord(bytes32 key) external view returns (Record memory) { return records[key]; }
    function historyLength(bytes32 key) external view returns (uint256) { return history[key].length; }
    function getEntry(bytes32 key, uint256 index) external view returns (Entry memory) { return history[key][index]; }
    function latestHash(bytes32 key) external view returns (bytes32) {
        uint256 n = history[key].length; return n == 0 ? bytes32(0) : history[key][n - 1].currHash;
    }
    /// True iff `hash` equals the latest anchored hash of the record.
    function verify(bytes32 key, bytes32 hash) external view returns (bool) {
        uint256 n = history[key].length; return n != 0 && history[key][n - 1].currHash == hash;
    }
}
