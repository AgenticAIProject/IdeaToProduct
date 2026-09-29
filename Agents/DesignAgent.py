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
    category: str = Field(description="Category of choice, e.g. 'backend', 'database', 'frontend', 'cli'")
    technology: str = Field(description="Selected technology name, e.g. 'FastAPI', 'PostgreSQL', 'React'")
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


def generate_design_fallback(requirements: dict) -> DesignDocument:
    """Deterministic fallback for DesignDocument when LLM fails or is unreachable."""
    problem = requirements.get("problem_statement", "Application")
    problem_lower = problem.lower()

    # Determine system type
    if any(k in problem_lower for k in ["frontend", "ui", "dashboard", "visualize", "interface", "web app"]):
        system_type = "Frontend Web Application"
        tech_choices = [
            TechnologyChoice(category="frontend", technology="HTML/CSS/JS", reason="Lightweight responsive client-side interface."),
            TechnologyChoice(category="testing", technology="jest", reason="Standard frontend testing framework.")
        ]
        api_endpoints = []
        data_entities = []
    else:
        system_type = "Backend REST API"
        tech_choices = [
            TechnologyChoice(category="backend", technology="FastAPI", reason="Modern high-performance async Python framework."),
            TechnologyChoice(category="database", technology="SQLite", reason="Self-contained local relational database."),
            TechnologyChoice(category="testing", technology="pytest", reason="Standard Python test framework.")
        ]
        api_endpoints = [
            APIEndpoint(id="EP-01", method="POST", path="/api/items", description="Create a new item", requirement_ids=["FR-01"]),
            APIEndpoint(id="EP-02", method="GET", path="/api/items", description="List all items", requirement_ids=["FR-01"]),
            APIEndpoint(id="EP-03", method="GET", path="/api/items/{id}", description="Get item by ID", requirement_ids=["FR-01"])
        ]
        data_entities = [
            DataEntity(id="ENT-01", name="Item", purpose="Primary data entity", attributes=["id", "title", "created_at"], relationships=[], requirement_ids=["FR-01"])
        ]

    components = [
        DesignComponent(id="COMP-01", name="MainController", responsibility=f"Coordinates core functionality for {problem[:40]}.", requirement_ids=["FR-01"]),
        DesignComponent(id="COMP-02", name="DataService", responsibility="Manages state and operations.", requirement_ids=["FR-01"])
    ]

    decisions = [
        DesignDecision(id="DEC-01", decision="Layered Modular Architecture", reason="Clear separation of concerns.", requirement_ids=["FR-01"])
    ]

    edge_cases = [
        EdgeCase(id="EC-01", description="Empty or invalid input handling.", requirement_ids=["FR-01"], component_ids=["COMP-01"])
    ]

    return DesignDocument(
        system_type=system_type,
        architecture="Layered modular architecture adhering directly to requirement specifications.",
        components=components,
        data_entities=data_entities,
        api_endpoints=api_endpoints,
        external_integrations=[],
        technology_choices=tech_choices,
        design_decisions=decisions,
        edge_cases=edge_cases
    )


def Design_Agent(state: AgentState) -> dict:
    print("\nDesign Agent received requirements")

    requirements = state.get("requirements", {})

    response = None
    try:
        llm = imports.get_llm(agent_type="design", max_tokens=4000)
        design_llm = llm.with_structured_output(DesignDocument)
        design_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/design_prompt.txt"))
        result = design_llm.invoke([
            design_prompt,
            imports.HumanMessage(
                content=f"""Here are the requirements produced by the Requirement Agent:

{requirements}
"""
            )
        ])
        if result and isinstance(result, DesignDocument):
            response = result
        else:
            print("  [Design Agent] Structured response was empty or invalid — activating fallback.")
            response = generate_design_fallback(requirements)
    except Exception as e:
        print(f"  [Design Agent] Design LLM invocation issue: {e}")
        print("  [Design Agent] Activating design-driven fallback...")
        response = generate_design_fallback(requirements)

    design = response.model_dump()

    return {
        "design": design,
        "design_version": state.get("design_version", 0) + 1,
        "current_stage": "design",
        "workflow_status": "running"
    }