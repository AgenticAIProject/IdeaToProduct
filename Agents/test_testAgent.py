from State_definition import AgentState
from TestAgent import Test_Agent
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

    # Simulated code output from teammate's Code Agent
    "code": MOCK_CODE_ARTIFACT,
    "code_version": 1,

    "test_results": {},
    "test_version": 0,

    "review": {},
    "review_version": 0,

    "documentation": {},
    "documentation_version": 0,

    "current_stage": "code",
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


if __name__ == "__main__":
    print("\n========== TEST AGENT EXECUTION TEST ==========")
    result = Test_Agent(state)

    print("\nCurrent stage:", result.get("current_stage"))
    print("Test version:", result.get("test_version"))
    test_res = result.get("test_results", {})
    print("\nTest Run Success:", test_res.get("success"))
    print("Summary:", test_res.get("summary"))
    print(f"Metrics: {test_res.get('passed_tests')}/{test_res.get('total_tests')} passed, {test_res.get('failed_tests')} failed.")
    print("Duration:", test_res.get("duration_seconds"), "seconds")
    
    print("\nGenerated Test Suites:")
    for name in test_res.get("test_files", {}):
        print(f"- {name}")

    print("\nExecution Output Excerpt:")
    raw = test_res.get("raw_output", "")
    print(raw[:500] if len(raw) > 500 else raw)
