# IdeaToProduct

# Hackathon-to-Product Studio Agent

An agentic AI software engineering system that transforms a raw product idea into a validated, designed, implemented, tested, reviewed, documented, and release-ready software project.

The system models a structured software development workflow using specialized AI agents, external tools, persistent artifacts, project memory, and governance controls.

---

## Overview

Given a raw software idea, the system coordinates a multi-stage agentic workflow:

```text
Raw Idea
   |
   v
Requirement
   |
   v
Design
   |
   v
Code
   |
   v
Test
   |
   v
Review
   |
   +---- Reject ----> Rework
   |
   +---- Approve
           |
           v
         Docs
           |
           v
        Release
```

Each stage consumes the output of the preceding stage and produces a versioned artifact.

The system is designed around two core principles:

1. **Artifact traceability** — outputs from each stage are preserved rather than silently overwritten.
2. **Governed progression** — downstream stages are allowed to execute only when their prerequisites are satisfied.

---

## Problem

Current AI coding systems can generate code from natural-language prompts, but a software project involves more than code generation.

A real development workflow requires:

* understanding and validating the problem
* defining requirements
* designing the system
* implementing the solution
* executing tests
* independently reviewing the result
* documenting the product
* preparing a release

This project explores how an agentic AI system can coordinate these activities while maintaining context, artifacts, decisions, and quality gates across the development lifecycle.

---

## Objectives

The project aims to build an agentic pipeline that can:

* transform unstructured ideas into structured requirements
* ground requirements using external evidence
* generate an implementation-oriented system design
* generate and modify an actual software repository
* execute tests against generated code
* independently evaluate the resulting software
* enforce approval before release
* preserve artifacts and their lineage
* retain the rationale behind important decisions
* support controlled rework when a stage fails review

---

## Pipeline

The system consists of seven primary stages.

### 1. Requirement

**Input:** Raw idea

**Output:** Requirement artifact

The Requirement Agent converts a vague product idea into structured user stories and requirements. The stage may also perform market validation and use external developer issue data for grounding.

---

### 2. Design

**Input:** Requirement artifact

**Output:** Design artifact

The Design Agent converts the requirements into an implementation-oriented system design, including architecture, components, interfaces, data models, and relevant technical decisions.

---

### 3. Code

**Input:** Design artifact

**Output:** Source repository / code artifact

The Code Agent implements the system described by the design. Repository scaffolding and code-generation tools are used to create and modify the project workspace.

---

### 4. Test

**Input:** Generated repository

**Output:** Test results

The Test Agent executes the generated software and evaluates it using an execution tool. Test results are based on actual execution rather than only static inspection or the Code Agent's explanation.

---

### 5. Review

**Input:** Pipeline artifacts and test results

**Output:** Review artifact + approval decision

The Review Agent evaluates the consistency and quality of the project across requirements, design, implementation, and testing.

Review is a hard quality gate.

```text
Review
   |
   +---- REJECT ----> Rework
   |
   +---- APPROVE ---> Documentation
```

---

### 6. Documentation

**Input:** Approved project artifacts

**Output:** Documentation artifact

The Documentation Agent generates user-facing and project documentation based on the resulting system.

---

### 7. Release

**Input:** Review approval + final artifacts

**Output:** Release artifact

The Release Agent prepares release notes and a versioned release summary.

Release execution is blocked unless the required review approval exists.

---

## Agent Architecture

Agents are separated from the tools they use.

```text
                    Orchestrator
                         |
        +----------------+----------------+
        |                |                |
   Requirement        Design            Code
      Agent            Agent            Agent
        |                |                |
      Tools            Tools            Tools
        |                |                |
        +----------------+----------------+
                         |
                      Test Agent
                         |
                    Test Runner
                         |
                    Review Agent
                         |
                 Approval / Rework
                    /         \
                Reject       Approve
                  |             |
                Rework         Docs
                                |
                              Release
```

The orchestrator is responsible for coordinating execution and enforcing pipeline transitions.

Agents are responsible for reasoning and producing stage-specific outputs.

Tools provide controlled interaction with external systems or execution environments.

---

## Tools

The initial system is designed around the following tools.

### `market_check`

Evaluates a product idea against available startup outcome data and returns evidence that can be used during requirement generation.

### `repo_scaffold`

Creates the initial repository structure from a system design specification.

### `test_runner`

Executes generated code/tests and returns objective execution results such as pass, fail, error, and timeout information.

### GitHub MCP

The Requirement stage uses GitHub through MCP to retrieve relevant issue information and ground requirement generation in real developer problem descriptions.

---

## Grounding Data

The current project specification identifies two primary sources for grounding:

### Startup Success Prediction Dataset

Used by the Requirement stage to support market-oriented evaluation of an idea.

### GH Archive / GitHub Issue Data

Used to provide realistic examples of developer-reported problems, feature requests, and issue descriptions.

The grounding layer is intended to reduce reliance on purely generative assumptions during requirement formation.

---

## Agent Skills

The system uses structured skills rather than relying exclusively on unconstrained prompts.

For example, the Requirement Agent follows a defined requirements-writing method that consistently converts an idea into structured user stories and requirements.

Skills are intended to make agent behavior:

* repeatable
* testable
* inspectable
* easier to evaluate

---

## Memory

The system maintains project-level memory for important decisions and their rationale.

Example:

```text
Decision:
Remove feature X from V1

Reason:
Implementation complexity exceeds the current scope

Impact:
Design
Code
Documentation
Release
```

The objective is to preserve not only the current project state, but also the reasoning behind significant changes.

---

## Artifact Model

Every pipeline stage produces a persistent artifact.

Conceptually:

```text
Artifact
├── id
├── project_id
├── stage
├── version
├── content
├── parent_artifact
├── created_at
└── metadata
```

Artifacts form a lineage:

```text
Requirement v1
      |
      v
Design v1
      |
      v
Code v1
      |
      v
Test v1
      |
      v
Review v1
```

Later revisions create new versions rather than silently replacing historical artifacts.

---

## Governance

The pipeline enforces stage-transition rules.

The primary governance constraint is:

```text
Release requires Review approval.
```

An unapproved project cannot proceed through the normal release path.

This provides an explicit quality gate and an auditable decision point before release.

---

## Rework

A rejected project can enter a controlled rework cycle.

```text
Code
  |
Test
  |
Review
  |
  +---- Reject
          |
          v
       Rework
          |
          v
        Test
          |
          v
       Review
```

The rework mechanism is intended to pass relevant failure information back to the appropriate stage while preserving previous artifacts.

---

## Development Roadmap

| Phase    | Focus                                       | Status  |
| -------- | ------------------------------------------- | ------- |
| Phase 0  | Project Foundation & Architecture           | Planned |
| Phase 1  | Agent Runtime & Core Infrastructure         | Planned |
| Phase 2  | Requirement Agent                           | Planned |
| Phase 3  | Grounding, Market Intelligence & MCP        | Planned |
| Phase 4  | Design Agent                                | Planned |
| Phase 5  | Code Agent & Repository Generation          | Planned |
| Phase 6  | Test Agent & Code Execution                 | Planned |
| Phase 7  | Review Agent & Governance                   | Planned |
| Phase 8  | Documentation & Release                     | Planned |
| Phase 9  | Memory, Artifact Versioning & Rework        | Planned |
| Phase 10 | Integration, Evaluation & Product Interface | Planned |

Detailed implementation plans are maintained under `docs/`.

---

## Repository Structure

```text
.
├── agents/              # Agent implementations
├── api/                 # API layer
├── artifacts/            # Generated project artifacts
├── memory/              # Project memory and decisions
├── models/              # Shared data models and schemas
├── orchestration/       # Pipeline orchestration
├── tools/               # Agent tools and integrations
├── tests/               # Unit, integration and E2E tests
├── docs/                # Architecture and engineering documentation
├── .env.example         # Environment variable template
├── .gitignore
├── README.md
└── pyproject.toml
```

---

## Engineering Principles

### Separation of concerns

Agents, tools, orchestration, memory, and artifacts are separate components.

### Explicit contracts

Agent inputs, outputs, tools, and artifacts use defined schemas rather than relying on unstructured text wherever possible.

### Artifact immutability

Historical stage outputs are preserved and versioned.

### Independent testing

The Test stage evaluates executable output independently from the Code Agent's reasoning.

### Governed execution

Certain transitions require explicit conditions, particularly the Review → Release transition.

### Observability

Agent executions, tool calls, failures, decisions, and pipeline transitions should be traceable.

### Reproducibility

The same input and pipeline configuration should produce inspectable intermediate artifacts that allow the result to be evaluated.

---

## Testing Strategy

Testing will be performed at three levels.

### Unit Tests

Individual agents, tools, schemas, and state-transition logic.

### Integration Tests

Interactions between agents, tools, artifacts, and the orchestrator.

### End-to-End Tests

Execution of the complete pipeline from a raw idea through release.

Particular attention will be given to governance cases such as:

```text
Rejected Review -> Release must be blocked
Missing Artifact -> Downstream stage must not execute
Failed Test -> Review receives failure information
Rework -> Previous artifacts remain preserved
```

---

