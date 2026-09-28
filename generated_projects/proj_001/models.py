from pydantic import BaseModel

class Goal(BaseModel):
    id: int
    title: str
    completed: bool = False
