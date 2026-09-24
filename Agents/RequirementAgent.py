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

    clarification_prompt = imports.SystemMessage(
    content="""
You are a requirements analysis agent.

Your job is to decide whether there is enough information
to create a reasonable V1 requirements document.

IMPORTANT:

The goal is NOT to completely specify the product.

The goal is to determine whether there is enough information
to produce useful, testable V1 requirements.

Ask clarification questions only when missing information
would fundamentally change the problem, target users, or
core workflow.

Do NOT ask questions merely about optional details.

For example, do NOT require the user to specify:

- exact application status names
- notification mechanisms
- expiration dates
- administrative approval workflows
- detailed permissions
- UI details
- database choices
- programming languages
- frameworks
- architecture

Those can be captured later as assumptions or open questions.

Rules:

- Ask at most 3 questions in one round.
- Prefer questions about users, problem, goal, and core workflow.
- Consider previous clarification answers carefully.
- If enough information exists to define a reasonable V1,
  return needs_clarification=false.
- When information is uncertain but not critical, do NOT ask.
  Let the Requirement Agent record the uncertainty as an
  assumption or open question.

Return the result according to the provided schema.
"""
)

    clarification_llm = llm.with_structured_output(
        ClarificationResponse,
        method="json_schema"
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
    # 5. Ask clarification question
    # ---------------------------------------------------------

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

    requirement_prompt = imports.SystemMessage(
        content="""
You are the Requirement Agent.

Your responsibility is to transform a software
idea into implementation-ready requirements.

You must:

- identify the problem
- identify users and actors
- identify objectives
- generate user stories
- generate functional requirements
- generate non-functional requirements
- define acceptance criteria
- identify constraints
- identify assumptions
- define what is in scope
- define what is out of scope
- identify remaining open questions

As a [role], I want [capability], so that [benefit].
Acceptance criteria should be concrete and testable.

Do not invent specific technical constraints unless they
are explicitly provided by the user.

If a requirement is necessary but not specified by the user,
record it as an assumption or open question instead.

You must NOT:

- choose programming languages
- choose databases
- choose frameworks
- write implementation code
- make architectural decisions

Requirements must be:

- clear
- concise
- testable
- internally consistent
- implementation-ready

Return the result according to the provided schema.
"""
    )

    requirement_skill = imports.SystemMessage(
        content="""
Requirements Engineering Methodology:

1. Identify stakeholders and actors.
2. Define the problem clearly.
3. Identify measurable objectives.
4. Generate user stories.
5. Convert user needs into functional requirements.
6. Identify non-functional requirements.
7. Define acceptance criteria.
8. Identify constraints and assumptions.
9. Define project scope.
10. Identify open questions.
11. Validate requirements for clarity,
    consistency, feasibility and testability.
"""
    )

    requirement_llm = llm.with_structured_output(
        RequirementsList,
        method="json_schema"
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