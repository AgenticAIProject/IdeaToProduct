from langgraph.graph import StateGraph, END

from State_definition import AgentState
from RequirementAgent import Requirement_Agent
from DesignAgent import Design_Agent


def requirement_node(state: AgentState) -> AgentState:
    return Requirement_Agent(state)


def design_node(state: AgentState) -> AgentState:
    return Design_Agent(state)


def requirement_router(state: AgentState):

    if state["current_stage"] == "clarification":
        return "clarification"

    if state["current_stage"] == "requirements":
        return "design"

    return "design"


builder = StateGraph(AgentState)

builder.add_node("requirement", requirement_node)
builder.add_node("design", design_node)

builder.set_entry_point("requirement")

builder.add_conditional_edges(
    "requirement",
    requirement_router,
    {
        "clarification": END,
        "design": "design"
    }
)

builder.add_edge("design", END)

graph = builder.compile()