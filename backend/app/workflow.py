"""Business rules shared by System A and System B: roles, course scoping, legal state transitions.
Pure data: no I/O, so it is unit-testable and identical for both systems."""
from dataclasses import dataclass

ENTERED, SUBMITTED, MODERATED, APPROVED, LOCKED = "Entered", "Submitted", "Moderated", "Approved", "Locked"
CORR_REQ, CORR_AUTH = "CorrectionRequested", "CorrectionAuthorized"

@dataclass(frozen=True)
class Action:
    role: str
    from_status: frozenset
    to_status: str
    course_scoped: bool = False      # faculty must be assigned to the record's course
    needs_marks: bool = False
    needs_reason: bool = False

ACTIONS = {
    "update_marks":         Action("FACULTY",    frozenset({ENTERED}),   ENTERED,   True,  needs_marks=True),
    "submit":               Action("FACULTY",    frozenset({ENTERED}),   SUBMITTED, True),
    "moderate":             Action("MODERATOR",  frozenset({SUBMITTED}), MODERATED),
    "approve":              Action("MODERATOR",  frozenset({MODERATED}), APPROVED),
    "reject":               Action("MODERATOR",  frozenset({MODERATED}), ENTERED,   needs_reason=True),
    "lock":                 Action("EXAM_ADMIN", frozenset({APPROVED}),  LOCKED),
    "request_correction":   Action("FACULTY",    frozenset({LOCKED}),    CORR_REQ,  True,  needs_reason=True),
    "authorize_correction": Action("EXAM_ADMIN", frozenset({CORR_REQ}),  CORR_AUTH),
    "apply_correction":     Action("FACULTY",    frozenset({CORR_AUTH}), SUBMITTED, True,  needs_marks=True),
}
ROLES = {"FACULTY", "MODERATOR", "EXAM_ADMIN", "STUDENT"}
