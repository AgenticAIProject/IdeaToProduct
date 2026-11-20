from generated_test_validation import (
    exported_reset_helper,
    validate_state_isolation,
    validate_test_quality,
)


def test_exported_reset_helper_is_required_in_each_test():
    code_files = [{
        "path": "logic.js",
        "content": """
const _exports = {
  handleClick,
  _resetState: () => { state = ''; }
};
module.exports = _exports;
""",
    }]
    test_content = """
test('first', () => { logic.handleClick('1'); });
test('second', () => { logic.handleClick('2'); });
"""

    assert exported_reset_helper(code_files) == "_resetState"
    assert "every test" in validate_state_isolation(test_content, code_files)


def test_reset_in_before_each_hook_is_valid():
    code_files = [{
        "path": "logic.js",
        "exports": ["_resetState"],
        "content": "module.exports = api;",
    }]
    test_content = """
beforeEach(() => logic._resetState());
test('first', () => {});
test('second', () => {});
"""

    assert validate_state_isolation(test_content, code_files) is None


def test_no_assumed_reset_api_is_required():
    code_files = [{"path": "logic.js", "content": "module.exports = { add, remove };"}]

    assert validate_state_isolation("test('first', () => {});", code_files) is None


def test_test_quality_requires_assertions_and_complete_acceptance_criterion_mapping():
    requirements = {
        "acceptance_criteria": [{"id": "AC-01"}, {"id": "AC-02"}],
    }
    test_cases = [
        {
            "id": "TC-01",
            "acceptance_criterion_id": "AC-01",
            "test_function_name": "test_add_task",
        },
    ]

    report = validate_test_quality(
        "javascript",
        "test('example', () => {});",
        requirements,
        test_cases,
    )

    assert report["assertion_found"] is False
    assert report["missing_criterion_ids"] == ["AC-02"]
    assert any("no recognized assertions" in error for error in report["errors"])


def test_test_quality_accepts_assertions_and_all_required_ids():
    requirements = {
        "acceptance_criteria": [{"id": "AC-01"}],
    }
    cases = [{
        "id": "TC-01",
        "acceptance_criterion_id": "AC-01",
        "test_function_name": "test_add_task",
    }]

    report = validate_test_quality(
        "javascript",
        "test('test_add_task AC-01 behavior', () => { assert.equal(actual, expected); });",
        requirements,
        cases,
    )

    assert report["errors"] == []
    assert report["covered_criterion_ids"] == ["AC-01"]


def test_native_test_quality_recognizes_c_assertions_and_functional_requirement_fallback():
    report = validate_test_quality(
        "c",
        "static void test_add(void) { assert(add(2, 2) == 4); }\n"
        "int main(void) { test_add(); }",
        {"functional_requirements": [{"id": "FR-01"}]},
        [{
            "id": "TC-01",
            "acceptance_criterion_id": "FR-01",
            "test_function_name": "test_add",
        }],
    )

    assert report["assertion_found"] is True
    assert report["errors"] == []
