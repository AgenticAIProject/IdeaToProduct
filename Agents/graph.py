from langgraph.graph import StateGraph, END
from State_definition import AgentState
from RequirementAgent import Requirement_Agent
from DesignAgent import Design_Agent
from ReviewAgent import Review_Agent
from TestAgent import Test_Agent
from DocumentationAgent import Documentation_Agent
from CodeAgent import Code_Agent


def requirement_node(state: AgentState) -> dict:
    return Requirement_Agent(state)


def design_node(state: AgentState) -> dict:
    return Design_Agent(state)


def code_node(state: AgentState) -> dict:
    return Code_Agent(state)


def test_node(state: AgentState) -> dict:
    return Test_Agent(state)


def review_node(state: AgentState) -> dict:
    return Review_Agent(state)


def documentation_node(state: AgentState) -> dict:
    return Documentation_Agent(state)


def requirement_router(state: AgentState):
    if state["current_stage"] == "clarification":
        return "clarification"

    if state["current_stage"] == "requirements":
        return "design"

    return "design"


def review_router(state: AgentState):
    if state.get("approval_status") == "approved":
        return "approved"
    return "rejected"


builder = StateGraph(AgentState)

builder.add_node("requirement", requirement_node)
builder.add_node("design", design_node)
builder.add_node("code", code_node)
builder.add_node("test", test_node)
builder.add_node("review", review_node)
builder.add_node("documentation", documentation_node)

builder.set_entry_point("requirement")

builder.add_conditional_edges(
    "requirement",
    requirement_router,
    {
        "clarification": END,
        "design": "design"
    }
)

# Flow from design -> code -> test -> review
builder.add_edge("design", "code")
builder.add_edge("code", "test")
builder.add_edge("test", "review")

# Review routes to documentation if approved, loops back to requirement if rejected
builder.add_conditional_edges(
    "review",
    review_router,
    {
        "approved": "documentation",
        "rejected": "requirement"
    }
)

builder.add_edge("documentation", END)

graph = builder.compile()

if __name__ == "__main__":
    print("\n========== LangGraph Workflow Diagram (Mermaid) ==========\n")
    print(graph.get_graph().draw_mermaid())