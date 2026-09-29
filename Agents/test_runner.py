import tempfile
import os
import subprocess
import time
from typing import Dict, List, Union

def run_code_tests(files: Union[List[Dict], Dict], test_files: Dict[str, str], test_command: str = None, timeout_seconds: int = 30) -> dict:
    """
    Executes the provided code and test files in a secure, isolated Docker container.
    Returns structured results including stdout/stderr, pass/fail status, and duration.
    """
    start_time = time.time()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Write the source code files to the temp directory
        if isinstance(files, list):
            for f in files:
                path = f.get("path")
                content = f.get("content")
                if path and content:
                    full_path = os.path.join(temp_dir, path)
                    os.makedirs(os.path.dirname(full_path), exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as out_f:
                        out_f.write(content)
        elif isinstance(files, dict):
            for path, content in files.items():
                full_path = os.path.join(temp_dir, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as out_f:
                    out_f.write(content)
                    
        # 2. Write the AI-generated test files
        for path, content in test_files.items():
            full_path = os.path.join(temp_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as out_f:
                out_f.write(content)

        # 3. Check if Docker is available on host
        has_docker = False
        try:
            has_docker = subprocess.run(["docker", "--version"], capture_output=True).returncode == 0
        except (FileNotFoundError, Exception):
            has_docker = False
        
        # 4. Construct command and execute tests
        def _is_executable_test_cmd(cmd_val) -> bool:
            if not cmd_val:
                return False
            if isinstance(cmd_val, list):
                if not cmd_val:
                    return False
                first = str(cmd_val[0]).strip().lower()
            else:
                s = str(cmd_val).strip()
                if any(phrase in s.lower() for phrase in ("no automated", "not required", "manual", "open in browser", "open index", "verify by", "n/a", "none")):
                    return False
                parts = s.split()
                if not parts:
                    return False
                first = parts[0].lower()
            valid_starters = ("pytest", "python", "python3", "node", "npm", "npx", "yarn", "vitest", "jest", "unittest")
            return any(first == v or first.endswith(v) for v in valid_starters)

        try:
            if has_docker:
                run_cmd = ""
                if os.path.exists(os.path.join(temp_dir, "requirements.txt")):
                    print("  [Sandbox] Installing dependencies from requirements.txt...")
                    run_cmd += "pip install -r requirements.txt > /dev/null 2>&1 && "
                if _is_executable_test_cmd(test_command):
                    run_cmd += test_command if isinstance(test_command, str) else " ".join(test_command)
                else:
                    print("  [Sandbox] Preparing pytest environment...")
                    run_cmd += "pip install pytest > /dev/null 2>&1 && pytest --tb=short"

                print("  [Sandbox] 🐳 Spawning secure Docker container (python:3.11-slim)...")
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{temp_dir}:/app",
                    "-w", "/app",
                    "python:3.11-slim",
                    "bash", "-c", run_cmd
                ]
                cwd = None
            else:
                # Local fallback execution
                import sys
                if os.path.exists(os.path.join(temp_dir, "requirements.txt")):
                    print("  [Sandbox] Installing dependencies from requirements.txt...")
                    try:
                        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=temp_dir, timeout=60)
                    except Exception:
                        pass

                if _is_executable_test_cmd(test_command):
                    parts = test_command if isinstance(test_command, list) else test_command.split()
                    if parts[0] in ("python", "python3"):
                        cmd = [sys.executable] + parts[1:]
                    elif parts[0] == "pytest":
                        cmd = [sys.executable, "-m", "pytest"] + parts[1:]
                    else:
                        cmd = parts
                else:
                    cmd = [sys.executable, "-m", "pytest", "--tb=short"]
                cwd = temp_dir
                
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout.decode() if e.stdout else ""
            stderr = e.stderr.decode() if e.stderr else f"Execution timed out after {timeout_seconds}s"
            returncode = 124
        except Exception as e:
            stdout = ""
            stderr = str(e)
            returncode = 1
            
        # 6. Parse and format the results for the ReviewAgent
        duration = time.time() - start_time
        success = returncode == 0
        
        # Metric parsing based on pytest output text
        import re
        m_passed = re.search(r'(\d+)\s+passed\b', stdout, re.IGNORECASE)
        m_failed = re.search(r'(\d+)\s+failed\b', stdout, re.IGNORECASE)
        m_errors = re.search(r'(\d+)\s+error(?:s)?\b', stdout, re.IGNORECASE)

        passed_tests = int(m_passed.group(1)) if m_passed else stdout.count("PASSED")
        failed_tests = (int(m_failed.group(1)) if m_failed else 0) + (int(m_errors.group(1)) if m_errors else 0)
        if not m_failed and not m_errors:
            failed_tests += stdout.count("FAILED") + stdout.count("ERROR")
        total_tests = passed_tests + failed_tests

        # Ensure failures are logged if the run crashed completely
        if not success and total_tests == 0:
            failed_tests = 1
            total_tests = 1
            
        return {
            "success": success,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "errors": [stderr] if stderr else [],
            "raw_output": stdout + "\n" + stderr,
            "summary": "Tests passed successfully" if success else "Test execution failed",
            "duration_seconds": round(duration, 2)
        }
