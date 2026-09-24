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
                    with open(full_path, "w") as out_f:
                        out_f.write(content)
        elif isinstance(files, dict):
            for path, content in files.items():
                full_path = os.path.join(temp_dir, path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w") as out_f:
                    out_f.write(content)
                    
        # 2. Write the AI-generated test files
        for path, content in test_files.items():
            full_path = os.path.join(temp_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as out_f:
                out_f.write(content)

        # 3. Check if Docker is available on host
        has_docker = subprocess.run(["docker", "--version"], capture_output=True).returncode == 0
        
        # 4. Construct the test execution command
        run_cmd = ""
        # If the CodeAgent provided dependencies, install them quietly first
        if os.path.exists(os.path.join(temp_dir, "requirements.txt")):
            run_cmd += "pip install -r requirements.txt > /dev/null 2>&1 && "
            
        if test_command:
            run_cmd += test_command
        else:
            # Default to pytest
            run_cmd += "pip install pytest > /dev/null 2>&1 && pytest --tb=short"
            
        # 5. Run the tests in Docker sandbox (or fallback to subprocess)
        try:
            if has_docker:
                # Secure Docker isolation
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{temp_dir}:/app",
                    "-w", "/app",
                    "python:3.11-slim",
                    "bash", "-c", run_cmd
                ]
            else:
                # Fallback to local subprocess execution
                cmd = ["bash", "-c", run_cmd]
                
            result = subprocess.run(
                cmd,
                cwd=temp_dir if not has_docker else None,
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
        
        # Very simple metric parsing based on pytest output text
        passed_tests = stdout.count("PASSED")
        failed_tests = stdout.count("FAILED") + stdout.count("ERROR")
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
