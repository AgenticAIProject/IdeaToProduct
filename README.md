# IdeaToProduct: Autonomous Agentic SDLC Studio

> An end-to-end agentic software development system that transforms natural-language product ideas into validated, designed, implemented, tested, reviewed, documented, and release-ready software repositories.

---

## Table of Contents
1. [Overview & Executive Summary](#1-overview--executive-summary)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Agentic Workflow & Pipeline Stages](#3-agentic-workflow--pipeline-stages)
4. [Multi-Model Provider Routing & Key Pools](#4-multi-model-provider-routing--key-pools)
5. [Docker Sandboxing & Test Isolation](#5-docker-sandboxing--test-isolation)
6. [Quality Gate, Governance & Automated Rework](#6-quality-gate-governance--automated-rework)
7. [Agent Specifications & Skill Framework](#7-agent-specifications--skill-framework)
8. [Data Models & State Schema](#8-data-models--state-schema)
9. [Integration History & Engineering Notes](#9-integration-history--engineering-notes)
10. [Setup & Quick Start](#10-setup--quick-start)
11. [Repository Structure](#11-repository-structure)
12. [Development Roadmap](#12-development-roadmap)

---

## 1. Overview & Executive Summary

Given a raw software concept, **IdeaToProduct** coordinates a multi-stage team of specialized AI agents. Unlike standard single-prompt code generators, IdeaToProduct treats software engineering as a structured, traceable lifecycle:

```text
Raw Idea
   │
   ▼
[1. Requirements Agent] ── Ambiguous? ──► [Clarification Prompt] ──► User Input
   │
   ▼
[2. Design Agent]
   │
   ▼
[3. Code Agent] ◄─────────────────────────────────────────────┐
   │ (Layered: Models → API → Frontend)                        │ Rework Loop
   ▼                                                          │ (Max 3 attempts)
[4. Test Agent] ──► Isolated Docker Container (pytest)         │
   │                                                          │
   ▼                                                          │
[5. Review Agent] ── Quality Gate (Tests Pass & FRs Met?) ────┘
   │
   ├─► Rejected ──► Passes stack traces & defects to Code Agent
   │
   └─► Approved (Score >= 7)
         │
         ▼
[6. Documentation Agent] ──► Synthesizes 5 markdown docs + JSON specs
         │
         ▼
[7. Release Agent] ───────► Local package & optional GitHub release
```

### Core Engineering Principles
1. **Artifact Traceability & Immutability**: Historical outputs are versioned (`v1`, `v2`) rather than overwritten.
2. **Deterministic Governance**: Downstream execution strictly requires upstream prerequisites. Releasing requires explicit Review Agent approval.
3. **Independent Verification**: The Test Agent generates and executes unit/integration tests independently from the Code Agent's self-assessment.
4. **Isolated Sandboxing**: All user code and tests execute inside containerized environments, preventing system tampering and environmental drift.

---

## 2. High-Level Architecture

The studio operates with a browser-based UI, an asynchronous Python backend, and a compiled LangGraph state machine:

```text
┌─────────────────────────────────────────────────────────────┐
│                       Frontend UI                           │
│   • Single-page responsive studio (HTML5 / CSS3 / ES6)      │
│   • Live SSE / Polling stage progression & artifact viewer  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON API
┌──────────────────────────────▼──────────────────────────────┐
│                    Python HTTP Server                       │
│   • Asynchronous session worker daemon                      │
│   • Thread-safe SQLite audit & governance logger            │
└──────────────────────────────┬──────────────────────────────┘
                               │ StateGraph Execution
┌──────────────────────────────▼──────────────────────────────┐
│                  LangGraph State Machine                    │
│   • MemorySaver checkpointing for pause / resume            │
│   • Conditional edge routing (quality gate & rework)        │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
┌──────▼───┐┌─────▼────┐┌────▼─────┐┌───▼────┐┌────▼─────┐
│Requirements│Design    ││Code Agent ││Test Agent│Review/Docs│
│  (Groq)  ││  (Groq)  ││(DeepSeek) ││ (Groq)   ││(Google)  │
└──────────┘└──────────┘└────┬─────┘└───┬────┘└──────────┘
                             │          │
┌────────────────────────────▼──────────▼─────────────────────┐
│                 Execution Sandbox (Docker)                  │
│   • Pre-warmed image (ideatoprod-runner:python)             │
│   • Pre-installed: FastAPI, Pytest, HTTPX, SQLAlchemy       │
│   • 4-second sub-process isolated test execution            │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Agentic Workflow & Pipeline Stages

| Stage | Primary Model | Input | Output Artifact | Key Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **1. Requirements** | Groq (`gpt-oss-120b`) | Raw Idea | Requirements Document | Extracts Actors, User Stories, Functional Requirements (FRs), Non-Functional Requirements (NFRs), and Acceptance Criteria (ACs). Halts for clarification if ambiguous. |
| **2. Design** | Groq (`gpt-oss-120b`) | Requirements | System Design Document | Defines component boundaries, REST endpoints, database schemas, and architectural patterns. |
| **3. Code** | DeepSeek (`deepseek-flash`) | Design + Requirements | Complete Source Repository | Generates production code using an adaptive layered approach (Data Models → API/Logic → UI Assets). |
| **4. Test** | Groq (`gpt-oss-120b`) | Code + ACs | Test Suite & Results | Generates `test_verification.py` and executes tests inside an isolated Docker runner. Reports pass/fail counts and stack traces. |
| **5. Review** | Google (`gemini-3.8-flash`) | Code + Tests + Specs | Review Audit | Acts as a strict quality gate. Evaluates functional completeness and security. Enforces failure if any automated test fails. |
| **6. Documentation**| Google (`gemini-3.8-flash`) | All Prior Artifacts | Documentation Package | Synthesizes `README.md`, `API_REFERENCE.md`, `ARCHITECTURE.md`, `USER_GUIDE.md`, and `CHANGELOG.md`. |
| **7. Release** | Local Runtime | Approved Project | Production Bundle | Packages source files, writes release metadata, and optionally pushes to a remote GitHub repository. |

---

## 4. Multi-Model Provider Routing & Key Pools

To eliminate rate-limiting (`HTTP 429`) and concurrency bottlenecks, IdeaToProduct implements an isolated, multi-provider model routing strategy in `Agents/imports.py`:

```ini
# Explicit Per-Agent Provider Pinning (.env)
PROVIDER_CODE=deepseek
PROVIDER_DOCUMENTATION=google
PROVIDER_REVIEW=google
PROVIDER_REQUIREMENT=groq
PROVIDER_DESIGN=groq
PROVIDER_TEST=groq
```

### Failover & Key Management Architecture
- **DeepSeek Isolation**: `deepseek-flash` is strictly reserved for the Code Agent. It receives 0 requests during Requirements and Design, guaranteeing a completely cooled TPM/RPM limit when repository generation starts.
- **Groq Multi-Key Pool**: Rotates across 3 API keys (`GROQ_API_KEY`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`) with automatic 90s temporary exhaustion penalties upon receiving a 429.
- **Google Gemini Pool**: Rotates across 4 API keys with 60s cooldown penalties.
- **Non-Coding Fallback**: Non-coding agents fall back strictly between Groq and Google. They are prevented from spilling over into DeepSeek's quota.

---

## 5. Docker Sandboxing & Test Isolation

All generated software is verified in a hermetic container sandbox:

### The Pre-Warmed Runner Image (`ideatoprod-runner:python`)
- Standard wheel downloads across the Windows-WSL2 9P filesystem bridge can cause severe I/O bottlenecks.
- To resolve this, a local base image (`ideatoprod-runner:python`) comes pre-installed with `pytest`, `fastapi`, `httpx`, `sqlalchemy`, `pydantic`, and `python-dotenv`.
- `Agents/test_runner.py` inspects `requirements.txt` via `_needs_pip_install()`. If only standard dependencies are requested, the network `pip install` phase is skipped entirely, executing full test suites in **~4 seconds**.

### Sandbox Constraints
- Containers run with `--network none` (when packages are pre-installed) to guarantee zero external side-effects.
- Read-only code mounts where appropriate.
- Memory limit: `1g`.
- Execution timeout: 35 seconds.

---

## 6. Quality Gate, Governance & Automated Rework

### Deterministic Quality Gate
The Review Agent enforces non-negotiable governance policies:
1. **Automated Test Rule**: If `test_results["all_passed"] == False`, the build **must be rejected** (`approval_status = "rejected"`), and the score is capped at $\le 5/10$.
2. **Specification Conformance**: Verifies that every FR and endpoint described in the Design stage actually exists in the code files.

### The Feedback Rework Loop
When rejected:
1. Review defects, failed test names, and stack traces are injected into the LangGraph state.
2. LangGraph triggers `rework_repository_single_shot` on the Code Agent.
3. The Code Agent repairs the broken modules and updates `code_version` (`v1` $\rightarrow$ `v2`).
4. The Test Agent re-runs the verification suite.
5. If tests pass, Review approves (`Score >= 7`), and LangGraph unlocks Documentation and Release.

---

## 7. Agent Specifications & Skill Framework

Every agent in the studio follows a standardized contract:

```text
Agent Structure:
├── 1. Purpose (Clear functional scope)
├── 2. Input Contract (Validated AgentState slice)
├── 3. Output Schema (Pydantic BaseModel with strict validation)
├── 4. Assigned LLM (Pinned provider and model)
├── 5. Tools (Docker runner, Git tools, Kaggle market grounding)
├── 6. System Prompt (Role persona and anti-hallucination rules)
└── 7. Success Criteria (Quality gate prerequisites)
```

### Dynamic Execution Properties
- **State & Checkpoints**: Ephemeral in-memory execution backed by LangGraph checkpoints.
- **Self-Repair**: The Test Agent incorporates a self-repair loop: if a failure is due to a broken test fixture rather than an application bug, it auto-repairs the test file up to 3 times before declaring an application failure.
- **Governance Checklist**:
  - Human intervention points (Clarification and Final Release approval).
  - SQLite audit trail in `logs/pipeline_audit.db`.
  - Rollbacks and preservation of intermediate generation versions.

---

## 8. Data Models & State Schema

The central state object passed through LangGraph is defined in `Agents/State_definition.py`:

```python
class AgentState(TypedDict, total=False):
    project_id: str
    idea: str
    current_stage: str
    workflow_status: str          # "running" | "failed" | "completed"
    approval_status: str          # "approved" | "rejected" | "pending"
    
    # Artifact Payloads
    requirements: dict
    clarification: Optional[dict]
    design: dict
    code: dict
    test_results: dict
    tests: dict
    review: dict
    documentation: dict
    release: dict
    
    # Versioning & Audit
    code_version: int
    test_version: int
    review_version: int
    documentation_version: int
    retry_count: dict[str, int]
    token_usage: dict[str, Any]
    generated_project_path: str
```

---

## 9. Integration History & Engineering Notes

### Key Milestones & Fixes
- **Token Usage Normalization**: Standardized token usage extraction across LangChain ChatOpenAI, ChatGroq (`response_metadata.get("token_usage")`), and ChatGoogleGenerativeAI.
- **Windows Encoding Fix**: Enforced `utf-8` with replacement errors on all file I/O to prevent Windows `cp1252` encoding crashes.
- **Prompt Size Optimization**: Reduced code excerpts in `DocumentationAgent.py` from 2000 to 1000 characters per file, cutting prompt size by 50% and preventing output truncation.
- **Reasoning Model Headroom**: Configured `CODE_MAX_TOKENS=12000` and `DOCS_MAX_TOKENS=6000` to provide sufficient output headroom for reasoning models (`deepseek-flash`) that consume tokens during internal chain-of-thought.
- **Frontend Error Synchronization**: Updated `frontend/app.js` to render failed stages with red indicators and preserve partial artifacts rather than displaying false completions.

---

## 10. Setup & Quick Start

### Prerequisites
- Python 3.10+
- Docker Desktop (running)
- API Keys: DeepSeek, Groq (1-3 keys), Google Gemini (1-4 keys)

### 1. Installation
```bash
git clone <repo-url> IdeaToProduct
cd IdeaToProduct
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
```ini
LLM_PROVIDER=deepseek
CODE_MAX_TOKENS=12000
DOCS_MAX_TOKENS=6000

# DeepSeek (Code Agent)
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_CODE_MODEL=deepseek-flash

# Groq Key Pool (Requirements, Design, Tests)
GROQ_API_KEY=gsk_key1
GROQ_API_KEY_2=gsk_key2
GROQ_API_KEY_3=gsk_key3
GROQ_MODEL=openai/gpt-oss-120b

# Google Gemini Key Pool (Review, Documentation)
GOOGLE_API_KEY=your-gemini-key1
GOOGLE_API_KEY_2=your-gemini-key2
GEMINI_MODEL=gemini-3.8-flash

# Provider Routing
PROVIDER_CODE=deepseek
PROVIDER_DOCUMENTATION=google
PROVIDER_REVIEW=google
PROVIDER_REQUIREMENT=groq
PROVIDER_DESIGN=groq
PROVIDER_TEST=groq
```

### 3. Build Pre-Warmed Docker Image
```bash
# In the project root:
docker build -t ideatoprod-runner:python -f Dockerfile.runner .
```

### 4. Run Studio Server
```bash
python server.py
```
Open your browser at `http://localhost:8000` to launch the IdeaToProduct studio.

---

## 11. Repository Structure

```text
.
├── Agents/                     # Agent implementations & prompts
│   ├── CodeAgent.py            # Layered & adaptive code generator
│   ├── DesignAgent.py          # Architecture & schema designer
│   ├── DocumentationAgent.py   # Technical docs synthesizer
│   ├── ReleaseAgent.py         # Packaging & GitHub release
│   ├── RequirementAgent.py     # FR/NFR extraction & clarification
│   ├── ReviewAgent.py          # Quality gate auditor
│   ├── TestAgent.py            # Test generator & self-repair loop
│   ├── graph.py                # LangGraph pipeline definition
│   ├── imports.py              # LLM factory, key pools & fallbacks
│   ├── test_runner.py          # Docker test execution engine
│   └── prompts/                # Dedicated system prompts
├── frontend/                   # Browser UI studio
│   ├── index.html              # Studio single-page application
│   ├── app.js                  # SSE polling & stage renderer
│   └── style.css               # Studio design system
├── generated_projects/         # Runtime directory for generated apps
├── logs/                       # SQLite pipeline audit trail
│   └── pipeline_audit.db
├── complete_pipeline_langgraph.py # Standalone compiled workflow script
├── server.py                   # Main HTTP API & static file server
├── requirements.txt            # Host Python dependencies
└── README.md                   # Consolidated project master documentation
```

---

## 12. Development Roadmap

- [x] Multi-key pool rotation for Groq and Gemini.
- [x] Isolated Docker test execution with pre-warmed image caching.
- [x] Adaptive layered code generation (Models → API → Frontend).
- [x] Quality gate review loop with automated rework.
- [x] Full-lifecycle documentation synthesis (`README`, `API`, `Architecture`, `User Guide`, `Changelog`).
- [ ] Multi-user session persistence with PostgreSQL backend.
- [ ] Interactive live in-browser preview of generated frontend apps.
- [ ] Additional language runner images (Node.js/TypeScript, Go, Rust).
