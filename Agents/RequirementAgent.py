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
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class ClarificationResponse(BaseModel):
    needs_clarification: bool
    questions: list[str]


def Requirement_Agent(state: imports.AgentState) -> imports.AgentState:

    idea = state["idea"]

    print("Requirement Agent received:")
    print(idea)

    # ---------------------------------------------------------
    # 1. Create LLM
    # ---------------------------------------------------------

    llm = imports.get_llm(max_tokens=2000)

    # ---------------------------------------------------------
    # 2. Check whether clarification is required
    # ---------------------------------------------------------

    clarification_prompt = imports.SystemMessage(content=imports.load_prompt("prompts/clarification_prompt.txt"))

    clarification_llm = llm.with_structured_output(
        ClarificationResponse
    )

    # ---------------------------------------------------------
    # 3. Include previous answers if this is a
    #    clarification round
    # ---------------------------------------------------------

    user_input = idea

    if state["user_answers"]:

        user_input += "\n\nPrevious clarification answers:\n"

        for answer in state["user_answers"]:
            user_input += f"- {answer}\n"
 # ---------------------------------------------------------
# 4. Maximum clarification rounds
# ---------------------------------------------------------

    MAX_CLARIFICATION_ROUNDS = 2

    if state["clarification_round"] >= MAX_CLARIFICATION_ROUNDS:
        clarification_check = ClarificationResponse(
            needs_clarification=False,
            questions=[]
        )

    else:
        clarification_check = clarification_llm.invoke([
            clarification_prompt,
            imports.HumanMessage(content=user_input)
        ])

    # ---------------------------------------------------------
    # 6. If clarification is needed, stop here
    # ---------------------------------------------------------

    if clarification_check.needs_clarification:

        return {
            "clarification_questions":
                clarification_check.questions,

            "clarification_round":
                state["clarification_round"] + 1,

            "current_stage":
                "clarification",

            "workflow_status":
                "waiting_for_user"
        }

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
        imports.HumanMessage(content=user_input)
    ])

    output_requirements = response.model_dump()

    # ---------------------------------------------------------
    # 8. Return requirements
    # ---------------------------------------------------------

    return {
        "requirements": output_requirements,

        "requirements_version":
            state["requirements_version"] + 1,

        "clarification_questions": [],

        "current_stage":
            "requirements",

        "workflow_status":
            "running"
    }