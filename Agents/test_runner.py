import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


# Whitelist of safe environment variables to pass into test subprocess
# Strictly avoids leaking sensitive API keys (e.g. OPENROUTER_API_KEY) or system secrets
SAFE_ENV_VARS = {
    "PATH",
    "PYTHONPATH",
    "LANG",
    "LC_ALL",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "VIRTUAL_ENV",
}


def get_sanitized_env() -> dict[str, str]:
    """
    Builds a clean environment dictionary for subprocess execution,
    ensuring that secrets, tokens, and API keys are not exposed to the test runner.
    """
    sanitized = {}
    for key in SAFE_ENV_VARS:
        val = os.environ.get(key)
        if val is not None:
            sanitized[key] = val

    # Ensure current python executable path is available in PATH
    py_dir = str(Path(sys.executable).parent)
    current_path = sanitized.get("PATH", "")
    if py_dir not in current_path:
        sanitized["PATH"] = f"{py_dir}:{current_path}" if current_path else py_dir

    return sanitized


def run_code_tests(
    files: dict[str, str],
    test_files: Optional[dict[str, str]] = None,
    test_command: Optional[str] = None,
    timeout_seconds: int = 30,
    max_output_chars: int = 8000,
) -> dict:
    """
    Secure Test Runner Tool:
    1. Sets up an isolated temporary workspace directory.
    2. Writes code files and independent test files into the workspace.
    3. Executes the test suite in a sandboxed subprocess with:
       - Stripped/sanitized environment (no API keys or credentials leaked).
       - Hard execution timeout (prevents infinite loops / hanging).
    4. Parses stdout/stderr and returns a structured result dictionary.
    """
    start_time = time.time()
    all_files = dict(files)
    if test_files:
        all_files.update(test_files)

    with tempfile.TemporaryDirectory(prefix="agent_test_sandbox_") as sandbox_dir:
        sandbox_path = Path(sandbox_dir)

        # 1. Write all files to the temporary sandbox
        for rel_path, content in all_files.items():
            file_path = sandbox_path / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

        # 2. Determine command to execute
        # Default fallback: try python -m unittest discover or pytest
        if test_command:
            cmd = test_command.split()
        else:
            # Check if any test file starts with test_
            cmd = [sys.executable, "-m", "unittest", "discover", "-s", ".", "-p", "test*.py"]

        # Ensure command uses the current python interpreter if it references python
        if cmd and cmd[0] in ("python", "python3"):
            cmd[0] = sys.executable

        env = get_sanitized_env()
        # Add sandbox to PYTHONPATH so tests can import modules directly
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{sandbox_dir}:{existing_pythonpath}" if existing_pythonpath else sandbox_dir

        try:
            completed = subprocess.run(
                cmd,
                cwd=sandbox_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            raw_stdout = completed.stdout or ""
            raw_stderr = completed.stderr or ""
            exit_code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as e:
            raw_stdout = e.stdout or ""
            raw_stderr = f"Execution timed out after {timeout_seconds} seconds."
            exit_code = -1
            timed_out = True
        except Exception as e:
            raw_stdout = ""
            raw_stderr = f"Execution error: {str(e)}"
            exit_code = -1
            timed_out = False

        duration = round(time.time() - start_time, 2)

        # 3. Truncate outputs to avoid huge token costs or buffer overflows
        combined_output = f"{raw_stdout}\n{raw_stderr}".strip()
        if len(combined_output) > max_output_chars:
            combined_output = (
                combined_output[: max_output_chars // 2]
                + "\n... [output truncated for brevity] ...\n"
                + combined_output[-max_output_chars // 2 :]
            )

        # 4. Parse test results
        is_success = (exit_code == 0) and not timed_out
        total_tests, passed_tests, failed_tests, errors = _parse_test_metrics(
            raw_stdout, raw_stderr, is_success
        )

        return {
            "success": is_success,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "errors": errors,
            "raw_output": combined_output,
            "duration_seconds": duration,
            "summary": _build_summary(is_success, total_tests, passed_tests, failed_tests, timed_out),
        }


def _parse_test_metrics(stdout: str, stderr: str, is_success: bool) -> tuple[int, int, int, list[str]]:
    """
    Extracts pass/fail counts and tracebacks from standard unittest / pytest outputs.
    """
    text = f"{stdout}\n{stderr}"
    errors = []

    # Heuristic parsing for unittest / pytest
    total = 0
    passed = 0
    failed = 0

    lines = text.splitlines()
    for line in lines:
        line_clean = line.strip()
        # unittest style: "Ran 5 tests in 0.002s"
        if line_clean.startswith("Ran ") and "test" in line_clean:
            parts = line_clean.split()
            try:
                total = int(parts[1])
            except (IndexError, ValueError):
                pass
        # unittest style: "FAILED (failures=2, errors=1)"
        if "FAILED (" in line_clean or "OK" in line_clean:
            if "OK" in line_clean and is_success:
                passed = total
                failed = 0
            elif "FAILED" in line_clean:
                if "failures=" in line_clean:
                    try:
                        f_part = line_clean.split("failures=")[1].split(",")[0].rstrip(")")
                        failed += int(f_part)
                    except (IndexError, ValueError):
                        pass
                if "errors=" in line_clean:
                    try:
                        e_part = line_clean.split("errors=")[1].split(",")[0].rstrip(")")
                        failed += int(e_part)
                    except (IndexError, ValueError):
                        pass
                passed = max(0, total - failed)

        # Record FAIL/ERROR lines
        if line_clean.startswith("FAIL:") or line_clean.startswith("ERROR:"):
            errors.append(line_clean)

    if total == 0:
        total = 1 if is_success else 1
        passed = 1 if is_success else 0
        failed = 0 if is_success else 1

    return total, passed, failed, errors


def _build_summary(
    is_success: bool, total: int, passed: int, failed: int, timed_out: bool
) -> str:
    if timed_out:
        return f"Test run timed out. Execution was halted for safety."
    if is_success:
        return f"All {total} tests passed successfully."
    return f"Test suite failed: {failed}/{total} test(s) failed or encountered errors."
