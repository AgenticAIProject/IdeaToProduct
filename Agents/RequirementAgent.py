

# Pydantic structured output


"""

system prompt
You are the Requirement Agent.

Your responsibility is to transform a vague software
idea into implementation-ready requirements.

You must:
- identify users
- identify objectives
- generate user stories
- generate functional requirements
- generate non-functional requirements
- identify constraints
- define acceptance criteria

You must NOT:
- choose programming languages
- choose databases
- write implementation code
- make architectural decisions


skills

Requirement Agent
        │
        └── Requirements Engineering Skill
               ├── User story methodology
               ├── FR/NFR identification
               ├── Acceptance criteria
               ├── Scope analysis
               └── Requirement validation

               


               {
    "agent": "requirements",
    "model": "....",
    "input_tokens": 4200,
    "output_tokens": 1800,
    "latency_ms": 3200
}


for tokens control


Requirement Agent
→ idea + relevant memory + GitHub evidence

Design Agent
→ requirements + relevant memory

Code Agent
→ requirements + design + relevant memory + repository

Test Agent
→ code + requirements/acceptance criteria

Review Agent
→ requirements + design + code + test results





security 


with restrictions on:

filesystem access
network access
CPU
memory
execution time
secrets/environment variables
dangerous commands





Long-term Memory
 ├── scope decisions
 ├── architecture decisions
 ├── rejected approaches
 ├── user constraints
 └── lessons learned



 artifacts

 Requirement Agent
    ↓
requirements.json

Design Agent
    ↓
design.md

Code Agent
    ↓
Git repository / commit

Test Agent
    ↓
test_results.json

Review Agent
    ↓
review.md

Documentation Agent
    ↓
README.md / documentation




Requirement Agent tools

github MCP
artifact reading / writing
memory access


"""



from pydantic import BaseModel, Field


class RequirementsList(BaseModel):

    problem_statement: str

    objectives: list[str]

    actors: list[str]

    user_stories: list[str]

    functional_requirements: list[str]

    non_functional_requirements: list[str]

    acceptance_criteria: list[str]

    constraints: list[str]

    assumptions: list[str]

    in_scope: list[str]

    out_of_scope: list[str]

    open_questions: list[str]



class ClarificationResponse(imports.BaseModel):
    needs_clarification: bool
    questions: list[str]




import json

import imports



# from app.graph.agentState import ProjectState


def Requirement_Agent(state: imports.AgentState) -> imports.AgentState:
    idea = state["idea"]
    print("Requirement Agent received:")
    print(idea)

    # Later:
    # 1. retrieve memory
    # 2. search GitHub issues
    # 3. call LLM
    # 4. validate requirements
    # 5. create artifact

    requirements = {
        "problem_statement": "",
        "objectives": [],
        "actors": [],
        "user_stories": [],
        "functional_requirements": [],
        "non_functional_requirements": [],
        "acceptance_criteria": [],
        "constraints": [],
        "assumptions": [],
        "in_scope": [],
        "out_of_scope": [],
        "open_questions": []
    }

    # system_prompt
    # REQUIREMENT_SYSTEM_PROMPT = """
    systemP=""" 
You are the Requirement Agent.

Your responsibility is to transform a vague software
idea into implementation-ready requirements.

You must:
- identify users
- identify objectives
- generate user stories
- generate functional requirements
- generate non-functional requirements
- identify constraints
- define acceptance criteria

You must NOT:
- choose programming languages
- choose databases
- write implementation code
- make architectural decisions

Return only valid JSON with exactly these keys:

problem_statement,
objectives,
actors,
user_stories,
functional_requirements,
non_functional_requirements,
acceptance_criteria,
constraints,
assumptions,
in_scope,
out_of_scope,
open_questions.

Use a string for problem_statement and arrays of concise
strings for every other key.

Do not use Markdown, code fences, or explanatory text.
"""

    REQUIREMENT_SKILL = """
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
10. Validate requirements for clarity,
    consistency, feasibility and testability.
"""


    userInput=imports.HumanMessage(content=idea)
    systemPrompt=imports.SystemMessage(systemP  + "\n\n"+ REQUIREMENT_SKILL)

    llm = imports.ChatOpenRouter(
        model="gemini-3.6-flash",
        max_tokens=2000,
        model_kwargs={
            "response_format": {"type": "json_object"}
        }
    )


    requirement_llm=llm.with_structured_output(RequirementsList)

    # response = llm.invoke(
    #     "Hi, good Evening! Explain what a functional requirement is in one sentence."
    # )

    response = requirement_llm.invoke([systemPrompt, userInput])

    outputRequirements = response.model_dump()


   



    # response_text = response.content.strip()
    # try:
    #     parsed_requirements = json.loads(response_text)
    # except json.JSONDecodeError:
    #     raise ValueError(
    #         "Requirement Agent failed to generate valid JSON"
    #     )

    # if not isinstance(parsed_requirements, dict):
    #     raise ValueError(
    #         "Requirement Agent output must be a JSON object"
    #     )

    # return {
    #     "requirements": parsed_requirements,
    #     "requirements_version": 1
    # }








        
    clarification_llm = llm.with_structured_output(
        ClarificationResponse
    )


    clarification_prompt = imports.SystemMessage(
    content="""
You are a requirements analysis agent.

Determine whether the user's software idea contains
enough information to generate implementation-ready
requirements.

Ask clarification questions only when missing
information materially affects the requirements.

Rules:
- Ask at most 3 questions.
- Questions must concern the problem, users, goals,
  scope, or expected behavior.
- Do NOT ask about programming languages,
  databases, frameworks, or architecture.
- If enough information is available, return
  needs_clarification=false and an empty questions list.
"""
)


    clarification_check = clarification_llm.invoke([
        clarification_prompt,
        imports.HumanMessage(content=idea)
    ])

    if clarification_check.needs_clarification:

        return {
            "clarification_questions":
                clarification_check.questions,

            "clarification_round":
                state["clarification_round"] + 1,

            "current_stage": "clarification"
        }


    return {
        "requirements": outputRequirements,
        "requirements_version": 1
    }

