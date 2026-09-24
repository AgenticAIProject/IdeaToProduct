# Requirement Analysis Skill

1. **Understand the raw idea.**
2. **Identify target users.**
3. **Identify the core problem.**
4. **Generate functional requirements.**
5. **Generate non-functional requirements.**
6. **Convert requirements into user stories.**
7. **Check for ambiguity.**
8. **Identify missing information.**
9. **Produce structured output.**




# agents will have
1. **purpose**
2. **input**
3. **output schema**
4. **LLM/model**
5. **tools**
6. **instruction**
7. **success criteria**

# some depends on agent

1. **state**
2. **memory**
3. **decision logic**
4. **validation**
5. **retry**
6. **fallback**


# Governance items
# these are for agents that can cause actions (like code, test agents)
1. **Human intervention**
2. **permission**
3. **audit logging**
4. **guardrils**
5. **rollbacks**







hackathon-product-studio/
│
├── app/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── requirement_agent.py
│   │   ├── market_agent.py
│   │   ├── design_agent.py
│   │   ├── code_agent.py
│   │   ├── test_agent.py
│   │   ├── review_agent.py
│   │   └── documentation_agent.py
│   │
│   ├── tools/
│   │   ├── file_tools.py
│   │   ├── git_tools.py
│   │   └── test_tools.py
│   │
│   ├── skills/
│   │   └── requirements_skill.py
│   │
│   ├── memory/
│   │   └── memory_service.py
│   │
│   ├── graph/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── workflow.py
│   │
│   └── main.py
│
├── artifacts/
├── tests/
├── .env
├── .gitignore
├── requirements.txt
└── README.md





problems : - >

problem in review agent -> on error agent should not go back to requirement agent

code agent should use different model like claude-3.5-sonnet or qwen-coder;

need a edits in code agent like eddit particular line or small part. 
