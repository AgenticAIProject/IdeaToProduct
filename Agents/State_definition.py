
from typing import TypedDict


from typing import TypedDict


class AgentState(TypedDict):

    # Project
    project_id: str
    user_id: str
    idea: str

    # Requirements
    clarification_questions: list[str]
    user_answers: list[str]
    clarification_round: int
    requirements: dict
    requirements_version: int

    # Design
    design: dict
    design_version: int

    # Code
    code: dict
    code_version: int

    # Testing
    test_results: dict
    test_version: int

    # Review
    review: dict
    review_version: int

    # Documentation
    documentation: dict
    documentation_version: int

    # Workflow
    current_stage: str
    workflow_status: str

    # Retry
    retry_count: dict[str, int]

    # Approval
    approval_status: str



# agent states 
# tools filewriting, github access, commit, etcc..
# system prompts
# conditional edges
# edges
# skills
# LLM calls 
# number of tokens(input and output), context window, security, 
