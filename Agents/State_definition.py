from typing import TypedDict

class TestResults(TypedDict):
    success: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    errors: list[str]
    raw_output: str
    summary: str
    duration_seconds: float
    test_files: dict[str, str]

class DocumentationArtifact(TypedDict):
    readme: str
    api_reference: str
    architecture_overview: str
    user_guide: str
    changelog: str

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
