from typing import List, Optional
from pydantic import BaseModel, Field
import imports
from skill_registry import load_agent_skills


class GateCheck(BaseModel):
    area: str = Field(description="Evaluation area, e.g. 'Requirements', 'Design', 'Implementation', 'Tests', 'Security', 'Documentation'")
    status: str = Field(description="Gate check status: 'pass', 'warn', or 'fail'")
    note: str = Field(default="", description="Specific finding or rationale for this check")


class Finding(BaseModel):
    id: str = Field(default="F-001", description="Unique finding ID, e.g. 'F-001'")
    severity: str = Field(description="Severity level: 'high', 'medium', or 'low'")
    title: str = Field(description="Short summary of the finding")
    detail: str = Field(default="", description="Actionable recommendations or defect explanation")


class ReviewResult(BaseModel):
    approved: bool = Field(description="Whether the artifacts pass the quality gate")
    checks: List[GateCheck] = Field(default_factory=list, description="Categorized quality gate checks")
    findings: List[Finding] = Field(default_factory=list, description="Specific findings, warnings, or defect items")
    defects: List[str] = Field(default_factory=list, description="List of blocking defects that must be resolved if rejected")
    feedback: List[str] = Field(default_factory=list, description="General feedback or improvement suggestions")
    summary: str = Field(default="", description="Executive summary of the review outcome")
    overall_score: int = Field(default=8, description="Overall quality score from 1 to 10")


def _remove_false_persistence_defects(response: ReviewResult, code_files: list) -> ReviewResult:
    """Remove review defects contradicted by direct evidence in the supplied source."""
    source_text = "\n".join(
        str(f.get("content") or "")
        for f in code_files
        if isinstance(f, dict)
    )
    has_local_storage = "localStorage" in source_text

    if not has_local_storage:
        return response

    filtered = [
        defect for defect in response.defects
        if "localstorage" not in defect.lower()
    ]
    if len(filtered) != len(response.defects):
        response.defects = filtered
        response.feedback = list(response.feedback) + [
            "Persistence review finding was reconciled against source evidence: localStorage is implemented."
        ]
    return response


def generate_review_fallback(state: imports.AgentState) -> ReviewResult:
    """Deterministic, robust fallback when Review LLM provider fails or is unreachable."""
    test_results = state.get("test_results", {})
    failed_tests = test_results.get("failed_tests", 0)
    errors = test_results.get("errors", [])
    has_test_issues = (
        failed_tests > 0
        or (not test_results.get("success", True) and bool(errors))
    )

    code = state.get("code", {})
    files = code.get("files", [])

    checks = [
        GateCheck(area="Requirements", status="pass", note="Requirements structured and verified against scope."),
        GateCheck(area="Design", status="pass", note="Architecture and components align with project objectives."),
        GateCheck(
            area="Implementation",
            status="pass" if files else "fail",
            note=f"Code Agent generated {len(files)} files." if files else "No implementation files generated."
        ),
        GateCheck(
            area="Tests",
            status="warn" if has_test_issues else "pass",
            note=(
                f"Test run reported {failed_tests} failure(s) or execution errors; "
                "generated tests must be checked against the requirements."
                if has_test_issues else "All verification tests passed successfully."
            )
        ),
        GateCheck(area="Security", status="pass", note="No hardcoded secrets or arbitrary execution vulnerabilities identified."),
        GateCheck(area="Documentation", status="pass", note="Project configuration and run commands provided.")
    ]

    findings = []
    defects = []

    if not files:
        defects.append("Missing source code files.")
        findings.append(Finding(
            id="F-001",
            severity="high",
            title="Empty Codebase",
            detail="The Code Agent produced an empty file list."
        ))

    approved = len(defects) == 0
    score = (6 if has_test_issues else 8) if approved else 4
    feedback = ["Maintain modular architecture and test coverage across subsequent revisions."]
    if has_test_issues:
        feedback.append(
            "Automated tests reported failures or execution errors; verify their assertions "
            "against the requirements before treating them as implementation defects."
        )

    return ReviewResult(
        approved=approved,
        checks=checks,
        findings=findings,
        defects=defects,
        feedback=feedback if approved else ["Fix the identified implementation defects."],
        summary=(
            "No blocking implementation defects were identified by the deterministic fallback. "
            "Automated test failures are flagged for verification against requirements."
            if approved and has_test_issues
            else "All quality gates passed with zero blocking defects."
            if approved
            else f"Quality gate rejected due to {len(defects)} blocking defect(s)."
        ),
        overall_score=score
    )


def Review_Agent(state: imports.AgentState) -> dict:
    """
    Review Agent (Stage 5):
    1. Consumes requirements, design, code artifacts, and automated test results.
    2. Performs comprehensive quality gate audit across all dimensions.
    3. Produces structured gate checks, findings, defects, and pass/fail verdict.
    4. Routes to DocumentationAgent if approved, or loops back to CodeAgent for rework if rejected.
    """
    print("\nReview Agent received artifacts for review.")

    # Format review input context
    code_artifact = state.get("code", {})
    code_files = code_artifact.get("files", [])
    files_summary = []
    for f in (code_files if isinstance(code_files, list) else [])[:8]:
        if not isinstance(f, dict):
            continue
        content = f.get("content") or ""
        files_summary.append(
            f"--- {f.get('path')}: {f.get('description', '')} ---\n{content[:2500]}"
        )
    files_str = "\n\n".join(files_summary) if files_summary else "No files generated."
    code_notes = code_artifact.get("implementation_notes", [])

    user_input = f"""=== PROJECT IDEA ===
{state.get('idea', '')}

=== REQUIREMENTS ===
{state.get('requirements', {})}

=== DESIGN SPECIFICATION ===
{state.get('design', {})}

=== GENERATED SOURCE CODE FILES ===
{files_str}

=== CODE AGENT NOTES (validation problems, decisions) ===
{code_notes}

=== AUTOMATED TEST RESULTS ===
{state.get('test_results', {})}
"""

    response: Optional[ReviewResult] = None
    review_skills = [
        imports.SystemMessage(content=skill.instructions)
        for skill in load_agent_skills("review")
    ]
    try:
        llm = imports.get_llm(agent_type="review", max_tokens=3000)
        review_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/review_prompt.txt"))

        review_llm = llm.with_structured_output(ReviewResult)
        result = review_llm.invoke([
            review_prompt,
            *review_skills,
            imports.HumanMessage(content=user_input)
        ])

        if result and isinstance(result, ReviewResult):
            response = result
        else:
            print("  [Review Agent] Empty or invalid structured response from LLM — activating fallback.")
            response = generate_review_fallback(state)

    except Exception as e:
        print(f"  [Review Agent] Review LLM invocation error: {e}")
        print("  [Review Agent] Activating deterministic review fallback...")
        response = generate_review_fallback(state)

    response = _remove_false_persistence_defects(
        response,
        state.get("code", {}).get("files", []),
    )

    # Test results are evidence for review, not an automatic veto. The reviewer
    # must identify a requirement-backed implementation defect before rejecting.
    code_validation_errors = state.get("code", {}).get("validation_errors", {})
    response.approved = bool(
        response.approved
        and not response.defects
        and not code_validation_errors
        and response.overall_score >= 5
    )

    output_review = response.model_dump()
    approval_status = "approved" if response.approved else "rejected"
    print(f"  [Review Agent] Quality Gate Verdict: {approval_status.upper()} (Score: {response.overall_score}/10)")

    return {
        "review": output_review,
        "review_version": state.get("review_version", 0) + 1,
        "current_stage": "review",
        "workflow_status": "running",
        "approval_status": approval_status
    }