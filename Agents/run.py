"""
run.py - Entry point to run the IdeaToProduct pipeline.

Usage:
    python run.py

Make sure you have set OPENROUTER_API_KEY in the .env file at the project root.
"""

import sys
import json
from pathlib import Path
from graph import graph


def print_section(title: str, char: str = "-", width: int = 60):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_requirements(req: dict):
    print_section("REQUIREMENTS DOCUMENT", "=")
    fields = [
        ("Problem Statement",       "problem_statement"),
        ("Objectives",              "objectives"),
        ("Actors",                  "actors"),
        ("User Stories",            "user_stories"),
        ("Functional Requirements", "functional_requirements"),
        ("Non-Functional Reqs",     "non_functional_requirements"),
        ("Acceptance Criteria",     "acceptance_criteria"),
        ("Constraints",             "constraints"),
        ("Assumptions",             "assumptions"),
        ("In Scope",                "in_scope"),
        ("Out of Scope",            "out_of_scope"),
        ("Open Questions",          "open_questions"),
    ]
    for label, key in fields:
        value = req.get(key)
        if not value:
            continue
        print(f"\n  [{label}]")
        if isinstance(value, list):
            for item in value:
                print(f"    - {item}")
        else:
            print(f"    {value}")


def print_grounding(market: dict, issues: list):
    if not market and not issues:
        return
    print_section("DATA GROUNDING & MARKET INTELLIGENCE", "=")
    if market:
        cat = market.get("category", "General")
        score = market.get("viability_score", "N/A")
        verdict = market.get("verdict", "N/A")
        rate = market.get("success_rate", 0)
        source = market.get("grounding_source", "Kaggle Startup Dataset")
        print(f"\n  [Kaggle Startup Success Grounding]")
        print(f"    Source: {source}")
        print(f"    Sector: {cat} | Viability Score: {score}/10 ({verdict})")
        if rate:
            print(f"    Historical V1 Survival Rate: {rate * 100:.0f}%")
        competitors = market.get("similar_products", [])
        if competitors:
            print(f"    Top Incumbents: {', '.join(competitors)}")
        risks = market.get("risks", [])
        if risks:
            print("    Top Failure Modes Mitigated in Requirements:")
            for r in risks[:3]:
                print(f"      * {r}")
    if issues:
        print(f"\n  [GH Archive / GitHub Public Issue Grounding]")
        print(f"    Retrieved {len(issues)} real developer issues for edge-case grounding:")
        for iss in issues[:3]:
            repo = iss.get("repo", "repo")
            title = iss.get("title", "")
            print(f"      * [{repo}] {title}")


def print_design(design: dict):
    print_section("DESIGN DOCUMENT", "=")
    fields = [
        ("Architecture",    "architecture"),
        ("Components",      "components"),
        ("Data Model",      "data_model"),
        ("API Endpoints",   "api_endpoints"),
        ("Decisions",       "decisions"),
        ("Edge Cases",      "edge_cases"),
    ]
    for label, key in fields:
        value = design.get(key)
        if not value:
            continue
        print(f"\n  [{label}]")
        if isinstance(value, list):
            for item in value:
                print(f"    - {item}")
        else:
            print(f"    {value}")


def print_code(code: dict):
    print_section("CODE ARTIFACT", "=")
    files = code.get("files", [])
    if files:
        print(f"\n  [Generated Files - {len(files)} total]")
        for f in files:
            desc = f.get("description", "")
            suffix = f"  ({desc})" if desc else ""
            print(f"    {f['path']}{suffix}")

    deps = code.get("dependencies", [])
    if deps:
        print("\n  [Dependencies]")
        for d in deps:
            print(f"    - {d}")

    notes = code.get("implementation_notes", [])
    if notes:
        print("\n  [Implementation Notes]")
        for n in notes:
            print(f"    - {n}")

    project_path = code.get("generated_project_path", "")
    if project_path:
        print(f"\n  [Project written to disk]")
        print(f"    {project_path}")

    setup = code.get("setup_instructions", "")
    if setup:
        print("\n  [Setup Instructions]")
        for line in setup.splitlines():
            print(f"    {line}")


def print_test(test: dict):
    if not test:
        return
    print_section("TEST RESULTS", "=")
    print(f"  Summary: {test.get('summary', 'N/A')}")
    status_str = "PASSED" if test.get("success") else "FAILED"
    print(f"  Status: {status_str}")
    print(f"  Total Tests: {test.get('total_tests', 0)} | Passed: {test.get('passed_tests', 0)} | Failed: {test.get('failed_tests', 0)}")
    if test.get("duration_seconds"):
        print(f"  Duration: {test.get('duration_seconds')}s")
    errors = test.get("errors", [])
    if errors:
        print("\n  [Errors / Failures]")
        for err in errors:
            print(f"    - {err}")


def print_review(review: dict, approval_status: str = ""):
    if not review:
        return
    print_section("REVIEW & GOVERNANCE", "=")
    status = approval_status.upper() if approval_status else ("APPROVED" if review.get("approved") else "REJECTED")
    score = review.get("overall_score", "N/A")
    print(f"  Approval Status: {status}")
    print(f"  Overall Score: {score}/10")
    feedback = review.get("feedback", [])
    if feedback:
        print("\n  [Feedback]")
        for item in feedback:
            print(f"    - {item}")
    defects = review.get("defects", [])
    if defects:
        print("\n  [Defects]")
        for d in defects:
            print(f"    - {d}")


def print_documentation(docs: dict):
    if not docs:
        return
    print_section("DOCUMENTATION PACKAGE", "=")
    doc_sections = [
        ("readme", "README"),
        ("api_reference", "API Reference"),
        ("architecture_overview", "Architecture Overview"),
        ("user_guide", "User Guide"),
        ("changelog", "Changelog"),
    ]
    for key, label in doc_sections:
        content = docs.get(key, "")
        if content:
            lines = content.strip().splitlines()
            preview = "\n    ".join(lines[:6])
            print(f"\n  [{label}] ({len(lines)} lines)")
            print(f"    {preview}")
            if len(lines) > 6:
                print("    ...")


def main():
    idea = input("Enter your product idea: ").strip()

    if not idea:
        print("No idea provided. Exiting.")
        sys.exit(1)

    # Auto-increment project_id so new runs don't overwrite previous projects
    projects_dir = Path(__file__).resolve().parent.parent / "generated_projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    existing_nums = []
    for p in projects_dir.glob("project-*"):
        if p.is_dir():
            try:
                existing_nums.append(int(p.name.split("-")[1]))
            except (IndexError, ValueError):
                pass
    next_num = max(existing_nums, default=0) + 1
    project_id = f"project-{next_num:03d}"

    # Initial state
    state = {
        "project_id":              project_id,
        "user_id":                 "user-001",
        "idea":                    idea,
        "clarification_questions": [],
        "user_answers":            [],
        "clarification_round":     0,
        "requirements":            {},
        "requirements_version":    0,
        "market_analysis":         {},
        "github_evidence":         [],
        "design":                  {},
        "design_version":          0,
        "code":                    {},
        "code_version":            0,
        "generated_project_path":  "",
        "test_results":            {},
        "test_version":            0,
        "review":                  {},
        "review_version":          0,
        "documentation":           {},
        "documentation_version":   0,
        "current_stage":           "requirement",
        "workflow_status":         "running",
        "retry_count":             {},
        "approval_status":         "pending",
    }

    config = {
        "configurable": {"thread_id": f"{project_id}_session"},
        "recursion_limit": 50
    }

    print("\nStarting IdeaToProduct Pipeline...\n")

    while True:
        result = graph.invoke(state, config=config)
        stage  = result.get("current_stage", "unknown")

        # -- Clarification round ------------------------------------------
        if stage == "clarification":
            questions = result.get("clarification_questions", [])
            print_section("CLARIFICATION NEEDED")
            print("  The agent needs a bit more detail before proceeding.\n")

            answers = []
            for i, q in enumerate(questions, 1):
                print(f"  Q{i}: {q}")
                ans = input(f"  A{i}: ").strip()
                answers.append(f"Q: {q}\nA: {ans}")
                print()

            prev_answers = result.get("user_answers", [])
            state = {
                **result,
                "user_answers":    prev_answers + answers,
                "current_stage":   "requirement",
                "workflow_status": "running",
            }
            print("  Processing your answers...\n")
            continue

        # -- Pipeline complete or reached terminal stage --------------------
        print_grounding(result.get("market_analysis", {}), result.get("github_evidence", []))
        if result.get("requirements"):
            print_requirements(result.get("requirements", {}))
        if result.get("design"):
            print_design(result.get("design", {}))
        if result.get("code"):
            print_code(result.get("code", {}))
        if result.get("test_results"):
            print_test(result.get("test_results", {}))
        if result.get("review"):
            print_review(result.get("review", {}), result.get("approval_status", ""))
        if result.get("documentation"):
            print_documentation(result.get("documentation", {}))

        print_section("Pipeline Complete!", "=")
        print(f"  Project ID:      {project_id}")
        print(f"  Final Stage:     {stage}")
        print(f"  Workflow Status: {result.get('workflow_status', 'N/A')}")
        print(f"  Approval Status: {result.get('approval_status', 'N/A')}")
        artifacts_dir = Path(__file__).resolve().parent.parent / "generated_projects" / project_id / "artifacts"
        if artifacts_dir.exists():
            print(f"  Artifacts Saved: {artifacts_dir}")
        break


if __name__ == "__main__":
    main()
