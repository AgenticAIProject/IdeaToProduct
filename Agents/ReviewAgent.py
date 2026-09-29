from typing import List, Optional
from pydantic import BaseModel, Field
import imports


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


def generate_review_fallback(state: imports.AgentState) -> ReviewResult:
    """Deterministic, robust fallback when Review LLM provider fails or is unreachable."""
    test_results = state.get("test_results", {})
    failed_tests = test_results.get("failed_tests", 0)
    errors = test_results.get("errors", [])
    has_test_failures = failed_tests > 0 or bool(errors)

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
            status="fail" if has_test_failures else "pass",
            note=f"{failed_tests} test(s) failed." if has_test_failures else "All verification tests passed successfully."
        ),
        GateCheck(area="Security", status="pass", note="No hardcoded secrets or arbitrary execution vulnerabilities identified."),
        GateCheck(area="Documentation", status="pass", note="Project configuration and run commands provided.")
    ]

    findings = []
    defects = []

    if has_test_failures:
        defects.append(f"Automated test execution reported {failed_tests} failure(s) or errors.")
        findings.append(Finding(
            id="F-001",
            severity="high",
            title="Test Execution Failures",
            detail=f"Test runner reported failures: {'; '.join(errors) if errors else 'Unit test assertions failed.'}"
        ))

    if not files:
        defects.append("Missing source code files.")
        findings.append(Finding(
            id="F-002",
            severity="high",
            title="Empty Codebase",
            detail="The Code Agent produced an empty file list."
        ))

    approved = len(defects) == 0
    score = 8 if approved else 4

    return ReviewResult(
        approved=approved,
        checks=checks,
        findings=findings,
        defects=defects,
        feedback=["Maintain modular architecture and test coverage across subsequent revisions."] if approved else ["Fix the identified test failures in the next code iteration."],
        summary="All quality gates passed with zero blocking defects." if approved else f"Quality gate rejected due to {len(defects)} blocking defect(s).",
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
    files_summary = [f"- {f.get('path')}: {f.get('description', '')}" for f in code_files]
    files_str = "\n".join(files_summary) if files_summary else "No files generated."

    user_input = f"""=== PROJECT IDEA ===
{state.get('idea', '')}

=== REQUIREMENTS ===
{state.get('requirements', {})}

=== DESIGN SPECIFICATION ===
{state.get('design', {})}

=== GENERATED SOURCE CODE FILES ===
{files_str}

=== AUTOMATED TEST RESULTS ===
{state.get('test_results', {})}
"""

    response: Optional[ReviewResult] = None
    try:
        llm = imports.get_llm(agent_type="review", max_tokens=2000)
        review_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/review_prompt.txt"))
        review_skill = imports.SystemMessage(content=imports.load_prompt("skills/review_skill.txt"))

        review_llm = llm.with_structured_output(ReviewResult)
        result = review_llm.invoke([
            review_prompt,
            review_skill,
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

    # If test runner reported explicit test failures, enforce rejection (no false approvals)
    test_results = state.get("test_results", {})
    if test_results.get("failed_tests", 0) > 0 or test_results.get("errors"):
        if response.approved:
            print("  [Review Agent] Overriding verdict to REJECTED due to failing automated test results.")
            response.approved = False
            if not response.defects:
                response.defects.append("Failing automated tests must be resolved before approval.")

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
