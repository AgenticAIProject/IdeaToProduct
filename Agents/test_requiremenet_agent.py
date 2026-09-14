from State_definition import AgentState
from RequirementAgent import Requirement_Agent

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

result = Requirement_Agent(state)

print(result)