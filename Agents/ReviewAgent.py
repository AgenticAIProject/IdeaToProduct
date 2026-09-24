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

    llm = imports.ChatOpenRouter(
        model="google/gemini-3.6-flash",
        max_tokens=3000
    )

    # ---------------------------------------------------------
    # 2. Setup Review Prompt
    # ---------------------------------------------------------

    review_prompt = imports.SystemMessage(
        content="""
You are the Review Agent.

Your responsibility is to review the software artifacts generated in the current project, including requirements, design, code, and test results.
You must analyze them for consistency, correctness, completeness, and overall quality.

You must:
- Evaluate if the design and code fulfill all the original requirements.
- Identify any defects, bugs, security vulnerabilities, or architectural flaws.
- Provide constructive feedback for improvements.
- Decide whether to approve the current iteration or reject it (which requires a retry).
- Assign an overall quality score from 1 to 10.

Return the result according to the provided schema.
"""
    )

    review_skill = imports.SystemMessage(
        content="""
Review Methodology:

1. Consistency Check: Ensure requirements match design and code implementations.
2. Completeness Check: Ensure no missing features or unhandled edge cases.
3. Quality Check: Look for best practices, maintainability, and clean architecture.
4. Defect Identification: Highlight any test failures, potential bugs, or performance issues.
5. Final Verdict: If defects are critical, reject the build. Otherwise, approve.
"""
    )

    review_llm = llm.with_structured_output(
        ReviewResult,
        method="json_schema"
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

    # ---------------------------------------------------------
    # 5. Return review state
    # ---------------------------------------------------------
    
    approval_status = "approved" if response.approved else "rejected"
    
    return {
        "review": output_review,
        
        "review_version": state.get("review_version", 0) + 1,
        
        "current_stage": "review",
        
        "workflow_status": "running",
        
        "approval_status": approval_status
    }
