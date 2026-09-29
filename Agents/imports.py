import os
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from pydantic import BaseModel, Field


MODELS = {
    "requirement": "llama3.2",
    "code": "llama3.2",
    "design": "llama3.2",
    "review": "llama3.2",
    "test": "llama3.2",
    "documentation": "llama3.2"
}

def get_llm(agent_type: str = "requirement", max_tokens: int = 2000):
    """Centralized LLM initialization."""
    return ChatOllama(
        model=MODELS.get(agent_type, "llama3.2"),
        temperature=0.2
    )


def load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / filename
    with open(path, "r") as f:
        return f.read()


def invoke_and_parse(llm, messages, schema):
    structured_llm = llm.with_structured_output(
        schema,
        method="json_schema",
    )
    return structured_llm.invoke(messages)


