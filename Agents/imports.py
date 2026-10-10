import os
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

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



MODELS = {
    "requirement":   "anthropic/claude-sonnet-5.5",      # short output, shapes every later stage
    "design":        "anthropic/claude-sonnet-5.5",      # same reason
    "code":          "deepseek/deepseek-v4-pro-0813",    # most tokens, so the cheap coder goes here
    "test":          "z-ai/glm-5.3",                     # different model family from code
    "review":        "openai/gpt-6.1-sol",               # third family; reads code, writes little
    "documentation": "openai/gpt-6-luna",                # low risk, cheapest tier
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


def invoke_and_parse(llm, messages, schema):
    structured_llm = llm.with_structured_output(
        schema,
        method="json_schema",
    )
    return structured_llm.invoke(messages)


