from langgraph.graph import StateGraph, END
import imports
from State_definition import AgentState
from RequirementAgent import Requirement_Agent
from DesignAgent import Design_Agent
from ReviewAgent import Review_Agent
from TestAgent import Test_Agent
from DocumentationAgent import Documentation_Agent
from ReleaseAgent import Release_Agent
from CodeAgent import Code_Agent


def requirement_node(state: AgentState) -> dict:
    return _run_with_usage("requirement", Requirement_Agent, state)


def design_node(state: AgentState) -> dict:
    return _run_with_usage("design", Design_Agent, state)


def code_node(state: AgentState) -> dict:
    return _run_with_usage("code", Code_Agent, state)


def test_node(state: AgentState) -> dict:
    return _run_with_usage("test", Test_Agent, state)


def review_node(state: AgentState) -> dict:
    return _run_with_usage("review", Review_Agent, state)


def documentation_node(state: AgentState) -> dict:
    return _run_with_usage("documentation", Documentation_Agent, state)


def release_node(state: AgentState) -> dict:
    return Release_Agent(state)


def _run_with_usage(agent_type: str, agent, state: AgentState) -> dict:
    update = agent(state)
    usage = dict(state.get("token_usage", {}))
    usage[agent_type] = imports.get_token_usage(agent_type)
    update["token_usage"] = usage
    return update


def requirement_router(state: AgentState):
    if state["current_stage"] == "clarification":
        return "clarification"

    if state["current_stage"] == "requirements":
        return "design"

    return "design"


def code_router(state: AgentState):
    """If code generation itself failed (provider error, no plan), stop. Testing nothing wastes calls."""
    if state.get("workflow_status") == "failed" or not (state.get("code") or {}).get("files"):
        return "failed"
    return "test"


def review_router(state: AgentState):
    if state.get("approval_status") == "approved":
        return "approved"

    # Code generation runs once per pipeline; preserve the artifacts if review rejects.
    retry_count = state.get("retry_count", {})
    code_retries = retry_count.get("code", 0)
    if code_retries >= 1:
        print("  [Review Router] Code Agent already ran once. Routing rejected artifacts to documentation.")
        return "give_up"

    return "rejected"


def documentation_router(state: AgentState):
    if state.get("approval_status") == "approved":
        return "release"
    return "end"


builder = StateGraph(AgentState)  # pyrefly: ignore[bad-specialization]

builder.add_node("requirement", requirement_node)
builder.add_node("design", design_node)
builder.add_node("code", code_node)
builder.add_node("test", test_node)
builder.add_node("review", review_node)
builder.add_node("documentation", documentation_node)
builder.add_node("release", release_node)

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
builder.add_conditional_edges(
    "code",
    code_router,
    {"failed": END, "test": "test"}
)
builder.add_edge("test", "review")

# Review routes to documentation if approved, loops back to code if rejected
builder.add_conditional_edges(
    "review",
    review_router,
    {
        "approved": "documentation",
        "rejected": "code",
        "give_up": "documentation"
    }
)

builder.add_conditional_edges(
    "documentation",
    documentation_router,
    {
        "release": "release",
        "end": END,
    }
)

builder.add_edge("release", END)

from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)

if __name__ == "__main__":
    print("\n========== LangGraph Workflow Diagram (Mermaid) ==========\n")
    print(graph.get_graph().draw_mermaid())