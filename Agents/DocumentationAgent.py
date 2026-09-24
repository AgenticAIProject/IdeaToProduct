import imports
from pydantic import BaseModel, Field
from State_definition import AgentState, DocumentationArtifact


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

    code_files = code_artifact.get("files", {})
    code_summary = "\n".join(
        [f"- File: `{filename}` ({len(content)} chars)" for filename, content in code_files.items()]
    ) or "No code files provided."

    llm = imports.get_llm(max_tokens=2000)

    doc_llm = llm.with_structured_output(
        DocumentationDocument,
        method="json_schema"
    )

    doc_prompt = imports.SystemMessage(
        content="""
You are an expert Technical Writer and Software Documentation Agent.

Your responsibility is to generate clean, professional, and comprehensive documentation
for a software project based on its approved requirements, system design, source code, and test results.

You must generate:
1. `readme`:
   - Project title & clear problem statement
   - Feature highlights derived from functional requirements
   - Setup, installation, and environment configuration instructions
   - How to run the application and execute tests
2. `api_reference`:
   - Detailed specification of the public API endpoints / core classes / methods
   - Parameter names, types, expected inputs, outputs, and status codes
   - Clear code examples of how to invoke the APIs
3. `architecture_overview`:
   - System design breakdown (components, data models, and relationships)
   - Technical decisions made and their architectural rationale
   - Edge case considerations and failure recovery strategies
4. `user_guide`:
   - Step-by-step user journeys broken down by actors/personas
   - Actionable instructions for using each core capability
5. `changelog`:
   - Clean V1.0.0 release notes summarizing initial launch capabilities and verified tests

RULES:
- Base all documentation directly on the provided project artifacts.
- Do NOT invent features that are not in the requirements, design, or code.
- Format all outputs with clean GitHub-flavored Markdown.
- Return the structured documentation document adhering to the schema.
"""
    )

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

    response: DocumentationDocument = doc_llm.invoke([
        doc_prompt,
        human_prompt
    ])

    documentation_payload: DocumentationArtifact = response.model_dump()

    return {
        "documentation": documentation_payload,
        "documentation_version": state.get("documentation_version", 0) + 1,
        "current_stage": "documentation",
        "workflow_status": "running"
    }
