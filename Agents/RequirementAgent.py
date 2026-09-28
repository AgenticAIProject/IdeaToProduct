from pydantic import BaseModel, Field
import imports
from tools import fetch_github_grounding


class UserStory(BaseModel):
    id: str = Field(description="Unique ID, e.g. US-01")
    actor: str = Field(description="The role or persona (e.g. 'user', 'admin')")
    story: str = Field(description="Full user story: As a [actor], I want [capability], so that [benefit].")
    priority: str = Field(description="Must, Should, Could, or Won't")


class FunctionalRequirement(BaseModel):
    id: str = Field(description="Unique ID, e.g. FR-01")
    description: str = Field(description="Precise system behavior: 'The system shall...'")
    priority: str = Field(description="Must, Should, Could, or Won't")
    user_story_ids: list[str] = Field(default_factory=list, description="IDs of related user stories, e.g. ['US-01']")


class NonFunctionalRequirement(BaseModel):
    id: str = Field(description="Unique ID, e.g. NFR-01")
    category: str = Field(description="Category: performance, security, usability, reliability, scalability, etc.")
    description: str = Field(description="Quality requirement description")


class AcceptanceCriterion(BaseModel):
    id: str = Field(description="Unique ID, e.g. AC-01")
    requirement_id: str = Field(description="ID of the functional requirement this validates, e.g. FR-01")
    description: str = Field(description="Concrete, testable condition. Prefer Given/When/Then format.")


class Constraint(BaseModel):
    id: str = Field(description="Unique ID, e.g. CON-01")
    description: str = Field(description="A limitation or boundary explicitly established by the problem or user.")


class Assumption(BaseModel):
    id: str = Field(description="Unique ID, e.g. ASM-01")
    description: str = Field(description="A condition assumed to be true for V1. Can be challenged later.")


class OpenQuestion(BaseModel):
    id: str = Field(description="Unique ID, e.g. OQ-01")
    question: str = Field(description="An unresolved question that could materially change requirements.")
    impacts: list[str] = Field(default_factory=list, description="FR or US IDs affected if this question changes, e.g. ['FR-01', 'US-02']")


class RequirementsList(BaseModel):
    problem_statement: str
    objectives: list[str]
    actors: list[str]
    user_stories: list[UserStory]
    functional_requirements: list[FunctionalRequirement]
    non_functional_requirements: list[NonFunctionalRequirement] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list, description="List of specific features and items that are in scope.")
    out_of_scope: list[str] = Field(default_factory=list, description="List of specific features and items that are out of scope.")
    open_questions: list[OpenQuestion] = Field(default_factory=list)




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

    llm = imports.get_llm(agent_type="requirement", max_tokens=3000)

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
    # 6. Developer Issue Grounding (Phase 3)
    # ---------------------------------------------------------

    print("  [Grounding] Querying GH Archive for real developer issue patterns...")
    grounding_result = fetch_github_grounding.invoke({"idea": state["idea"]})
    github_data = grounding_result["github_data"]
    issues_text  = grounding_result["issues_text"]

    grounding_prompt = imports.SystemMessage(content=f"""
Empirical Developer Issues & Edge Cases (GH Archive):
{issues_text}

INSTRUCTION: Use the above real developer issues to directly inform your:
1. Acceptance criteria (include safeguards against the edge cases above)
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
    # 8. Return requirements with grounding evidence
    # ---------------------------------------------------------

    return {
        "requirements":          output_requirements,
        "requirements_version":  state["requirements_version"] + 1,
        "github_evidence":       github_data.get("issues", []),
        "clarification_questions": [],
        "current_stage":         "requirements",
        "workflow_status":       "running"
    }
