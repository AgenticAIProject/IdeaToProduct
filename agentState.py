from typing import TypedDict

class ProjectState(TypedDict):
    project_id: str
    idea: str
    requirements: dict
    design: dict
    code: dict
    test_results: dict
    review: dict
    documentation: dict
    current_stage: str
    retry_count: int
    approval_status: str



# agent states 
# tools     filewriting, github access, commit, etcc..
# system prompts
# conditional edges
# edges
# skills
# 