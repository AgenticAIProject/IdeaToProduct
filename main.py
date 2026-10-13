import sys
from pathlib import Path

# Add Agents to the Python path so bare imports work
agents_dir = str(Path(__file__).resolve().parent / "Agents")
if agents_dir not in sys.path:
    sys.path.insert(0, agents_dir)

from State_definition import AgentState
from graph import graph
from pprint import pprint

def main():
    print("=" * 60)
    print("         AI PRODUCT DEVELOPMENT WORKFLOW")
    print("=" * 60)
    
    # Prompt the user for the idea with a sensible default fallback
    default_idea = "Build a calculator in c language."
    user_idea = input(f"\nEnter your product idea (press Enter for default: '{default_idea}'):\n> ").strip()
    if not user_idea:
        user_idea = default_idea

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_id = f"proj_{timestamp}"
    thread_id = f"{project_id}_session"

    print(f"\n[Project ID]: {project_id}")
    print(f"[Product Idea]: {user_idea}\n")
    print("Running LangGraph workflow...\n")

    # Initialize the starting state
    initial_state: AgentState = {
        "project_id": project_id,
        "user_id": "user_001",
        "idea": user_idea,
        
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 0,
        "requirements": {},
        "requirements_version": 0,
        "github_evidence": [],
        
        "design": {},
        "design_version": 0,
        
        "code": {},
        "code_version": 0,
        "generated_project_path": "",
        
        "test_results": {},
        "test_version": 0,
        
        "review": {},
        "review_version": 0,
        
        "documentation": {},
        "documentation_version": 0,
        
        "release": {},
        "release_version": 0,
        
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

    # Configure thread memory and recursion limit (unique thread_id prevents checkpoint collisions)
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 30
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
        print("CLARIFICATION NEEDED (Type 'skip' or press Enter to skip)")
        print("="*50)
        print("The Requirement Agent needs a few more details (or skip to use standard defaults):\n")

        collected_answers = []
        user_skipped = False

        for i, question in enumerate(questions, 1):
            print(f"Q{i}: {question}")
            answer = input("Your answer (or press Enter to skip): ").strip()
            if not answer or answer.lower() == "skip":
                collected_answers.append(f"Q: {question}\nA: Skip (use standard architectural defaults)")
                user_skipped = True
            else:
                collected_answers.append(f"Q: {question}\nA: {answer}")
            print()

        # Merge new answers into the existing ones and resume
        prior_answers = result.get("user_answers", [])
        resume_input = {
            "user_answers":    prior_answers + collected_answers,
            "current_stage":   "requirements",
            "workflow_status": "running",
        }

        if user_skipped:
            print("\nSkipping further clarification. Resuming workflow with standard defaults...\n")
        else:
            print("\nResuming workflow with your answers...\n")
        result = graph.invoke(resume_input, config=config)

    print("\n\n" + "="*50)
    print("WORKFLOW COMPLETE")
    print("="*50)
    
    print("\n[Final Stage]:", result.get("current_stage"))
    print("[Workflow Status]:", result.get("workflow_status"))
    print("[Approval Status]:", result.get("approval_status"))

    gen_path = result.get("generated_project_path") or (result.get("code") or {}).get("generated_project_path")
    if gen_path:
        print(f"\n📂 Generated Project Location: {gen_path}")
        code_files = (result.get("code") or {}).get("files", [])
        if code_files:
            print("Generated Files:")
            for f in code_files:
                path_str = f.get("path") if isinstance(f, dict) else str(f)
                print(f"  - {path_str}")

    test_res = result.get("test_results") or {}
    if test_res:
        print("\n🧪 Test Summary:")
        print(f"  Summary: {test_res.get('summary', 'N/A')}")
        print(f"  Passed: {test_res.get('passed_tests', 0)}, Failed: {test_res.get('failed_tests', 0)}")

    rev = result.get("review") or {}
    if rev:
        print("\n📋 Review Summary:")
        print(f"  Approved: {rev.get('approved')}")
        print(f"  Overall Score: {rev.get('overall_score')}/10")
        if rev.get("summary"):
            print(f"  Verdict: {rev.get('summary')}")

    docs = result.get("documentation") or {}
    if docs and docs.get("readme"):
        readme_preview = docs["readme"][:300].strip()
        print(f"\n📄 Documentation Generated (README Preview):\n{readme_preview}...\n")

if __name__ == "__main__":
    main()
