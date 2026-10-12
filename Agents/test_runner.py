"""
test_runner.py
==============
Executes AI-generated code and tests in a hardened, isolated Docker container.

Security guarantees
-------------------
- AI-generated code is NEVER executed directly on the host.
- If Docker is unavailable, execution is refused and a structured failure is returned.
- Docker container runs with:
    --network none          (test phase for Python; install phase needs network)
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
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Union

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DOCKER_IMAGE       = "python:3.11-slim"
DOCKER_TIMEOUT_CAP = 300           # hard upper bound for the TEST phase
INSTALL_TIMEOUT    = 240           # separate budget for pip install (has network)
JUNIT_CONTAINER    = "/app/test-results.xml"
JUNIT_HOST_NAME    = "test-results.xml"

RUNTIME_IMAGES = {
    "python": "python:3.11-slim",
    "go": "golang:1.22-alpine",
    "java": "eclipse-temurin:17-jdk-alpine",
    "node": "node:20-slim",
    "rust": "rust:1.77-slim",
    "c": "gcc:13",
}

def _detect_docker_image(files: Union[List[Dict], Dict], test_files: Dict[str, str]) -> str:
    """Dynamically determine the runtime container based on file extensions and manifests."""
    source_paths: list[str] = []
    if isinstance(files, list):
        for f in files:
            source_paths.append(f.get("path", "").lower())
    elif isinstance(files, dict):
        source_paths.extend(k.lower() for k in files.keys())

    # Check source code files first
    if any(p.endswith(".go") or p == "go.mod" for p in source_paths):
        return RUNTIME_IMAGES["go"]
    if any(p.endswith((".java", ".jar")) or p in ("pom.xml", "build.gradle") for p in source_paths):
        return RUNTIME_IMAGES["java"]
    if any(p.endswith((".c", ".h")) for p in source_paths):
        return RUNTIME_IMAGES["c"]
    if any(p.endswith((".ts", ".tsx", ".js", ".jsx", ".html")) or p == "package.json" for p in source_paths):
        if not any(p.endswith(".py") for p in source_paths):
            return RUNTIME_IMAGES["node"]
    if any(p.endswith(".rs") or p == "cargo.toml" for p in source_paths):
        return RUNTIME_IMAGES["rust"]
    if any(p.endswith(".py") for p in source_paths):
        return RUNTIME_IMAGES["python"]

    # Fallback to test files
    test_paths = [k.lower() for k in test_files.keys()]
    if any(p.endswith(".go") for p in test_paths):
        return RUNTIME_IMAGES["go"]
    if any(p.endswith((".js", ".jsx", ".ts", ".tsx")) for p in test_paths):
        return RUNTIME_IMAGES["node"]

    return RUNTIME_IMAGES["python"]


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
    "go"        – Go testing package (_test.go)
    "junit"     – Java JUnit test (test.java)
    "node"      – JavaScript / TypeScript test (.test.js, .spec.js, etc.)
    "pytest"    – pytest conventions (assert statements, @pytest.*, test_*.py)
    "unittest"  – unittest.TestCase
    None        – framework cannot be determined
    """
    for filename, content in test_files.items():
        content = content or ""
        fn_lower = filename.lower()

        # Polyglot test frameworks
        if fn_lower.endswith("_test.go") or 'import "testing"' in content:
            return "go"
        if fn_lower.endswith("test.java") or "@Test" in content or "org.junit" in content:
            return "junit"
        if any(fn_lower.endswith(ext) for ext in (".test.js", ".spec.js", ".test.ts", ".spec.ts")) or "describe(" in content:
            return "node"

        # Python frameworks
        if "import pytest" in content or "from pytest" in content:
            return "pytest"
        if "import unittest" in content or "from unittest" in content:
            return "unittest"

        has_test_case = "unittest.TestCase" in content
        has_bare_assert = "\n    assert " in content or content.startswith("assert ")
        has_pytest_fixture = "@pytest.fixture" in content or "@pytest.mark" in content

        if has_pytest_fixture or (has_bare_assert and not has_test_case):
            return "pytest"

        if has_test_case:
            return "unittest"

        if fn_lower.startswith("test_") or fn_lower.endswith("_test.py"):
            return "pytest"

    return None


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def _build_run_cmd(
    test_command: str | None,
    has_requirements: bool,
    test_files: Dict[str, str],
    source_files: list[str] | None = None,
) -> str:
    """
    Build the shell command executed *inside* the container.
    """
    parts: list[str] = []

    if has_requirements:
        parts.append("pip install -r requirements.txt")

    if test_command:
        parts.append(test_command)
    else:
        framework = _detect_framework(test_files)

        if framework == "pytest":
            parts.append("pip install pytest")
            parts.append(f"pytest --tb=short -v --junitxml={JUNIT_CONTAINER}")
        elif framework == "unittest":
            parts.append("python -m unittest discover -v")
        elif framework == "go":
            parts.append("go test -v ./...")
        elif framework == "node":
            node_test_files = [fn for fn in test_files.keys() if fn.endswith((".js", ".mjs", ".cjs", ".ts"))]
            if node_test_files:
                parts.append(f"node --test {' '.join(node_test_files)}")
            else:
                parts.append("node --test")
        elif framework == "junit":
            parts.append("mvn test")
        elif framework == "c":
            project_sources = [
                fn for fn in (source_files or [])
                if fn.endswith(".c") and not fn.endswith("main.c")
            ]
            compile_sources = sorted(set(project_sources + [fn for fn in test_files.keys() if fn.endswith(".c")]))
            if not compile_sources:
                compile_sources = sorted(fn for fn in test_files.keys() if fn.endswith(".c"))
            compile_list = " ".join(compile_sources)
            parts.append(f"gcc -std=c11 -Wall -Wextra -Werror -I/app -o /tmp/test_binary {compile_list} && /tmp/test_binary")
        else:
            js_files = [fn for fn in test_files.keys() if fn.endswith((".js", ".mjs", ".cjs"))]
            if js_files:
                parts.append(f"node --test {' '.join(js_files)}")
            else:
                parts.append("python -m unittest discover -v")

    return " && ".join(parts)


def _build_docker_cmd(temp_dir: str, run_cmd: str, docker_image: str = DOCKER_IMAGE, network: bool = True) -> list[str]:
    """
    Return the hardened `docker run` command.

    Runs as the host user (when available) so files in the bind mount stay readable/removable
    (with --cap-drop ALL, root inside the container cannot read a 0700 host temp dir).
    """
    shell = "sh" if "alpine" in docker_image else "bash"
    cmd = [
        "docker", "run", "--rm",
        "--memory", "512m",
        "--cpus", "1.0",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
    ]
    if not network:
        cmd += ["--network", "none"]
    if hasattr(os, "getuid"):
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd += [
        "-e", "HOME=/tmp",
        "-e", "GOCACHE=/tmp/.gocache",
        "-e", "npm_config_cache=/tmp/.npm",
        "-e", "PIP_DISABLE_PIP_VERSION_CHECK=1",
        "-v", f"{temp_dir}:/app",
        "-w", "/app",
        docker_image,
        shell, "-c", run_cmd,
    ]
    return cmd


def _python_test_cmd(test_command: str | None) -> str:
    """
    Normalise any pytest-ish command to: python -m pytest <args> --junitxml=...
    - `python -m` puts the project root on sys.path (so `import app` works)
    - --junitxml gives exact counts instead of fragile stdout scraping
    """
    env = "export PYTHONPATH=/app/.deps:/app PYTHONDONTWRITEBYTECODE=1 && "
    cmd = (test_command or "").strip()
    m = re.search(r"pytest\b(.*)$", cmd) if cmd else None
    if cmd and not m:                      # unittest or a custom command
        return env + cmd
    args = m.group(1) if m else " --tb=short -v"
    if "--junitxml" not in args:
        args += f" --junitxml={JUNIT_CONTAINER}"
    return f"{env}python -m pytest{args} -p no:cacheprovider"


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
        if root.tag == "testsuite":
            suite = root
        else:
            found = root.find("testsuite")
            suite = found if found is not None else root

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
    """Parse test counts from standard test runner outputs (pytest, unittest, node --test, go test)."""
    # 1. Node.js node:test summary lines: "ℹ pass 3", "# pass 3", "ℹ fail 0"
    pass_match = re.search(r"(?:#|ℹ)?\s*pass(?:ed)?\s+(\d+)", stdout, re.IGNORECASE)
    fail_match = re.search(r"(?:#|ℹ)?\s*fail(?:ed)?\s+(\d+)", stdout, re.IGNORECASE)
    if pass_match or fail_match:
        passed = int(pass_match.group(1)) if pass_match else 0
        failed = int(fail_match.group(1)) if fail_match else 0
        return passed + failed, passed, failed

    # 2. Node TAP lines: "ok 1 - ...", "not ok 2 - ..."
    ok_count = len(re.findall(r"^ok\s+\d+", stdout, re.MULTILINE))
    not_ok_count = len(re.findall(r"^not ok\s+\d+", stdout, re.MULTILINE))
    if ok_count > 0 or not_ok_count > 0:
        return ok_count + not_ok_count, ok_count, not_ok_count

    # 3. Python unittest: "Ran 3 tests in ...", "OK", "FAILED (failures=1)"
    ran_match = re.search(r"Ran\s+(\d+)\s+tests?", stdout)
    if ran_match:
        total = int(ran_match.group(1))
        fails = 0
        err_m = re.search(r"failures=(\d+)", stdout)
        if err_m:
            fails += int(err_m.group(1))
        err_e = re.search(r"errors=(\d+)", stdout)
        if err_e:
            fails += int(err_e.group(1))
        passed = max(total - fails, 0)
        return total, passed, fails

    # 4. Pytest summary line: "== 2 failed, 3 passed, 1 error in 0.5s =="
    p = re.search(r"(\d+)\s+passed", stdout)
    f = re.search(r"(\d+)\s+failed", stdout)
    e = re.search(r"(\d+)\s+errors?\b", stdout)
    if p or f or e:
        passed = int(p.group(1)) if p else 0
        failed = (int(f.group(1)) if f else 0) + (int(e.group(1)) if e else 0)
        return passed + failed, passed, failed

    # 5. Go test: "--- PASS:", "--- FAIL:"
    go_pass = stdout.count("--- PASS:")
    go_fail = stdout.count("--- FAIL:")
    if go_pass + go_fail > 0:
        return go_pass + go_fail, go_pass, go_fail

    return 0, 0, 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_code_tests(
    files:          Union[List[Dict], Dict],
    test_files:     Dict[str, str],
    test_command:   str | None = None,
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
        docker_image = _detect_docker_image(files, test_files)
        is_python = docker_image == RUNTIME_IMAGES["python"]
        effective_timeout = min(timeout_seconds, DOCKER_TIMEOUT_CAP)

        def _early(status: str, summary: str, errors: list[str], raw: str = "") -> dict:
            return {
                "success": False, "execution_status": status,
                "total_tests": 0, "passed_tests": 0, "failed_tests": 0,
                "errors": errors, "raw_output": raw, "summary": summary,
                "duration_seconds": round(time.time() - start_time, 2),
            }

        if is_python:
            # Phase 1 (network ON): install deps + the test tooling into /app/.deps.
            # pytest/httpx are ALWAYS installed: the generated requirements.txt rarely lists them,
            # and FastAPI/Starlette TestClient needs httpx.
            reqs = "-r requirements.txt " if has_requirements else ""
            install_cmd = f"pip install -q --no-cache-dir --target /app/.deps {reqs}pytest httpx"
            print(f"  [Sandbox] Phase 1/2: installing dependencies ({docker_image}, network on)...")
            try:
                ir = subprocess.run(
                    _build_docker_cmd(temp_dir, install_cmd, docker_image, network=True),
                    capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return _early("setup_error", f"Dependency install timed out after {INSTALL_TIMEOUT}s",
                              [f"pip install did not finish in {INSTALL_TIMEOUT}s (check requirements.txt)."])
            if ir.returncode != 0:
                log = ((ir.stderr or "") + (ir.stdout or "")).strip()
                return _early("setup_error", "Dependency install failed",
                              [f"[DEPENDENCY] pip install failed (requirements.txt problem): {log[-1500:]}"],
                              raw=log)
            run_cmd = _python_test_cmd(test_command)
            network = False          # Phase 2: AI-generated code runs with NO network
            print("  [Sandbox] Phase 2/2: running tests (network off)...")
        else:
            try:
                source_paths = [
                    entry.get("path") if isinstance(entry, dict) else str(entry)
                    for entry in (files if isinstance(files, list) else [])
                ]
                source_paths.extend(
                    key for key in (files if isinstance(files, dict) else {})
                )
                source_paths = sorted(set(p for p in source_paths if p))
                run_cmd = _build_run_cmd(test_command, has_requirements, test_files, source_paths)
            except ValueError as exc:
                return _early("setup_error", "Test framework could not be determined", [str(exc)])
            network = False
            print(f"  [Sandbox] Phase 1/2: installing dependencies ({docker_image}, network on)...")
            if docker_image == RUNTIME_IMAGES["c"]:
                print("  [Sandbox] Phase 2/2: running tests (network off)...")
            else:
                print(f"  [Sandbox] Spawning Docker container ({docker_image})...")

        cmd = _build_docker_cmd(temp_dir, run_cmd, docker_image=docker_image, network=network)

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

        # Collect errors: stderr (visible on failure) + per-test msgs
        all_errors: list[str] = []
        if not success and stderr.strip():
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