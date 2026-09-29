import sys
from pathlib import Path

# Add Agents to path
sys.path.append(str(Path(__file__).parent / "Agents"))

from Agents.ReviewAgent import Review_Agent, ReviewResult
from Agents.State_definition import AgentState


def test_review_agent_suite():
    print("==================================================================")
    print("RUNNING REVIEW AGENT UNIT & INTEGRATION TESTS")
    print("==================================================================")

    # Test 1: Clean passing state
    state_pass: AgentState = {
        "project_id": "test_proj_01",
        "user_id": "user_1",
        "idea": "Build a simple habit tracker API",
        "requirements": {
            "functional_requirements": [{"id": "FR-01", "description": "Create habit"}]
        },
        "design": {
            "components": [{"name": "HabitAPI", "responsibility": "Handles routes"}]
        },
        "code": {
            "files": [{"path": "main.py", "content": "from fastapi import FastAPI\napp = FastAPI()"}]
        },
        "test_results": {
            "success": True,
            "total_tests": 3,
            "passed_tests": 3,
            "failed_tests": 0,
            "errors": []
        },
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 0,
        "requirements_version": 1,
        "github_evidence": [],
        "design_version": 1,
        "code_version": 1,
        "generated_project_path": "generated_projects/test_proj_01",
        "test_version": 1,
        "review": {},
        "review_version": 0,
        "documentation": {},
        "documentation_version": 0,
        "current_stage": "test",
        "workflow_status": "running",
        "retry_count": {"requirements": 0, "design": 0, "code": 0, "test": 0, "review": 0},
        "approval_status": "pending"
    }

    res_pass = Review_Agent(state_pass)
    assert res_pass["approval_status"] == "approved", f"Expected approved, got {res_pass['approval_status']}"
    assert res_pass["review"]["overall_score"] >= 7, f"Expected high score, got {res_pass['review']['overall_score']}"
    assert len(res_pass["review"]["checks"]) >= 4, "Expected structured checks"
    print("✓ Test 1 Passed: Clean passing state gets APPROVED with structured checks.")

    # Test 2: Failing test state overrides to rejected
    state_fail: AgentState = {
        "project_id": "test_proj_02",
        "user_id": "user_2",
        "idea": "Build a broken habit tracker API",
        "requirements": {"functional_requirements": [{"id": "FR-01", "description": "Create habit"}]},
        "design": {"components": [{"name": "HabitAPI"}]},
        "code": {"files": [{"path": "main.py", "content": "broken syntax"}]},
        "test_results": {
            "success": False,
            "total_tests": 2,
            "passed_tests": 0,
            "failed_tests": 2,
            "errors": ["AssertionError: expected status 200, got 500"]
        },
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 0,
        "requirements_version": 1,
        "github_evidence": [],
        "design_version": 1,
        "code_version": 1,
        "generated_project_path": "generated_projects/test_proj_02",
        "test_version": 1,
        "review": {},
        "review_version": 0,
        "documentation": {},
        "documentation_version": 0,
        "current_stage": "test",
        "workflow_status": "running",
        "retry_count": {"requirements": 0, "design": 0, "code": 0, "test": 0, "review": 0},
        "approval_status": "pending"
    }

    res_fail = Review_Agent(state_fail)
    assert res_fail["approval_status"] == "rejected", f"Expected rejected, got {res_fail['approval_status']}"
    assert len(res_fail["review"]["defects"]) > 0, "Expected defects list on test failure"
    print("✓ Test 2 Passed: Failing test execution enforces REJECTED verdict and generates defect items.")

    print("\n==================================================================")
    print("ALL REVIEW AGENT TESTS PASSED! ✅")
    print("==================================================================")


if __name__ == "__main__":
    test_review_agent_suite()
