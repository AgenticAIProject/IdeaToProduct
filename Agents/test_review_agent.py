from State_definition import AgentState
from ReviewAgent import Review_Agent

# Mock state simulating a project that has passed through requirement, design, code, and test stages.
state: AgentState = {
    # Project
    "project_id": "project_001",
    "user_id": "user_001",
    "idea": "Build an internship platform for students",

    # Requirements
    "clarification_questions": [],
    "user_answers": [],
    "clarification_round": 0,
    "requirements": {
        "problem_statement": "Students need a streamlined way to find and apply for internships, while recruiters need an easy way to manage applications.",
        "functional_requirements": [
            "User registration for students and recruiters.",
            "Internship search and filtering.",
            "Resume upload and application submission."
        ]
    },
    "requirements_version": 1,

    # Design
    "design": {
        "architecture": "3-tier web application (SPA + REST API + PostgreSQL).",
        "api_endpoints": [
            "POST /api/v1/auth/register",
            "GET /api/v1/internships",
            "POST /api/v1/applications"
        ]
    },
    "design_version": 1,

    # Code
    "code": {
        "app.py": "def register(): return 'Success'",
        "db.py": "def get_internships(): return []"
    },
    "code_version": 1,

    # Testing
    "test_results": {
        "tests_passed": 24,
        "tests_failed": 0,
        "coverage": "92%",
        "critical_bugs_found": 0
    },
    "test_version": 1,

    # Review
    "review": {},
    "review_version": 0,

    # Documentation
    "documentation": {},
    "documentation_version": 0,

    # Workflow
    "current_stage": "review",
    "workflow_status": "running",

    # Retry
    "retry_count": {
        "requirements": 0,
        "design": 0,
        "code": 0,
        "test": 0,
        "review": 0
    },

    # Approval
    "approval_status": "pending"
}

# =========================================================
# RUN REVIEW AGENT
# =========================================================

print("\n========== RUNNING REVIEW AGENT ==========")

result = Review_Agent(state)

print("\nCurrent stage:")
print(result.get("current_stage"))

print("\nWorkflow status:")
print(result.get("workflow_status"))

print("\nApproval status:")
print(result.get("approval_status"))

print("\nReview results:")
print(result.get("review"))
