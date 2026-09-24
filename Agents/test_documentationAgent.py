from State_definition import AgentState
from DocumentationAgent import Documentation_Agent
from mock_code_data import MOCK_CODE_ARTIFACT


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
        "actors": ["Student", "Company Recruiter"],
        "user_stories": [
            "As a Student, I want to search and filter internship listings.",
            "As a Student, I want to apply for internships.",
            "As a Recruiter, I want to manage internship listings and update application status."
        ],
        "functional_requirements": [
            "Students can search and filter internship listings.",
            "Students can submit applications.",
            "Recruiters can post internships and update application status."
        ],
        "acceptance_criteria": [
            "Searching with empty query returns all postings.",
            "Applying with empty student_id raises ValueError.",
            "Duplicate applications for the same internship are rejected.",
            "Updating to an invalid status raises ValueError."
        ],
        "constraints": [],
        "assumptions": [],
        "in_scope": ["Internship discovery", "Application submission", "Status management"],
        "out_of_scope": ["Payment processing"],
        "open_questions": []
    },
    "requirements_version": 1,

    "design": {
        "architecture": "Modular single-package service with in-memory store.",
        "components": ["InternshipPlatform", "Internship", "Application"],
        "data_model": [
            "Internship(id, title, company, location, description)",
            "Application(id, internship_id, student_id, resume, status)"
        ],
        "api_endpoints": [
            "post_internship(title, company, location, description)",
            "search_internships(query, location)",
            "apply_for_internship(internship_id, student_id, resume)",
            "update_application_status(application_id, new_status)"
        ],
        "decisions": ["Use in-memory dictionary storage for V1 simplicity."],
        "edge_cases": [
            "Applying to non-existent internship raises KeyError.",
            "Duplicate applications raise ValueError.",
            "Invalid status update raises ValueError."
        ]
    },
    "design_version": 1,

    "code": MOCK_CODE_ARTIFACT,
    "code_version": 1,

    "test_results": {
        "success": True,
        "total_tests": 4,
        "passed_tests": 4,
        "failed_tests": 0,
        "errors": [],
        "raw_output": "Ran 4 tests in 0.003s\nOK",
        "summary": "All 4 tests passed successfully.",
        "duration_seconds": 0.45
    },
    "test_version": 1,

    "review": {
        "verdict": "APPROVED",
        "summary": "Project implementation accurately reflects all functional requirements and passes unit tests.",
        "strengths": ["Clean modular entities", "Edge cases properly validated"],
        "issues": [],
        "recommendations": ["Consider adding persistent database storage in V2."]
    },
    "review_version": 1,

    "documentation": {},
    "documentation_version": 0,

    "current_stage": "review",
    "workflow_status": "running",

    "retry_count": {
        "requirements": 0,
        "design": 0,
        "code": 0,
        "test": 0,
        "review": 0
    },

    "approval_status": "approved"
}


if __name__ == "__main__":
    print("\n========== DOCUMENTATION AGENT TEST ==========")
    result = Documentation_Agent(state)

    print("\nCurrent stage:", result.get("current_stage"))
    print("Documentation version:", result.get("documentation_version"))
    docs = result.get("documentation", {})

    print("\n----- README.MD EXCERPT -----")
    readme = docs.get("readme", "")
    print(readme[:600] + "..." if len(readme) > 600 else readme)

    print("\n----- API REFERENCE EXCERPT -----")
    api = docs.get("api_reference", "")
    print(api[:500] + "..." if len(api) > 500 else api)

    print("\n----- USER GUIDE EXCERPT -----")
    guide = docs.get("user_guide", "")
    print(guide[:500] + "..." if len(guide) > 500 else guide)

    print("\n----- CHANGELOG EXCERPT -----")
    changelog = docs.get("changelog", "")
    print(changelog[:400] + "..." if len(changelog) > 400 else changelog)
