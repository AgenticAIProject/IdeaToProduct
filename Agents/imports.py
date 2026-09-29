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


# Check which provider to use
MODELS = {
    "requirement": "openai/gpt-4o-mini",    # working 
    "code": "google/gemma-2-9b-it",  # working 
    "design": "anthropic/claude-haiku-4.5",  # working
    "review": "meta-llama/llama-3.3-70b-instruct",  # working
    "test": "openai/gpt-4o-mini",  # working
    "documentation": "openai/gpt-4o-mini"
}

class GeminiAIMessage:
    def __init__(self, content: str):
        self.content = content

    def __str__(self):
        return self.content


class GeminiStructuredLLM:
    def __init__(self, client, model: str, schema: type, max_tokens: int = 4000):
        self.client = client
        self.model = model
        self.schema = schema
        self.max_tokens = max_tokens

    def invoke(self, messages, config=None, **kwargs):
        prompt_parts = []
        if isinstance(messages, str):
            prompt_parts.append(messages)
        elif isinstance(messages, (list, tuple)):
            for m in messages:
                if hasattr(m, "content"):
                    prompt_parts.append(str(m.content))
                else:
                    prompt_parts.append(str(m))
        else:
            prompt_parts.append(str(messages))

        full_prompt = "\n\n".join(prompt_parts)

        # Fallback order if a model is temporarily unavailable / experiencing high demand
        candidate_models = [self.model, "gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=m,
                    contents=full_prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": self.schema,
                        "max_output_tokens": self.max_tokens,
                        "temperature": 0.2,
                    }
                )
                return self.schema.model_validate_json(response.text)
            except Exception as e:
                last_err = e
                continue
        raise last_err


class GeminiLLMWrapper:
    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite", max_tokens: int = 4000):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def with_structured_output(self, schema, **kwargs):
        return GeminiStructuredLLM(self.client, self.model, schema, self.max_tokens)

    def invoke(self, messages, config=None, **kwargs):
        prompt_parts = []
        if isinstance(messages, str):
            prompt_parts.append(messages)
        elif isinstance(messages, (list, tuple)):
            for m in messages:
                if hasattr(m, "content"):
                    prompt_parts.append(str(m.content))
                else:
                    prompt_parts.append(str(m))
        else:
            prompt_parts.append(str(messages))

        full_prompt = "\n\n".join(prompt_parts)
        candidate_models = [self.model, "gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash"]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_err = None
        for m in models_to_try:
            try:
                res = self.client.models.generate_content(
                    model=m,
                    contents=full_prompt,
                    config={"max_output_tokens": self.max_tokens, "temperature": 0.2}
                )
                return GeminiAIMessage(res.text or "")
            except Exception as e:
                last_err = e
                continue
        raise last_err


def get_llm(agent_type: str = "requirement", max_tokens: int = 4000):
    """Centralized LLM initialization: uses Google Gemini if GEMINI_API_KEY is present, otherwise OpenRouter."""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        preferred_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        return GeminiLLMWrapper(
            api_key=gemini_key,
            model=preferred_model,
            max_tokens=max_tokens
        )

    from langchain_openrouter import ChatOpenRouter
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


