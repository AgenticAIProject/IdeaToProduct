import imports
from pydantic import BaseModel, Field
from State_definition import AgentState


class DocumentationDocument(BaseModel):
    readme: str = Field(
        description="Comprehensive project README in Markdown. Includes Overview, Key Features, Setup & Installation, Quickstart Guide, and Testing Instructions."
    )
    api_reference: str = Field(
        description="Detailed API and module reference in Markdown. Documents all endpoints, functions, classes, arguments, and response models."
    )
    architecture_overview: str = Field(
        description="Technical architecture document in Markdown. Explains system components, interactions, data models, and decisions."
    )
    user_guide: str = Field(
        description="User-facing guide organized by target personas (e.g., Students, Recruiters) detailing end-to-end workflows."
    )
    changelog: str = Field(
        description="Version 1.0.0 Changelog and release summary in Markdown."
    )


def Documentation_Agent(state: AgentState) -> dict:
    """
    Documentation Agent (Stage 6):
    Consumes approved project artifacts (Requirements, Design, Code, Test Results)
    and synthesizes comprehensive user-facing and technical documentation.
    """
    print("\nDocumentation Agent synthesizing project documentation...")

    # Governance check: verify if the project was rejected in review
    approval_status = state.get("approval_status", "approved")
    if approval_status == "rejected":
        print("Warning: Documentation Agent invoked on a rejected project.")
        return {
            "documentation": {
                "readme": "# Project Status: Review Rejected\n\nDocumentation generation blocked due to failed review.",
                "api_reference": "",
                "architecture_overview": "",
                "user_guide": "",
                "changelog": ""
            },
            "documentation_version": state.get("documentation_version", 0) + 1,
            "current_stage": "documentation",
            "workflow_status": "blocked_by_governance"
        }

    idea = state.get("idea", "")
    requirements = state.get("requirements", {})
    design = state.get("design", {})
    code_artifact = state.get("code", {})
    test_results = state.get("test_results", {})
    review = state.get("review", {})

    code_files = code_artifact.get("files", [])
    if isinstance(code_files, list):
        code_summary = "\n".join(
            [f"- File: `{f.get('path', '')}` ({len(f.get('content', ''))} chars)" for f in code_files if isinstance(f, dict)]
        )
    elif isinstance(code_files, dict):
        code_summary = "\n".join(
            [f"- File: `{filename}` ({len(content)} chars)" for filename, content in code_files.items()]
        )
    else:
        code_summary = ""
    code_summary = code_summary or "No code files provided."

    llm = imports.get_llm(agent_type="documentation", max_tokens=2000)

    doc_llm = llm.with_structured_output(
        DocumentationDocument,
        
    )

    doc_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/documentation_prompt.txt"))

    human_prompt = imports.HumanMessage(
        content=f"""
=== PROJECT IDEA ===
{idea}

=== REQUIREMENTS ===
{requirements}

=== SYSTEM DESIGN ===
{design}

=== SOURCE CODE FILES ===
{code_summary}

=== TEST RESULTS ===
{test_results}

=== REVIEW FINDINGS ===
{review}

Generate the complete project documentation package.
"""
    )

    try:
        response: DocumentationDocument = doc_llm.invoke([
            doc_prompt,
            human_prompt
        ])
        documentation_payload: dict = response.model_dump()
    except Exception as e:
        print(f"  [Doc Agent] LLM failed to generate structured DocumentationDocument: {e} - using fallback docs.")
        documentation_payload = {
            "readme": f"# {idea.capitalize()}\n\nAutomated software generation completed.",
            "api_reference": "## API Endpoints\n- GET /api/health",
            "architecture_overview": "FastAPI + SQLite architecture.",
            "user_guide": "Refer to README.md for setup instructions.",
            "changelog": "v1.0.0 Initial Release"
        }

    return {
        "documentation": documentation_payload,
        "documentation_version": state.get("documentation_version", 0) + 1,
        "current_stage": "documentation",
        "workflow_status": "running"
    }
