from State_definition import AgentState
from DesignAgent import Design_Agent


state: AgentState = {
    "project_id": "project_001",
    "user_id": "user_001",
    "idea": "Build an internship platform for students",

    "clarification_questions": [],
    "user_answers": [],
    "clarification_round": 2,

    "requirements": {
        "problem_statement": "Students need a centralized platform to discover internships, apply, and track applications.",

        "objectives": [
            "Provide internship discovery and application capabilities.",
            "Allow recruiters to manage internship listings and applications."
        ],

        "actors": [
            "Student",
            "Company Recruiter",
            "System Administrator"
        ],

        "user_stories": [
            "As a Student, I want to search and filter internship listings so that I can find relevant opportunities.",
            "As a Student, I want to apply for internships so that I can submit applications.",
            "As a Student, I want to track my applications so that I know their status.",
            "As a Recruiter, I want to manage internship listings so that I can recruit candidates.",
            "As a Recruiter, I want to review applications so that I can evaluate candidates."
        ],

        "functional_requirements": [
            "Students can search and filter internship listings.",
            "Students can submit applications.",
            "Students can track application status.",
            "Recruiters can create and manage internship listings.",
            "Recruiters can review applications.",
            "Recruiters can update application status."
        ],

        "non_functional_requirements": [],

        "acceptance_criteria": [],

        "constraints": [],
        "assumptions": [],
        "in_scope": [
            "Internship discovery",
            "Internship applications",
            "Application tracking",
            "Recruiter listing management",
            "Recruiter application review"
        ],
        "out_of_scope": [],
        "open_questions": []
    },

    "requirements_version": 1,

    "design": {},
    "design_version": 0,

    "code": {},
    "code_version": 0,

    "test_results": {},
    "test_version": 0,

    "review": {},
    "review_version": 0,

    "documentation": {},
    "documentation_version": 0,

    "current_stage": "requirements",
    "workflow_status": "running",

    "retry_count": {
        "requirements": 0,
        "design": 0,
        "code": 0,
        "test": 0,
        "review": 0
    },

    "approval_status": "pending"
}


print("\n========== DESIGN TEST ==========")

result = Design_Agent(state)

print("\nCurrent stage:")
print(result["current_stage"])

print("\nWorkflow status:")
print(result["workflow_status"])

print("\nDesign:")
print(result["design"])