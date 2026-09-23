from State_definition import AgentState
from graph import graph


state: AgentState = {

    # Project
    "project_id": "project_001",
    "user_id": "user_001",
    "idea": "Build an internship platform for students",

    # Requirements
    "clarification_questions": [],
    "user_answers": [],
    "clarification_round": 0,
    "requirements": {},
    "requirements_version": 0,

    # Design
    "design": {},
    "design_version": 0,

    # Code
    "code": {},
    "code_version": 0,

    # Testing
    "test_results": {},
    "test_version": 0,

    # Review
    "review": {},
    "review_version": 0,

    # Documentation
    "documentation": {},
    "documentation_version": 0,

    # Workflow
    "current_stage": "requirements",
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
# ROUND 1
# =========================================================

print("\n========== ROUND 1 ==========")

result = graph.invoke(state)


print("\nCurrent stage:")
print(result["current_stage"])

print("\nWorkflow status:")
print(result["workflow_status"])

print("\nClarification questions:")

for i, question in enumerate(
    result["clarification_questions"],
    start=1
):
    print(f"{i}. {question}")


# =========================================================
# USER ANSWERS
# =========================================================

answers = [
    "The main users are students and company recruiters.",

    "Students should be able to search internships, filter listings, view details, upload resumes, apply, and track application status.",

    "Applications should be submitted directly through the platform. Recruiters should review applications and update the application status."
]


# Add answers to state
result["user_answers"] = answers


# =========================================================
# ROUND 2
# =========================================================

print("\n========== ROUND 2 ==========")

result = graph.invoke(result)


print("\nCurrent stage:")
print(result["current_stage"])

print("\nWorkflow status:")
print(result["workflow_status"])

print("\nClarification questions:")

for i, question in enumerate(
    result["clarification_questions"],
    start=1
):
    print(f"{i}. {question}")


print("\nRequirements:")

print(result["requirements"])

print("\nDesign:")
print(result["design"])