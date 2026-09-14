from State_definition import AgentState


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

"""




from pathlib import Path

from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# from app.graph.agentState import ProjectState


def Requirement_Agent(state: AgentState) -> AgentState:
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
        "deleteThis":"",
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



    



    llm = ChatOpenRouter(
        model="gemini-3.6-flash",
        max_tokens=256
    )

    response = llm.invoke(
        "Hi, good Evening! Explain what a functional requirement is in one sentence."
    )

    requirements["deleteThis"] = response.text
    print(response.text)
    return {
        "requirements": requirements,
        "requirements_version": 1
    }