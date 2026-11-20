"""Static checks for generated test files."""

import re
from typing import Any


def exported_reset_helper(code_files: list[dict[str, Any]]) -> str | None:
    """Find a reset helper explicitly exposed by a CommonJS project module."""
    for file in code_files:
        if not isinstance(file, dict) or not str(file.get("path", "")).lower().endswith((".js", ".cjs")):
            continue
        content = file.get("content", "")
        declared_exports = file.get("exports", [])
        if isinstance(declared_exports, str):
            declared_exports = re.split(r"[\s,]+", declared_exports)
        if "_resetState" in declared_exports:
            return "_resetState"
        if re.search(r"\bexports\._resetState\s*=", content):
            return "_resetState"
        if re.search(r"\bmodule\.exports\s*=\s*\{[\s\S]*?\b_resetState\s*[:,]", content):
            return "_resetState"
        exported_object = re.search(
            r"\bconst\s+(\w+)\s*=\s*\{[\s\S]*?\b_resetState\s*[:,]",
            content,
        )
        if exported_object and re.search(
            rf"\bmodule\.exports\s*=\s*{re.escape(exported_object.group(1))}\b",
            content,
        ):
            return "_resetState"
    return None


def validate_state_isolation(test_content: str, code_files: list[dict[str, Any]]) -> str | None:
    """Require each Node test to reset state when a reset helper is exported."""
    reset_helper = exported_reset_helper(code_files)
    if not reset_helper:
        return None

    test_count = len(re.findall(r"\btest\s*\(", test_content))
    reset_count = len(re.findall(rf"\b{re.escape(reset_helper)}\s*\(", test_content))
    has_reset_hook = bool(re.search(r"\bbeforeEach\s*\(", test_content)) and reset_count > 0
    if test_count and not has_reset_hook and reset_count < test_count:
        return (
            f"Call the exported {reset_helper}() in every test or in a beforeEach hook "
            "to isolate mutable module state."
        )
    return None


def validate_test_quality(
    stack_key: str,
    test_content: str,
    requirements: dict[str, Any],
    test_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check that generated tests contain assertions and map to every required criterion."""
    code = re.sub(r"/\*[\s\S]*?\*/", " ", test_content)
    code = re.sub(r"(?m)^\s*//.*$", " ", code)
    if stack_key == "javascript":
        assertion_found = bool(re.search(
            r"\bassert(?:\.(?:strictEqual|deepEqual|deepStrictEqual|equal|notEqual|ok|throws|rejects|"
            r"match|doesNotThrow|notStrictEqual|notDeepEqual|ifError))?\s*\(",
            code,
        ))
    elif stack_key in ("c", "cpp"):
        assertion_found = bool(re.search(r"\bassert\s*\(", code))
    else:
        raise ValueError(f"Unknown test stack for quality validation: {stack_key!r}")

    criteria = requirements.get("acceptance_criteria") or []
    if criteria:
        required_ids = {
            str(item.get("id", "")).strip()
            for item in criteria
            if isinstance(item, dict) and item.get("id")
        }
    else:
        required_ids = {
            str(item.get("id", "")).strip()
            for item in requirements.get("functional_requirements", [])
            if isinstance(item, dict) and item.get("id")
        }

    valid_cases = [case for case in test_cases if isinstance(case, dict)]
    case_ids = {
        str(case.get("acceptance_criterion_id", "")).strip()
        for case in valid_cases
        if case.get("acceptance_criterion_id")
    }
    case_names = {
        str(case.get("test_function_name", "")).strip()
        for case in valid_cases
        if case.get("test_function_name")
    }
    covered_ids = case_ids & required_ids
    missing_ids = sorted(required_ids - covered_ids)
    unknown_ids = sorted(case_ids - required_ids)
    missing_case_names = sorted(name for name in case_names if name not in code)
    errors = []
    if not assertion_found:
        errors.append("Generated test file contains no recognized assertions.")
    if missing_ids:
        errors.append(f"Test plan does not map cases to all required criteria: {', '.join(missing_ids)}.")
    if unknown_ids:
        errors.append(f"Test plan references unknown requirement IDs: {', '.join(unknown_ids)}.")
    if missing_case_names:
        errors.append(
            "Generated test file does not contain planned test labels/functions: "
            f"{', '.join(missing_case_names)}."
        )

    return {
        "assertion_found": assertion_found,
        "required_criterion_ids": sorted(required_ids),
        "covered_criterion_ids": sorted(covered_ids),
        "missing_criterion_ids": missing_ids,
        "planned_test_case_names": sorted(case_names),
        "missing_test_case_names": missing_case_names,
        "errors": errors,
    }
