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

        # Parse summary line e.g. "4 passed, 1 warning in 0.58s" or "3 passed, 1 failed"
        import re
        m_passed = re.search(r'(\d+)\s+passed\b', output)
        m_failed = re.search(r'(\d+)\s+failed\b', output)
        m_errors = re.search(r'(\d+)\s+error(?:s)?\b', output)

        passed = int(m_passed.group(1)) if m_passed else 0
        failed = int(m_failed.group(1)) if m_failed else 0
        errors = int(m_errors.group(1)) if m_errors else 0

        status = "pass" if (failed == 0 and errors == 0 and passed > 0) else \
                 "no_tests" if (passed == 0 and failed == 0 and errors == 0) else "fail"

        return {"status": status, "passed": passed, "failed": failed,
                "errors": errors, "output": output}

    except subprocess.TimeoutExpired:
        return {"status": "error", "output": "Test run timed out (60s)",
                "passed": 0, "failed": 0, "errors": 1}
    except Exception as e:
        return {"status": "error", "output": str(e),
                "passed": 0, "failed": 0, "errors": 1}


# ──────────────────────────────────────────────────────────────────────────────
# market_check (Grounded with Kaggle Startup Success Prediction dataset)
# ──────────────────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

@tool
def market_check(idea: str) -> dict:
    """
    Evaluates a product idea against Kaggle Startup Success Prediction benchmark data.

    Returns a dict with:
        category        : matched startup sector
        viability_score : 0-10 benchmark score
        success_rate    : historical percentage of startups surviving V1
        similar_products: known market incumbents
        risks           : top reasons startups in this domain fail
        critical_factors: essential V1 features needed to avoid common failure modes
        opportunities   : market differentiators
        verdict         : 'viable' | 'risky' | 'saturated'
    """
    benchmarks_path = DATA_DIR / "startup_success_benchmarks.json"
    if not benchmarks_path.exists():
        return {
            "category": "General Software",
            "viability_score": 7.0,
            "success_rate": 0.40,
            "similar_products": ["SaaS Incumbents"],
            "risks": ["High customer acquisition cost", "Lack of clear product differentiation"],
            "critical_factors": ["Focused V1 scope", "Clear value proposition"],
            "opportunities": ["Niche specialization"],
            "verdict": "viable"
        }

    try:
        benchmarks = json.loads(benchmarks_path.read_text(encoding="utf-8"))
    except Exception:
        benchmarks = {}

    idea_lower = idea.lower()
    best_match = None
    max_hits = 0

    for key, data in benchmarks.items():
        keywords = data.get("keywords", [])
        hits = sum(1 for kw in keywords if kw in idea_lower)
        if hits > max_hits:
            max_hits = hits
            best_match = data

    if not best_match:
        best_match = benchmarks.get("general_software", {
            "category": "General Software",
            "viability_score": 6.8,
            "historical_success_rate": 0.40,
            "top_competitors": ["Standard SaaS incumbents"],
            "failure_reasons": ["Lack of clear value proposition", "Building too many complex features"],
            "critical_v1_factors": ["Focused single-problem solution"],
            "opportunities": ["Modern developer experience"],
            "verdict": "viable"
        })

    return {
        "category": best_match.get("category", "General Software"),
        "viability_score": best_match.get("viability_score", 7.0),
        "success_rate": best_match.get("historical_success_rate", 0.40),
        "similar_products": best_match.get("top_competitors", []),
        "risks": best_match.get("failure_reasons", []),
        "critical_factors": best_match.get("critical_v1_factors", []),
        "opportunities": best_match.get("opportunities", []),
        "verdict": best_match.get("verdict", "viable"),
        "grounding_source": "Kaggle Startup Success Prediction Benchmark"
    }


# ──────────────────────────────────────────────────────────────────────────────
# github_issues_check (Grounded with GH Archive / GitHub Public Issue Text)
# ──────────────────────────────────────────────────────────────────────────────

@tool
def github_issues_check(keywords: list[str]) -> dict:
    """
    Searches GitHub issues / GH Archive data for real developer bug reports
    and edge cases matching the given feature keywords.

    Returns a dict with:
        issues: list of issue dicts containing repo, title, body snippet, and labels
        source: 'live_github_api' | 'gh_archive_samples'
    """
    import urllib.request
    import urllib.parse

    query = " ".join(keywords[:3]).strip()
    issues = []
    source = "gh_archive_samples"

    # Attempt live GitHub search API first (short timeout, no auth needed)
    if query:
        try:
            encoded_q = urllib.parse.quote(f"{query} is:issue state:closed")
            url = f"https://api.github.com/search/issues?q={encoded_q}&sort=reactions&per_page=3"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "IdeaToProduct-Agent/1.0", "Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("items", [])[:3]:
                    issues.append({
                        "repo": item.get("repository_url", "").split("/")[-1] or "github",
                        "title": item.get("title", ""),
                        "body": (item.get("body") or "")[:250],
                        "labels": [lbl.get("name", "") for lbl in item.get("labels", [])][:3]
                    })
                if issues:
                    source = "live_github_api"
        except Exception:
            # Fall back to local GH Archive samples on network/rate-limit error
            pass

    # Fallback to local curated GH Archive dataset
    if not issues:
        archive_path = DATA_DIR / "github_archive_samples.json"
        if archive_path.exists():
            try:
                archive = json.loads(archive_path.read_text(encoding="utf-8"))
                query_words = set(query.lower().split() + [kw.lower() for kw in keywords])
                scored_issues = []
                for entry in archive:
                    entry_kws = set(entry.get("keywords", []))
                    score = len(query_words.intersection(entry_kws))
                    scored_issues.append((score, entry))
                scored_issues.sort(key=lambda x: x[0], reverse=True)
                issues = [
                    {
                        "repo": item["repo"],
                        "title": item["title"],
                        "body": item["body"][:250],
                        "labels": item["labels"]
                    }
                    for _, item in scored_issues[:3]
                ]
            except Exception:
                pass

    return {
        "query": query,
        "source": source,
        "issue_count": len(issues),
        "issues": issues
    }
