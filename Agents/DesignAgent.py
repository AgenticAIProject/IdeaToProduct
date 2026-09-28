import imports
from pydantic import BaseModel, Field
from State_definition import AgentState


class DesignComponent(BaseModel):
    name: str = Field(description="Component name, e.g. 'GoalService'")
    responsibility: str = Field(description="What this component does")
    requirement_ids: list[str] = Field(default_factory=list, description="FR IDs this component implements, e.g. ['FR-01', 'FR-02']")


class APIEndpoint(BaseModel):
    method: str = Field(description="HTTP method: GET, POST, PUT, DELETE")
    path: str = Field(description="Route path, e.g. /api/goals")
    description: str = Field(description="What this endpoint does")
    requirement_ids: list[str] = Field(default_factory=list, description="FR IDs this endpoint satisfies")


class DesignDocument(BaseModel):
    architecture: str = Field(description="High-level architecture description")
    components: list[DesignComponent] = Field(default_factory=list)
    data_model: list[str] = Field(default_factory=list)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)


def Design_Agent(state: AgentState) -> AgentState:

    print("\nDesign Agent received requirements")

    requirements = state["requirements"]

    llm = imports.get_llm(agent_type="design", max_tokens=3000)

    design_llm = llm.with_structured_output(
        DesignDocument,
        
    )

    design_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/design_prompt.txt"))

    response = design_llm.invoke([
        design_prompt,
        imports.HumanMessage(
            content=f"""
Here are the requirements produced by the Requirement Agent:

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