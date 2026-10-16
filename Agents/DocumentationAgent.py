import imports
from pydantic import BaseModel, Field
from State_definition import AgentState


class DocumentationDocument(BaseModel):
    readme: str = Field(
        description="Comprehensive project README in Markdown. Include only facts supported by the supplied artifacts: problem statement, V1 features, setup, exact run command, exact test command, testing status, and known issues."
    )
    api_reference: str = Field(
        description="Detailed API and module reference in Markdown. Document only endpoints, functions, classes, arguments, and response models visible in the supplied design and source code. For frontend-only projects, document public UI behavior instead of inventing APIs."
    )
    architecture_overview: str = Field(
        description="Technical architecture document in Markdown. Explain only the supplied components, interactions, data entities, technologies, decisions, and edge cases. Do not invent components or infrastructure."
    )
    
    user_guide: str = Field(
        description="User-facing Markdown guide organized only around the supplied actors and implemented V1 workflows. Do not invent personas or capabilities."
    )
    changelog: str = Field(
        description="Markdown V1.0.0 changelog based only on implemented features and actual test/review status. Never claim all tests passed unless test_results confirms it."
    )


def Documentation_Agent(state: AgentState) -> dict:
    """
    Documentation Agent (Stage 6):
    Consumes approved project artifacts (Requirements, Design, Code, Test Results)
    and synthesizes comprehensive user-facing and technical documentation.
    """
    print("\nDocumentation Agent synthesizing project documentation...")

    idea = state.get("idea", "")
    requirements = state.get("requirements", {})
    design = state.get("design", {})
    code_artifact = state.get("code", {})
    test_results = state.get("test_results", {})
    review = state.get("review", {})

    code_files = code_artifact.get("files", [])
    if isinstance(code_files, list):
        code_summary = "\n\n".join(
            f"""--- File: `{f.get('path', '')}` ---
Description: {f.get('description', '')}
Exports: {f.get('exports', [])}
Requirement IDs: {f.get('requirement_ids', [])}
Source:
{(f.get('content') or '')[:12000]}"""
            for f in code_files if isinstance(f, dict)
        )
    elif isinstance(code_files, dict):
        code_summary = "\n".join(
            [f"- File: `{filename}` ({len(content)} chars)" for filename, content in code_files.items()]
        )
    else:
        code_summary = ""
    code_summary = code_summary or "No code files provided."

    llm = imports.get_llm(agent_type="documentation", max_tokens=5000)

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

=== RUN AND TEST COMMANDS ===
Run command: {code_artifact.get("setup_instructions", "")}
Test command: {code_artifact.get("test_command", "")}
Dependencies: {code_artifact.get("dependencies", [])}
Implementation notes: {code_artifact.get("implementation_notes", [])}

=== TEST RESULTS ===
{test_results}

=== REVIEW FINDINGS ===
{review}

Generate the complete project documentation package. Treat the supplied
requirements, design, source, test results, and review as authoritative.
Do not fill missing facts with guesses; say "Not specified" or "Not applicable"
when the artifacts do not provide the information.
"""
    )

    response = imports.invoke_structured(llm, DocumentationDocument, [
        doc_prompt,
        human_prompt
    ])

    documentation_payload: dict = response.model_dump()

    # ---------------------------------------------------------
    # Persist documentation files to the generated project folder
    # ---------------------------------------------------------
    from pathlib import Path

    project_id = state.get("project_id") or "project"
    generated_project_path = state.get("generated_project_path")
    project_dir = Path(generated_project_path) if generated_project_path else None
    if project_dir is None or not project_dir.exists():
        project_dir = Path(__file__).resolve().parent.parent / "generated_projects" / project_id

    project_dir.mkdir(parents=True, exist_ok=True)

    written_doc_files: list[str] = []

    if response.readme:
        readme_path = project_dir / "README.md"
        readme_path.write_text(response.readme, encoding="utf-8")
        written_doc_files.append("README.md")

    if response.api_reference:
        api_path = project_dir / "API_REFERENCE.md"
        api_path.write_text(response.api_reference, encoding="utf-8")
        written_doc_files.append("API_REFERENCE.md")

    if response.architecture_overview:
        arch_path = project_dir / "ARCHITECTURE.md"
        arch_path.write_text(response.architecture_overview, encoding="utf-8")
        written_doc_files.append("ARCHITECTURE.md")

    if response.user_guide:
        user_guide_path = project_dir / "USER_GUIDE.md"
        user_guide_path.write_text(response.user_guide, encoding="utf-8")
        written_doc_files.append("USER_GUIDE.md")

    if response.changelog:
        changelog_path = project_dir / "CHANGELOG.md"
        changelog_path.write_text(response.changelog, encoding="utf-8")
        written_doc_files.append("CHANGELOG.md")

    documentation_payload["files_written"] = written_doc_files
    documentation_payload["project_dir"] = str(project_dir)

    print(f"  [Documentation Agent] Wrote {len(written_doc_files)} documentation files to: {project_dir}")
    for doc_name in written_doc_files:
        print(f"    - {doc_name}")

    return {
        "documentation": documentation_payload,
        "documentation_version": state.get("documentation_version", 0) + 1,
        "current_stage": "documentation",
        "workflow_status": "running"
    }