import os
import re
import json
import time
import threading
from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from typing import Any, Literal, Type, TypeVar, TypedDict, Annotated, Sequence
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
# Providers: "deepseek", "groq", "google", "ollama" (default: groq for speed & reliability)
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower().strip()
GOOGLE_MODEL = os.environ.get("GEMINI_MODEL", os.environ.get("GOOGLE_MODEL", "gemini-3.8-flash"))
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_CODE_MODEL = os.environ.get("GROQ_CODE_MODEL", "openai/gpt-oss-120b")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_CODE_MODEL = os.environ.get("DEEPSEEK_CODE_MODEL", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
_ALL_AGENTS = {"requirement", "design", "code", "test", "review", "documentation"}
_RUNTIME_MODELS: dict[str, str] = {}
_TOKEN_USAGE: dict[str, dict[str, int | str]] = {}


class APIKeyPool:
    """Manages a pool of API keys for a provider with rotation and 429 quota/rate-limit backoff."""

    def __init__(self, provider_name: str, env_singles: tuple[str, ...], env_prefixes: tuple[str, ...], default_penalty: float = 300.0):
        self.provider_name = provider_name
        self.env_singles = env_singles
        self.env_prefixes = env_prefixes
        self.default_penalty = default_penalty
        self._lock = threading.Lock()
        self._exhausted_until: dict[str, float] = {}
        self._index = 0

    def get_keys(self) -> list[str]:
        keys: list[str] = []
        for var in self.env_singles:
            val = os.environ.get(var, "").strip()
            if val:
                for k in val.split(","):
                    k = k.strip().strip("'").strip('"')
                    if k and k not in keys:
                        keys.append(k)
        numbered = []
        for var, val in os.environ.items():
            if any(var.startswith(p) for p in self.env_prefixes) and val.strip():
                clean_k = val.strip().strip("'").strip('"')
                if clean_k:
                    numbered.append((var, clean_k))
        numbered.sort(key=lambda x: x[0])
        for _, clean_k in numbered:
            if clean_k not in keys:
                keys.append(clean_k)
        return keys

    def get_active_key(self) -> tuple[str | None, int]:
        """Return (active_key, remaining_active_count)."""
        with self._lock:
            all_keys = self.get_keys()
            if not all_keys:
                return None, 0
            now = time.time()
            available = [k for k in all_keys if self._exhausted_until.get(k, 0) <= now]
            if not available:
                return None, 0
            key = available[self._index % len(available)]
            self._index = (self._index + 1) % len(available)
            return key, len(available)

    def mark_exhausted(self, key: str, penalty_seconds: float | None = None) -> None:
        """Mark a key as quota-exhausted so requests immediately rotate to the next key in pool."""
        penalty = penalty_seconds if penalty_seconds is not None else self.default_penalty
        with self._lock:
            self._exhausted_until[key] = time.time() + penalty
            masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "***"
            now = time.time()
            active_count = sum(1 for k in self.get_keys() if self._exhausted_until.get(k, 0) <= now)
            print(f"  [{self.provider_name} Key Pool] Key {masked} hit quota/429 limit; rotated away for {int(penalty)}s ({active_count} active keys remaining in pool).")

    def reset(self) -> None:
        with self._lock:
            self._exhausted_until.clear()


_GEMINI_KEY_POOL = APIKeyPool(
    provider_name="Gemini",
    env_singles=("GOOGLE_API_KEYS", "GEMINI_API_KEYS", "GOOGLE_API_KEY", "GEMINI_API_KEY"),
    env_prefixes=("GOOGLE_API_KEY_", "GEMINI_API_KEY_"),
    default_penalty=300.0,
)

_GROQ_KEY_POOL = APIKeyPool(
    provider_name="Groq",
    env_singles=("GROQ_API_KEYS", "GROQ_API_KEY"),
    env_prefixes=("GROQ_API_KEY_",),
    default_penalty=90.0,
)

# Compatibility alias
GeminiKeyPool = APIKeyPool


def _default_model_name() -> str:
    if DEFAULT_PROVIDER == "deepseek":
        return DEEPSEEK_MODEL
    elif DEFAULT_PROVIDER == "groq":
        return GROQ_MODEL
    elif DEFAULT_PROVIDER == "google":
        return GOOGLE_MODEL
    return OLLAMA_MODEL


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
        "model": _default_model_name(), "calls": 0,
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
    })
    current["calls"] = int(current["calls"]) + 1
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        current[key] = int(current[key]) + usage[key]


def get_token_usage(agent_type: str) -> dict:
    current = _TOKEN_USAGE.get(agent_type)
    if not current:
        return {
            "model": _default_model_name(), "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        }
    return dict(current)


def _estimate_input_tokens(value: Any) -> int:
    """Approximate prompt tokens when the provider does not return them before invoke."""
    if isinstance(value, list):
        value = "\n".join(str(getattr(item, "content", item)) for item in value)
    return max(1, (len(str(value)) + 3) // 4)


def _log_request(agent_type: str, provider: str, model: str, args: tuple, kwargs: dict, output_limit: int) -> None:
    prompt = args[0] if args else kwargs.get("input", "")
    print(
        f"  [LLM request] agent={agent_type} provider={provider} model={model} "
        f"input~{_estimate_input_tokens(prompt)} output_limit={output_limit}"
    )


class _TrackedRunnable:
    def __init__(self, runnable: Any, agent_type: str, provider: str, model: str, output_limit: int):
        self._runnable = runnable
        self._agent_type = agent_type
        self._provider = provider
        self._model = model
        self._output_limit = output_limit

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        _log_request(self._agent_type, self._provider, self._model, args, kwargs, self._output_limit)
        response = self._runnable.invoke(*args, **kwargs)
        if isinstance(response, dict) and response.get("raw") is not None:
            _record_token_usage(self._agent_type, response["raw"])
            return response.get("parsed")
        _record_token_usage(self._agent_type, response)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runnable, name)


class _TrackedLLM:
    def __init__(self, llm: Any, agent_type: str, provider: str = "google", is_fallback: bool = False, fallback_depth: int = 0):
        self._llm = llm
        self._agent_type = agent_type
        self.provider = provider
        self.is_fallback = is_fallback or (fallback_depth > 0)
        self.fallback_depth = fallback_depth

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        _log_request(
            self._agent_type, self.provider,
            getattr(self._llm, "model", None) or getattr(self._llm, "model_name", "llm"),
            args, kwargs, int(getattr(self._llm, "max_tokens", None) or getattr(self._llm, "max_output_tokens", 0) or getattr(self._llm, "num_predict", 0) or 0),
        )
        try:
            response = self._llm.invoke(*args, **kwargs)
        except Exception as exc:
            if _is_rate_limit_error(exc):
                active_key = getattr(self._llm, "_api_key", None)
                if self.provider == "google":
                    if active_key:
                        _GEMINI_KEY_POOL.mark_exhausted(active_key)
                    next_key, total_active = _GEMINI_KEY_POOL.get_active_key()
                    if next_key and total_active > 0:
                        print(f"  [LLM] Rotating to next Gemini API key in pool ({total_active} active)...")
                        next_llm = get_llm(agent_type=self._agent_type, provider="google", is_fallback=self.is_fallback)
                        return next_llm.invoke(*args, **kwargs)
                elif self.provider == "groq":
                    if active_key:
                        _GROQ_KEY_POOL.mark_exhausted(active_key)
                    next_key, total_active = _GROQ_KEY_POOL.get_active_key()
                    if next_key and total_active > 0:
                        print(f"  [LLM] Rotating to next Groq API key in pool ({total_active} active)...")
                        next_llm = get_llm(agent_type=self._agent_type, provider="groq", is_fallback=self.is_fallback)
                        return next_llm.invoke(*args, **kwargs)
            if self.is_fallback:
                raise
            fallback_llm = _provider_fallback(self)
            if fallback_llm is None:
                raise
            print(f"  [LLM] Provider {self.provider} call failed ({exc}); falling back to {fallback_llm.provider}...")
            return fallback_llm.invoke(*args, **kwargs)
        _record_token_usage(self._agent_type, response)
        return response

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _TrackedRunnable:
        kwargs["include_raw"] = True
        return _TrackedRunnable(
            self._llm.with_structured_output(*args, **kwargs),
            self._agent_type,
            self.provider,
            getattr(self._llm, "model", None) or getattr(self._llm, "model_name", "llm"),
            int(getattr(self._llm, "max_tokens", None) or getattr(self._llm, "max_output_tokens", 0) or getattr(self._llm, "num_predict", 0) or 0),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


def _resolve_agent_provider(agent_type: str) -> str:
    """
    Determine preferred provider for an agent type based on user priority:
    - Code Agent: DeepSeek (primary) -> Groq -> Google
    - Non-coding Agents (Requirement, Design, Test, Review, Docs): Groq (primary) -> Google (secondary) -> DeepSeek (third)
    """
    # Check explicit per-agent environment override:
    env_override = os.environ.get(f"PROVIDER_{agent_type.upper()}")
    if env_override:
        return env_override.lower().strip()

    # Code agent: primary is DeepSeek
    if agent_type == "code":
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
        groq_key, _ = _GROQ_KEY_POOL.get_active_key()
        if groq_key:
            return "groq"
        active_key, _ = _GEMINI_KEY_POOL.get_active_key()
        if active_key:
            return "google"

    # Non-coding agents:
    # 1. Primary Priority: Groq (via 3-key pool)
    groq_key, _ = _GROQ_KEY_POOL.get_active_key()
    if groq_key:
        return "groq"

    # 2. Secondary Priority: Google Gemini (via 4-key pool)
    active_key, _ = _GEMINI_KEY_POOL.get_active_key()
    if active_key:
        return "google"

    # 3. Third Priority: DeepSeek
    if os.environ.get("DEEPSEEK_API_KEY"):
        return "deepseek"

    return DEFAULT_PROVIDER


def get_llm(
    agent_type: str = "requirement",
    max_tokens: int = 4000,
    provider: Literal["google", "ollama", "groq", "deepseek"] | None = None,
    is_fallback: bool = False,
    fallback_depth: int = 0,
):
    """
    Build a tracked LLM with per-agent role routing and fallback resilience.
    - Code Agent defaults to DeepSeek (using DEEPSEEK_CODE_MODEL) when configured.
    - Simple tasks (review, documentation, requirements) default to Groq with Google & DeepSeek fallback.
    - Groq provides ultra-fast generation and multi-key pool fallback.
    """
    if provider is None:
        selected_provider = _resolve_agent_provider(agent_type)
    else:
        selected_provider = provider.lower().strip()

    if selected_provider == "deepseek":
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
        if not deepseek_key:
            groq_key, _ = _GROQ_KEY_POOL.get_active_key()
            if groq_key and not is_fallback:
                print("  [LLM] DEEPSEEK_API_KEY not configured; falling back to Groq.")
                return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="groq", is_fallback=True, fallback_depth=fallback_depth + 1)
            raise RuntimeError(
                "DEEPSEEK_API_KEY is required in your .env file to use DeepSeek models. "
                "Get an API key from https://platform.deepseek.com"
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            print(f"  [LLM] langchain_openai missing ({exc}); falling back to Groq.")
            return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="groq", is_fallback=is_fallback, fallback_depth=fallback_depth + 1)

        if agent_type == "code":
            selected_model = _RUNTIME_MODELS.get(agent_type) or DEEPSEEK_CODE_MODEL
        else:
            selected_model = _RUNTIME_MODELS.get(agent_type) or DEEPSEEK_MODEL

        usage = _TOKEN_USAGE.setdefault(agent_type, {
            "model": selected_model, "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        })
        usage["model"] = selected_model
        return _TrackedLLM(ChatOpenAI(
            model=selected_model,
            api_key=deepseek_key,
            base_url=DEEPSEEK_BASE_URL,
            max_tokens=max_tokens,
            temperature=0,
        ), agent_type, provider="deepseek", is_fallback=is_fallback or (fallback_depth > 0), fallback_depth=fallback_depth)

    if selected_provider == "groq":
        groq_key, total_active = _GROQ_KEY_POOL.get_active_key()
        if not groq_key:
            print("  [LLM] No active Groq keys in pool (all exhausted or none configured); falling back to Google or DeepSeek.")
            active_gkey, _ = _GEMINI_KEY_POOL.get_active_key()
            if active_gkey and not is_fallback:
                return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="google", is_fallback=True, fallback_depth=fallback_depth + 1)
            if os.environ.get("DEEPSEEK_API_KEY") and not is_fallback:
                return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="deepseek", is_fallback=True, fallback_depth=fallback_depth + 1)
            raise RuntimeError(
                "GROQ_API_KEY is required in your .env file to use Groq models. "
                "Get a free API key from https://console.groq.com"
            )
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            print(f"  [LLM] langchain_groq missing ({exc}); falling back to Google Gemini.")
            return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="google", is_fallback=is_fallback, fallback_depth=fallback_depth + 1)

        selected_model = _RUNTIME_MODELS.get(agent_type) or (GROQ_CODE_MODEL if agent_type == "code" else GROQ_MODEL)
        usage = _TOKEN_USAGE.setdefault(agent_type, {
            "model": selected_model, "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        })
        usage["model"] = selected_model
        groq_llm = ChatGroq(
            model=selected_model,
            api_key=groq_key,
            max_tokens=max_tokens,
            temperature=0,
        )
        setattr(groq_llm, "_api_key", groq_key)
        return _TrackedLLM(groq_llm, agent_type, provider="groq", is_fallback=is_fallback or (fallback_depth > 0), fallback_depth=fallback_depth)

    if selected_provider == "google":
        key, total_active = _GEMINI_KEY_POOL.get_active_key()
        if not key:
            print("  [LLM] No active Google Gemini keys in pool (all exhausted or none configured); falling back to Groq / DeepSeek.")
            groq_key, _ = _GROQ_KEY_POOL.get_active_key()
            if groq_key and not is_fallback:
                return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="groq", is_fallback=True, fallback_depth=fallback_depth + 1)
            if os.environ.get("DEEPSEEK_API_KEY") and not is_fallback:
                return get_llm(agent_type=agent_type, max_tokens=max_tokens, provider="deepseek", is_fallback=True, fallback_depth=fallback_depth + 1)
            raise RuntimeError(
                "GEMINI_API_KEY or GOOGLE_API_KEY is required in your .env file to use Google models. "
                "Get a free Gemini API key from https://aistudio.google.com/app/apikey"
            )
        selected_model = _RUNTIME_MODELS.get(agent_type) or GOOGLE_MODEL
        usage = _TOKEN_USAGE.setdefault(agent_type, {
            "model": selected_model, "calls": 0,
            "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        })
        usage["model"] = selected_model
        google_llm = ChatGoogleGenerativeAI(
            model=selected_model,
            google_api_key=key,
            temperature=0,
            max_output_tokens=max_tokens,
            max_retries=1,
            timeout=30.0,
        )
        setattr(google_llm, "_api_key", key)
        return _TrackedLLM(google_llm, agent_type, provider="google", is_fallback=is_fallback or (fallback_depth > 0), fallback_depth=fallback_depth)

    if selected_provider == "ollama":
        if agent_type in _ALL_AGENTS:
            selected_model = _RUNTIME_MODELS.get(agent_type) or OLLAMA_MODEL
            usage = _TOKEN_USAGE.setdefault(agent_type, {
                "model": selected_model, "calls": 0,
                "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
            })
            usage["model"] = selected_model
            num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))
            return _TrackedLLM(ChatOllama(
                model=selected_model,
                base_url=OLLAMA_BASE_URL,
                num_predict=max_tokens,
                num_ctx=num_ctx,
            ), agent_type, provider="ollama", is_fallback=is_fallback or (fallback_depth > 0), fallback_depth=fallback_depth)

    raise ValueError(
        f"Unsupported provider '{selected_provider}' for agent '{agent_type}'. "
        f"Expected one of: 'deepseek', 'groq', 'google', 'ollama'."
    )


def _provider_fallback(llm: Any, max_tokens: int | None = None) -> Any:
    """
    Fallback to alternative provider if active provider fails.
    Priorities:
    - Code Agent: Groq -> Google
    - Non-coding Agents: Google (secondary) -> DeepSeek (third)
    """
    # Allow up to 2 fallbacks in succession (e.g. Groq -> Google -> DeepSeek)
    current_depth = int(getattr(llm, "fallback_depth", 0))
    if current_depth >= 2:
        return None
    next_depth = current_depth + 1

    current_provider = getattr(llm, "provider", None)
    agent_type = getattr(llm, "_agent_type", "code")

    # Code agent priority: Groq first, then Google
    if agent_type == "code":
        if current_provider != "groq":
            active_key, _ = _GROQ_KEY_POOL.get_active_key()
            if active_key:
                print(f"  [LLM fallback] Code agent {current_provider} failed; falling back to Groq (depth {next_depth})...")
                return get_llm(agent_type=agent_type, max_tokens=max_tokens or 4000, provider="groq", is_fallback=True, fallback_depth=next_depth)
        if current_provider != "google":
            active_key, _ = _GEMINI_KEY_POOL.get_active_key()
            if active_key:
                print(f"  [LLM fallback] Code agent {current_provider} failed; falling back to Google Gemini (depth {next_depth})...")
                return get_llm(agent_type=agent_type, max_tokens=max_tokens or 4000, provider="google", is_fallback=True, fallback_depth=next_depth)
        return None

    # Non-coding agents:
    # 1. Secondary Priority: Google Gemini (if current was Groq)
    if current_provider != "google":
        active_key, _ = _GEMINI_KEY_POOL.get_active_key()
        if active_key:
            print(f"  [LLM fallback] {current_provider} failed; falling back to Google Gemini (secondary, depth {next_depth})...")
            return get_llm(agent_type=agent_type, max_tokens=max_tokens or 4000, provider="google", is_fallback=True, fallback_depth=next_depth)

    # 2. Third Priority: DeepSeek (if Google also failed or unavailable)
    if current_provider != "deepseek" and os.environ.get("DEEPSEEK_API_KEY"):
        print(f"  [LLM fallback] {current_provider} failed; falling back to DeepSeek (third, depth {next_depth})...")
        return get_llm(agent_type=agent_type, max_tokens=max_tokens or 4000, provider="deepseek", is_fallback=True, fallback_depth=next_depth)

    # If DeepSeek was the one that somehow failed, fall back to Groq
    if current_provider != "groq":
        active_key, _ = _GROQ_KEY_POOL.get_active_key()
        if active_key:
            print(f"  [LLM fallback] {current_provider} failed; falling back to Groq (depth {next_depth})...")
            return get_llm(agent_type=agent_type, max_tokens=max_tokens or 4000, provider="groq", is_fallback=True, fallback_depth=next_depth)

    return None


def set_runtime_models(models: dict[str, str]) -> None:
    """Update models used by subsequent agent calls without restarting the server."""
    default_mod = _default_model_name()
    for agent_type, model in models.items():
        if agent_type in _ALL_AGENTS:
            _RUNTIME_MODELS[agent_type] = model.strip() if model.strip() else default_mod


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


def _extract_json_from_text(text: Any) -> dict:
    """Extract the first JSON object from raw model text, handling strings, lists, or structured parts."""
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif hasattr(item, "text"):
                parts.append(str(item.text))
            elif hasattr(item, "content"):
                parts.append(str(item.content))
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    elif not isinstance(text, str):
        text = str(text)

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
    """Identify provider quota, rate limits, or transient unavailability (503) to trigger immediate rotation/fallback."""
    status_code = getattr(exc, "status_code", None)
    details = str(exc).lower()
    return (
        status_code in (429, 503, 502, 504)
        or "429" in details
        or "503" in details
        or "unavailable" in details
        or "high demand" in details
        or "too many requests" in details
        or "rate-limited" in details
        or "rate_limit" in details
        or "resource_exhausted" in details
        or "quota" in details
        or "overloaded" in details
    )


def _rate_limit_message(exc: Exception) -> str:
    data = getattr(exc, "data", None)
    metadata = getattr(data, "metadata", None)
    raw = getattr(metadata, "raw", None) if metadata else None
    detail = raw or str(exc)
    return (
        f"Provider rate limit or quota exceeded: {detail}"
    )


def _extract_from_failed_generation(exc: Exception, schema: Type[T]) -> T | None:
    """Salvage valid structured data if provider returned tool_use_failed with failed_generation."""
    try:
        body = getattr(exc, "body", None)
        failed_gen = None
        if isinstance(body, dict):
            failed_gen = body.get("error", {}).get("failed_generation")
        if not failed_gen:
            response = getattr(exc, "response", None)
            if response and hasattr(response, "json"):
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        failed_gen = data.get("error", {}).get("failed_generation")
                except Exception:
                    pass
        if not failed_gen:
            err_str = str(exc)
            idx = err_str.find("'failed_generation': '")
            if idx != -1:
                start = idx + len("'failed_generation': '")
                end = err_str.rfind("'")
                if end > start:
                    raw_str = err_str[start:end]
                    try:
                        failed_gen = bytes(raw_str, "utf-8").decode("unicode_escape")
                    except Exception:
                        failed_gen = raw_str
        if failed_gen:
            parsed = _extract_json_from_text(failed_gen)
            if isinstance(parsed, dict) and "arguments" in parsed and isinstance(parsed["arguments"], dict):
                parsed = parsed["arguments"]
            validated = schema.model_validate(parsed)
            print(f"  [invoke_structured] Successfully salvaged complete structured data from provider failed_generation!")
            return validated
    except Exception as e:
        print(f"  [invoke_structured] Salvage from failed_generation skipped: {e}")
    return None


def _handle_structured_rate_limit_or_fallback(
    llm: Any,
    schema: Type[T],
    messages: list,
    max_retries: int,
    exc: Exception,
) -> T:
    provider = getattr(llm, "provider", None)
    raw_llm = getattr(llm, "_llm", llm)
    active_key = getattr(raw_llm, "_api_key", None)
    agent_type = getattr(llm, "_agent_type", "requirement")

    if provider == "google":
        if active_key:
            _GEMINI_KEY_POOL.mark_exhausted(active_key)
        next_key, total_active = _GEMINI_KEY_POOL.get_active_key()
        if next_key and total_active > 0:
            print(f"  [invoke_structured] Rotating to next Gemini API key in pool ({total_active} active)...")
            next_llm = get_llm(agent_type=agent_type, provider="google")
            return invoke_structured(next_llm, schema, messages, max_retries=max_retries)
    elif provider == "groq":
        if active_key:
            _GROQ_KEY_POOL.mark_exhausted(active_key)
        next_key, total_active = _GROQ_KEY_POOL.get_active_key()
        if next_key and total_active > 0:
            print(f"  [invoke_structured] Rotating to next Groq API key in pool ({total_active} active)...")
            next_llm = get_llm(agent_type=agent_type, provider="groq")
            return invoke_structured(next_llm, schema, messages, max_retries=max_retries)

    fallback_llm = _provider_fallback(llm)
    if fallback_llm is not None:
        print(f"  [invoke_structured] Provider {provider} rate-limited; falling back to {fallback_llm.provider}...")
        return invoke_structured(fallback_llm, schema, messages, max_retries=max_retries)
    raise RuntimeError(_rate_limit_message(exc)) from exc


def invoke_structured(llm, schema: Type[T], messages: list, max_retries: int = 2) -> T:
    """
    Try native structured output first, then ask the same model for plain JSON.
    The JSON path supports models that do not implement tool calling.
    Handles automatic rotation across Gemini key pool, Groq key pool, and graceful provider fallback.
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
                    return _handle_structured_rate_limit_or_fallback(llm, schema, messages, max_retries, exc)
                salvaged = _extract_from_failed_generation(exc, schema)
                if salvaged is not None:
                    return salvaged
                last_err = exc
                print(f"  [invoke_structured] native attempt {attempt + 1}/{max_retries} failed: {exc}")
    except Exception as exc:
        if _is_rate_limit_error(exc):
            return _handle_structured_rate_limit_or_fallback(llm, schema, messages, max_retries, exc)
        salvaged = _extract_from_failed_generation(exc, schema)
        if salvaged is not None:
            return salvaged
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
                return _handle_structured_rate_limit_or_fallback(llm, schema, messages, max_retries, exc)
            last_err = exc
            print(f"  [invoke_structured] JSON fallback attempt {attempt + 1}/{max_retries} failed: {exc}")

    fallback_llm = _provider_fallback(llm)
    if fallback_llm is not None:
        print("  [invoke_structured] Provider failed; falling back to alternative provider.")
        return invoke_structured(fallback_llm, schema, messages, max_retries=max_retries)

    raise RuntimeError(
        f"Structured output for {schema.__name__} failed after native and JSON strategies. "
        f"Last error: {last_err}"
    )


def invoke_and_parse(llm, messages, schema):
    return invoke_structured(llm, schema, messages)