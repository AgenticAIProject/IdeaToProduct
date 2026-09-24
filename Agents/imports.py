


from pathlib import Path
from State_definition import AgentState
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

load_dotenv(Path(__file__).resolve().parent.parent / ".env")



from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage,HumanMessage,AIMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode




from pydantic import BaseModel, Field

def get_llm(max_tokens: int = 2000) -> ChatOpenRouter:
    """Centralized LLM initialization so the model can be changed in one place."""
    return ChatOpenRouter(
        model="google/gemini-1.5-flash",
        max_tokens=max_tokens
    )

