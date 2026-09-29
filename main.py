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

    print(f"Idea: {initial_state['idea']}")
    print("\nRunning LangGraph workflow...\n")

    # Configure the thread memory and recursion limit
    config = {
        "configurable": {"thread_id": "project_001_session"},
        "recursion_limit": 15
    }

    # --- First invocation ---
    result = graph.invoke(initial_state, config=config)

    # --- Clarification loop ---
    # If the RequirementAgent needs more info, it pauses here.
    # We print questions, collect user answers, and resume the graph
    # using the same thread_id so MemorySaver restores the checkpoint.
    while result.get("workflow_status") == "waiting_for_user":
        questions = result.get("clarification_questions", [])

        print("\n" + "="*50)
        print("CLARIFICATION NEEDED")
        print("="*50)
        print("The Requirement Agent needs a few more details:\n")

        collected_answers = []
        for i, question in enumerate(questions, 1):
            print(f"Q{i}: {question}")
            answer = input("Your answer: ").strip()
            collected_answers.append(f"Q: {question}\nA: {answer}")
            print()

        # Merge new answers into the existing ones and resume
        prior_answers = result.get("user_answers", [])
        resume_input = {
            "user_answers":    prior_answers + collected_answers,
            "current_stage":   "requirements",
            "workflow_status": "running",
        }

        print("\nResuming workflow with your answers...\n")
        result = graph.invoke(resume_input, config=config)

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
