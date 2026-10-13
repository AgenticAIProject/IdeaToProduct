import os
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter
from langchain_ollama import ChatOllama

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

# ── Model configuration ──────────────────────────────────────────────────────
# Agents that run on local Ollama (port 11434)
# Code and Documentation generate the highest volume of tokens
OLLAMA_AGENTS = {"code", "documentation"}
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

# If set, also run test agent on local Ollama instead of OpenRouter Account 2
if os.environ.get("TEST_ON_OLLAMA", "").lower() in ("true", "1", "yes"):
    OLLAMA_AGENTS.add("test")

# OpenRouter models. Use an explicit model instead of the dynamic openrouter/free
# alias so structured-output requests are routed consistently.
OPENROUTER_DEFAULT_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free"
)
OPENROUTER_MODELS = {
    "requirement": os.environ.get("REQUIREMENT_MODEL", OPENROUTER_DEFAULT_MODEL),
    "design":      os.environ.get("DESIGN_MODEL", OPENROUTER_DEFAULT_MODEL),
    "test":        os.environ.get("TEST_MODEL", OPENROUTER_DEFAULT_MODEL),
    "review":      os.environ.get("REVIEW_MODEL", OPENROUTER_DEFAULT_MODEL),
}

# Account 2 handles QA & Governance (Test, Review)
# Account 1 handles Upstream Planning (Requirement, Design)
OPENROUTER_ACCOUNT_2_AGENTS = {"test", "review"}


def get_llm(agent_type: str = "requirement", max_tokens: int = 2000):
    """
    Model routing:
      - code, documentation: Local Ollama (qwen2.5-coder:7b)
      - requirement, design: OpenRouter Account 1 (OPENROUTER_API_KEY)
      - test, review:        OpenRouter Account 2 (OPENROUTER_API_KEY2)
    """
    if agent_type in OLLAMA_AGENTS:
        model = OLLAMA_MODEL
        if agent_type == "code":
            model = os.environ.get("CODE_MODEL", model)
        elif agent_type == "test":
            model = os.environ.get("TEST_MODEL", model)
        return ChatOllama(
            model=model,
            base_url=OLLAMA_BASE_URL,
            num_predict=max_tokens,
        )
    else:
        # Route to Account 2 for test & review, Account 1 for requirement & design
        if agent_type in OPENROUTER_ACCOUNT_2_AGENTS:
            api_key = (
                os.environ.get("OPENROUTER_API_KEY2")
                or os.environ.get("OPENROUTER_API_KEY_2")
                or os.environ.get("OPENROUTER_API_KEY")
            )
        else:
            api_key = (
                os.environ.get("OPENROUTER_API_KEY1")
                or os.environ.get("OPENROUTER_API_KEY_1")
                or os.environ.get("OPENROUTER_API_KEY")
            )

        model = OPENROUTER_MODELS.get(agent_type, OPENROUTER_DEFAULT_MODEL)

        return ChatOpenRouter(
            model=model,
            max_tokens=max_tokens,
            openrouter_api_key=api_key,
        )


def load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / filename
    with open(path, "r") as f:
        return f.read()


T = TypeVar("T", bound=BaseModel)


def invoke_structured(llm, schema: Type[T], messages: list, max_retries: int = 3) -> T:
    """
    llm.with_structured_output(schema).invoke() is typed as returning `dict | BaseModel`.
    Normalise it to exactly `schema`, so type checkers (and later code) see the right type,
    and a provider that returns a plain dict still works.
    Retries up to max_retries times if the model returns None (common with free-tier models).
    """
    structured_llm = llm.with_structured_output(schema)
    last_err = None
    for attempt in range(max_retries):
        try:
            result: Any = structured_llm.invoke(messages)
            if result is None:
                print(f"  [invoke_structured] {schema.__name__} returned None (attempt {attempt + 1}/{max_retries}), retrying...")
                continue
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
            raise TypeError(f"Structured output for {schema.__name__} came back as {type(result).__name__}, not a valid object.")
        except TypeError:
            raise
        except Exception as e:
            last_err = e
            print(f"  [invoke_structured] {schema.__name__} error (attempt {attempt + 1}/{max_retries}): {e}")
            continue
    raise RuntimeError(f"Structured output for {schema.__name__} failed after {max_retries} attempts. Last error: {last_err}")


def invoke_and_parse(llm, messages, schema):
    structured_llm = llm.with_structured_output(
        schema,
        method="json_schema",
    )
    return structured_llm.invoke(messages)