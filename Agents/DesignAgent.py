import imports
from pydantic import BaseModel, Field
from State_definition import AgentState


class DesignDocument(BaseModel):
    architecture: str

    components: list[str] = Field(default_factory=list)

    data_model: list[str] = Field(default_factory=list)

    api_endpoints: list[str] = Field(default_factory=list)

    decisions: list[str] = Field(default_factory=list)

    edge_cases: list[str] = Field(default_factory=list)


def Design_Agent(state: AgentState) -> AgentState:

    print("\nDesign Agent received requirements")

    requirements = state["requirements"]

    llm = imports.get_llm(max_tokens=3000)

    design_llm = llm.with_structured_output(
        DesignDocument,
        method="json_schema"
    )

    design_prompt = imports.SystemMessage(
        content="""
You are a software architecture and design agent.

Your job is to convert the approved V1 requirements into a
clear implementation-oriented design.

Produce:

1. Architecture
   - Describe the overall system architecture.
   - Explain how the major components interact.

2. Components
   - List the major software components/modules/services.

3. Data model
   - Identify the important entities and their relationships.
   - Describe important fields where useful.

4. API endpoints
   - Define the API surface required to support the V1
     requirements.
   - Map endpoints to the relevant user stories or
     functional requirements where possible.

5. Decisions
   - Record important design decisions.
   - Explain the reason for each decision.
   - If a decision was not specified in the requirements,
     explicitly identify it as a new Design-stage decision.

6. Edge cases
   - Identify important failure cases and boundary conditions
     that the implementation and tests should handle.

IMPORTANT RULES:

- Do NOT implement code.
- Do NOT generate source files.
- Do NOT invent requirements.
- Do NOT silently change the requirements.
- Every major design choice should support an existing
  requirement.
- If the requirements do not specify something necessary for
  implementation, make a reasonable V1 design decision and
  record it explicitly under decisions.
- Keep the design appropriate for a V1 product.
- Avoid unnecessary complexity.
- Do not add features that are outside the stated scope.

Return only the structured design document.
"""
    )

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