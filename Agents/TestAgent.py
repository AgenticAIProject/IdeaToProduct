import os
import re
import ast
import shutil
import subprocess
import tempfile
import imports
from stack_skills import stack_skill
from pydantic import BaseModel, Field
from State_definition import AgentState
from test_runner import run_code_tests


class TestCase(BaseModel):
    id: str = Field(description="Unique test case ID, e.g. TC-01")
    acceptance_criterion_id: str = Field(description="The AC ID this test validates, e.g. AC-01")
    description: str = Field(description="What this test case verifies")
    test_function_name: str = Field(description="The function name or test label, e.g. test_display_records")


class TestSuiteGeneration(BaseModel):
    test_plan: str = Field(
        description="A concise summary of what acceptance criteria and edge cases are being tested."
    )
    test_cases: list[TestCase] = Field(
        default_factory=list,
        description="Structured list of test cases mapping to AC IDs."
    )
    test_file_name: str = Field(
        default="test_verification.py",
        description="The relative filename for the test suite matching project language, e.g. 'verification.test.js' for JS/Node/Frontend, 'test_verification.py' for Python, 'verification_test.go' for Go."
    )
    test_file_content: str = Field(
        description="Complete, executable test code matching the project programming language and runtime."
    )


REUSE_PREVIOUS_TESTS = True   # keep tests stable across rework loops so code can converge
MAX_TEST_REPAIRS = 1
MAX_CONTINUATIONS = 2

# Signals that the TEST (not the code) is broken
TEST_SIDE_PATTERNS = (
    "SyntaxError", "ModuleNotFoundError", "ImportError", "ERROR collecting", "collected 0 items",
    "fixture '", "Cannot find module", "ReferenceError", "SyntaxError: Unexpected",
    "no test files", "undefined: ", "cannot find package", "package .* is not in",
)


class TestPlan(BaseModel):
    """Small structured call: the plan only. The test code is generated separately as plain text."""
    test_plan: str = Field(description="Concise summary of acceptance criteria and edge cases being tested, and what cannot be tested.")
    test_cases: list[TestCase] = Field(default_factory=list)
    test_file_name: str = Field(default="test_verification.py")


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


def _validate_test_file(name: str, content: str):
    """Return an error string if the test file is not even syntactically valid."""
    if len(content.strip()) < 30:
        return "Test file is empty."
    try:
        if name.endswith(".py"):
            ast.parse(content)
        elif name.endswith((".js", ".mjs", ".cjs")) and shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as t:
                t.write(content)
                p = t.name
            try:
                r = subprocess.run(["node", "--check", p], capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return r.stderr.strip()[:500]
            finally:
                os.unlink(p)
        elif name.endswith((".c", ".h")) and shutil.which("gcc"):
            with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False, encoding="utf-8") as t:
                t.write(content)
                p = t.name
            try:
                r = subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", p], capture_output=True, text=True, timeout=15)
                if r.returncode != 0:
                    return r.stderr.strip()[:500]
            finally:
                os.unlink(p)
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"
    return None


def _is_test_side_failure(result: dict, code_files: list | None = None) -> bool:
    """True if the run died because of the TEST file (bad import path, syntax, fixture) - not the code."""
    blob = (result.get("raw_output") or "") + " ".join(result.get("errors") or [])
    if "[DEPENDENCY]" in blob or result.get("execution_status") in ("docker_unavailable", "timeout"):
        return False
    # A missing module that the generated code itself imports = code-side (bad requirements / missing file)
    code_text = "\n".join(f.get("content", "") for f in (code_files or []) if isinstance(f, dict))
    for mod in re.findall(r"No module named '([\w\.]+)'", blob):
        top = mod.split(".")[0]
        if re.search(rf"^\s*(?:from|import)\s+{re.escape(top)}\b", code_text, re.MULTILINE):
            return False
    return any(re.search(p, blob) for p in TEST_SIDE_PATTERNS)


def _interfaces(code_files: list) -> str:
    lines = []
    for f in code_files:
        if isinstance(f, dict):
            lines.append(f"- {f.get('path')}: {f.get('description', '')} | exports: {f.get('exports', [])}")
    return "\n".join(lines)


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
                "summary": "Testing failed: Code Agent did not produce any source files.",
                "duration_seconds": 0.0,
                "test_files": {},
            },
            "test_version": state.get("test_version", 0) + 1,
            "current_stage": "test",
            "workflow_status": "running"
        }

    # 1. Detect project runtime stack from files
    file_paths = [f.get("path", "").lower() for f in code_files if isinstance(f, dict)]
    is_go = any(p.endswith(".go") or p == "go.mod" for p in file_paths)
    is_java = any(p.endswith((".java", ".jar")) or p == "pom.xml" for p in file_paths)
    is_c = any(p.endswith((".c", ".h")) for p in file_paths)
    is_python = any(p.endswith(".py") or p == "requirements.txt" for p in file_paths)
    is_js_or_frontend = any(p.endswith((".js", ".jsx", ".ts", ".tsx", ".html")) or p == "package.json" for p in file_paths) and not is_python

    if is_js_or_frontend:
        stack_guidelines = """
=== PROJECT STACK: JavaScript / Frontend / Node.js ===
CRITICAL TESTING INSTRUCTIONS:
1. Target filename: 'verification.test.js'
2. Use CommonJS ('const ... = require(...)') and Node.js built-in modules ONLY: 'node:test', 'node:assert', and 'node:fs'.
3. Do NOT use ESM syntax ('import ...', 'export ...'). Always use CommonJS require.
4. Do NOT require third-party packages (e.g. jest, mocha, chai, jsdom, react-scripts) because tests run in a clean Node environment without external node_modules.
5. Tests must exercise the REAL code: read the actual project files with fs (e.g. index.html, app.js) and assert
   required elements/ids/functions from the requirements exist, or require() a CommonJS module if the code exports one.
   NEVER assert on locally-defined mock objects - that proves nothing.
   Skeleton:
   const test = require('node:test');
   const assert = require('node:assert');
   const fs = require('node:fs');
6. Every single test case MUST be registered using test('TC-XX: description', () => { ... }).
7. NEVER generate Python code for a JavaScript frontend project!
"""
    elif is_go:
        stack_guidelines = """
=== PROJECT STACK: Go ===
CRITICAL TESTING INSTRUCTIONS:
1. Target filename: 'verification_test.go'
2. Use standard 'testing' package.
3. NEVER generate Python code for a Go project!
"""
    elif is_java:
        stack_guidelines = """
=== PROJECT STACK: Java ===
CRITICAL TESTING INSTRUCTIONS:
1. Target filename: 'VerificationTest.java'
2. Use standard org.junit.
"""
    elif is_c:
        stack_guidelines = """
=== PROJECT STACK: C ===
CRITICAL TESTING INSTRUCTIONS:
1. Target filename: 'test_verification.c'
2. Use standard C99/C11 features only: stdio.h, stdlib.h, assert.h, string.h, errno.h, math.h.
3. NEVER generate Python code for a C project.
4. Use a single executable test harness that calls the real functions declared in the project headers.
5. Include the project header files directly, e.g. #include \"input_parser.h\" or #include \"operation_executor.h\".
6. Use assert() and printf() to validate behavior; do not mock away business logic.
7. Compile the test harness with GCC in the runner using the project .c files, excluding the app main if present.
"""
    else:
        stack_guidelines = """
=== PROJECT STACK: Python ===
CRITICAL TESTING INSTRUCTIONS:
1. Target filename: 'test_verification.py'
2. Use pytest or unittest.
3. Directly import modules under test.
"""

    # 2. Test file name / command per stack
    if is_js_or_frontend:
        default_name, test_command = "verification.test.js", "node --test verification.test.js"
    elif is_go:
        default_name, test_command = "verification_test.go", "go test -v ./..."
    elif is_java:
        default_name, test_command = "VerificationTest.java", "mvn test"
    elif is_c:
        default_name, test_command = "test_verification.c", None
    else:
        default_name = "test_verification.py"
        test_command = code_artifact.get("test_command") or "pytest --tb=short -v"
        if test_command.startswith("pytest"):
            test_command = "python -m " + test_command   # puts project root on sys.path

    project_path = state.get("generated_project_path", "")
    if not project_path:
        project_path = os.path.join(os.getcwd(), "generated_projects", state.get("project_id", "proj_001"))

    llm = imports.get_llm(agent_type="test", max_tokens=4000)
    system_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/test_prompt.txt"))
    files_context = "\n\n".join(f"--- File: {f.get('path')} ---\n{f.get('content')}" for f in code_files if isinstance(f, dict))
    base_context = f"""=== REQUIREMENTS ===
{requirements}

=== DESIGN ===
{design}

=== PUBLIC INTERFACES OF THE CODE (use these exact names) ===
{_interfaces(code_files)}

=== SOURCE CODE FILES ===
{files_context}

{stack_guidelines}

{stack_skill(design, 'TEST')}
"""

    prev = state.get("test_results") or {}
    prev_tests = prev.get("test_files") or {}
    prev_was_test_side = bool(prev.get("test_side_error"))

    plan_text, test_name, test_content = "", default_name, ""

    # 3a. Keep the same tests across rework loops (moving-target tests => code never converges)
    if REUSE_PREVIOUS_TESTS and prev_tests and not prev_was_test_side:
        test_name, test_content = next(iter(prev_tests.items()))
        plan_text = prev.get("test_plan", "")
        print(f"  [Test Agent] Reusing previous test suite '{test_name}' (rework loop).")
    else:
        # 3b. Small structured call for the plan
        try:
            plan = imports.invoke_structured(llm, TestPlan, [
                system_prompt,
                imports.HumanMessage(content=base_context + f"\nProduce ONLY the test plan and test case list. Test file name: {default_name}"),
            ])
            plan_text = plan.test_plan
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
    err = _validate_test_file(test_name, test_content)
    repairs = 0
    while err and repairs < MAX_TEST_REPAIRS + 1:
        repairs += 1
        print(f"  [Test Agent] Test file invalid ({err[:100]}); repairing ({repairs}).")
        test_content = _complete_text(llm, [
            system_prompt,
            imports.HumanMessage(content=base_context + f"\n--- current {test_name} ---\n{test_content}\n\nError: {err}\nReturn the complete corrected test file only."),
        ])
        err = _validate_test_file(test_name, test_content)

    def _write_and_run(content: str) -> dict:
        files = {test_name: content}
        if os.path.exists(project_path):
            with open(os.path.join(project_path, test_name), "w", encoding="utf-8") as fh:
                fh.write(content)
        return run_code_tests(files=code_files, test_files=files, test_command=test_command, timeout_seconds=120)

    execution_result = _write_and_run(test_content)

    # 5. If the run died because of the TEST (import path, syntax, missing fixture), fix the test once and rerun
    test_side = (not execution_result["success"]) and _is_test_side_failure(execution_result, code_files)
    for _ in range(MAX_TEST_REPAIRS if test_side else 0):
        print("  [Test Agent] Failure looks test-side; regenerating test with the runner output.")
        tail = "\n".join((execution_result.get("raw_output") or "").splitlines()[-40:])
        test_content = _complete_text(llm, [
            system_prompt,
            imports.HumanMessage(content=base_context + f"\n--- current {test_name} ---\n{test_content}\n\nRunner output:\n{tail}\n\nFix the TEST FILE (imports, names, setup). Do not weaken assertions. Return the complete file only."),
        ])
        execution_result = _write_and_run(test_content)
        test_side = (not execution_result["success"]) and _is_test_side_failure(execution_result, code_files)

    test_files_to_run = {test_name: test_content}

    test_results_payload: dict = {
        "success": execution_result["success"],
        "total_tests": execution_result["total_tests"],
        "passed_tests": execution_result["passed_tests"],
        "failed_tests": execution_result["failed_tests"],
        "errors": execution_result["errors"],
        "raw_output": execution_result["raw_output"],
        "summary": execution_result["summary"],
        "duration_seconds": execution_result["duration_seconds"],
        "test_files": test_files_to_run,
        "test_plan": plan_text,
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