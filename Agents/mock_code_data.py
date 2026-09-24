"""
Mock Code Artifact for isolated testing and teammate collaboration.
Matches the contract defined in State_definition.py:CodeArtifact.
"""

APP_PY_CODE = '''"""
Internship Platform - Core Application Logic
"""
from typing import List, Dict, Optional
import uuid

class Internship:
    def __init__(self, id: str, title: str, company: str, location: str, description: str):
        self.id = id
        self.title = title
        self.company = company
        self.location = location
        self.description = description

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
        }

class Application:
    def __init__(self, id: str, internship_id: str, student_id: str, resume: str, status: str = "submitted"):
        self.id = id
        self.internship_id = internship_id
        self.student_id = student_id
        self.resume = resume
        self.status = status  # submitted, under_review, accepted, rejected

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "internship_id": self.internship_id,
            "student_id": self.student_id,
            "resume": self.resume,
            "status": self.status,
        }

class InternshipPlatform:
    def __init__(self):
        self.internships: Dict[str, Internship] = {}
        self.applications: Dict[str, Application] = {}

    def post_internship(self, title: str, company: str, location: str, description: str) -> Internship:
        if not title or not company:
            raise ValueError("Title and Company are required fields.")
        internship_id = str(uuid.uuid4())[:8]
        internship = Internship(internship_id, title, company, location, description)
        self.internships[internship_id] = internship
        return internship

    def search_internships(self, query: str = "", location: str = "") -> List[Dict]:
        results = []
        for item in self.internships.values():
            match_query = (not query) or (query.lower() in item.title.lower() or query.lower() in item.description.lower())
            match_loc = (not location) or (location.lower() in item.location.lower())
            if match_query and match_loc:
                results.append(item.to_dict())
        return results

    def apply_for_internship(self, internship_id: str, student_id: str, resume: str) -> Application:
        if internship_id not in self.internships:
            raise KeyError(f"Internship {internship_id} does not exist.")
        if not student_id or not resume:
            raise ValueError("Student ID and resume are required.")
        
        # Check duplicate
        for app in self.applications.values():
            if app.internship_id == internship_id and app.student_id == student_id:
                raise ValueError("Student has already applied for this internship.")

        app_id = str(uuid.uuid4())[:8]
        app = Application(app_id, internship_id, student_id, resume, "submitted")
        self.applications[app_id] = app
        return app

    def update_application_status(self, application_id: str, new_status: str) -> Application:
        valid_statuses = {"submitted", "under_review", "accepted", "rejected"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")
        if application_id not in self.applications:
            raise KeyError(f"Application {application_id} not found.")

        app = self.applications[application_id]
        app.status = new_status
        return app
'''

MOCK_CODE_ARTIFACT = {
    "repo_path": "internship_platform",
    "entrypoint": "app.py",
    "test_command": "python -m unittest discover -s . -p 'test*.py'",
    "dependencies": ["pytest"],
    "files": {
        "app.py": APP_PY_CODE,
    },
    "notes": "Initial implementation of InternshipPlatform, Internship, and Application entities with validation."
}
