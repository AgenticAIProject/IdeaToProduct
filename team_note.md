# Team Notes

## Current Milestone — Requirement + Design Agents

### What was added

#### Requirement Agent
- Converts a raw product idea into structured V1 requirements.
- Performs clarification before generating requirements.
- Uses structured Pydantic output.
- Produces:
  - Problem statement
  - Objectives
  - Actors
  - User stories
  - Functional requirements
  - Non-functional requirements
  - Acceptance criteria
  - Constraints
  - Assumptions
  - In-scope items
  - Out-of-scope items
  - Open questions
- Clarification is bounded to a maximum number of rounds.

#### Design Agent
- Consumes the structured requirements produced by the Requirement Agent.
- Produces:
  - Architecture
  - Components
  - Data model
  - API endpoints
  - Design decisions
  - Edge cases
- Design decisions are kept separate from user requirements.

### Graph

The current LangGraph flow is:

Requirement → Design

If clarification is required, the Requirement stage pauses for user input.

### Current Status

Requirement and Design agents have been tested independently and
the two stages have been connected successfully in the graph.

test_requirement_agent.py runs the graph.py testing both requirements and design agent implementation
Max_clarification is set to 2.

### Known Limitations / Future Work

- Proper persistent HITL/checkpointing is not implemented yet.
- `requirements.md` and `design.md` artifact generation is pending.
- `decisions.log` and CUT log handling are pending.
- Market-check grounding is pending.
- GitHub MCP evidence grounding is pending.
- Code Agent has not been added yet.
- The current test manually supplies clarification answers.