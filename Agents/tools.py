"""
tools.py - Agent tools for the IdeaToProduct pipeline.

Tools:
  - repo_scaffold(project_id, files) → writes generated files to disk
  - market_check(idea)               → placeholder for market grounding
  - test_runner(project_path)        → placeholder for test execution
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

from langchain_core.tools import tool


# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "generated_projects"


# ──────────────────────────────────────────────────────────────────────────────
# repo_scaffold
# ──────────────────────────────────────────────────────────────────────────────

@tool
def repo_scaffold(project_id: str, files: list[dict]) -> dict:
    """
    Writes a list of files to disk under generated_projects/<project_id>/.

    Each file dict must have:
        path    : relative file path (e.g. 'src/main.py')
        content : the file content as a string

    Returns a summary dict with the project path and list of written files.
    """
    project_dir = WORKSPACE_ROOT / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for file_spec in files:
        rel_path = file_spec.get("path", "").lstrip("/")
        content  = file_spec.get("content", "")

        if not rel_path:
            continue

        abs_path = project_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(content, encoding="utf-8")
        written.append(rel_path)

    # Write a manifest
    manifest = {
        "project_id":   project_id,
        "generated_at": datetime.utcnow().isoformat(),
        "files":        written,
    }
    (project_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    return {
        "project_path": str(project_dir),
        "files_written": written,
        "file_count": len(written),
    }


# ──────────────────────────────────────────────────────────────────────────────
# test_runner
# ──────────────────────────────────────────────────────────────────────────────

@tool
def test_runner(project_path: str) -> dict:
    """
    Runs pytest inside the given project directory and returns results.

    Returns a dict with:
        passed   : number of tests passed
        failed   : number of tests failed
        errors   : number of errors
        output   : raw pytest output (truncated to 4000 chars)
        status   : 'pass' | 'fail' | 'error' | 'no_tests'
    """
    path = Path(project_path)
    if not path.exists():
        return {"status": "error", "output": f"Path not found: {project_path}",
                "passed": 0, "failed": 0, "errors": 1}

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "--tb=short", "-q", str(path)],
            capture_output=True, text=True, timeout=60
        )
        output = (result.stdout + result.stderr)[:4000]

        # Parse summary line  e.g. "3 passed, 1 failed"
        passed = failed = errors = 0
        for line in output.splitlines():
            if "passed" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "passed" and i > 0:
                        try: passed = int(parts[i - 1])
                        except ValueError: pass
                    if p == "failed" and i > 0:
                        try: failed = int(parts[i - 1])
                        except ValueError: pass
                    if p == "error" in p and i > 0:
                        try: errors = int(parts[i - 1])
                        except ValueError: pass

        status = "pass" if failed == 0 and errors == 0 and passed > 0 else \
                 "no_tests" if passed == 0 and failed == 0 else "fail"

        return {"status": status, "passed": passed, "failed": failed,
                "errors": errors, "output": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "Test run timed out (60s)",
                "passed": 0, "failed": 0, "errors": 1}
    except Exception as e:
        return {"status": "error", "output": str(e),
                "passed": 0, "failed": 0, "errors": 1}


# ──────────────────────────────────────────────────────────────────────────────
# market_check  (stub — will be grounded with Kaggle dataset in Phase 3)
# ──────────────────────────────────────────────────────────────────────────────

@tool
def market_check(idea: str) -> dict:
    """
    Evaluates a product idea against startup market signals.

    Returns a dict with:
        viability_score : 0-10
        similar_products: list of similar known products
        risks           : list of market risks
        opportunities   : list of opportunities
        verdict         : 'viable' | 'risky' | 'saturated'
    """
    # Phase 3 will connect this to the Kaggle Startup Success Prediction dataset
    # and GH Archive issue data. For now, returns a structured placeholder.
    return {
        "viability_score": 7,
        "similar_products": [
            "Shopify", "WooCommerce", "BigCommerce"
        ],
        "risks": [
            "Highly competitive market",
            "High customer acquisition cost",
            "Payment gateway complexity"
        ],
        "opportunities": [
            "Niche market differentiation possible",
            "Mobile-first shopping trend",
            "Headless commerce demand growing"
        ],
        "verdict": "viable",
        "note": "Stub result — Phase 3 will ground this with Kaggle dataset."
    }
