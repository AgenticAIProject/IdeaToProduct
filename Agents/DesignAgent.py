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


class DesignDocument(BaseModel):
    system_type: str = Field(
        description="Type of system being built, e.g. 'full-stack web app', 'CLI tool', 'frontend-only SPA', 'REST API'."
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

    return {
        "design": design,
        "design_version": state["design_version"] + 1,
        "current_stage": "design",
        "workflow_status": "running"
    }