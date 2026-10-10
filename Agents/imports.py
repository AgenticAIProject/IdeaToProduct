import os
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from typing import Any, Type, TypeVar, TypedDict, Annotated, Sequence
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

# "design": "anthropic/claude-haiku-4.5",  #working
#     "review": "meta-llama/llama-3.3-70b-instruct",  #working
#     "test": "openai/gpt-4o-mini",  #working


# MODELS = {
#     "requirement": "openai/gpt-4o-mini",    # working 
#     "code": "openai/gpt-4o-mini",           # working 
#     "design": "openai/gpt-4o-mini",         # working
#     "review": "openai/gpt-4o-mini",         # working
#     "test": "openai/gpt-4o-mini",           # working
#     "documentation": "openai/gpt-4o-mini"
# }


# MODELS = {
#     "requirement":   "google/gemma-4-26b-a4b-it:free",
#     "code":          "meta-llama/llama-3.3-70b-instruct:free",
#     "design":        "google/gemini-2.0-flash-lite-preview-02-05:free",
#     "test":          "meta-llama/llama-3.3-70b-instruct:free",
#     "review":        "meta-llama/llama-3.3-70b-instruct:free",
#     "documentation": "google/gemini-2.0-flash-lite-preview-02-05:free",
# }

MODELS = {
    "requirement":   "openrouter/free",
    "design":        "openrouter/free",
    "code":          "openrouter/free",
    "test":          "openrouter/free",
    "review":        "openrouter/free",
    "documentation": "openrouter/free",
}

def get_llm(agent_type: str = "requirement", max_tokens: int = 2000) -> ChatOpenRouter:
    """Centralized LLM initialization."""
    return ChatOpenRouter(
        model=MODELS.get(agent_type, "openai/gpt-4o-mini"),
        max_tokens=max_tokens
    )


def load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / filename
    with open(path, "r") as f:
        return f.read()


T = TypeVar("T", bound=BaseModel)


def invoke_structured(llm, schema: Type[T], messages: list) -> T:
    """
    llm.with_structured_output(schema).invoke() is typed as returning `dict | BaseModel`.
    Normalise it to exactly `schema`, so type checkers (and later code) see the right type,
    and a provider that returns a plain dict still works.
    """
    result: Any = llm.with_structured_output(schema).invoke(messages)
    if isinstance(result, schema):
        return result
    if isinstance(result, dict):
        return schema.model_validate(result)
    raise TypeError(f"Structured output for {schema.__name__} came back as {type(result).__name__}, not a valid object.")


def invoke_and_parse(llm, messages, schema):
    structured_llm = llm.with_structured_output(
        schema,
        method="json_schema",
    )
    return structured_llm.invoke(messages)