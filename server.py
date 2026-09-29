import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add Agents to path
sys.path.append(str(Path(__file__).parent / "Agents"))

try:
    from Agents.graph import graph
except Exception as e:
    print(f"Error loading graph: {e}")
    graph = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class IdeaRequest(BaseModel):
    idea: str

@app.post("/api/launch")
def launch_pipeline(req: IdeaRequest):

    if not graph:
        raise HTTPException(status_code=500, detail="Graph failed to load.")
        
    initial_state = {
        "project_id": "proj_001",
        "user_id": "user_001",
        "idea": req.idea,
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 2, # Bypass clarification to ensure continuous run
        "requirements": {},
        "requirements_version": 0,
        "design": {},
        "design_version": 0,
        "code": {},
        "code_version": 0,
        "test_results": {},
        "test_version": 0,
        "review": {},
        "review_version": 0,
        "documentation": {},
        "documentation_version": 0,
        "current_stage": "requirements",
        "workflow_status": "starting",
        "retry_count": { "requirements": 0, "design": 0, "code": 0, "test": 0, "review": 0 },
        "approval_status": "pending"
    }
    
    config = {
        "configurable": {"thread_id": "api_session"},
        "recursion_limit": 15
    }
    
    try:
        result = graph.invoke(initial_state, config=config)
        return {
            "status": "success",
            "requirements": result.get("requirements", {}),
            "design": result.get("design", {}),
            "code": result.get("code", {}),
            "review": result.get("review", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("Starting Antigrav IDE Backend API on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8888)
