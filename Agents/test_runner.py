"""
test_runner.py
==============
Executes supported AI-generated code and tests in a hardened, isolated Docker container.

Security guarantees
-------------------
- AI-generated code is NEVER executed directly on the host.
- If Docker is unavailable, execution is refused and a structured failure is returned.
- Docker container runs with:
    --network none
    --memory 512m           (RAM cap)
    --cpus 1.0              (CPU cap)
    --cap-drop ALL          (drop all Linux capabilities)
    --security-opt no-new-privileges
- Source files are bind-mounted read/write inside the isolated container.
- All user-supplied file paths are validated to prevent path-traversal attacks.

Parsing strategy
----------------
1. Node's test summary → deterministic count parsing
2. stdout token count → PASSED / FAILED fallback

Public API
----------
run_code_tests(files, test_files, test_command=None, timeout_seconds=30) -> dict
"""

import os
import re
import shlex
import subprocess
import tempfile
import time
from typing import Dict, List, Union

from test_stacks import TEST_STACKS, resolve_test_stack

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DOCKER_TIMEOUT_CAP = 300           # hard upper bound for the TEST phase

RUNTIME_IMAGES = {key: stack.runtime_image for key, stack in TEST_STACKS.items()}


def _detect_docker_image(files: Union[List[Dict], Dict], test_files: Dict[str, str]) -> str:
    """Choose one of the supported test runtimes from generated project files."""
    return resolve_test_stack(files).runtime_image


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
    """Return the supported framework matching the supplied test file."""
    for filename, content in test_files.items():
        fn_lower = filename.lower()
        if fn_lower.endswith((".c", ".cpp", ".cc", ".cxx")):
            return "c"
        if fn_lower.endswith((".js", ".mjs", ".cjs")):
            return "node"
    return None


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------

def _build_run_cmd(
    test_command: str | None,
    test_files: Dict[str, str],
    source_files: list[str] | None = None,
    source_contents: Dict[str, str] | None = None,
) -> str:
    """
    Build the shell command executed *inside* the container.
    """
    framework = _detect_framework(test_files)
    if framework == "node":
        stack = TEST_STACKS["javascript"]
        if test_command not in (None, stack.test_command):
            raise ValueError("Custom JavaScript test commands are not supported.")
        if stack.test_filename not in test_files:
            raise ValueError(f"JavaScript test suite must include {stack.test_filename}.")
        return stack.test_command
    if framework == "c":
        if test_command:
            raise ValueError("Custom C/C++ test commands are not supported.")
        project_sources = [
            fn for fn in (source_files or [])
            if fn.lower().endswith((".c", ".cpp", ".cc", ".cxx"))
            and not re.search(r"\bmain\s*\(", (source_contents or {}).get(fn, ""))
        ]
        test_sources = [fn for fn in test_files if fn.lower().endswith((".c", ".cpp", ".cc", ".cxx"))]
        if not test_sources:
            raise ValueError("C/C++ test suite must include a C/C++ test harness.")
        compile_sources = sorted(set(project_sources + test_sources))
        compile_list = " ".join(shlex.quote(path) for path in compile_sources)
        include_dirs = {"/app"}
        include_dirs.update(
            f"/app/{os.path.dirname(path)}"
            for path in [*(source_files or []), *test_files.keys()]
            if os.path.dirname(path)
        )
        include_flags = " ".join(f"-I {shlex.quote(path)}" for path in sorted(include_dirs))
        compiler = "g++" if any(path.lower().endswith((".cpp", ".cc", ".cxx")) for path in compile_sources) else "gcc"
        standard = "-std=c++17" if compiler == "g++" else "-std=c11"
        return (
            f"{compiler} {standard} -Wall -Wextra {include_flags} "
            f"-o /tmp/test_binary {compile_list} && /tmp/test_binary"
        )
    raise ValueError("Test framework could not be determined for a supported JavaScript, C, or C++ project.")


def _build_docker_cmd(temp_dir: str, run_cmd: str, docker_image: str, network: bool = True) -> list[str]:
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
        "-e", "npm_config_cache=/tmp/.npm",
        "-v", f"{temp_dir}:/app",
        "-w", "/app",
        docker_image,
        shell, "-c", run_cmd,
    ]
    return cmd


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

def _parse_stdout_fallback(stdout: str) -> tuple[int, int, int]:
    """Parse test counts from Node.js node:test summary output."""
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
    """Run JavaScript, C, or C++ tests in an isolated Docker container."""
    start_time = time.time()

    def _early(status: str, summary: str, errors: list[str], raw: str = "") -> dict:
        return {
            "success": False,
            "execution_status": status,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "errors": errors,
            "raw_output": raw,
            "summary": summary,
            "duration_seconds": round(time.time() - start_time, 2),
        }

    try:
        stack = resolve_test_stack(files)
        docker_image = stack.runtime_image
    except ValueError as exc:
        return _early("unsupported_stack", "Unsupported generated project stack", [str(exc)])

    if test_command not in (None, stack.test_command):
        return _early(
            "command_rejected",
            "Custom test commands are not supported",
            ["The runner only executes the test command configured for the detected project stack."],
        )

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

        effective_timeout = min(timeout_seconds, DOCKER_TIMEOUT_CAP)

        source_paths = [
            entry.get("path") if isinstance(entry, dict) else str(entry)
            for entry in (files if isinstance(files, list) else [])
        ]
        source_paths.extend(key for key in (files if isinstance(files, dict) else {}))
        source_paths = sorted(set(path for path in source_paths if path))
        source_contents = {
            entry.get("path"): entry.get("content", "")
            for entry in (files if isinstance(files, list) else [])
            if isinstance(entry, dict) and entry.get("path")
        }
        if isinstance(files, dict):
            source_contents.update(files)
        try:
            run_cmd = _build_run_cmd(stack.test_command, test_files, source_paths, source_contents)
        except ValueError as exc:
            return _early("setup_error", "Test framework could not be determined", [str(exc)])

        print(f"  [Sandbox] Running tests in isolated Docker container ({docker_image}, network off)...")
        cmd = _build_docker_cmd(temp_dir, run_cmd, docker_image=docker_image, network=False)

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
        # 4. Parse Node test output; native C/C++ harnesses are counted as one suite.
        # ------------------------------------------------------------------
        total, passed, failed = _parse_stdout_fallback(stdout)
        if total == 0 and docker_image in (RUNTIME_IMAGES["c"], RUNTIME_IMAGES["cpp"]):
            total, passed, failed = (1, 1, 0) if returncode == 0 else (1, 0, 1)

        # If the container crashed before any test ran, count as 1 failure
        if returncode != 0 and total == 0:
            failed = max(failed, 1)
            total  = max(total,  1)

        success = (returncode == 0) and (failed == 0)

        # Determine execution_status
        if success:
            execution_status = "passed"
        elif returncode != 0 and total <= 1 and passed == 0:
            execution_status = "setup_error"
        else:
            execution_status = "failed"

        # Collect errors: stderr (visible on failure) + per-test msgs
        all_errors: list[str] = []
        if not success and stderr.strip():
            all_errors.append(stderr.strip())

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