"""
test_runner.py
==============
Executes AI-generated code and tests in a hardened, isolated Docker container.

Security guarantees
-------------------
- AI-generated code is NEVER executed directly on the host.
- If Docker is unavailable, execution is refused and a structured failure is returned.
- Docker container runs with:
    --network none          (no outbound/inbound network)
    --memory 512m           (RAM cap)
    --cpus 1.0              (CPU cap)
    --cap-drop ALL          (drop all Linux capabilities)
    --security-opt no-new-privileges
- Source files are bind-mounted read/write so pytest can emit JUnit XML.
- All user-supplied file paths are validated to prevent path-traversal attacks.

Parsing strategy
----------------
1. pytest --junitxml  → deterministic XML parsing  (preferred)
2. stdout token count → PASSED / FAILED fallback   (last resort)

Public API
----------
run_code_tests(files, test_files, test_command=None, timeout_seconds=30) -> dict
"""

import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DOCKER_IMAGE       = "python:3.11-slim"
DOCKER_TIMEOUT_CAP = 120           # hard upper bound regardless of caller value
JUNIT_CONTAINER    = "/app/test-results.xml"
JUNIT_HOST_NAME    = "test-results.xml"


# ---------------------------------------------------------------------------
# Docker availability
# ---------------------------------------------------------------------------

def _docker_available() -> bool:
    """Return True only when the Docker daemon is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _docker_unavailable_result(duration: float) -> dict:
    return {
        "success":          False,
        "execution_status": "docker_unavailable",
        "total_tests":      0,
        "passed_tests":     0,
        "failed_tests":     0,
        "errors": [
            "Docker is not available on this host. "
            "AI-generated code cannot be executed without Docker isolation. "
            "Install Docker and ensure the daemon is running before retrying."
        ],
        "raw_output":       "",
        "summary":          "Execution skipped – Docker not available",
        "duration_seconds": round(duration, 2),
    }


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def _safe_join(base: str, user_path: str) -> str:
    """
    Resolve *user_path* relative to *base*.
    Raises ValueError on any path-traversal attempt.
    """
    # Strip leading separators so os.path.join won't treat it as absolute
    user_path = user_path.lstrip("/").lstrip("\\")
    resolved  = os.path.realpath(os.path.join(base, user_path))
    base_real = os.path.realpath(base)
    if resolved != base_real and not resolved.startswith(base_real + os.sep):
        raise ValueError(
            f"Path traversal detected: '{user_path}' resolves outside the sandbox "
            f"(resolved to '{resolved}')."
        )
    return resolved


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _write_files(
    files:      Union[List[Dict], Dict],
    test_files: Dict[str, str],
    temp_dir:   str,
) -> None:
    """Write source and test files to *temp_dir* with path-traversal guard."""
    # -- Source files --------------------------------------------------------
    if isinstance(files, list):
        for entry in files:
            path    = entry.get("path", "")
            content = entry.get("content", "")
            if path and content is not None:
                full = _safe_join(temp_dir, path)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w") as fh:
                    fh.write(content)
    elif isinstance(files, dict):
        for path, content in files.items():
            if path and content is not None:
                full = _safe_join(temp_dir, path)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w") as fh:
                    fh.write(content)

    # -- Test files ----------------------------------------------------------
    for path, content in test_files.items():
        if path and content is not None:
            full = _safe_join(temp_dir, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(content)


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

def _detect_framework(test_files: Dict[str, str]) -> str | None:
    """
    Inspect test file names and content to determine the test framework.

    Returns
    -------
    "pytest"    – file uses pytest conventions (assert statements, @pytest.*,
                  pytest imports, or a filename that begins with ``test_``)
    "unittest"  – file subclasses unittest.TestCase
    None        – framework cannot be determined
    """
    for filename, content in test_files.items():
        content = content or ""

        # Explicit import signals are the most reliable indicators
        if "import pytest" in content or "from pytest" in content:
            return "pytest"
        if "import unittest" in content or "from unittest" in content:
            return "unittest"

        # pytest-style bare assert statements with no TestCase class
        has_test_case = "unittest.TestCase" in content
        has_bare_assert = "\n    assert " in content or content.startswith("assert ")
        has_pytest_fixture = "@pytest.fixture" in content or "@pytest.mark" in content

        if has_pytest_fixture or (has_bare_assert and not has_test_case):
            return "pytest"

        if has_test_case:
            return "unittest"

        # Filename convention: test_*.py or *_test.py → lean towards pytest
        name = os.path.basename(filename)
        if name.startswith("test_") or name.endswith("_test.py"):
            return "pytest"

    return None


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def _build_run_cmd(
    test_command: str | None,
    has_requirements: bool,
    test_files: Dict[str, str],
) -> str:
    """
    Build the shell command executed *inside* the container.

    Rules
    -----
    - If *test_command* is provided by the Code Agent, use it as-is.
    - Otherwise, detect the framework from *test_files*:
        pytest    → install pytest, run with --junitxml for machine-readable output.
        unittest  → no extra install needed; run via ``python -m unittest discover``.
        unknown   → raise ValueError so run_code_tests returns a ``setup_error``
                    instead of silently running the wrong tool.
    - Dependency installation output is NOT suppressed so pip errors are visible.
    """
    parts: list[str] = []

    if has_requirements:
        parts.append("pip install -r requirements.txt")   # visible – errors surface

    if test_command:
        # Code Agent explicitly provided a command; trust it.
        parts.append(test_command)
    else:
        framework = _detect_framework(test_files)

        if framework == "pytest":
            parts.append("pip install pytest")
            parts.append(f"pytest --tb=short -v --junitxml={JUNIT_CONTAINER}")

        elif framework == "unittest":
            # unittest ships with Python – no extra install required.
            # -v for verbose output so PASSED/FAILED tokens appear per test.
            parts.append("python -m unittest discover -v")

        else:
            raise ValueError(
                "Cannot determine test framework: no 'import pytest' or "
                "'import unittest' found in test files, and no test_command "
                "was provided by the Code Agent. "
                "Set code_artifact['test_command'] to the exact shell command "
                "to run the tests (e.g. 'pytest --tb=short -v "
                f"--junitxml={JUNIT_CONTAINER}')."
            )

    return " && ".join(parts)


def _build_docker_cmd(temp_dir: str, run_cmd: str) -> list[str]:
    """
    Return the hardened `docker run` command.

    Security flags applied
    ----------------------
    --network none              no network access inside the container
    --memory 512m               RAM limit
    --cpus 1.0                  CPU limit
    --cap-drop ALL              drop all Linux capabilities
    --security-opt no-new-privileges   prevent privilege escalation
    bind-mount temp_dir → /app  writable so pytest can write JUnit XML
    """
    return [
        "docker", "run",
        "--rm",
        "--network",      "none",
        "--memory",       "512m",
        "--cpus",         "1.0",
        "--cap-drop",     "ALL",
        "--security-opt", "no-new-privileges",
        "-v", f"{temp_dir}:/app",
        "-w", "/app",
        DOCKER_IMAGE,
        "bash", "-c", run_cmd,
    ]


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

def _parse_junit(xml_path: str) -> tuple[int, int, int, list[str]]:
    """
    Parse a JUnit XML report.

    Returns (total, passed, failed, error_messages).
    Falls back to (0, 0, 0, [reason]) when the file is absent or malformed.
    """
    if not os.path.exists(xml_path):
        return 0, 0, 0, ["JUnit XML report not produced – tests may not have run."]

    try:
        root  = ET.parse(xml_path).getroot()
        suite = root if root.tag == "testsuite" else (root.find("testsuite") or root)

        total    = int(suite.get("tests",    0))
        errors   = int(suite.get("errors",   0))
        failures = int(suite.get("failures", 0))
        failed   = errors + failures
        passed   = max(total - failed, 0)

        msgs: list[str] = []
        for tc in suite.iter("testcase"):
            for child in tc:
                if child.tag in ("failure", "error"):
                    msgs.append(
                        f"[{child.tag.upper()}] {tc.get('name', 'unknown')}: "
                        f"{(child.text or '').strip()}"
                    )

        return total, passed, failed, msgs

    except ET.ParseError as exc:
        return 0, 0, 0, [f"JUnit XML parse error: {exc}"]


def _parse_stdout_fallback(stdout: str) -> tuple[int, int, int]:
    """Emergency fallback: count PASSED/FAILED tokens in raw pytest stdout."""
    passed = stdout.count("PASSED")
    failed = stdout.count("FAILED") + stdout.count("ERROR")
    return passed + failed, passed, failed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_code_tests(
    files:          Union[List[Dict], Dict],
    test_files:     Dict[str, str],
    test_command:   str  = None,
    timeout_seconds: int = 30,
) -> dict:
    """
    Execute *test_files* against *files* inside a hardened Docker container.

    Parameters
    ----------
    files           : Source code - list of {"path": ..., "content": ...} dicts
                      or a plain -{path: content} mapping.
    test_files      : Test source {path: content} mapping.
    test_command    : Shell command to run instead of the default pytest invocation.
                      Must not rely on host-side resources.
    timeout_seconds : Wall-clock limit for the Docker run.
                      Capped at DOCKER_TIMEOUT_CAP internally.

    Returns
    -------
    dict with the following keys (all present, all typed):

        success          (bool)    - True only if all tests passed
        execution_status (str)     - one of:
                                       "passed"           all tests green
                                       "failed"           one or more tests failed
                                       "timeout"          container exceeded timeout
                                       "docker_unavailable" Docker not running
                                       "setup_error"      file/dependency/import error
                                       "error"            unexpected internal error
        total_tests      (int)
        passed_tests     (int)
        failed_tests     (int)
        errors           (list[str]) -  dep install errors + per-test failure msgs
        raw_output       (str)      -  combined stdout + stderr
        summary          (str)      -  human-readable one-liner
        duration_seconds (float)
    """
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Docker hard requirement – no fallback to local execution
    # ------------------------------------------------------------------
    if not _docker_available():
        return _docker_unavailable_result(time.time() - start_time)

    # ------------------------------------------------------------------
    # 2. Write files to temp directory with path-traversal guard
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as temp_dir:

        try:
            _write_files(files, test_files, temp_dir)
        except ValueError as exc:
            duration = time.time() - start_time
            return {
                "success":          False,
                "execution_status": "setup_error",
                "total_tests":      0,
                "passed_tests":     0,
                "failed_tests":     0,
                "errors":           [str(exc)],
                "raw_output":       "",
                "summary":          "File setup failed – invalid path detected",
                "duration_seconds": round(duration, 2),
            }

        has_requirements = os.path.exists(os.path.join(temp_dir, "requirements.txt"))
        try:
            run_cmd = _build_run_cmd(test_command, has_requirements, test_files)
        except ValueError as exc:
            duration = time.time() - start_time
            return {
                "success":          False,
                "execution_status": "setup_error",
                "total_tests":      0,
                "passed_tests":     0,
                "failed_tests":     0,
                "errors":           [str(exc)],
                "raw_output":       "",
                "summary":          "Test framework could not be determined",
                "duration_seconds": round(duration, 2),
            }
        cmd = _build_docker_cmd(temp_dir, run_cmd)
        effective_timeout = min(timeout_seconds, DOCKER_TIMEOUT_CAP)

        print(f"  [Sandbox] 🐳 Spawning hardened Docker container ({DOCKER_IMAGE})...")
        if has_requirements:
            print("  [Sandbox] Installing dependencies (output visible)...")

        # ------------------------------------------------------------------
        # 3. Run inside Docker
        # ------------------------------------------------------------------
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            stdout     = result.stdout or ""
            stderr     = result.stderr or ""
            returncode = result.returncode

        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            stderr += f"\nExecution timed out after {effective_timeout}s."
            duration = time.time() - start_time
            return {
                "success":          False,
                "execution_status": "timeout",
                "total_tests":      0,
                "passed_tests":     0,
                "failed_tests":     0,
                "errors":           [stderr.strip()],
                "raw_output":       stdout + "\n" + stderr,
                "summary":          f"Test run timed out after {effective_timeout}s",
                "duration_seconds": round(duration, 2),
            }

        except Exception as exc:
            duration = time.time() - start_time
            return {
                "success":          False,
                "execution_status": "error",
                "total_tests":      0,
                "passed_tests":     0,
                "failed_tests":     0,
                "errors":           [str(exc)],
                "raw_output":       "",
                "summary":          "Unexpected error during Docker execution",
                "duration_seconds": round(duration, 2),
            }

        # ------------------------------------------------------------------
        # 4. Parse test results (JUnit XML preferred, stdout fallback)
        # ------------------------------------------------------------------
        host_junit = os.path.join(temp_dir, JUNIT_HOST_NAME)

        if os.path.exists(host_junit):
            total, passed, failed, err_msgs = _parse_junit(host_junit)
            used_xml = True
        else:
            total, passed, failed = _parse_stdout_fallback(stdout)
            err_msgs = []
            used_xml = False

        # If the container crashed before any test ran, count as 1 failure
        if returncode != 0 and total == 0:
            failed = max(failed, 1)
            total  = max(total,  1)

        success = (returncode == 0) and (failed == 0)

        # Determine execution_status
        if success:
            execution_status = "passed"
        elif returncode != 0 and not used_xml and total <= 1 and passed == 0:
            execution_status = "setup_error"
        else:
            execution_status = "failed"

        # Collect errors: stderr (dep install failures visible here) + per-test msgs
        all_errors: list[str] = []
        if stderr.strip():
            all_errors.append(stderr.strip())
        all_errors.extend(err_msgs)

        duration = time.time() - start_time

        summary = (
            f"{passed}/{total} tests passed"
            if total > 0
            else ("All tests passed" if success else "Test execution failed")
        )

        return {
            "success":          success,
            "execution_status": execution_status,
            "total_tests":      total,
            "passed_tests":     passed,
            "failed_tests":     failed,
            "errors":           all_errors,
            "raw_output":       stdout + ("\n" + stderr if stderr.strip() else ""),
            "summary":          summary,
            "duration_seconds": round(duration, 2),
        }
