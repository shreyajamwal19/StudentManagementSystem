from app.workflow import ACTIONS, ROLES

def test_every_action_has_valid_role_and_target():
    for name, a in ACTIONS.items():
        assert a.role in ROLES, name
        assert a.to_status and a.from_status

def test_only_faculty_actions_are_course_scoped():
    for name, a in ACTIONS.items():
        assert a.course_scoped == (a.role == "FACULTY"), name

def test_no_action_edits_marks_of_locked_record_directly():
    for name, a in ACTIONS.items():
        if a.needs_marks:
            assert "Locked" not in a.from_status, name

def test_correction_path_requires_authorization_and_re_review():
    assert ACTIONS["request_correction"].to_status == "CorrectionRequested"
    assert ACTIONS["authorize_correction"].from_status == {"CorrectionRequested"}
    assert ACTIONS["apply_correction"].from_status == {"CorrectionAuthorized"}
    assert ACTIONS["apply_correction"].to_status == "Submitted"  # must pass moderate -> approve -> lock again
