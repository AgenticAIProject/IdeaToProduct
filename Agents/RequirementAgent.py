from pydantic import BaseModel, Field
import imports


class RequirementsList(BaseModel):
    problem_statement: str
    objectives: list[str]
    actors: list[str]
    user_stories: list[str]
    functional_requirements: list[str]
    non_functional_requirements: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list, description="List of specific features and items that are in scope.")
    out_of_scope: list[str] = Field(default_factory=list, description="List of specific features and items that are out of scope.")
    open_questions: list[str] = Field(default_factory=list)


class ClarificationResponse(BaseModel):
    needs_clarification: bool
    questions: list[str] = Field(default_factory=list)


def Requirement_Agent(state: imports.AgentState) -> imports.AgentState:

    idea = state["idea"]

    print("Requirement Agent received:")
    print(idea)
    print()

    # ---------------------------------------------------------
    # 1. Create LLM
    # ---------------------------------------------------------

    llm = imports.get_llm(max_tokens=3000)

    # ---------------------------------------------------------
    # 2. Build user input (include previous answers if any)
    # ---------------------------------------------------------

    user_input = idea

    if state["user_answers"]:
        user_input += "\n\nPrevious clarification answers:\n"
        for answer in state["user_answers"]:
            user_input += f"- {answer}\n"

    # ---------------------------------------------------------
    # 3. Maximum clarification rounds — skip check if exceeded
    # ---------------------------------------------------------

    MAX_CLARIFICATION_ROUNDS = 2

    if state["clarification_round"] >= MAX_CLARIFICATION_ROUNDS:
        clarification_check = ClarificationResponse(
            needs_clarification=False,
            questions=[]
        )
    else:
        # ---------------------------------------------------------
        # 4. Ask LLM whether clarification is needed
        # ---------------------------------------------------------

        clarification_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/clarification_prompt.txt"))
        
        clarification_llm = llm.with_structured_output(
            ClarificationResponse
        )
        
        clarification_check = clarification_llm.invoke(
            [clarification_prompt, imports.HumanMessage(content=user_input)]
        )

    # ---------------------------------------------------------
    # 5. If clarification is needed, stop here
    # ---------------------------------------------------------

    if clarification_check.needs_clarification:
        return {
            "clarification_questions": clarification_check.questions,
            "clarification_round":     state["clarification_round"] + 1,
            "current_stage":           "clarification",
            "workflow_status":         "waiting_for_user"
        }

    # ---------------------------------------------------------
    # 6. Market & Developer Issue Grounding (Phase 3)
    # ---------------------------------------------------------
    from tools import market_check, github_issues_check

    # print("  [Grounding] Querying Kaggle Startup Success benchmark...")
    market_data = {} # market_check.invoke({"idea": state["idea"]})
    # print(f"  [Grounding] Sector: {market_data.get('category')} | Viability: {market_data.get('viability_score')}/10 ({market_data.get('verdict')})")

    idea_keywords = [w for w in state["idea"].lower().split() if len(w) > 3]
    print("  [Grounding] Querying GH Archive for real developer issue patterns...")
    github_data = github_issues_check.invoke({"keywords": idea_keywords[:5]})
    print(f"  [Grounding] Retrieved {github_data.get('issue_count', 0)} related developer issue cases ({github_data.get('source')})")

    # Format issue summaries
    issues_summary = []
    for issue in github_data.get("issues", []):
        issues_summary.append(f"- [{issue.get('repo')}] {issue.get('title')}: {issue.get('body')[:150]}")
    issues_text = "\n".join(issues_summary) if issues_summary else "No specific edge cases retrieved."

    grounding_prompt = imports.SystemMessage(content=f"""
Market Grounding Evidence (Kaggle Startup Success Dataset):
- Category: {market_data.get('category')}
- Historical Success Rate: {market_data.get('success_rate', 0.40) * 100:.0f}%
- Market Viability Score: {market_data.get('viability_score')}/10 (Verdict: {market_data.get('verdict')})
- Top Incumbent Competitors: {', '.join(market_data.get('similar_products', []))}
- Critical Failure Modes to Avoid: {', '.join(market_data.get('risks', []))}
- Key V1 Factors: {', '.join(market_data.get('critical_factors', []))}

Empirical Developer Issues & Edge Cases (GH Archive):
{issues_text}

INSTRUCTION: Use the above market signals and real developer issues to directly inform your:
1. Acceptance criteria (include safeguards against the failure modes and edge cases above)
2. Constraints and assumptions
3. Non-functional requirements (scalability, security, input validation)
""")

    # ---------------------------------------------------------
    # 7. Generate requirements
    # ---------------------------------------------------------

    requirement_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/requirement_prompt.txt"))
    requirement_skill = imports.SystemMessage(content=imports.load_prompt("skills/requirement_skill.txt"))

    requirement_llm = llm.with_structured_output(
        RequirementsList
    )

    response = requirement_llm.invoke([
        requirement_prompt, 
        requirement_skill, 
        grounding_prompt, 
        imports.HumanMessage(content=user_input)
    ])

    output_requirements = response.model_dump()

    # ---------------------------------------------------------
    # 8. Return requirements with market & issue intelligence
    # ---------------------------------------------------------

    return {
        "requirements":          output_requirements,
        "requirements_version":  state["requirements_version"] + 1,
        "market_analysis":       market_data,
        "github_evidence":       github_data.get("issues", []),
        "clarification_questions": [],
        "current_stage":         "requirements",
        "workflow_status":       "running"
    }