from ReviewAgent import Review_Agent, ReviewResult, generate_review_fallback
from TestAgent import _can_reuse_previous_tests, _is_test_side_failure


def test_fallback_does_not_reject_only_because_generated_assertions_failed():
    result = generate_review_fallback({
        "code": {"files": [{"path": "app.py"}]},
        "test_results": {
            "success": False,
            "failed_tests": 3,
            "errors": [],
        },
    })

    assert result.approved is True
    assert result.defects == []
    assert next(check for check in result.checks if check.area == "Tests").status == "warn"


def test_review_does_not_apply_an_automatic_test_failure_veto(monkeypatch):
    class FakeReviewModel:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return ReviewResult(approved=True, overall_score=7)

    monkeypatch.setattr(
        "ReviewAgent.imports.get_llm",
        lambda **_kwargs: FakeReviewModel(),
    )
    result = Review_Agent({
        "code": {"files": [{"path": "app.py"}]},
        "test_results": {
            "success": False,
            "failed_tests": 3,
            "errors": [],
        },
    })

    assert result["approval_status"] == "approved"


def test_review_still_rejects_a_requirement_backed_defect(monkeypatch):
    class FakeReviewModel:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return ReviewResult(
                approved=False,
                defects=["app.py: Required news category filter is missing."],
                overall_score=3,
            )

    monkeypatch.setattr(
        "ReviewAgent.imports.get_llm",
        lambda **_kwargs: FakeReviewModel(),
    )
    result = Review_Agent({
        "code": {"files": [{"path": "app.py"}]},
        "test_results": {
            "success": False,
            "failed_tests": 3,
            "errors": [],
        },
    })

    assert result["approval_status"] == "rejected"


def test_failed_test_suite_is_not_reused():
    assert not _can_reuse_previous_tests({
        "test_files": {"verification.test.js": "old assertions"},
        "success": False,
        "failed_tests": 3,
    })


def test_passing_or_unavailable_test_suite_can_be_reused():
    suite = {"verification.test.js": "valid tests"}
    assert _can_reuse_previous_tests({
        "test_files": suite,
        "success": True,
        "failed_tests": 0,
    })
    assert _can_reuse_previous_tests({
        "test_files": suite,
        "success": False,
        "execution_status": "docker_unavailable",
    })


def test_missing_assumed_reset_helper_is_classified_as_test_failure():
    assert _is_test_side_failure({
        "raw_output": "TypeError: logic._resetState is not a function",
        "errors": [],
    }, [{"path": "logic.js", "content": "module.exports = { searchTextbooks };"}])


def test_other_application_type_errors_are_not_automatically_test_failures():
    assert not _is_test_side_failure({
        "raw_output": "TypeError: invalid application value",
        "errors": [],
    }, [{"path": "logic.js", "content": "module.exports = { searchTextbooks };"}])
