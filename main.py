import sys
from pathlib import Path

# Add Agents to the Python path
sys.path.append(str(Path(__file__).parent / "Agents"))

from Agents.State_definition import AgentState
from Agents.graph import graph
from pprint import pprint

def main():
    print("========== INITIALIZING WORKFLOW ==========\n")
    
    # Initialize the starting state
    initial_state: AgentState = {
        "project_id": "proj_001",
        "user_id": "user_001",
        "idea": "Build a minimalist habit tracker app where users can check off daily goals.",
        
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 0,
        
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
        
        "retry_count": {
            "requirements": 0,
            "design": 0,
            "code": 0,
            "test": 0,
            "review": 0
        },
        
        "approval_status": "pending"
    }

    # Since the Requirement Agent might pause for clarification, 
    # we bypass it here for the sake of demonstrating the full flow 
    # directly to design and review.
    # We do this by simulating a state where clarification is already met 
    # (i.e. clarification_round = 2).
    initial_state["clarification_round"] = 2

    print(f"Idea: {initial_state['idea']}")
    print("\nRunning LangGraph workflow...\n")
    
    # Configure the thread memory and recursion limit
    config = {
        "configurable": {"thread_id": "project_001_session"},
        "recursion_limit": 15
    }
    
    # Invoke the graph with the configuration
    result = graph.invoke(initial_state, config=config)

    print("\n\n" + "="*50)
    print("WORKFLOW COMPLETE")
    print("="*50)
    
    print("\nFinal Current Stage:", result.get("current_stage"))
    print("Final Workflow Status:", result.get("workflow_status"))
    print("Final Approval Status:", result.get("approval_status"))
    
    print("\n--- Generated Requirements ---")
    pprint(result.get("requirements"))
    
    print("\n--- Generated Design ---")
    pprint(result.get("design"))
    
    print("\n--- Final Review Results ---")
    pprint(result.get("review"))

if __name__ == "__main__":
    main()
