"""
schemas.py - Pydantic request and response schemas.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ItemCreate(BaseModel):
    title: str
    category: Optional[str] = "general"
    description: Optional[str] = ""
    status: Optional[str] = "active"


class ItemResponse(ItemCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: str
    email: str
    role: Optional[str] = "user"


class UserResponse(UserCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
