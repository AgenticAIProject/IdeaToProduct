import os
import re
import json
import shutil
import subprocess
import tempfile
import imports
from skill_registry import load_agent_skills, load_skill
from pydantic import BaseModel, Field
from State_definition import AgentState
from generated_test_validation import validate_state_isolation, validate_test_quality
from test_stacks import UnsupportedTestStackError, resolve_test_stack
from test_runner import run_code_tests


class TestCase(BaseModel):
    id: str = Field(description="Unique test case ID, e.g. TC-01")
    acceptance_criterion_id: str = Field(description="The AC ID this test validates, e.g. AC-01")
    description: str = Field(description="What this test case verifies")
    test_function_name: str = Field(description="The function name or test label, e.g. test_display_records")


REUSE_PREVIOUS_TESTS = True   # reuse passing tests; regenerate after assertion failures
MAX_TEST_REPAIRS = 1
MAX_CONTINUATIONS = 2

# Signals that the TEST (not the code) is broken
TEST_SIDE_PATTERNS = (
    "SyntaxError", "Cannot find module", "ReferenceError", "SyntaxError: Unexpected",
    r"_resetState is not a function",
    r"test_verification\.(?:c|cpp):\d+(?::\d+)?:.*(?:fatal )?error:",
    "no test files", "no tests found",
)


class TestPlan(BaseModel):
    """Small structured call: the plan only. The test code is generated separately as plain text."""
    test_plan: str = Field(description="Concise summary of acceptance criteria and edge cases being tested, and what cannot be tested.")
    test_cases: list[TestCase] = Field(default_factory=list)


def _strip_fences(text: str) -> str:
    """Extract raw code from LLM output that may contain preamble, fences, and postamble."""
    t = text.strip()
    m = re.search(r"```[\w+-]*\n(.*?)\n```", t, re.DOTALL)
    if m:
        return m.group(1).strip()
    # No fences — strip commentary lines at the top/bottom
    lines = t.splitlines()
    while lines and _is_commentary(lines[0]):
        lines.pop(0)
    while lines and _is_commentary(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def _is_commentary(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    starts = (
        "#", "certainly", "sure", "here is", "here's", "below is", "below are",
        "it appears", "it seems", "the complete", "the file", "note:", "explanation",
        "---",
    )
    return s.lower().startswith(starts)


def _text(msg) -> str:
    c = msg.content
    return c if isinstance(c, str) else "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)


def _complete_text(llm, messages: list) -> str:
    """Plain-text completion that continues automatically when cut off by the token limit."""
    out = ""
    for _ in range(MAX_CONTINUATIONS + 1):
        msg = llm.invoke(messages)
        chunk = _text(msg)
        out += chunk
        if (getattr(msg, "response_metadata", None) or {}).get("finish_reason") != "length":
            break
        messages = messages + [
            imports.AIMessage(content=chunk),
            imports.HumanMessage(content="You were cut off. Continue EXACTLY where you stopped. Output only the remaining code, no fences, no repetition."),
        ]
    return _strip_fences(out)


def _validate_test_file(name: str, content: str, code_files: list | None = None):
    """Return an error string if the test file is not even syntactically valid."""
    if len(content.strip()) < 30:
        return "Test file is empty."
    try:
        if name.endswith(".js") and shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
                t.write(content)
                p = t.name
            try:
                r = subprocess.run(["node", "--check", p], capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return r.stderr.strip()[:500]
            finally:
                os.unlink(p)
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"

    return validate_state_isolation(content, code_files or [])


def _is_test_side_failure(result: dict, code_files: list | None = None) -> bool:
    """True if the run died because of the TEST file (bad import path, syntax, fixture) - not the code."""
    blob = (result.get("raw_output") or "") + " ".join(result.get("errors") or [])
    if "[DEPENDENCY]" in blob or result.get("execution_status") in ("docker_unavailable", "timeout"):
        return False
    return any(re.search(p, blob) for p in TEST_SIDE_PATTERNS)


def _can_reuse_previous_tests(test_results: dict, expected_filename: str | None = None) -> bool:
    """Reuse a suite only after it passed or when Docker prevented execution."""
    return bool(
        REUSE_PREVIOUS_TESTS
        and test_results.get("test_files")
        and (
            expected_filename is None
            or expected_filename in test_results.get("test_files", {})
        )
        and not test_results.get("test_side_error")
        and (
            (test_results.get("success") is True and test_results.get("failed_tests", 0) == 0)
            or test_results.get("execution_status") == "docker_unavailable"
        )
    )


def _interfaces(code_files: list) -> str:
    lines = []
    for f in code_files:
        if isinstance(f, dict):
            lines.append(f"- {f.get('path')}: {f.get('description', '')} | exports: {f.get('exports', [])}")
    return "\n".join(lines)


def _compact_test_requirements(req: dict) -> str:
    """Format requirements specifically for test case generation: Acceptance Criteria are primary."""
    problem = req.get("problem_statement", "")
    acs = req.get("acceptance_criteria", [])
    frs = req.get("functional_requirements", [])

    clean_acs = [
        f"[{a.get('id', 'AC')}] (Validates {a.get('requirement_id', '')}): {a.get('description', '')}"
        for a in acs if isinstance(a, dict)
    ]
    clean_frs = [
        f"[{f.get('id', 'FR')}]: {f.get('description', '')}"
        for f in frs if isinstance(f, dict)
    ]
    data = {
        "problem": problem,
        "acceptance_criteria_to_verify": clean_acs,
        "functional_requirements": clean_frs[:6],
    }
    return json.dumps(data, indent=1, ensure_ascii=False)


def _compact_test_design(design: dict) -> str:
    """Format design for tests: endpoints, tech choices, edge cases."""
    data = {
        "system_type": design.get("system_type", ""),
        "technology_choices": [
            f"{c.get('category')}: {c.get('technology')}"
            for c in design.get("technology_choices", []) if isinstance(c, dict)
        ],
        "api_endpoints": [
            f"{ep.get('method')} {ep.get('path')} -> {ep.get('success_status', 200)}: {ep.get('description', '')}"
            for ep in design.get("api_endpoints", []) if isinstance(ep, dict)
        ],
        "edge_cases": [
            e.get("description", "") for e in design.get("edge_cases", []) if isinstance(e, dict)
        ][:5]
    }
    return json.dumps(data, indent=1, ensure_ascii=False)


def _compact_code_context(code_files: list) -> str:
    from CodeAgent import extract_file_interface
    parts = []
    for f in code_files:
        if not isinstance(f, dict):
            continue
        p = f.get("path", "")
        c = f.get("content", "")
        # If small file or header file, include directly
        if len(c) <= 800 or p.endswith((".h", ".hpp")):
            parts.append(f"--- File: {p} ---\n{c}")
        else:
            interface = extract_file_interface(p, c)
            parts.append(f"--- File: {p} (Public Signatures & Exports) ---\n{interface}")
    return "\n\n".join(parts)


def Test_Agent(state: AgentState) -> dict:
    """
    Test Agent (Stage 4):
    1. Consumes requirements, design, and the code artifact generated by the Code Agent.
    2. Autonomously generates independent verification unit tests based on acceptance criteria and design edge cases.
    3. Executes the test suite in a sandboxed, security-isolated runner tool (test_runner.py).
    4. Evaluates the execution outcome (pass/fail/errors) and stores structured metrics in state['test_results'].
    """
    print("\nTest Agent received code artifact for testing.")

    requirements = state.get("requirements", {})
    design = state.get("design", {})
    code_artifact = state.get("code", {})
    code_files = code_artifact.get("files", [])

    if not code_files:
        print("Warning: No code files provided to Test Agent.")
        return {
            "test_results": {
                "success": False,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "errors": ["No code files available in state['code']['files'] to execute tests against."],
                "raw_output": "Execution skipped: empty code artifact.",
                "execution_status": "missing_code",
                "summary": "Testing failed: Code Agent did not produce any source files.",
                "duration_seconds": 0.0,
                "test_files": {},
            },
            "test_version": state.get("test_version", 0) + 1,
            "current_stage": "test",
            "workflow_status": "running"
        }

    try:
        test_stack = resolve_test_stack(code_files, design)
    except UnsupportedTestStackError as exc:
        message = str(exc)
        print(f"  [Test Agent] {message}")
        return {
            "test_results": {
                "success": False,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "errors": [message],
                "raw_output": "",
                "execution_status": "unsupported_stack",
                "summary": "Testing skipped: unsupported generated project stack.",
                "duration_seconds": 0.0,
                "test_files": {},
                "test_plan": "",
                "test_cases": [],
                "test_side_error": False,
            },
            "test_version": state.get("test_version", 0) + 1,
            "current_stage": "test",
            "workflow_status": "running",
        }

    default_name = test_stack.test_filename
    test_command = test_stack.test_command

    project_path = state.get("generated_project_path", "")
    if not project_path:
        project_path = os.path.join(os.getcwd(), "generated_projects", state.get("project_id", "proj_001"))

    llm = imports.get_llm(agent_type="test", max_tokens=4000)
    test_skills = [
        skill.instructions for skill in load_agent_skills("test")
    ]
    test_skills.append(load_skill(test_stack.skill_id).instructions)
    system_prompt = imports.SystemMessage(content=(
        imports.load_prompt("prompts/test_prompt.txt") + "\n\n" + "\n\n".join(test_skills)
    ))

    req_context = _compact_test_requirements(requirements)
    design_context = _compact_test_design(design)
    code_context = _compact_code_context(code_files)

    prev = state.get("test_results") or {}
    prev_tests = prev.get("test_files") or {}
    previous_test_audit = ""
    if (
        prev_tests
        and not prev.get("success", False)
        and prev.get("execution_status") != "docker_unavailable"
    ):
        previous_test_name, previous_test_content = next(iter(prev_tests.items()))
        previous_output = (prev.get("raw_output") or "")[-3000:]
        previous_test_audit = f"""
=== PREVIOUS FAILING TEST SUITE — AUDIT, DO NOT REUSE ===
The previous suite failed. Treat its assertions as untrusted: compare each one with the
acceptance criteria and design below. Do not require UI elements, fields, endpoints, or
behaviors that are not specified. Regenerate tests that match the actual requirements;
keep valid requirement-based assertions even if the implementation currently fails them.

Previous test file ({previous_test_name}, truncated):
{previous_test_content[:3000]}

Previous test output (last 8000 characters):
{previous_output}
"""

    base_context = f"""=== REQUIREMENTS & ACCEPTANCE CRITERIA ===
{req_context}

=== ARCHITECTURE & TECH CHOICES ===
{design_context}

=== PUBLIC INTERFACES / EXPORTS ===
{_interfaces(code_files)}

=== SOURCE CODE UNDER TEST (SIGNATURES & CODE) ===
{code_context}

=== SELECTED TEST STACK ===
{test_stack.name}

{previous_test_audit}
"""

    plan_text, test_name, test_content = "", default_name, ""
    test_cases = []

    # Keep a stable suite only when it passed or execution never started (Docker unavailable).
    if _can_reuse_previous_tests(prev, default_name):
        test_name, test_content = next(iter(prev_tests.items()))
        plan_text = prev.get("test_plan", "")
        test_cases = prev.get("test_cases") or []
        print(f"  [Test Agent] Reusing previous test suite '{test_name}' (rework loop).")
    else:
        # 3b. Small structured call for the plan
        try:
            plan = imports.invoke_structured(llm, TestPlan, [
                system_prompt,
                imports.HumanMessage(content=base_context + f"\nProduce ONLY the test plan and test case list. Test file name: {default_name}"),
            ])
            plan_text = plan.test_plan
            test_cases = [case.model_dump() for case in plan.test_cases]
            test_name = default_name   # runner command is built around this name
        except Exception as e:  # noqa: BLE001
            print(f"  [Test Agent] Plan generation failed ({e}); continuing without a plan.")

        # 3c. Test code as plain text (no JSON wrapping => no truncation / escape problems)
        test_content = _complete_text(llm, [
            system_prompt,
            imports.HumanMessage(content=base_context + f"""
=== TEST PLAN ===
{plan_text}

Write the COMPLETE test file `{test_name}`. Output ONLY the raw code: no markdown fences, no commentary."""),
        ])

    # 4. Validate, then repair the test file itself before blaming the code
    err = _validate_test_file(test_name, test_content, code_files)
    repairs = 0
    while err and repairs < MAX_TEST_REPAIRS + 1:
        repairs += 1
        print(f"  [Test Agent] Test file invalid ({err[:100]}); repairing ({repairs}).")
        test_content = _complete_text(llm, [
            system_prompt,
            imports.HumanMessage(content=base_context + f"\n--- current {test_name} ---\n{test_content}\n\nError: {err}\nReturn the complete corrected test file only."),
        ])
        err = _validate_test_file(test_name, test_content, code_files)

    def _write_and_run(content: str) -> tuple[dict, dict]:
        files = {test_name: content}
        if os.path.exists(project_path):
            with open(os.path.join(project_path, test_name), "w", encoding="utf-8") as fh:
                fh.write(content)
        quality = validate_test_quality(test_stack.key, content, requirements, test_cases)
        if quality["errors"]:
            return ({
                "success": False,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "errors": quality["errors"],
                "raw_output": "",
                "execution_status": "test_quality_error",
                "summary": "Test execution skipped: generated suite did not meet quality checks.",
                "duration_seconds": 0.0,
            }, quality)
        return (
            run_code_tests(
                files=code_files,
                test_files=files,
                test_command=test_command,
                timeout_seconds=120,
            ),
            quality,
        )

    execution_result, test_quality = _write_and_run(test_content)

    # 5. If the run died because of the TEST (import path, syntax, missing fixture), fix the test once and rerun
    test_side = (
        not execution_result["success"]
        and execution_result.get("execution_status") != "test_quality_error"
        and _is_test_side_failure(execution_result, code_files)
    )
    for _ in range(MAX_TEST_REPAIRS if test_side else 0):
        print("  [Test Agent] Failure looks test-side; regenerating test with the runner output.")
        tail = "\n".join((execution_result.get("raw_output") or "").splitlines()[-40:])
        test_content = _complete_text(llm, [
            system_prompt,
            imports.HumanMessage(content=base_context + f"\n--- current {test_name} ---\n{test_content}\n\nRunner output:\n{tail}\n\nFix the TEST FILE (imports, names, setup). Do not weaken assertions. Return the complete file only."),
        ])
        execution_result, test_quality = _write_and_run(test_content)
        test_side = (
            not execution_result["success"]
            and execution_result.get("execution_status") != "test_quality_error"
            and _is_test_side_failure(execution_result, code_files)
        )

    test_files_to_run = {test_name: test_content}

    test_results_payload: dict = {
        "success": execution_result["success"],
        "total_tests": execution_result["total_tests"],
        "passed_tests": execution_result["passed_tests"],
        "failed_tests": execution_result["failed_tests"],
        "errors": execution_result["errors"],
        "raw_output": execution_result["raw_output"],
        "execution_status": execution_result.get("execution_status"),
        "summary": execution_result["summary"],
        "duration_seconds": execution_result["duration_seconds"],
        "test_files": test_files_to_run,
        "test_plan": plan_text,
        "test_cases": test_cases,
        "test_quality": test_quality,
        "test_side_error": bool(test_side),
    }
    if test_side:
        test_results_payload["errors"] = ["[TEST-INFRA] Tests could not run correctly (import/setup problem); see raw_output."] + list(test_results_payload["errors"])

    return {
        "test_results": test_results_payload,
        "test_version": state.get("test_version", 0) + 1,
        "current_stage": "test",
        "workflow_status": "running"
    }