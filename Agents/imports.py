import os
import re
import json
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
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
# Every LLM-backed agent uses the local Ollama coding model.
OLLAMA_AGENTS = {"requirement", "design", "code", "test", "review", "documentation"}
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
_RUNTIME_MODELS: dict[str, str] = {}
_TOKEN_USAGE: dict[str, dict[str, int | str]] = {}


def _usage_from_response(response: Any) -> dict[str, int]:
    """Read token counters from provider-specific LangChain response metadata."""
    metadata = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    usage = metadata or response_metadata.get("usage", {}) or response_metadata

    def number(*keys: str) -> int:
        for key in keys:
            value = usage.get(key) if isinstance(usage, dict) else None
            if isinstance(value, (int, float)):
                return int(value)
        return 0

    input_tokens = number("input_tokens", "prompt_tokens", "prompt_eval_count")
    output_tokens = number("output_tokens", "completion_tokens", "eval_count")
    total_tokens = number("total_tokens")
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens or input_tokens + output_tokens,
    }


def _record_token_usage(agent_type: str, response: Any) -> None:
    usage = _usage_from_response(response)
    current = _TOKEN_USAGE.setdefault(agent_type, {
        "model": OLLAMA_MODEL, "calls": 0,
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
    })
    current["calls"] = int(current["calls"]) + 1
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        current[key] = int(current[key]) + usage[key]


def get_token_usage(agent_type: str) -> dict:
    current = _TOKEN_USAGE.get(agent_type)
    if not current:
        return {
            "model": OLLAMA_MODEL, "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        }
    return dict(current)


class _TrackedRunnable:
    def __init__(self, runnable: Any, agent_type: str):
        self._runnable = runnable
        self._agent_type = agent_type

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        response = self._runnable.invoke(*args, **kwargs)
        if isinstance(response, dict) and response.get("raw") is not None:
            _record_token_usage(self._agent_type, response["raw"])
            return response.get("parsed")
        _record_token_usage(self._agent_type, response)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runnable, name)


class _TrackedLLM:
    def __init__(self, llm: Any, agent_type: str):
        self._llm = llm
        self._agent_type = agent_type

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        response = self._llm.invoke(*args, **kwargs)
        _record_token_usage(self._agent_type, response)
        return response

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _TrackedRunnable:
        kwargs["include_raw"] = True
        return _TrackedRunnable(
            self._llm.with_structured_output(*args, **kwargs),
            self._agent_type,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def get_llm(agent_type: str = "requirement", max_tokens: int = 4000):
    """
    All LLM-backed agents: local Ollama
    """
    if agent_type in OLLAMA_AGENTS:
        selected_model = _RUNTIME_MODELS.get(agent_type) or OLLAMA_MODEL
        usage = _TOKEN_USAGE.setdefault(agent_type, {
            "model": selected_model, "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        })
        usage["model"] = selected_model
        return _TrackedLLM(ChatOllama(
            model=selected_model,
            base_url=OLLAMA_BASE_URL,
            num_predict=max_tokens,
        ), agent_type)

    raise ValueError(
        f"Unknown agent type '{agent_type}'. Expected one of: {sorted(OLLAMA_AGENTS)}"
    )


def set_runtime_models(models: dict[str, str]) -> None:
    """Update models used by subsequent agent calls without restarting the server."""
    for agent_type, model in models.items():
        if agent_type in OLLAMA_AGENTS:
            _RUNTIME_MODELS[agent_type] = model.strip() if model.strip() else OLLAMA_MODEL


def load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / filename
    with open(path, "r") as f:
        return f.read()


T = TypeVar("T", bound=BaseModel)


def _json_schema_hint(schema: Type[BaseModel]) -> str:
    """Build a compact JSON schema hint to inject into a prompt fallback."""
    try:
        return json.dumps(schema.model_json_schema(), indent=2)
    except Exception:
        return str(schema)


def _extract_json_from_text(text: str) -> dict:
    """Extract the first JSON object from raw model text."""
    # Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    # First { ... } block
    brace = re.search(r"(\{[\s\S]*\})", text)
    if brace:
        try:
            return json.loads(brace.group(1))
        except Exception:
            pass
    raise ValueError(f"No valid JSON found in model output:\n{text[:500]}")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Identify provider or model-pool rate limits before retrying needlessly."""
    status_code = getattr(exc, "status_code", None)
    details = str(exc).lower()
    return status_code == 429 or "too many requests" in details or "rate-limited" in details


def _rate_limit_message(exc: Exception) -> str:
    data = getattr(exc, "data", None)
    metadata = getattr(data, "metadata", None)
    raw = getattr(metadata, "raw", None) if metadata else None
    detail = raw or str(exc)
    return (
        "OpenRouter rate limit for google/gemma-4-26b-a4b-it:free. "
        f"{detail}"
    )


def invoke_structured(llm, schema: Type[T], messages: list, max_retries: int = 3) -> T:
    """
    Try native structured output first, then ask the same model for plain JSON.
    The JSON path supports models that do not implement tool calling.
    """
    last_err = None
    schema_hint = _json_schema_hint(schema)
    fallback_instruction = SystemMessage(content=(
        "IMPORTANT: You must respond with ONLY a valid JSON object matching "
        "the schema below. No explanation, no markdown, no code fences — "
        f"just the raw JSON object.\n\nSchema:\n{schema_hint}"
    ))
    fallback_messages = [fallback_instruction] + list(messages)

    model_name = getattr(llm, "model", "") or getattr(llm, "model_name", "llm")
    print(f"  [invoke_structured] Trying model: {model_name}")

    try:
        structured_llm = llm.with_structured_output(schema)
        for attempt in range(max_retries):
            try:
                result: Any = structured_llm.invoke(messages)
                if isinstance(result, schema):
                    return result
                if isinstance(result, dict):
                    return schema.model_validate(result)
                last_err = ValueError("Structured output was empty or invalid.")
            except TypeError:
                raise
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise RuntimeError(_rate_limit_message(exc)) from exc
                last_err = exc
                print(f"  [invoke_structured] native attempt {attempt + 1}/{max_retries} failed: {exc}")
    except Exception as exc:
        if _is_rate_limit_error(exc):
            raise RuntimeError(_rate_limit_message(exc)) from exc
        last_err = exc
        print(f"  [invoke_structured] native strategy unavailable: {exc}")

    print(f"  [invoke_structured] Falling back to JSON prompt mode for {schema.__name__}...")
    for attempt in range(max_retries):
        try:
            raw = llm.invoke(fallback_messages)
            text = raw.content if hasattr(raw, "content") else str(raw)
            return schema.model_validate(_extract_json_from_text(text))
        except Exception as exc:
            if _is_rate_limit_error(exc):
                raise RuntimeError(_rate_limit_message(exc)) from exc
            last_err = exc
            print(f"  [invoke_structured] JSON fallback attempt {attempt + 1}/{max_retries} failed: {exc}")

    raise RuntimeError(
        f"Structured output for {schema.__name__} failed after native and JSON strategies. "
        f"Last error: {last_err}"
    )


def invoke_and_parse(llm, messages, schema):
    return invoke_structured(llm, schema, messages)