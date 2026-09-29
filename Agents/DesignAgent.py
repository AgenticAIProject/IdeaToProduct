import imports
from pydantic import BaseModel, Field
from State_definition import AgentState

class DesignComponent(BaseModel):
    id: str
    name: str
    responsibility: str
    requirement_ids: list[str] = Field(default_factory=list)


class DataEntity(BaseModel):
    id: str
    name: str
    purpose: str
    attributes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class APIEndpoint(BaseModel):
    id: str
    method: str
    path: str
    description: str
    requirement_ids: list[str] = Field(default_factory=list)


class DesignDecision(BaseModel):
    id: str
    decision: str
    reason: str
    requirement_ids: list[str] = Field(default_factory=list)


class EdgeCase(BaseModel):
    id: str
    description: str
    requirement_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)


class TechnologyChoice(BaseModel):
    category: str = Field(description="Category of choice, e.g. 'frontend', 'backend', 'database', 'cli', 'testing'")
    technology: str = Field(description="Selected technology name: Frontend ('HTML/CSS/JS', 'React'), Backend ('FastAPI', 'Flask', 'Django', 'Python CLI', 'Pandas'), Database ('SQLite', 'PostgreSQL', 'MySQL', 'MongoDB', 'LocalStorage', or 'None')")
    reason: str = Field(description="Reason for selection")


class DesignDocument(BaseModel):
    system_type: str = Field(
        description="Type of system being built, e.g. 'Frontend web application', 'Backend REST API', 'CLI application', 'Data processing application'."
    )

    architecture: str = Field(
        description="High-level architecture description: major parts, responsibilities, and how they interact."
    )

    components: list[DesignComponent] = Field(
        default_factory=list
    )

    data_entities: list[DataEntity] = Field(
        default_factory=list
    )

    api_endpoints: list[APIEndpoint] = Field(
        default_factory=list
    )

    external_integrations: list[str] = Field(
        default_factory=list
    )

    technology_choices: list[TechnologyChoice] = Field(
        default_factory=list
    )

    design_decisions: list[DesignDecision] = Field(
        default_factory=list
    )

    edge_cases: list[EdgeCase] = Field(
        default_factory=list
    )


def Design_Agent(state: AgentState) -> AgentState:
    print("\nDesign Agent received requirements")

    requirements = state["requirements"]

    llm = imports.get_llm(agent_type="design", max_tokens=4000)

    design_llm = llm.with_structured_output(
        DesignDocument,
    )

    design_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/design_prompt.txt"))
    response = design_llm.invoke([
        design_prompt,
        imports.HumanMessage(
            content=f"""Here are the requirements produced by the Requirement Agent:

{requirements}
"""
        )
    ])

    design = response.model_dump()

    try:
        from tools import save_stage_artifact, format_design_md
        pid = state.get("project_id", "project_default")
        md_content = format_design_md(pid, design)
        save_stage_artifact(pid, "2_design", design, md_content)
    except Exception as e:
        print(f"  [Artifact] Warning saving design artifact: {e}")

    return {
        "design": design,
        "design_version": state["design_version"] + 1,
        "current_stage": "design",
        "workflow_status": "running"
    }