from pydantic import BaseModel, Field
import imports

class ReviewResult(BaseModel):
    approved: bool = Field(description="Whether the artifacts pass the review")
    feedback: list[str] = Field(default_factory=list, description="General feedback or improvement suggestions")
    defects: list[str] = Field(default_factory=list, description="List of defects or critical issues found")
    overall_score: int = Field(description="Overall quality score from 1 to 10")

def Review_Agent(state: imports.AgentState) -> imports.AgentState:
    print("Review Agent received artifacts for review.")

    # ---------------------------------------------------------
    # 1. Create LLM
    # ---------------------------------------------------------

    llm = imports.get_llm(agent_type="review", max_tokens=2000)

    # ---------------------------------------------------------
    # 2. Setup Review Prompt
    # ---------------------------------------------------------

    review_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/review_prompt.txt"))

    review_skill = imports.SystemMessage(content=imports.load_prompt("skills/review_skill.txt"))

    review_llm = llm.with_structured_output(
        ReviewResult,
        
    )

    # ---------------------------------------------------------
    # 3. Construct User Input
    # ---------------------------------------------------------

    user_input = f"Idea:\n{state.get('idea', '')}\n\n"
    user_input += f"Requirements:\n{state.get('requirements', {})}\n\n"
    user_input += f"Design:\n{state.get('design', {})}\n\n"
    user_input += f"Code:\n{state.get('code', {})}\n\n"
    user_input += f"Test Results:\n{state.get('test_results', {})}\n"

    # ---------------------------------------------------------
    # 4. Generate Review
    # ---------------------------------------------------------

    response = review_llm.invoke([
        review_prompt,
        review_skill,
        imports.HumanMessage(content=user_input)
    ])

    output_review = response.model_dump()
    approval_status = "approved" if response.approved else "rejected"

    try:
        from tools import save_stage_artifact, format_review_md
        pid = state.get("project_id", "project_default")
        md_content = format_review_md(pid, output_review, approval_status)
        save_stage_artifact(pid, "5_review", output_review, md_content)
    except Exception as e:
        print(f"  [Artifact] Warning saving review artifact: {e}")

    # ---------------------------------------------------------
    # 5. Return review state
    # ---------------------------------------------------------

    return {
        "review": output_review,
        "review_version": state.get("review_version", 0) + 1,
        "current_stage": "review",
        "workflow_status": "running",
        "approval_status": approval_status
    }
