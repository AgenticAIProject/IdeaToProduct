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
import shutil

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
    artifacts_dir = project_dir / "artifacts"
    backup_artifacts = WORKSPACE_ROOT / f".tmp_{project_id}_artifacts"

    # Preserve any existing artifacts if scaffolding the code directory
    if artifacts_dir.exists():
        if backup_artifacts.exists():
            shutil.rmtree(backup_artifacts)
        shutil.copytree(artifacts_dir, backup_artifacts)

    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Restore preserved artifacts
    if backup_artifacts.exists():
        shutil.copytree(backup_artifacts, project_dir / "artifacts")
        shutil.rmtree(backup_artifacts)

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
# Stage Artifact Persistence & Formatters
# ──────────────────────────────────────────────────────────────────────────────

def save_stage_artifact(project_id: str, stage_name: str, data: dict, custom_md: str = None) -> Path:
    """
    Saves a stage-specific artifact under generated_projects/<project_id>/artifacts/:
      - <stage_name>.json
      - <stage_name>.md
    """
    if not project_id:
        project_id = "project_default"

    artifacts_dir = WORKSPACE_ROOT / project_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. JSON artifact
    json_path = artifacts_dir / f"{stage_name}.json"
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    # 2. Markdown artifact
    md_path = artifacts_dir / f"{stage_name}.md"
    if not custom_md:
        title = stage_name.replace("_", " ").title()
        custom_md = (
            f"# Artifact: {title}\n\n"
            f"- **Project**: `{project_id}`\n"
            f"- **Timestamp**: `{datetime.utcnow().isoformat()}Z`\n\n"
            f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
        )
    md_path.write_text(custom_md, encoding="utf-8")
    return artifacts_dir


def format_requirements_md(project_id: str, req: dict, github_evidence: list = None) -> str:
    md = f"# Requirements Artifact (Stage 1) — {project_id}\n\n"
    md += f"**Problem Statement:**\n> {req.get('problem_statement', 'N/A')}\n\n"

    objs = req.get("objectives", [])
    if objs:
        md += "## Objectives\n"
        for o in objs:
            md += f"- {o}\n"
        md += "\n"

    stories = req.get("user_stories", [])
    if stories:
        md += "## User Stories\n\n"
        md += "| ID | Priority | Actor | User Story |\n|---|---|---|---|\n"
        for s in stories:
            if isinstance(s, dict):
                md += f"| `{s.get('id', 'US')}` | **{s.get('priority', 'Must')}** | {s.get('actor', 'User')} | {s.get('story', '')} |\n"
        md += "\n"

    frs = req.get("functional_requirements", [])
    if frs:
        md += "## Functional Requirements\n\n"
        md += "| ID | Priority | Description | Related Stories |\n|---|---|---|---|\n"
        for f in frs:
            if isinstance(f, dict):
                rels = ", ".join(f.get("user_story_ids", [])) or "—"
                md += f"| `{f.get('id', 'FR')}` | **{f.get('priority', 'Must')}** | {f.get('description', '')} | {rels} |\n"
        md += "\n"

    acs = req.get("acceptance_criteria", [])
    if acs:
        md += "## Acceptance Criteria\n\n"
        for ac in acs:
            if isinstance(ac, dict):
                md += f"- **[{ac.get('id', 'AC')}]** (Validates `{ac.get('requirement_id', '')}`): {ac.get('description', '')}\n"
        md += "\n"

    nfrs = req.get("non_functional_requirements", [])
    if nfrs:
        md += "## Non-Functional Requirements\n\n"
        for nfr in nfrs:
            if isinstance(nfr, dict):
                md += f"- **[{nfr.get('category', 'Quality')}]** {nfr.get('description', '')}\n"
        md += "\n"

    if github_evidence:
        md += "## Grounding Evidence (GitHub / Public Issues)\n\n"
        for iss in github_evidence[:5]:
            if isinstance(iss, dict):
                md += f"- **[{iss.get('repo', 'GitHub')}]**: {iss.get('title', '')}\n"
        md += "\n"

    return md


def format_design_md(project_id: str, design: dict) -> str:
    md = f"# System Design Artifact (Stage 2) — {project_id}\n\n"
    md += f"- **System Type:** `{design.get('system_type', 'N/A')}`\n\n"
    md += f"## Architecture Overview\n{design.get('architecture', 'N/A')}\n\n"

    techs = design.get("technology_choices", [])
    if techs:
        md += "## Technology Choices\n\n"
        md += "| Category | Technology | Rationale |\n|---|---|---|\n"
        for t in techs:
            if isinstance(t, dict):
                md += f"| **{t.get('category', '').title()}** | `{t.get('technology', '')}` | {t.get('reason', '')} |\n"
        md += "\n"

    comps = design.get("components", [])
    if comps:
        md += "## Components\n\n"
        md += "| Component ID | Name | Responsibility | Requirements |\n|---|---|---|---|\n"
        for c in comps:
            if isinstance(c, dict):
                reqs = ", ".join(c.get("requirement_ids", [])) or "—"
                md += f"| `{c.get('id', '')}` | {c.get('name', '')} | {c.get('responsibility', '')} | {reqs} |\n"
        md += "\n"

    entities = design.get("data_entities", [])
    if entities:
        md += "## Data Model & Entities\n\n"
        for e in entities:
            if isinstance(e, dict):
                attrs = ", ".join(e.get("attributes", [])) or "None specified"
                md += f"### Entity: `{e.get('name', 'Entity')}` (`{e.get('id', '')}`)\n"
                md += f"- **Purpose**: {e.get('purpose', '')}\n"
                md += f"- **Attributes**: `{attrs}`\n\n"

    endpoints = design.get("api_endpoints", [])
    if endpoints:
        md += "## API Endpoints\n\n"
        md += "| Method | Path | Description | Requirements |\n|---|---|---|---|\n"
        for ep in endpoints:
            if isinstance(ep, dict):
                reqs = ", ".join(ep.get("requirement_ids", [])) or "—"
                md += f"| `{ep.get('method', 'GET')}` | `{ep.get('path', '/')}` | {ep.get('description', '')} | {reqs} |\n"
        md += "\n"

    decisions = design.get("design_decisions", [])
    if decisions:
        md += "## Design Decisions\n\n"
        for d in decisions:
            if isinstance(d, dict):
                md += f"- **[{d.get('id', 'DEC')}] {d.get('decision', '')}**: {d.get('reason', '')}\n"
        md += "\n"

    return md


def format_code_md(project_id: str, code: dict) -> str:
    md = f"# Code Artifact (Stage 3) — {project_id}\n\n"
    md += f"- **Stack**: `{code.get('stack', 'standard')}`\n"
    md += f"- **Generated Path**: `{code.get('generated_project_path', '')}`\n\n"

    files = code.get("files", [])
    if files:
        md += f"## Generated Files ({len(files)} total)\n\n"
        md += "| Path | Description | Requirement Traceability |\n|---|---|---|\n"
        for f in files:
            if isinstance(f, dict):
                reqs = ", ".join(f.get("requirement_ids", [])) or "—"
                md += f"| `{f.get('path', '')}` | {f.get('description', '')} | {reqs} |\n"
        md += "\n"

    deps = code.get("dependencies", [])
    if deps:
        md += "## Dependencies\n\n"
        for d in deps:
            md += f"- `{d}`\n"
        md += "\n"

    setup = code.get("setup_instructions", "")
    if setup:
        md += f"## Setup & Run Instructions\n\n```bash\n{setup}\n```\n\n"

    notes = code.get("implementation_notes", [])
    if notes:
        md += "## Implementation Notes\n\n"
        for n in notes:
            md += f"- {n}\n"
        md += "\n"

    return md


def format_test_md(project_id: str, test: dict) -> str:
    md = f"# Test Execution Artifact (Stage 4) — {project_id}\n\n"
    status_label = "✅ PASSED" if test.get("success") else "❌ FAILED"
    md += f"## Status: {status_label}\n\n"
    md += f"- **Summary**: {test.get('summary', 'N/A')}\n"
    md += f"- **Total Tests**: {test.get('total_tests', 0)}\n"
    md += f"- **Passed**: {test.get('passed_tests', 0)}\n"
    md += f"- **Failed**: {test.get('failed_tests', 0)}\n"
    md += f"- **Duration**: {test.get('duration_seconds', 0)}s\n\n"

    errors = test.get("errors", [])
    if errors:
        md += "## Errors & Failures\n\n"
        for err in errors:
            md += f"```text\n{err}\n```\n\n"

    raw = test.get("raw_output", "")
    if raw:
        md += f"## Raw Execution Output\n\n```text\n{raw[:3000]}\n```\n"

    return md


def format_review_md(project_id: str, review: dict, approval_status: str = "") -> str:
    md = f"# Review & Governance Artifact (Stage 5) — {project_id}\n\n"
    app_str = approval_status.upper() if approval_status else ("APPROVED" if review.get("approved") else "REJECTED")
    icon = "✅" if app_str == "APPROVED" else "❌"
    md += f"## Decision: {icon} {app_str}\n\n"
    md += f"- **Overall Quality Score**: `{review.get('overall_score', 'N/A')}/10`\n\n"

    feedback = review.get("feedback", [])
    if feedback:
        md += "## Reviewer Feedback\n\n"
        for item in feedback:
            md += f"- {item}\n"
        md += "\n"

    defects = review.get("defects", [])
    if defects:
        md += "## Defects Identified\n\n"
        for d in defects:
            md += f"- ⚠️ {d}\n"
        md += "\n"

    return md


def format_documentation_md(project_id: str, docs: dict) -> str:
    md = f"# Documentation Package Artifact (Stage 6) — {project_id}\n\n"

    sections = [
        ("Project README", "readme"),
        ("API & Module Reference", "api_reference"),
        ("Architecture Overview", "architecture_overview"),
        ("User Guide", "user_guide"),
        ("Changelog", "changelog"),
    ]

    for title, key in sections:
        content = docs.get(key, "")
        if content:
            md += f"## {title}\n\n{content}\n\n---\n\n"

    return md


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


# ──────────────────────────────────────────────────────────────────────────────
# fetch_github_grounding  (high-level wrapper — accepts idea string directly)
# ──────────────────────────────────────────────────────────────────────────────

@tool
def fetch_github_grounding(idea: str) -> dict:
    """
    High-level grounding tool. Accepts a raw idea string, extracts keywords,
    queries GitHub issues, and returns a formatted summary ready for LLM prompts.

    Returns a dict with:
        issues_text  : formatted string of developer issues for prompt injection
        github_data  : raw result from github_issues_check (issues list, source)
    """
    keywords = [w for w in idea.lower().split() if len(w) > 3]
    raw = github_issues_check.invoke({"keywords": keywords[:5]})

    issues_summary = [
        f"- [{issue.get('repo')}] {issue.get('title')}: {issue.get('body', '')[:150]}"
        for issue in raw.get("issues", [])
    ]
    issues_text = "\n".join(issues_summary) if issues_summary else "No specific edge cases retrieved."

    print(f"  [Grounding] Retrieved {raw.get('issue_count', 0)} related developer issue cases ({raw.get('source')})")

    return {
        "issues_text": issues_text,
        "github_data": raw
    }
