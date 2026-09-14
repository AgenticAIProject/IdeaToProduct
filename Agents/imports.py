


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