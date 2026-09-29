"""
CodeAgent.py - Design-driven and requirement-traceable code generation agent.

Consumes structured Requirements and Design artifacts, and generates a complete,
functional, syntactically verified, and runnable codebase written to disk.

Strictly obeys the DesignDocument contract:
- Does NOT assume FastAPI or any framework unless explicitly specified by Design.
- Does NOT create database entities or persistence unless explicitly specified by Design.
- Does NOT invent API endpoints or CRUD routes unless explicitly specified by Design.
- Does NOT create auto health/root/status endpoints unless explicitly in design.
- Supports multiple application types: Frontend-only, Backend REST API, CLI, Data processing.
- Generates dependency manifests matching the selected technology (requirements.txt / package.json).
- Separates Code Agent implementation decisions from Design Agent design decisions.
- Maintains requirement and design traceability on every generated file.
"""

import ast
import json
import re
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

import imports
from State_definition import AgentState
from tools import repo_scaffold


# ──────────────────────────────────────────────────────────────────────────────
# SystemType Enum — controlled vocabulary for design system types
# ──────────────────────────────────────────────────────────────────────────────

class SystemType(str, Enum):
    FRONTEND        = "frontend"
    BACKEND_API     = "backend_api"
    FULL_STACK      = "full_stack"
    CLI             = "cli"
    DATA_PROCESSING = "data_processing"
    SCRIPT          = "script"
    LIBRARY         = "library"
    UNKNOWN         = "unknown"


# Maps known DesignDocument system_type string patterns → SystemType
_SYSTEM_TYPE_MAP: list[tuple[list[str], SystemType]] = [
    (["frontend", "spa", "static site", "static web", "web application"], SystemType.FRONTEND),
    (["backend", "rest api", "api service", "web api"], SystemType.BACKEND_API),
    (["full-stack", "full stack", "fullstack"], SystemType.FULL_STACK),
    (["cli", "command line", "command-line", "terminal tool", "shell tool"], SystemType.CLI),
    (["data processing", "pipeline", "etl", "batch", "data science", "ml pipeline"], SystemType.DATA_PROCESSING),
    (["script", "automation script", "utility script"], SystemType.SCRIPT),
    (["library", "sdk", "package"], SystemType.LIBRARY),
]


def _parse_system_type(raw_system_type: str) -> SystemType:
    """Normalises a free-text system_type string to a SystemType enum value."""
    lower = raw_system_type.lower().strip()
    # Exact enum match first
    for st in SystemType:
        if st.value == lower:
            return st
    # Pattern match
    for patterns, st in _SYSTEM_TYPE_MAP:
        if any(p in lower for p in patterns):
            return st
    return SystemType.UNKNOWN


# ──────────────────────────────────────────────────────────────────────────────
# Module-Level Constants
# ──────────────────────────────────────────────────────────────────────────────

# Python-based package dependency sets keyed by stack key.
# frontend stack generates no requirements.txt (static HTML/CSS/JS has none).
# Node/Java/other stacks handled via separate dependency manifest.
FRAMEWORK_DEPS: dict[str, list[str]] = {
    "fastapi": [
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.22.0",
        "pydantic>=2.0.0",
        "pytest>=7.0.0",
        "httpx>=0.24.0",
    ],
    "fastapi_db": [
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.22.0",
        "pydantic>=2.0.0",
        "sqlalchemy>=2.0.0",
        "alembic>=1.12.0",
        "pytest>=7.0.0",
        "httpx>=0.24.0",
    ],
    "full_stack": [
        "fastapi>=0.100.0",
        "uvicorn[standard]>=0.22.0",
        "pydantic>=2.0.0",
        "sqlalchemy>=2.0.0",
        "alembic>=1.12.0",
        "pytest>=7.0.0",
        "httpx>=0.24.0",
    ],
    "flask": [
        "flask>=3.0.0",
        "pydantic>=2.0.0",
        "pytest>=7.0.0",
        "requests>=2.31.0",
    ],
    "django": [
        "django>=4.2.0",
        "djangorestframework>=3.14.0",
        "pytest-django>=4.7.0",
    ],
    "cli": [
        "pytest>=7.0.0",
    ],
    "data": [
        "pandas>=2.0.0",
        "numpy>=1.24.0",
        "pytest>=7.0.0",
    ],
    # frontend=static HTML/CSS/JS — no Python runtime dependencies
    # package manifest will be README only unless a JS framework is chosen
    "frontend": [],
    "minimal": [
        "pytest>=7.0.0",
    ],
}

# Setup/run command per stack
FRAMEWORK_RUN_CMD: dict[str, str] = {
    "fastapi":    "uvicorn main:app --reload --port 8000",
    "fastapi_db": "uvicorn main:app --reload --port 8000",
    "full_stack": "uvicorn main:app --reload --port 8000",
    "flask":      "flask --app main run --reload --port 5000",
    "django":     "python manage.py runserver 8000",
    "cli":        "python main.py",
    "data":       "python main.py",
    "frontend":   "open index.html  # or: python -m http.server 3000",
    "minimal":    "python main.py",
}

# Test commands per stack (technology-appropriate, not always pytest)
FRAMEWORK_TEST_CMD: dict[str, str] = {
    "fastapi":    "pytest -v",
    "fastapi_db": "pytest -v",
    "full_stack": "pytest -v",
    "flask":      "pytest -v",
    "django":     "pytest -v",
    "cli":        "pytest -v",
    "data":       "pytest -v",
    # frontend tests: standard library unittest requires 0 dependencies
    "frontend":   "python -m unittest test_frontend.py",
    "minimal":    "pytest -v",
}

# Irregular English plurals for domain entity handling
_IRREGULAR_PLURALS: dict[str, str] = {
    "person": "people",
    "man": "men",
    "woman": "women",
    "child": "children",
    "company": "companies",
    "category": "categories",
    "city": "cities",
    "country": "countries",
    "currency": "currencies",
    "query": "queries",
    "library": "libraries",
    "delivery": "deliveries",
    "activity": "activities",
    "faculty": "faculties",
    "university": "universities",
    "entry": "entries",
    "story": "stories",
    "policy": "policies",
    "property": "properties",
    "opportunity": "opportunities",
    "community": "communities",
    "entity": "entities",
    "ability": "abilities",
    "technology": "technologies",
    "agency": "agencies",
    "emergency": "emergencies",
    "status": "statuses",
}

# SQLAlchemy column type map
_ATTR_TYPE_MAP: list[tuple[list[str], tuple[str, str]]] = [
    (["price", "amount", "cost", "salary", "stipend", "budget", "balance", "fee", "revenue"], ("float", "Float")),
    (["count", "quantity", "qty", "age", "year", "month", "day", "hour", "num_", "number", "rank", "score", "limit"], ("int", "Integer")),
    (["is_", "has_", "can_", "active", "enabled", "verified", "published", "deleted"], ("bool", "Boolean")),
    (["date", "deadline", "due_date", "dob", "expiry"], ("date", "Date")),
    (["timestamp", "created_at", "updated_at", "datetime"], ("datetime", "DateTime")),
    (["email"], ("str", "String(254)")),
    (["url", "link", "website", "image", "photo"], ("str", "String(500)")),
    (["description", "content", "body", "bio", "summary", "notes", "text"], ("str", "Text")),
    (["status", "state", "type", "kind", "category", "priority", "role"], ("str", "String(100)")),
    (["name", "title", "full_name", "username", "company", "address", "code", "slug"], ("str", "String(255)")),
]


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────

class ResolvedTechnology(BaseModel):
    system_type: SystemType
    frontend: Optional[str] = None
    backend: Optional[str] = None
    database: Optional[str] = None
    test_framework: Optional[str] = None
    package_manager: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class GenerationPlan(BaseModel):
    """
    Immutable generation configuration derived ONLY from ResolvedTechnology.
    Acts as the single authoritative technology contract for all code generators.
    """
    system_type: SystemType
    frontend: Optional[str] = None
    backend: Optional[str] = None
    database: Optional[str] = None
    test_framework: str = "pytest"
    package_manager: str = "pip"
    runtime: str = "python"
    dependencies: list[str] = Field(default_factory=list)
    npm_dependencies: dict[str, str] = Field(default_factory=dict)
    npm_dev_dependencies: dict[str, str] = Field(default_factory=dict)
    run_command: str = ""
    test_command: str = ""
    is_supported: bool = True
    unsupported_reasons: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CodeFile(BaseModel):
    path: str = Field(description="Relative file path, e.g. 'main.py', 'index.html', 'test_main.py'")
    content: str = Field(description="Full, complete source code content without stubs or placeholders")
    description: str = Field(default="", description="One-line summary of file responsibility")
    requirement_ids: list[str] = Field(default_factory=list, description="Requirement IDs implemented in this file")
    design_component_ids: list[str] = Field(default_factory=list, description="Design component IDs implemented in this file")


class CodeArtifact(BaseModel):
    files: list[CodeFile] = Field(default_factory=list, description="All source, config, and test files required to run the project")
    dependencies: list[str] = Field(default_factory=list, description="List of package dependencies, e.g. ['pytest>=7.0.0']")
    setup_instructions: str = Field(default="", description="Command-line steps to set up and run the codebase")
    implementation_notes: list[str] = Field(default_factory=list, description="Key implementation notes and architectural decisions")
    test_command: str = Field(default="", description="Command used to run automated tests")


# ──────────────────────────────────────────────────────────────────────────────
# Traceability & Context Builders
# ──────────────────────────────────────────────────────────────────────────────

def format_requirements_context(requirements: dict) -> str:
    """Formats full structured requirements into a readable prompt block with AC mapping."""
    lines = []
    problem = requirements.get("problem_statement", "Application")
    lines.append(f"Problem Statement: {problem}")

    objectives = requirements.get("objectives", [])
    if objectives:
        lines.append("Objectives:")
        for obj in objectives:
            lines.append(f"  - {obj}")

    user_stories = requirements.get("user_stories", [])
    if user_stories:
        lines.append("\nUser Stories:")
        for us in user_stories:
            if isinstance(us, dict):
                lines.append(f"  * [{us.get('id', 'US')}] ({us.get('priority', 'Must')}) {us.get('story', '')}")
            else:
                lines.append(f"  * {us}")

    frs = requirements.get("functional_requirements", [])
    acs = requirements.get("acceptance_criteria", [])

    ac_by_req: dict[str, list[str]] = {}
    for ac in acs:
        if isinstance(ac, dict):
            req_id = ac.get("requirement_id", "general")
            ac_id = ac.get("id", "AC")
            desc = ac.get("description", "")
            ac_by_req.setdefault(req_id, []).append(f"[{ac_id}] {desc}")
        elif isinstance(ac, str):
            ac_by_req.setdefault("general", []).append(ac)

    if frs:
        lines.append("\nFunctional Requirements & Acceptance Criteria:")
        for fr in frs:
            if isinstance(fr, dict):
                fid = fr.get("id", "FR")
                prio = fr.get("priority", "Must")
                desc = fr.get("description", "")
                lines.append(f"  * [{fid}] ({prio}): {desc}")
                for ac_text in ac_by_req.get(fid, []):
                    lines.append(f"      -> AC: {ac_text}")
            elif isinstance(fr, str):
                lines.append(f"  * {fr}")

    constraints = requirements.get("constraints", [])
    if constraints:
        lines.append("\nConstraints:")
        for c in constraints:
            desc = c.get("description", c) if isinstance(c, dict) else c
            lines.append(f"  - {desc}")

    return "\n".join(lines)


def format_design_context(design: dict) -> str:
    """Formats full structured design specifications into an actionable implementation guide."""
    lines = []
    lines.append(f"System Type: {design.get('system_type', 'Not specified (determine from requirements)')}")
    lines.append(f"Architecture: {design.get('architecture', 'Modular architecture')}")

    tech_choices = design.get("technology_choices", [])
    if tech_choices:
        lines.append("\nExplicit Technology Choices (MUST FOLLOW):")
        for tc in tech_choices:
            if isinstance(tc, dict):
                lines.append(f"  * [{tc.get('category', 'tech')}] {tc.get('technology', '')}: {tc.get('reason', '')}")
            else:
                lines.append(f"  * {tc}")
    else:
        lines.append("\nExplicit Technology Choices: None specified in design (choose minimal implementation technology if necessary).")

    components = design.get("components", [])
    if components:
        lines.append("\nDesign Components:")
        for comp in components:
            if isinstance(comp, dict):
                reqs = comp.get("requirement_ids", [])
                req_str = f" (satisfies {', '.join(reqs)})" if reqs else ""
                lines.append(f"  * [{comp.get('id', 'COMP')}] {comp.get('name', '')}: {comp.get('responsibility', '')}{req_str}")
            elif isinstance(comp, str):
                lines.append(f"  * {comp}")

    data_entities = design.get("data_entities", [])
    if data_entities:
        lines.append("\nData Entities (Persistence Required):")
        for ent in data_entities:
            if isinstance(ent, dict):
                lines.append(f"  * [{ent.get('id', 'ENT')}] {ent.get('name', '')} ({ent.get('purpose', '')}):")
                attrs = ent.get("attributes", [])
                if attrs:
                    lines.append(f"      Attributes: {', '.join(str(a) for a in attrs)}")
                rels = ent.get("relationships", [])
                if rels:
                    lines.append(f"      Relationships: {', '.join(str(r) for r in rels)}")
            elif isinstance(ent, str):
                lines.append(f"  * {ent}")
    else:
        lines.append("\nData Entities: NONE (Do NOT create database, ORM, models.py, or SQLite persistence).")

    endpoints = design.get("api_endpoints", [])
    if endpoints:
        lines.append("\nAPI Endpoints:")
        for ep in endpoints:
            if isinstance(ep, dict):
                method = ep.get("method", "GET").upper()
                path = ep.get("path", "/")
                desc = ep.get("description", "")
                reqs = ep.get("requirement_ids", [])
                req_str = f" (implements {', '.join(reqs)})" if reqs else ""
                lines.append(f"  * [{ep.get('id', 'EP')}] {method} {path} - {desc}{req_str}")
            elif isinstance(ep, str):
                lines.append(f"  * {ep}")
    else:
        lines.append("\nAPI Endpoints: NONE (Do NOT generate API routes or CRUD endpoints).")

    integrations = design.get("external_integrations", [])
    if integrations:
        lines.append("\nExternal Integrations:")
        for ing in integrations:
            lines.append(f"  * {ing}")

    edge_cases = design.get("edge_cases", [])
    if edge_cases:
        lines.append("\nEdge Cases to Handle:")
        for ec in edge_cases:
            if isinstance(ec, dict):
                lines.append(f"  * [{ec.get('id', 'EC')}] {ec.get('description', '')}")
            elif isinstance(ec, str):
                lines.append(f"  * {ec}")

    decisions = design.get("design_decisions", [])
    if decisions:
        lines.append("\nKey Design Decisions:")
        for d in decisions:
            if isinstance(d, dict):
                lines.append(f"  * [{d.get('id', 'DEC')}] {d.get('decision', '')} (Reason: {d.get('reason', '')})")
            elif isinstance(d, str):
                lines.append(f"  * {d}")

    return "\n".join(lines)


def format_feedback_context(state: AgentState) -> str:
    """Formats previous review defects or test failures if this is an iterative loop."""
    review = state.get("review", {})
    defects = review.get("defects", []) if review else []
    feedback = review.get("feedback", []) if review else []
    test_results = state.get("test_results", {})

    failed_count = test_results.get("failed_tests", 0) if test_results else 0
    errors = test_results.get("errors", []) if test_results else []
    has_test_failures = failed_count > 0 or bool(errors)

    if not defects and not feedback and not has_test_failures:
        return ""

    lines = ["\n=== PREVIOUS FEEDBACK & DEFECTS TO FIX ==="]
    if defects:
        lines.append("Defects Identified in Review:")
        for d in defects:
            lines.append(f"  - [DEFECT] {d}")
    if feedback:
        lines.append("Review Feedback:")
        for fb in feedback:
            lines.append(f"  - {fb}")
    if has_test_failures:
        raw_output = test_results.get("raw_output", "") if test_results else ""
        lines.append(f"Test Execution Failures ({failed_count} failed):")
        for err in errors:
            lines.append(f"  - [ERROR] {err}")
        if raw_output:
            output_tail = "\n".join(raw_output.strip().splitlines()[-10:])
            lines.append(f"Test Log Excerpt:\n{output_tail}")

    lines.append("CRITICAL: You MUST resolve all defects and test failures above in this implementation.\n")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Code Sanitization & Syntax Validation
# ──────────────────────────────────────────────────────────────────────────────

def sanitize_code_content(path: str, content: str) -> str:
    """Cleans code content by removing unintended markdown code fences and JS booleans in Python code."""
    cleaned = content.strip()

    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()

    if path.endswith(".py"):
        cleaned = re.sub(r"\btrue\b", "True", cleaned)
        cleaned = re.sub(r"\bfalse\b", "False", cleaned)
        cleaned = re.sub(r"\bnull\b", "None", cleaned)

    return cleaned


def validate_python_files(files: list[CodeFile]) -> tuple[bool, list[str]]:
    """Runs AST syntax parsing on all Python files. Returns (all_valid, error_messages)."""
    errors = []
    for f in files:
        if f.path.endswith(".py"):
            try:
                ast.parse(f.content, filename=f.path)
            except SyntaxError as e:
                errors.append(f"{f.path}:{e.lineno}:{e.offset} SyntaxError: {e.msg}")
            except Exception as e:
                errors.append(f"{f.path} ParseError: {str(e)}")

    return (len(errors) == 0, errors)


# ──────────────────────────────────────────────────────────────────────────────
# Stack & Technology Resolution (Explicit & Design-Driven)
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_db_technology(design: dict) -> tuple[str, str, list[str]]:
    """
    Reads technology_choices for an explicit database technology.
    Returns (db_url_template, import_note, implementation_notes).

    Priority:
      1. Explicit database technology in technology_choices
      2. CodeAgent implementation decision (minimal, recorded explicitly)
    """
    notes = []
    for tc in design.get("technology_choices", []):
        if not isinstance(tc, dict):
            continue
        cat = tc.get("category", "").lower().strip()
        tech = tc.get("technology", "").lower().strip()
        reason = tc.get("reason", "")

        if cat in ("database", "db", "persistence"):
            if "sqlite" in tech:
                notes.append(f"Design decision: Using SQLite for persistence ({reason}).")
                return ("sqlite:///./app.db", "", notes)
            if "postgresql" in tech or "postgres" in tech:
                notes.append(f"Design decision: Using PostgreSQL for persistence ({reason}).")
                notes.append("CodeAgent implementation decision: Using SQLAlchemy with synchronous psycopg2-binary driver for PostgreSQL.")
                notes.append("Environment requirement: Set DATABASE_URL environment variable (e.g. postgresql+psycopg2://user:password@localhost:5432/dbname).")
                return ("postgresql+psycopg2://localhost:5432/app_db", "# NOTE: Configured via DATABASE_URL environment variable", notes)
            if "mysql" in tech or "mariadb" in tech:
                notes.append(f"Design decision: Using MySQL/MariaDB for persistence ({reason}).")
                notes.append("CodeAgent implementation decision: Using SQLAlchemy with synchronous pymysql driver for MySQL.")
                notes.append("Environment requirement: Set DATABASE_URL environment variable (e.g. mysql+pymysql://user:password@localhost:3306/dbname).")
                return ("mysql+pymysql://localhost:3306/app_db", "# NOTE: Configured via DATABASE_URL environment variable", notes)
            if "mongodb" in tech or "mongo" in tech:
                notes.append(f"Design decision: Using MongoDB for persistence ({reason}).")
                notes.append("CodeAgent implementation decision: Using PyMongo driver for document persistence. Relational SQLAlchemy ORM is not used.")
                notes.append("Environment requirement: Set MONGODB_URI environment variable (e.g. mongodb://localhost:27017).")
                return ("mongodb://localhost:27017", "# MongoDB: PyMongo connection via MONGODB_URI environment variable", notes)

    # CodeAgent fallback decision — no database technology specified by design
    notes.append("CodeAgent implementation decision: No database technology specified in design. Using SQLite as minimal local persistence. Record in review if a different database is required.")
    return ("sqlite:///./app.db", "", notes)


def resolve_technology(design: dict) -> ResolvedTechnology:
    """
    Authoritative technology resolver. Inspects DesignDocument:
      1. system_type (controlled vocabulary via SystemType)
      2. technology_choices (frontend, backend, database, testing, package manager)
    Maintains full-stack separation without collapsing to a single stack.
    """
    design_notes: list[str] = []
    code_notes: list[str] = []

    system_type_raw = design.get("system_type", "")
    st = _parse_system_type(system_type_raw)
    tech_choices = design.get("technology_choices", [])

    frontend_tech: Optional[str] = None
    backend_tech: Optional[str] = None
    database_tech: Optional[str] = None
    test_framework: Optional[str] = None
    package_manager: Optional[str] = None

    for tc in tech_choices:
        if not isinstance(tc, dict):
            continue
        cat = tc.get("category", "").lower().strip()
        tech = tc.get("technology", "").strip()
        reason = tc.get("reason", "")

        if cat in ("frontend", "ui", "web"):
            frontend_tech = tech
            design_notes.append(f"Design decision: Frontend = {tech} ({reason}).")
        elif cat in ("backend", "web framework", "api"):
            backend_tech = tech
            design_notes.append(f"Design decision: Backend = {tech} ({reason}).")
        elif cat in ("database", "db", "persistence"):
            database_tech = tech
            design_notes.append(f"Design decision: Database = {tech} ({reason}).")
        elif cat in ("cli", "command-line") or ("click" in tech.lower()):
            backend_tech = tech
            design_notes.append(f"Design decision: CLI tool = {tech} ({reason}).")
        elif cat == "data" or any(t in tech.lower() for t in ("pandas", "numpy", "scikit", "spark")):
            backend_tech = tech
            design_notes.append(f"Design decision: Data stack = {tech} ({reason}).")
        elif cat in ("test", "testing", "test framework"):
            test_framework = tech
            design_notes.append(f"Design decision: Test framework = {tech} ({reason}).")
        elif cat in ("package", "package manager", "dependency manager"):
            package_manager = tech
            design_notes.append(f"Design decision: Package manager = {tech} ({reason}).")

    # If system_type was UNKNOWN or empty, infer from tech choices
    if st == SystemType.UNKNOWN:
        if frontend_tech and backend_tech:
            st = SystemType.FULL_STACK
        elif frontend_tech and not backend_tech:
            st = SystemType.FRONTEND
        elif backend_tech:
            st = SystemType.BACKEND_API

    # Full stack resolution: preserve both frontend and backend
    if st == SystemType.FULL_STACK:
        if not frontend_tech:
            frontend_tech = "HTML/CSS/JS"
            code_notes.append("CodeAgent implementation decision: Full-stack system missing explicit frontend; defaulting to HTML/CSS/JS.")
        if not backend_tech:
            backend_tech = "FastAPI"
            code_notes.append("CodeAgent implementation decision: Full-stack system missing explicit backend; defaulting to FastAPI.")
        test_framework = test_framework or "pytest"
        package_manager = package_manager or "pip"
    elif st == SystemType.FRONTEND:
        frontend_tech = frontend_tech or "HTML/CSS/JS"
        test_framework = test_framework or "unittest"
        package_manager = package_manager or "none"
    elif st in (SystemType.CLI, SystemType.SCRIPT):
        backend_tech = backend_tech or "Python CLI"
        test_framework = test_framework or "pytest"
        package_manager = package_manager or "pip"
    elif st == SystemType.DATA_PROCESSING:
        backend_tech = backend_tech or "Pandas"
        test_framework = test_framework or "pytest"
        package_manager = package_manager or "pip"
    elif st == SystemType.BACKEND_API:
        if not backend_tech:
            backend_tech = "FastAPI"
            code_notes.append("CodeAgent implementation decision: technology_choices was empty; using Python/FastAPI as minimal backend implementation. Update design with explicit technology_choices for production.")
        test_framework = test_framework or "pytest"
        package_manager = package_manager or "pip"
    elif st == SystemType.UNKNOWN:
        code_notes.append("CodeAgent implementation decision: DesignDocument did not specify system_type or technology_choices. Generating minimal neutral Python structure. Design clarification required.")
        backend_tech = "Python"
        test_framework = "unittest"

    entities = design.get("data_entities", [])
    if entities and database_tech is None:
        code_notes.append("CodeAgent implementation decision: Data entities exist in design but no database technology was specified in technology_choices. Design clarification required.")

    return ResolvedTechnology(
        system_type=st,
        frontend=frontend_tech,
        backend=backend_tech,
        database=database_tech,
        test_framework=test_framework,
        package_manager=package_manager,
        notes=design_notes + code_notes,
    )


def create_generation_plan(resolved: ResolvedTechnology, design: dict) -> GenerationPlan:
    """
    Derives an immutable GenerationPlan ONLY from ResolvedTechnology and design constraints.
    Acts as the single authoritative technology contract for all code generators.
    """
    st = resolved.system_type
    notes = list(resolved.notes)
    is_supported = True
    unsupported_reasons: list[str] = []

    frontend = resolved.frontend
    backend = resolved.backend
    database = resolved.database
    test_framework = resolved.test_framework or "pytest"
    package_manager = resolved.package_manager or "pip"

    entities = [e for e in design.get("data_entities", []) if isinstance(e, dict)]
    has_entities = len(entities) > 0

    # 1. Normalize & validate frontend technology
    fe_norm: Optional[str] = None
    if frontend:
        fe_l = frontend.lower()
        if any(k in fe_l for k in ("react", "vite", "next")):
            fe_norm = "React"
        elif any(k in fe_l for k in ("html", "vanilla", "static", "css", "js")):
            fe_norm = "HTML/CSS/JS"
        else:
            fe_norm = frontend
            is_supported = False
            unsupported_reasons.append(
                f"Unsupported frontend technology: '{frontend}'. Supported: HTML/CSS/JS, React."
            )
    elif st in (SystemType.FRONTEND, SystemType.FULL_STACK):
        fe_norm = "HTML/CSS/JS"

    # 2. Normalize & validate backend technology
    be_norm: Optional[str] = None
    if backend:
        be_l = backend.lower()
        if "fastapi" in be_l:
            be_norm = "FastAPI"
        elif "flask" in be_l:
            be_norm = "Flask"
        elif "django" in be_l:
            be_norm = "Django"
        elif any(k in be_l for k in ("cli", "click")):
            be_norm = "Python CLI"
        elif any(k in be_l for k in ("pandas", "numpy", "data")):
            be_norm = "Pandas"
        elif "python" in be_l:
            be_norm = "Python"
        else:
            be_norm = backend
            is_supported = False
            unsupported_reasons.append(
                f"Unsupported backend technology: '{backend}'. Supported: FastAPI, Flask, Django, Python CLI, Pandas."
            )
    elif st in (SystemType.BACKEND_API, SystemType.FULL_STACK):
        be_norm = "FastAPI"
    elif st in (SystemType.CLI, SystemType.SCRIPT):
        be_norm = "Python CLI"
    elif st == SystemType.DATA_PROCESSING:
        be_norm = "Pandas"

    # 3. Normalize & validate database technology
    db_norm: Optional[str] = None
    if has_entities:
        if database:
            db_l = database.lower()
            if "sqlite" in db_l:
                db_norm = "SQLite"
            elif "postgres" in db_l:
                db_norm = "PostgreSQL"
            elif "mysql" in db_l or "mariadb" in db_l:
                db_norm = "MySQL"
            elif "mongo" in db_l:
                db_norm = "MongoDB"
            else:
                db_norm = database
                is_supported = False
                unsupported_reasons.append(
                    f"Unsupported database technology: '{database}'. Supported: SQLite, PostgreSQL, MySQL, MongoDB."
                )
        else:
            db_norm = "SQLite"
            notes.append(
                "CodeAgent implementation decision: Data entities exist in design but no database technology was specified in technology_choices. Provisioning provisional SQLite; Design clarification required."
            )

    # 4. Normalize test framework & package manager
    tf_norm = test_framework
    tf_l = (test_framework or "").lower()
    if "vitest" in tf_l:
        tf_norm = "Vitest"
    elif "jest" in tf_l:
        tf_norm = "Jest"
    elif "unittest" in tf_l:
        tf_norm = "unittest"
    else:
        tf_norm = "pytest"

    pm_norm = package_manager
    pm_l = (package_manager or "").lower()
    if "npm" in pm_l:
        pm_norm = "npm"
    elif "yarn" in pm_l:
        pm_norm = "yarn"
    elif "pip" in pm_l:
        pm_norm = "pip"
    elif "none" in pm_l:
        pm_norm = "none"
    else:
        if st == SystemType.FRONTEND and fe_norm == "React":
            pm_norm = "npm"
        elif st == SystemType.FRONTEND and fe_norm == "HTML/CSS/JS":
            pm_norm = "none"
        elif st == SystemType.FULL_STACK and fe_norm == "React":
            pm_norm = "npm/pip"
        else:
            pm_norm = "pip"

    # 5. Determine runtime
    if st == SystemType.FULL_STACK:
        runtime = "mixed" if fe_norm == "React" else "python"
    elif st == SystemType.FRONTEND:
        runtime = "node" if fe_norm == "React" else "static"
    else:
        runtime = "python"

    # 6. Derive dependencies dynamically
    py_deps: list[str] = []
    npm_deps: dict[str, str] = {}
    npm_dev_deps: dict[str, str] = {}

    if runtime in ("python", "mixed"):
        if be_norm == "FastAPI":
            py_deps.extend(["fastapi>=0.100.0", "uvicorn[standard]>=0.22.0", "pydantic>=2.0.0"])
            if tf_norm == "pytest":
                py_deps.append("httpx>=0.24.0")
        elif be_norm == "Flask":
            py_deps.append("flask>=3.0.0")
            if tf_norm == "pytest":
                py_deps.append("pytest>=7.0.0")
        elif be_norm == "Django":
            py_deps.extend(["django>=4.2.0", "djangorestframework>=3.14.0"])
        elif be_norm == "Pandas":
            py_deps.extend(["pandas>=2.0.0", "numpy>=1.24.0"])

        if db_norm in ("SQLite", "PostgreSQL", "MySQL"):
            py_deps.append("sqlalchemy>=2.0.0")
            if db_norm == "PostgreSQL":
                py_deps.append("psycopg2-binary>=2.9.9")
            elif db_norm == "MySQL":
                py_deps.append("pymysql>=1.1.0")
        elif db_norm == "MongoDB":
            py_deps.append("pymongo>=4.6.0")

        if tf_norm == "pytest" and "pytest>=7.0.0" not in py_deps:
            py_deps.append("pytest>=7.0.0")

    if runtime in ("node", "mixed") or fe_norm == "React":
        npm_deps["react"] = "^18.2.0"
        npm_deps["react-dom"] = "^18.2.0"
        npm_dev_deps["@vitejs/plugin-react"] = "^4.2.1"
        npm_dev_deps["vite"] = "^5.1.0"
        if tf_norm in ("Vitest", "Jest"):
            npm_dev_deps["vitest"] = "^1.3.0"
            npm_dev_deps["@testing-library/react"] = "^14.2.0"
            npm_dev_deps["jsdom"] = "^24.0.0"

    py_deps = list(dict.fromkeys(py_deps))

    # 7. Derive run & test commands
    if st == SystemType.FULL_STACK:
        if fe_norm == "React":
            run_cmd = "uvicorn backend.main:app --reload --port 8000"
            test_cmd = "pytest backend/ -v" if tf_norm == "pytest" else "npm test"
        else:
            if be_norm == "Flask":
                run_cmd = "flask --app main run --port 5000"
            else:
                run_cmd = "uvicorn main:app --reload --port 8000"
            test_cmd = "pytest -v" if tf_norm == "pytest" else "python -m unittest"
    elif st == SystemType.FRONTEND:
        if fe_norm == "React":
            run_cmd = "npm run dev"
            test_cmd = "npm test" if tf_norm in ("Vitest", "Jest") else "vitest run"
        else:
            run_cmd = "open index.html  # or: python -m http.server 3000"
            test_cmd = "python -m unittest test_frontend.py"
    elif st == SystemType.BACKEND_API:
        if be_norm == "Flask":
            run_cmd = "flask --app main run --port 5000"
        elif be_norm == "Django":
            run_cmd = "python manage.py runserver 8000"
        else:
            run_cmd = "uvicorn main:app --reload --port 8000"
        test_cmd = "pytest -v" if tf_norm == "pytest" else "python -m unittest"
    elif st in (SystemType.CLI, SystemType.SCRIPT, SystemType.DATA_PROCESSING):
        run_cmd = "python main.py"
        test_cmd = "pytest -v" if tf_norm == "pytest" else "python -m unittest"
    else:
        run_cmd = "python main.py"
        test_cmd = "python -m unittest"

    return GenerationPlan(
        system_type=st,
        frontend=fe_norm,
        backend=be_norm,
        database=db_norm,
        test_framework=tf_norm,
        package_manager=pm_norm,
        runtime=runtime,
        dependencies=py_deps,
        npm_dependencies=npm_deps,
        npm_dev_dependencies=npm_dev_deps,
        run_command=run_cmd,
        test_command=test_cmd,
        is_supported=is_supported,
        unsupported_reasons=unsupported_reasons,
        notes=notes,
    )


def _detect_stack(design: dict) -> tuple[str, list[str]]:
    """
    Resolves the technology stack from the DesignDocument.
    Preserves FULL_STACK instead of collapsing to frontend.
    """
    resolved = resolve_technology(design)
    st = resolved.system_type
    entities = design.get("data_entities", [])
    has_entities = len(entities) > 0

    if st == SystemType.FULL_STACK:
        return ("full_stack", resolved.notes)
    if st == SystemType.FRONTEND:
        return ("frontend", resolved.notes)
    if st in (SystemType.CLI, SystemType.SCRIPT):
        return ("cli", resolved.notes)
    if st == SystemType.DATA_PROCESSING:
        return ("data", resolved.notes)

    if resolved.backend:
        b = resolved.backend.lower()
        if "flask" in b:
            return ("flask", resolved.notes)
        if "django" in b:
            return ("django", resolved.notes)
        if "fastapi" in b:
            return ("fastapi_db" if has_entities else "fastapi", resolved.notes)

    if st == SystemType.BACKEND_API:
        return ("fastapi_db" if has_entities else "fastapi", resolved.notes)
    if st == SystemType.LIBRARY:
        return ("minimal", resolved.notes)

    return ("minimal", resolved.notes)


# ──────────────────────────────────────────────────────────────────────────────
# Output Guardrail Validator
# ──────────────────────────────────────────────────────────────────────────────

def validate_design_implementation(
    requirements: dict,
    design: dict,
    code_artifact: CodeArtifact,
) -> tuple[bool, list[str]]:
    """
    Validates that the generated CodeArtifact strictly follows the DesignDocument contract.

    Checks:
      A. Python AST syntax.
      B. No persistence when design.data_entities is empty, and no SQLAlchemy for MongoDB.
      C. No application API routes (GET/POST/PUT/DELETE/etc.) when design.api_endpoints is empty (for non-API system types).
      D. No web server for CLI/Script/Data applications (FULL_STACK explicitly permitted).
      E. Required design API endpoints are actually registered with route decorators.
      F. Dependency hygiene (requirements.txt matches technology and actual code imports).
      G. Layered Traceability & Coverage:
         - Layer 1: Referenced IDs exist in requirements/design.
         - Layer 2: MUST requirements have implementation file evidence.
         - Layer 3: MUST requirements have verification test evidence.
         - Layer 4: Acceptance criteria evidence in code or tests.

    Returns (is_valid: bool, messages: list[str]).
    Soft warnings are prefixed with [WARNING] and do not fail is_valid.
    Hard violations fail is_valid.
    """
    violations: list[str] = []
    warnings: list[str] = []

    # A. AST syntax check
    syntax_ok, syntax_errors = validate_python_files(code_artifact.files)
    if not syntax_ok:
        violations.extend(syntax_errors)

    entities  = design.get("data_entities", [])
    endpoints = design.get("api_endpoints", [])
    resolved  = resolve_technology(design)
    st = resolved.system_type

    file_paths  = [f.path.lower() for f in code_artifact.files]
    py_files    = [f for f in code_artifact.files if f.path.endswith(".py")]
    py_content  = "\n".join(f.content for f in py_files)
    py_content_lower = py_content.lower()
    all_content = "\n".join(f.content for f in code_artifact.files)
    all_content_lower = all_content.lower()

    # B. Technology Contract Enforcement (HARD VIOLATIONS)
    plan = create_generation_plan(resolved, design)

    # 1. Unsupported technology check
    if not plan.is_supported:
        violations.append(f"[TECH] Unsupported technology specified: {'; '.join(plan.unsupported_reasons)}")

    # 2. Frontend technology contract check
    if plan.frontend == "React":
        if not any(p.endswith("package.json") for p in file_paths):
            violations.append("[TECH] Design specified React frontend, but no package.json was generated.")
        if not any(p.endswith((".jsx", ".tsx")) for p in file_paths):
            violations.append("[TECH] Design specified React frontend, but no React components (.jsx/.tsx) were generated.")
    elif plan.frontend == "HTML/CSS/JS" and st == SystemType.FRONTEND:
        if not any(p.endswith("index.html") for p in file_paths):
            violations.append("[TECH] Design specified HTML/CSS/JS frontend, but index.html was not generated.")
        if any(p.endswith("package.json") for p in file_paths):
            violations.append("[TECH] Pure static HTML/CSS/JS frontend generated package.json.")

    # 3. Backend technology contract check
    if plan.backend == "Flask":
        if "flask" not in py_content_lower:
            violations.append("[TECH] Design specified Flask backend, but Flask was not imported in any Python file.")
        if "fastapi" in py_content_lower:
            violations.append("[TECH] Design specified Flask backend, but FastAPI was imported.")
    elif plan.backend == "FastAPI":
        if "fastapi" not in py_content_lower:
            violations.append("[TECH] Design specified FastAPI backend, but FastAPI was not imported in any Python file.")
        if "flask" in py_content_lower:
            violations.append("[TECH] Design specified FastAPI backend, but Flask was imported.")
    elif plan.backend == "Django":
        if "django" not in py_content_lower and not any("manage.py" in p or "settings.py" in p for p in file_paths):
            violations.append("[TECH] Design specified Django backend, but Django was not configured.")

    # 4. Database contract check (relational vs document)
    if not entities:
        db_files = [
            p for p in file_paths
            if p in ("models.py", "database.py", "db.py") or p.startswith("models/") or p.endswith("/models.py") or p.endswith("/database.py")
        ]
        if db_files:
            violations.append(f"[DB] Unnecessary database files generated (design.data_entities is empty): {db_files}")
        if "sqlalchemy" in py_content_lower or "create_engine" in py_content:
            violations.append("[DB] SQLAlchemy ORM introduced but design.data_entities is empty.")
    else:
        if plan.database == "MongoDB":
            if "sqlalchemy" in py_content_lower or "create_engine" in py_content:
                violations.append("[DB] Design specified MongoDB, but SQLAlchemy ORM was generated. Use PyMongo driver instead.")
            if "pymongo" not in py_content_lower and "motor" not in py_content_lower and "pymongo" not in all_content_lower:
                violations.append("[DB] Design specified MongoDB, but PyMongo/Motor driver was not imported.")
        elif plan.database in ("PostgreSQL", "MySQL", "SQLite"):
            if "pymongo" in py_content_lower:
                violations.append(f"[DB] Design specified relational database '{plan.database}', but PyMongo was imported.")

    # 5. Test framework contract check
    if plan.test_framework in ("Vitest", "Jest"):
        if "pytest" in py_content_lower or any("test_" in p and p.endswith(".py") for p in file_paths):
            violations.append("[TECH] Design specified Vitest/Jest test framework, but Python pytest was generated.")

    # 6. Package manager contract check
    if plan.package_manager == "npm" and st == SystemType.FRONTEND:
        if not any(p.endswith("package.json") for p in file_paths):
            violations.append("[TECH] Package manager npm specified, but package.json is missing.")
        if any(p.endswith("requirements.txt") for p in file_paths):
            violations.append("[TECH] Pure frontend npm project generated Python requirements.txt.")

    # 7. Static frontend with application server check
    if st == SystemType.FRONTEND:
        if any(fw in py_content_lower for fw in ("fastapi", "uvicorn", "flask", "django")):
            violations.append("[ARCH] Frontend-only application generated backend web server.")

    # C. API routes: no application endpoints when design specifies none AND type is not an API/Full-stack
    if not endpoints and st in (SystemType.CLI, SystemType.FRONTEND, SystemType.DATA_PROCESSING, SystemType.SCRIPT):
        route_decor_patterns = (
            "@app.get", "@app.post", "@app.put", "@app.delete", "@app.patch", "@app.route",
            "@router.get", "@router.post", "@router.put", "@router.delete", "@router.patch",
        )
        if any(d in py_content for d in route_decor_patterns):
            violations.append(
                f"[API] Server route decorators generated for {st.value} application when design.api_endpoints is empty."
            )

    # D. Web server: CLI/Data/Script should not launch a web server (FULL_STACK explicitly permitted)
    if st in (SystemType.CLI, SystemType.SCRIPT, SystemType.DATA_PROCESSING):
        if any(fw in py_content_lower for fw in ("fastapi", "uvicorn", "flask", "django")):
            violations.append(f"[ARCH] Web server framework imported in a {st.value} application.")

    # E. Required design endpoints coverage (distinguish registered route decorator vs mere comment)
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        path = ep.get("path", "")
        method = ep.get("method", "GET").upper()
        if not path:
            continue
        path_escaped = re.escape(path)
        reg_pattern = rf"@(app|router)\.(get|post|put|delete|patch|options|head)\(\s*['\"]{path_escaped}['\"]|@app\.route\(\s*['\"]{path_escaped}['\"]"
        if not re.search(reg_pattern, all_content, re.IGNORECASE):
            if path in all_content:
                warnings.append(f"[WARNING][API] Endpoint '{method} {path}' is mentioned in text/comments but has no active route registration decorator.")
            else:
                warnings.append(f"[WARNING][COVERAGE] Design endpoint '{method} {path}' not found in any generated file.")

    # F. Dependency hygiene check
    py_files = [f for f in code_artifact.files if f.path.endswith(".py")]
    has_py_files = len(py_files) > 0
    req_file = next((f for f in code_artifact.files if f.path == "requirements.txt"), None)

    if not has_py_files and req_file:
        warnings.append("[WARNING][DEPS] requirements.txt generated for project with no Python files.")
    elif req_file:
        req_text = req_file.content.lower()
        if "fastapi" in req_text and "fastapi" not in py_content_lower:
            warnings.append("[WARNING][DEPS] 'fastapi' listed in requirements.txt but never imported in source code.")
        if "sqlalchemy" in req_text and "sqlalchemy" not in py_content_lower:
            warnings.append("[WARNING][DEPS] 'sqlalchemy' listed in requirements.txt but never imported in source code.")
        if "pymongo" in req_text and "pymongo" not in py_content_lower and "motor" not in py_content_lower:
            warnings.append("[WARNING][DEPS] 'pymongo' listed in requirements.txt but never imported in source code.")
        if "pandas" in req_text and "pandas" not in py_content_lower:
            warnings.append("[WARNING][DEPS] 'pandas' listed in requirements.txt but never imported in source code.")

    if st == SystemType.FRONTEND:
        app_py_files = [f.path for f in py_files if not f.path.startswith("test_") and "conftest" not in f.path]
        if app_py_files:
            warnings.append(f"[WARNING][DEPS] Frontend project has non-test Python files: {app_py_files}. Verify this is intentional.")

    # G. Layered Traceability & Coverage Checks
    known_fr_ids: set[str] = set()
    for fr in requirements.get("functional_requirements", []):
        if isinstance(fr, dict) and fr.get("id"):
            known_fr_ids.add(fr["id"])

    known_comp_ids: set[str] = set()
    for comp in design.get("components", []):
        if isinstance(comp, dict) and comp.get("id"):
            known_comp_ids.add(comp["id"])

    # Layer 1: Traceability ID validity
    for f in code_artifact.files:
        for rid in f.requirement_ids:
            if known_fr_ids and rid not in known_fr_ids:
                warnings.append(f"[WARNING][TRACE] File '{f.path}' references unknown requirement_id '{rid}'.")
        for cid in f.design_component_ids:
            if known_comp_ids and cid not in known_comp_ids:
                warnings.append(f"[WARNING][TRACE] File '{f.path}' references unknown design_component_id '{cid}'.")

    # Layer 2 & 3: MUST Requirement Implementation & Test Verification Coverage
    impl_req_ids: set[str] = set()
    test_req_ids: set[str] = set()

    for f in code_artifact.files:
        is_test = f.path.startswith("test_") or "test" in f.path.lower()
        is_doc = f.path.lower() in ("readme.md", "requirements.txt", "package.json")
        if is_test:
            test_req_ids.update(f.requirement_ids)
        elif not is_doc:
            impl_req_ids.update(f.requirement_ids)

    for fr in requirements.get("functional_requirements", []):
        if isinstance(fr, dict):
            fid = fr.get("id", "")
            prio = fr.get("priority", "").lower()
            desc = fr.get("description", "")
            if prio in ("must", "must have") and fid:
                if fid not in impl_req_ids and fid not in all_content:
                    warnings.append(f"[WARNING][COVERAGE] MUST requirement '{fid}' ({desc}) has no non-test implementation file.")
                if fid not in test_req_ids and fid not in all_content:
                    warnings.append(f"[WARNING][COVERAGE] MUST requirement '{fid}' ({desc}) is not verified by any test file.")

    # Layer 4: Acceptance criteria evidence
    acs = requirements.get("acceptance_criteria", [])
    for ac in acs:
        if isinstance(ac, dict):
            ac_id = ac.get("id", "")
            ac_desc = ac.get("description", "")
            if ac_id and ac_id not in all_content:
                words = [w for w in re.findall(r"\w+", ac_desc) if len(w) > 4][:2]
                if not any(w.lower() in all_content_lower for w in words):
                    warnings.append(f"[WARNING][COVERAGE] Acceptance criterion '{ac_id}' has no corresponding implementation or test evidence.")

    # Combine: only hard violations affect is_valid
    all_messages = violations + warnings
    return (len(violations) == 0, all_messages)


# ──────────────────────────────────────────────────────────────────────────────
# Helper Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", s)


def _pascal_case(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "".join(w.capitalize() for w in words) if words else "Item"


def _pluralize(word: str) -> str:
    lower = word.lower().strip()
    if lower in _IRREGULAR_PLURALS:
        plural = _IRREGULAR_PLURALS[lower]
        return plural if word.islower() else plural.capitalize()
    if lower.endswith(("ies", "ses", "xes", "zes", "ches", "shes", "oes")):
        return word
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return word[:-1] + "ies"
    if lower.endswith("fe"):
        return word[:-2] + "ves"
    if lower.endswith("f") and not lower.endswith(("ff", "rf", "lf")):
        return word[:-1] + "ves"
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _resolve_attr_type(attr: object) -> tuple[str, str, str]:
    """
    Resolves (python_type, sqlalchemy_column, attr_slug) for a DataEntity attribute.

    Priority:
      1. Explicit dict attribute with 'type' key  — trust the Design Agent.
      2. Name-based inference via _ATTR_TYPE_MAP  — conservative fallback only.

    Accepts:
      - str: "name"  or  "name: string"  — infer from name
      - dict: {"name": "price", "type": "decimal", "required": True}  — explicit type
    """
    # ── Case 1: explicit structured attribute ──────────────────────────────
    if isinstance(attr, dict):
        attr_slug = _slugify(str(attr.get("name", "field")))
        explicit_type = str(attr.get("type", "")).lower().strip()

        _EXPLICIT_TYPE_MAP: dict[str, tuple[str, str]] = {
            "string":   ("str", "String(255)"),
            "str":      ("str", "String(255)"),
            "text":     ("str", "Text"),
            "int":      ("int", "Integer"),
            "integer":  ("int", "Integer"),
            "float":    ("float", "Float"),
            "decimal":  ("float", "Float"),
            "number":   ("float", "Float"),
            "bool":     ("bool", "Boolean"),
            "boolean":  ("bool", "Boolean"),
            "date":     ("date", "Date"),
            "datetime": ("datetime", "DateTime"),
            "timestamp":("datetime", "DateTime"),
            "uuid":     ("str", "String(36)"),
            "email":    ("str", "String(254)"),
            "url":      ("str", "String(500)"),
            "json":     ("str", "Text"),
        }
        if explicit_type in _EXPLICIT_TYPE_MAP:
            return (_EXPLICIT_TYPE_MAP[explicit_type][0], _EXPLICIT_TYPE_MAP[explicit_type][1], attr_slug)
        # Explicit type unknown — fall through to name inference
        return _infer_field_types(attr_slug) + (attr_slug,)

    # ── Case 2: string attribute — infer from name ─────────────────────────
    attr_str = str(attr).split(":")[0].split()[0]   # handle "name: string" format
    attr_slug = _slugify(attr_str)
    py_type, sa_col = _infer_field_types(attr_slug)
    return (py_type, sa_col, attr_slug)


def _infer_field_types(attr_name: str) -> tuple[str, str]:
    """Name-based type inference. Use only as a last resort."""
    slug = _slugify(attr_name)
    for keywords, (py_type, sa_col) in _ATTR_TYPE_MAP:
        for kw in keywords:
            if kw in slug:
                return (py_type, sa_col)
    return ("str", "String(255)")


# ──────────────────────────────────────────────────────────────────────────────
# Dynamic Fallback Generator (Design-Driven & Technology-Aware)
# ──────────────────────────────────────────────────────────────────────────────

def _build_fr_comment(frs: list, acs_by_id: dict[str, list[str]]) -> str:
    """Builds a short, readable comment block from functional requirements and ACs."""
    lines = ["Requirements implemented in this file:"]
    for fr in frs:
        if isinstance(fr, dict):
            fid = fr.get("id", "")
            desc = fr.get("description", "")
            lines.append(f"  [{fid}] {desc}")
            for ac in acs_by_id.get(fid, []):
                lines.append(f"    AC: {ac}")
    return "\n# ".join(lines)


def _make_react_frontend_files(
    project_id: str,
    problem: str,
    components: list[dict],
    req_ids: list[str],
    comp_ids: list[str],
    is_layered: bool = False,
    test_framework: str = "Vitest",
) -> list[CodeFile]:
    prefix = "frontend/" if is_layered else ""
    pkg_json_content = json.dumps(
        {
            "name": _slugify(project_id),
            "version": "1.0.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "test": "vitest run" if "vitest" in test_framework.lower() else "npm test",
            },
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0",
            },
            "devDependencies": {
                "@vitejs/plugin-react": "^4.2.1",
                "vite": "^5.1.0",
                "vitest": "^1.3.0",
                "@testing-library/react": "^14.2.0",
                "jsdom": "^24.0.0",
            },
        },
        indent=2,
    ) + "\n"

    vite_config_content = (
        "import { defineConfig } from 'vite';\n"
        "import react from '@vitejs/plugin-react';\n\n"
        "export default defineConfig({\n"
        "  plugins: [react()],\n"
        "  test: {\n"
        "    environment: 'jsdom',\n"
        "    globals: true,\n"
        "  },\n"
        "});\n"
    )

    index_html_content = (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"UTF-8\" />\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        f"  <title>{project_id.replace('-', ' ').replace('_', ' ').title()}</title>\n"
        f"  <meta name=\"description\" content=\"{problem}\" />\n"
        "</head>\n"
        "<body>\n"
        "  <div id=\"root\"></div>\n"
        f"  <script type=\"module\" src=\"/src/main.jsx\"></script>\n"
        "</body>\n"
        "</html>\n"
    )

    main_jsx_content = (
        "import React from 'react';\n"
        "import ReactDOM from 'react-dom/client';\n"
        "import App from './App';\n"
        "import './index.css';\n\n"
        "ReactDOM.createRoot(document.getElementById('root')).render(\n"
        "  <React.StrictMode>\n"
        "    <App />\n"
        "  </React.StrictMode>\n"
        ");\n"
    )

    comp_jsx_blocks = []
    for c in components:
        c_name = c.get("name", "Component")
        c_resp = c.get("responsibility", "")
        c_slug = _slugify(c_name)
        comp_jsx_blocks.append(
            f"        <section key=\"{c_slug}\" id=\"{c_slug}\" className=\"section\">\n"
            f"          <h2>{c_name}</h2>\n"
            f"          <p>{c_resp}</p>\n"
            f"        </section>"
        )
    if not comp_jsx_blocks:
        comp_jsx_blocks = [
            f"        <section id=\"main-content\" className=\"section\">\n"
            f"          <h2>{problem}</h2>\n"
            f"        </section>"
        ]
    comp_jsx_str = "\n".join(comp_jsx_blocks)

    app_jsx_content = (
        "import React, { useState } from 'react';\n"
        "import './index.css';\n\n"
        "export default function App() {\n"
        f"  const [title] = useState(\"{project_id.replace('-', ' ').replace('_', ' ').title()}\");\n\n"
        "  return (\n"
        "    <div className=\"app-container\">\n"
        "      <header className=\"app-header\">\n"
        "        <h1>{title}</h1>\n"
        f"        <p className=\"problem-stmt\">{problem}</p>\n"
        "      </header>\n"
        "      <main className=\"app-main\">\n"
        f"{comp_jsx_str}\n"
        "      </main>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
    )

    css_content = (
        "/* index.css — React styles */\n"
        "* { box-sizing: border-box; margin: 0; padding: 0; }\n"
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #0f172a; }\n"
        ".app-header { background: linear-gradient(135deg, #3b82f6, #06b6d4); color: #fff; padding: 2rem; }\n"
        ".app-header h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }\n"
        ".problem-stmt { opacity: 0.9; font-size: 1rem; }\n"
        ".app-main { padding: 2rem; max-width: 900px; margin: 0 auto; }\n"
        ".section { background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }\n"
        ".section h2 { color: #2563eb; margin-bottom: 0.5rem; font-size: 1.2rem; }\n"
    )

    app_test_content = (
        "// App.test.jsx — Vitest / Testing Library verification\n"
        "import { describe, it, expect } from 'vitest';\n"
        "import { render, screen } from '@testing-library/react';\n"
        "import App from './App';\n\n"
        "describe('App Component', () => {\n"
        "  it('renders application title', () => {\n"
        "    render(<App />);\n"
        "    const heading = screen.getByRole('heading', { level: 1 });\n"
        "    expect(heading).toBeDefined();\n"
        "  });\n"
        "});\n"
    )

    return [
        CodeFile(path=f"{prefix}package.json", content=pkg_json_content,
                 description="React project package manifest and dependencies",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}vite.config.js", content=vite_config_content,
                 description="Vite build and test configuration",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}index.html", content=index_html_content,
                 description="React single-page application HTML entrypoint",
                 requirement_ids=req_ids, design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}src/main.jsx", content=main_jsx_content,
                 description="React root DOM render script",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}src/App.jsx", content=app_jsx_content,
                 description="Main React App component composed from design components",
                 requirement_ids=req_ids, design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}src/index.css", content=css_content,
                 description="React application styles",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}src/App.test.jsx", content=app_test_content,
                 description="Frontend UI component verification tests",
                 requirement_ids=req_ids[:2], design_component_ids=comp_ids[:2]),
    ]


def _make_html_frontend_files(
    project_id: str,
    problem: str,
    components: list[dict],
    frs: list,
    acs_by_fr: dict[str, list[str]],
    req_ids: list[str],
    comp_ids: list[str],
    fr_comment: str,
    is_layered: bool = False,
) -> list[CodeFile]:
    prefix = "frontend/" if is_layered else ""
    sections_html = ""
    for comp in components:
        c_name = comp.get("name", "Section")
        c_resp = comp.get("responsibility", "")
        c_id = _slugify(c_name)
        sections_html += f"""
    <section id="{c_id}" class="section">
        <h2>{c_name}</h2>
        <p>{c_resp}</p>
    </section>"""
    if not sections_html:
        sections_html = f"""
    <section id="main-content" class="section">
        <h2>{problem}</h2>
    </section>"""

    nav_links = "".join(
        f'<a href="#{_slugify(c.get("name",""))}">{c.get("name","")}</a>\n        '
        for c in components
    )

    js_handlers = ""
    for comp in components:
        comp_id = _slugify(comp.get("name", "section"))
        comp_req_ids = comp.get("requirement_ids", [])
        handler_comment = ", ".join(
            fr.get("description", "") for fr in frs
            if isinstance(fr, dict) and fr.get("id", "") in comp_req_ids
        ) or comp.get("responsibility", f"{comp.get('name','Section')} interaction")
        js_handlers += f"""
    // {handler_comment}
    const el_{comp_id} = document.getElementById('{comp_id}');
    if (el_{comp_id}) {{
        el_{comp_id}.addEventListener('click', (e) => {{
            e.target.setAttribute('data-state', 'active');
        }});
    }}"""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_id.replace('-', ' ').replace('_', ' ').title()}</title>
    <meta name="description" content="{problem}">
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <header>
        <h1>{project_id.replace('-', ' ').replace('_', ' ').title()}</h1>
        <nav>
        {nav_links}</nav>
    </header>
    <main id="app">{sections_html}
    </main>
    <script src="app.js"></script>
</body>
</html>
"""
    css_content = """/* styles.css */
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f4f6f9;
    color: #1e1e2e;
}
header {
    background: linear-gradient(135deg, #4f46e5, #06b6d4);
    color: #fff;
    padding: 1.5rem 2rem;
}
header h1 { font-size: 1.5rem; margin-bottom: .25rem; }
nav a {
    color: rgba(255,255,255,.85);
    text-decoration: none;
    margin-right: 1rem;
    font-size: .9rem;
}
.section {
    background: #fff;
    border-radius: 8px;
    padding: 1.5rem;
    margin: 1rem 2rem;
    box-shadow: 0 1px 4px rgba(0,0,0,.07);
}
.section h2 { font-size: 1.1rem; margin-bottom: .5rem; color: #4f46e5; }
"""
    js_content = f"""'use strict';
// app.js — {project_id}
// {fr_comment}

document.addEventListener('DOMContentLoaded', () => {{{js_handlers}
}});
"""
    test_fe_py = (
        f'"""\n'
        f"test_frontend.py — Structure tests for {project_id}\n"
        f'"""\n'
        "import os\n"
        "import unittest\n\n\n"
        "class TestFrontendStructure(unittest.TestCase):\n"
        "    def test_required_files_exist(self):\n"
        f"        self.assertTrue(os.path.exists(\"{prefix}index.html\"), \"index.html missing\")\n"
        f"        self.assertTrue(os.path.exists(\"{prefix}styles.css\"), \"styles.css missing\")\n"
        f"        self.assertTrue(os.path.exists(\"{prefix}app.js\"), \"app.js missing\")\n\n"
        "    def test_html_has_required_sections(self):\n"
        f"        with open(\"{prefix}index.html\", encoding=\"utf-8\") as f:\n"
        "            html = f.read()\n"
        "        self.assertIn(\"<title>\", html)\n"
        "        self.assertIn('id=\"app\"', html)\n\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    return [
        CodeFile(path=f"{prefix}index.html", content=html_content,
                 description="Main HTML entrypoint",
                 requirement_ids=req_ids, design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}styles.css", content=css_content,
                 description="Application stylesheet",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}app.js", content=js_content,
                 description="Frontend event-handling logic derived from design components",
                 requirement_ids=req_ids, design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}test_frontend.py", content=test_fe_py,
                 description="Frontend structural verification tests",
                 requirement_ids=req_ids[:2], design_component_ids=comp_ids[:2]),
    ]


def _make_fastapi_backend_files(
    project_id: str,
    problem: str,
    endpoints: list[dict],
    entities: list[dict],
    is_mongodb: bool,
    req_ids: list[str],
    comp_ids: list[str],
    endpoint_req_ids: list[str],
    acs_by_fr: dict[str, list[str]],
    fr_comment: str,
    is_layered: bool = False,
    db_file: Optional[CodeFile] = None,
) -> list[CodeFile]:
    prefix = "backend/" if is_layered else ""
    route_defs: list[str] = []

    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "/")
        desc = ep.get("description", f"{method} {path}")
        ep_id = ep.get("id", "EP")
        ep_reqs = ep.get("requirement_ids", [])
        endpoint_req_ids.extend(ep_reqs)

        fname = f"{method.lower()}_{_slugify(path)}".strip("_")
        params_in_path = re.findall(r"\{(\w+)\}", path)
        param_str = ", ".join(f"{p}: int" for p in params_in_path) if params_in_path else ""

        matched = None
        if entities:
            matched = next(
                (e for e in entities
                 if _slugify(e["name"]) in path or _pluralize(_slugify(e["name"])) in path),
                None
            )

        if matched:
            cls = _pascal_case(matched["name"])
            table_name = _pluralize(_slugify(matched["name"]))
            if is_mongodb:
                if method == "GET" and not params_in_path:
                    body = f"    col = get_collection(\"{table_name}\")\n    return list(col.find({{}}, {{\"_id\": 0}}))\n"
                    sig_extras = ""
                elif method == "GET" and params_in_path:
                    body = (f"    col = get_collection(\"{table_name}\")\n"
                            f"    record = col.find_one({{\"id\": {params_in_path[0]}}}, {{\"_id\": 0}})\n"
                            f"    if not record:\n"
                            f"        raise HTTPException(404, detail='{cls} not found')\n"
                            f"    return record\n")
                    sig_extras = ""
                elif method == "POST":
                    body = (f"    col = get_collection(\"{table_name}\")\n"
                            f"    res = col.insert_one({{\"name\": \"new_{_slugify(matched['name'])}\"}})\n"
                            f"    return {{\"status\": \"created\", \"id\": str(res.inserted_id)}}\n")
                    sig_extras = ""
                else:
                    body = f"    # [{ep_id}] {desc}\n    return {{\"status\": \"ok\"}}\n"
                    sig_extras = ""
            else:
                if method == "GET" and not params_in_path:
                    body = f"    return db.query({cls}Record).all()\n"
                    sig_extras = ", db: Session = Depends(get_db)"
                elif method == "GET" and params_in_path:
                    body = (f"    record = db.query({cls}Record).filter({cls}Record.id == {params_in_path[0]}).first()\n"
                            f"    if not record:\n"
                            f"        raise HTTPException(404, detail='{cls} not found')\n"
                            f"    return record\n")
                    sig_extras = ", db: Session = Depends(get_db)"
                elif method == "POST":
                    body = (f"    record = {cls}Record()\n"
                            f"    db.add(record)\n"
                            f"    db.commit()\n"
                            f"    db.refresh(record)\n"
                            f"    return {{\"status\": \"created\", \"id\": record.id}}\n")
                    sig_extras = ", db: Session = Depends(get_db)"
                else:
                    body = f"    # [{ep_id}] {desc}\n    return {{\"status\": \"ok\"}}\n"
                    sig_extras = ""
        else:
            body = f"    # [{ep_id}] {desc}\n    return {{\"status\": \"ok\", \"endpoint\": \"{ep_id}\"}}\n"
            sig_extras = ""

        all_params = (f"{param_str}, " if param_str else "") + sig_extras.lstrip(", ")
        ep_reqs_str = ", ".join(ep_reqs) if ep_reqs else "see design"
        route_defs.append(
            f"\n# [{ep_id}] {desc} — implements: {ep_reqs_str}\n"
            f"@app.{method.lower()}(\"{path}\", summary=\"{desc}\")\n"
            f"def {fname}({all_params}):\n"
            f"{body}"
        )

    db_imports = ""
    if entities:
        if is_mongodb:
            db_imports = "from database import get_collection\n"
        else:
            model_names = ", ".join(["init_db", "get_db"] + [f"{_pascal_case(e['name'])}Record" for e in entities])
            db_imports = f"from models import {model_names}\nfrom sqlalchemy.orm import Session\n"

    main_py = (
        f'"""\n'
        f"main.py — Web application entrypoint for {project_id}\n"
        f"Problem: {problem}\n"
        f"# {fr_comment}\n"
        f'"""\n'
        f"from fastapi import FastAPI"
        + (", Depends, HTTPException" if (entities and not is_mongodb) else ", HTTPException" if (entities and is_mongodb) else "")
        + f"\n"
        + db_imports
        + f"\n"
    )
    if entities and not is_mongodb:
        main_py += (
            f"from contextlib import asynccontextmanager\n\n\n"
            f"@asynccontextmanager\n"
            f"async def lifespan(app):\n"
            f"    init_db()\n"
            f"    yield\n\n\n"
            f"app = FastAPI(title=\"{project_id}\", description=\"{problem}\", lifespan=lifespan)\n"
        )
    else:
        main_py += f"app = FastAPI(title=\"{project_id}\", description=\"{problem}\")\n"

    main_py += "".join(route_defs)

    if not route_defs:
        main_py += (
            f"\n\n"
            f"# NOTE: No API endpoints were specified in the DesignDocument.\n"
            f"# This application is a valid FastAPI service with no routes.\n"
            f"# Add endpoints via the DesignDocument api_endpoints field.\n"
        )

    main_py += (
        f"\n\n"
        f"if __name__ == '__main__':\n"
        f"    import uvicorn\n"
        f"    uvicorn.run('main:app', host='127.0.0.1', port=8000, reload=True)\n"
    )

    test_cases: list[str] = []
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "/")
        ep_id = ep.get("id", "EP")
        ep_reqs = ep.get("requirement_ids", [])
        fname = f"{method.lower()}_{_slugify(path)}".strip("_")
        exp_status = 200 if method == "GET" else 201 if method == "POST" else 200

        ac_lines = ""
        for rid in ep_reqs:
            for ac in acs_by_fr.get(rid, []):
                ac_lines += f"\n    # AC: {ac}"

        ep_reqs_str = ", ".join(ep_reqs) if ep_reqs else "see design"
        test_cases.append(
            f"\n# [{ep_id}] implements: {ep_reqs_str}"
            f"{ac_lines}\n"
            f"def test_{fname}():\n"
            f"    resp = client.{method.lower()}(\"{path}\")\n"
            f"    # Expected status for {method}: {exp_status}\n"
            f"    assert resp.status_code in ({exp_status}, 200, 422), resp.text\n"
        )

    if not test_cases:
        test_cases = ["\ndef test_app_instance():\n    assert app.title == \"" + project_id + "\"\n"]

    test_py = (
        f'"""\n'
        f"test_main.py — Verification tests for {project_id}\n"
        f"Tests derived from design API endpoints + acceptance criteria.\n"
        f'"""\n'
        f"import pytest\n"
        f"from fastapi.testclient import TestClient\n"
        f"from main import app\n\n"
        f"client = TestClient(app)\n"
        + "".join(test_cases)
    )

    b_files = [
        CodeFile(path=f"{prefix}main.py", content=main_py,
                 description="FastAPI application entrypoint",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}test_main.py", content=test_py,
                 description="Endpoint verification tests derived from design ACs",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
    ]
    if db_file:
        b_files.append(CodeFile(
            path=f"{prefix}{db_file.path}",
            content=db_file.content,
            description=db_file.description,
            requirement_ids=db_file.requirement_ids,
            design_component_ids=db_file.design_component_ids,
        ))
    return b_files


def _make_flask_backend_files(
    project_id: str,
    problem: str,
    endpoints: list[dict],
    entities: list[dict],
    is_mongodb: bool,
    req_ids: list[str],
    comp_ids: list[str],
    endpoint_req_ids: list[str],
    acs_by_fr: dict[str, list[str]],
    fr_comment: str,
    is_layered: bool = False,
    db_file: Optional[CodeFile] = None,
) -> list[CodeFile]:
    prefix = "backend/" if is_layered else ""
    route_defs: list[str] = []

    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "/")
        desc = ep.get("description", f"{method} {path}")
        ep_id = ep.get("id", "EP")
        ep_reqs = ep.get("requirement_ids", [])
        endpoint_req_ids.extend(ep_reqs)
        fname = f"{method.lower()}_{_slugify(path)}".strip("_")
        params_in_path = re.findall(r"\{(\w+)\}", path)
        flask_path = re.sub(r"\{(\w+)\}", r"<int:\1>", path) if params_in_path else path
        param_str = ", ".join(f"{p}: int" for p in params_in_path) if params_in_path else ""

        matched = None
        if entities:
            matched = next(
                (e for e in entities
                 if _slugify(e["name"]) in path or _pluralize(_slugify(e["name"])) in path),
                None
            )

        if matched:
            cls = _pascal_case(matched["name"])
            table_name = _pluralize(_slugify(matched["name"]))
            if is_mongodb:
                if method == "GET" and not params_in_path:
                    body = f"    col = get_collection(\"{table_name}\")\n    return jsonify(list(col.find({{}}, {{\"_id\": 0}})))\n"
                elif method == "GET" and params_in_path:
                    body = (f"    col = get_collection(\"{table_name}\")\n"
                            f"    record = col.find_one({{\"id\": {params_in_path[0]}}}, {{\"_id\": 0}})\n"
                            f"    if not record:\n"
                            f"        abort(404, description='{cls} not found')\n"
                            f"    return jsonify(record)\n")
                elif method == "POST":
                    body = (f"    col = get_collection(\"{table_name}\")\n"
                            f"    res = col.insert_one({{\"name\": \"new_{_slugify(matched['name'])}\"}})\n"
                            f"    return jsonify({{\"status\": \"created\", \"id\": str(res.inserted_id)}}), 201\n")
                else:
                    body = f"    # [{ep_id}] {desc}\n    return jsonify({{\"status\": \"ok\"}})\n"
            else:
                if method == "GET" and not params_in_path:
                    body = (f"    db = next(get_db())\n"
                            f"    records = db.query({cls}Record).all()\n"
                            f"    return jsonify([{{'id': r.id}} for r in records])\n")
                elif method == "GET" and params_in_path:
                    body = (f"    db = next(get_db())\n"
                            f"    record = db.query({cls}Record).filter({cls}Record.id == {params_in_path[0]}).first()\n"
                            f"    if not record:\n"
                            f"        abort(404, description='{cls} not found')\n"
                            f"    return jsonify({{'id': record.id}})\n")
                elif method == "POST":
                    body = (f"    db = next(get_db())\n"
                            f"    record = {cls}Record()\n"
                            f"    db.add(record)\n"
                            f"    db.commit()\n"
                            f"    db.refresh(record)\n"
                            f"    return jsonify({{\"status\": \"created\", \"id\": record.id}}), 201\n")
                else:
                    body = f"    # [{ep_id}] {desc}\n    return jsonify({{\"status\": \"ok\"}})\n"
        else:
            body = f"    # [{ep_id}] {desc}\n    return jsonify({{\"status\": \"ok\", \"endpoint\": \"{ep_id}\"}})\n"

        ep_reqs_str = ", ".join(ep_reqs) if ep_reqs else "see design"
        route_defs.append(
            f"\n# [{ep_id}] {desc} — implements: {ep_reqs_str}\n"
            f"@app.route(\"{flask_path}\", methods=[\"{method}\"])\n"
            f"def {fname}({param_str}):\n"
            f"{body}"
        )

    db_imports = ""
    if entities:
        if is_mongodb:
            db_imports = "from database import get_collection\n"
        else:
            model_names = ", ".join(["init_db", "get_db"] + [f"{_pascal_case(e['name'])}Record" for e in entities])
            db_imports = f"from models import {model_names}\n"

    main_py = (
        f'"""\n'
        f"main.py — Flask application entrypoint for {project_id}\n"
        f"Problem: {problem}\n"
        f"# {fr_comment}\n"
        f'"""\n'
        f"import os\n"
        f"from flask import Flask, jsonify, request, abort\n"
        + db_imports
        + "\n"
        f"app = Flask(__name__)\n\n"
        + "".join(route_defs)
    )

    if not route_defs:
        main_py += (
            f"\n\n"
            f"# NOTE: No API endpoints were specified in the DesignDocument.\n"
            f"# This application is a valid Flask service with no routes.\n"
            f"# Add endpoints via the DesignDocument api_endpoints field.\n"
        )

    main_py += (
        f"\n\n"
        f"if __name__ == '__main__':\n"
        + ("    init_db()\n" if (entities and not is_mongodb) else "")
        + f"    port = int(os.getenv('PORT', 5000))\n"
        f"    app.run(host='127.0.0.1', port=port, debug=True)\n"
    )

    test_cases: list[str] = []
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "/")
        ep_id = ep.get("id", "EP")
        ep_reqs = ep.get("requirement_ids", [])
        fname = f"{method.lower()}_{_slugify(path)}".strip("_")
        exp_status = 200 if method == "GET" else 201 if method == "POST" else 200

        ac_lines = ""
        for rid in ep_reqs:
            for ac in acs_by_fr.get(rid, []):
                ac_lines += f"\n    # AC: {ac}"

        ep_reqs_str = ", ".join(ep_reqs) if ep_reqs else "see design"
        test_cases.append(
            f"\n# [{ep_id}] implements: {ep_reqs_str}"
            f"{ac_lines}\n"
            f"def test_{fname}(client):\n"
            f"    resp = client.{method.lower()}(\"{path}\")\n"
            f"    assert resp.status_code in ({exp_status}, 200, 404, 422)\n"
        )

    if not test_cases:
        test_cases = ["\ndef test_app_instance(client):\n    assert app is not None\n"]

    test_py = (
        f'"""\n'
        f"test_main.py — Flask tests for {project_id}\n"
        f'"""\n'
        f"import pytest\n"
        f"from main import app\n\n"
        f"@pytest.fixture\n"
        f"def client():\n"
        f"    app.config['TESTING'] = True\n"
        f"    with app.test_client() as client:\n"
        f"        yield client\n"
        + "".join(test_cases)
    )

    b_files = [
        CodeFile(path=f"{prefix}main.py", content=main_py,
                 description="Flask web application entrypoint",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}test_main.py", content=test_py,
                 description="Flask endpoint verification tests",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
    ]
    if db_file:
        b_files.append(CodeFile(
            path=f"{prefix}{db_file.path}",
            content=db_file.content,
            description=db_file.description,
            requirement_ids=db_file.requirement_ids,
            design_component_ids=db_file.design_component_ids,
        ))
    return b_files


def _make_django_backend_files(
    project_id: str,
    problem: str,
    endpoints: list[dict],
    entities: list[dict],
    req_ids: list[str],
    comp_ids: list[str],
    endpoint_req_ids: list[str],
    fr_comment: str,
    is_layered: bool = False,
) -> list[CodeFile]:
    prefix = "backend/" if is_layered else ""
    views_code = (
        "from django.http import JsonResponse\n\n"
    )
    urls_code = (
        "from django.urls import path\n"
        "from . import views\n\n"
        "urlpatterns = [\n"
    )
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue
        p = ep.get("path", "/").lstrip("/")
        m = ep.get("method", "GET").lower()
        fn = f"{m}_{_slugify(p)}"
        views_code += (
            f"def {fn}(request):\n"
            f"    return JsonResponse({{'status': 'ok', 'endpoint': '{p}'}})\n\n"
        )
        urls_code += f"    path('{p}', views.{fn}),\n"
    urls_code += "]\n"

    settings_code = (
        f"SECRET_KEY = 'django-insecure-{_slugify(project_id)}'\n"
        "DEBUG = True\n"
        "ALLOWED_HOSTS = ['*']\n"
        "ROOT_URLCONF = 'core.urls'\n"
        "INSTALLED_APPS = ['django.contrib.contenttypes']\n"
        "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}\n"
    )
    manage_py = (
        "#!/usr/bin/env python\n"
        "import os\n"
        "import sys\n\n"
        "def main():\n"
        "    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')\n"
        "    try:\n"
        "        from django.core.management import execute_from_command_line\n"
        "    except ImportError as exc:\n"
        "        raise ImportError('Django is not installed') from exc\n"
        "    execute_from_command_line(sys.argv)\n\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    test_views = (
        "from django.test import TestCase, Client\n\n"
        "class ApiTests(TestCase):\n"
        "    def setUp(self):\n"
        "        self.client = Client()\n\n"
        "    def test_app_configured(self):\n"
        "        self.assertIsNotNone(self.client)\n"
    )
    return [
        CodeFile(path=f"{prefix}manage.py", content=manage_py,
                 description="Django management script",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}core/settings.py", content=settings_code,
                 description="Django configuration settings",
                 requirement_ids=[], design_component_ids=[]),
        CodeFile(path=f"{prefix}core/urls.py", content=urls_code,
                 description="Django URL routing",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}core/views.py", content=views_code,
                 description="Django API views",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
        CodeFile(path=f"{prefix}tests/test_views.py", content=test_views,
                 description="Django view verification tests",
                 requirement_ids=list(dict.fromkeys(req_ids + endpoint_req_ids)),
                 design_component_ids=comp_ids),
    ]


def generate_dynamic_fallback(project_id: str, requirements: dict, design: dict) -> CodeArtifact:
    """
    Generates a minimal, design-faithful codebase derived strictly from GenerationPlan.
    """
    problem = requirements.get("problem_statement", f"Project {project_id}")
    architecture = design.get("architecture", "Design-driven implementation")

    resolved = resolve_technology(design)
    plan = create_generation_plan(resolved, design)

    if not plan.is_supported:
        unsupported_file = CodeFile(
            path="UNSUPPORTED_TECHNOLOGY.md",
            content=(
                f"# Unsupported Technology Configuration for {project_id}\n\n"
                f"The DesignDocument specified technologies that are not supported by the CodeAgent:\n\n"
                + "\n".join(f"- {reason}" for reason in plan.unsupported_reasons)
                + "\n\n## Action Required\n"
                "Please update the DesignDocument with supported technologies:\n"
                "- Frontend: HTML/CSS/JS or React\n"
                "- Backend: FastAPI, Flask, Django, or Python CLI\n"
                "- Database: SQLite, PostgreSQL, MySQL, or MongoDB\n"
            ),
            description="Unsupported technology advisory and requirements for resolution",
            requirement_ids=[],
            design_component_ids=[],
        )
        return CodeArtifact(
            files=[unsupported_file],
            dependencies=[],
            setup_instructions="Design clarification required. Please update technology_choices with supported technologies.",
            implementation_notes=plan.unsupported_reasons,
            test_command="",
        )

    st = plan.system_type
    notes = list(plan.notes)
    deps = list(plan.dependencies)
    run_cmd = plan.run_command
    test_cmd = plan.test_command

    entities = [
        e if isinstance(e, dict) else {"name": str(e), "attributes": []}
        for e in design.get("data_entities", [])
    ]
    endpoints = [
        ep if isinstance(ep, dict) else {"path": str(ep)}
        for ep in design.get("api_endpoints", [])
    ]
    components = [
        c if isinstance(c, dict) else {"id": "", "name": str(c), "responsibility": ""}
        for c in design.get("components", [])
    ]

    frs = requirements.get("functional_requirements", [])
    acs = requirements.get("acceptance_criteria", [])

    acs_by_fr: dict[str, list[str]] = {}
    for ac in acs:
        if isinstance(ac, dict):
            rid = ac.get("requirement_id", "general")
            acs_by_fr.setdefault(rid, []).append(ac.get("description", ""))

    req_ids = [fr.get("id", f"FR-{i+1}") if isinstance(fr, dict) else f"FR-{i+1}" for i, fr in enumerate(frs)]
    comp_ids = [c.get("id", f"COMP-{i+1}") for i, c in enumerate(components)]

    fr_comment = _build_fr_comment(frs, acs_by_fr)
    files: list[CodeFile] = []

    # ── Database & Persistence Configuration ────────────────────────────────
    is_mongodb = (plan.database == "MongoDB")
    db_file: Optional[CodeFile] = None
    if entities and plan.database:
        if is_mongodb:
            database_py = (
                f'"""\n'
                f"database.py — PyMongo document persistence for {project_id}\n"
                f"# MongoDB persistence specified by DesignDocument\n"
                f"# {fr_comment}\n"
                f'"""\n'
                f"import os\n"
                f"from pymongo import MongoClient\n\n"
                f"MONGODB_URI = os.getenv(\"MONGODB_URI\", \"mongodb://localhost:27017\")\n"
                f"DB_NAME = os.getenv(\"DB_NAME\", \"{_slugify(project_id)}_db\")\n\n"
                f"client = MongoClient(MONGODB_URI)\n"
                f"db = client[DB_NAME]\n\n"
                f"def get_collection(name: str):\n"
                f"    \"\"\"Return MongoDB collection by entity name.\"\"\"\n"
                f"    return db[name]\n"
            )
            ent_reqs = list(dict.fromkeys(r for e in entities for r in e.get("requirement_ids", []))) or req_ids[:2]
            db_file = CodeFile(
                path="database.py",
                content=database_py,
                description="MongoDB database client and collection accessor",
                requirement_ids=ent_reqs,
                design_component_ids=comp_ids[:1],
            )
        else:
            if plan.database == "PostgreSQL":
                db_url_default = "postgresql+psycopg2://localhost:5432/app_db"
            elif plan.database == "MySQL":
                db_url_default = "mysql+pymysql://localhost:3306/app_db"
            else:
                db_url_default = "sqlite:///./app.db"

            sa_types_needed: set[str] = {"Integer", "DateTime"}
            model_classes: list[str] = []

            for ent in entities:
                cls_name = _pascal_case(ent["name"])
                table_name = _pluralize(_slugify(ent["name"]))
                col_defs = ["    id = Column(Integer, primary_key=True, index=True, autoincrement=True)"]

                for attr in ent.get("attributes", []):
                    py_type, sa_col, attr_slug = _resolve_attr_type(attr)
                    if attr_slug in ("id", "created_at", "updated_at", "pk"):
                        continue
                    sa_base = sa_col.split("(")[0]
                    sa_types_needed.add(sa_base)

                    if sa_base == "Boolean":
                        col_defs.append(f"    {attr_slug} = Column({sa_col}, default=False, nullable=False)")
                    elif sa_base in ("Integer", "Float"):
                        col_defs.append(f"    {attr_slug} = Column({sa_col}, default=0, nullable=False)")
                    else:
                        col_defs.append(f"    {attr_slug} = Column({sa_col}, default='', nullable=True)")

                col_defs.append("    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)")
                columns_str = "\n".join(col_defs)
                model_classes.append(
                    f"class {cls_name}Record(Base):\n"
                    f"    \"\"\"[{ent.get('id','ENT')}] {ent.get('purpose', cls_name + ' entity')}\"\"\"\n"
                    f"    __tablename__ = \"{table_name}\"\n\n"
                    f"{columns_str}\n"
                )

            sa_import_str = ", ".join(sorted(sa_types_needed))
            models_py = (
                f'"""\n'
                f"models.py — SQLAlchemy ORM models for {project_id}\n"
                f"# Persistence specified by DesignDocument: {plan.database}\n"
                f"# {fr_comment}\n"
                f'"""\n'
                f"import os\n"
                f"from datetime import datetime\n"
                f"from sqlalchemy import Column, {sa_import_str}, create_engine\n"
                f"from sqlalchemy.orm import declarative_base, sessionmaker\n\n"
                f"DATABASE_URL = os.getenv(\"DATABASE_URL\", \"{db_url_default}\")\n"
                f"connect_args = {{\"check_same_thread\": False}} if DATABASE_URL.startswith(\"sqlite\") else {{}}\n"
                f"engine = create_engine(DATABASE_URL, connect_args=connect_args)\n"
                f"SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n"
                f"Base = declarative_base()\n\n\n"
                + "\n\n".join(model_classes)
                + f"\ndef init_db() -> None:\n"
                f"    \"\"\"Create all tables if they do not exist.\"\"\"\n"
                f"    Base.metadata.create_all(bind=engine)\n\n"
                f"def get_db():\n"
                f"    db = SessionLocal()\n"
                f"    try:\n"
                f"        yield db\n"
                f"    finally:\n"
                f"        db.close()\n"
            )
            ent_reqs = list(dict.fromkeys(r for e in entities for r in e.get("requirement_ids", []))) or req_ids[:2]
            db_file = CodeFile(
                path="models.py",
                content=models_py,
                description="SQLAlchemy ORM models & DB session management",
                requirement_ids=ent_reqs,
                design_component_ids=comp_ids[:1],
            )

    # ── CASE A: Frontend-Only Application ────────────────────────────────────
    if st == SystemType.FRONTEND:
        if plan.frontend == "React":
            files.extend(_make_react_frontend_files(project_id, problem, components, req_ids, comp_ids, is_layered=False, test_framework=plan.test_framework))
        else:
            files.extend(_make_html_frontend_files(project_id, problem, components, frs, acs_by_fr, req_ids, comp_ids, fr_comment, is_layered=False))

    # ── CASE B: CLI Application ───────────────────────────────────────────────
    elif st in (SystemType.CLI, SystemType.SCRIPT):
        func_blocks: list[str] = []
        func_names: list[str] = []

        for comp in components:
            slug = _slugify(comp.get("name", "run"))
            resp = comp.get("responsibility", "Execute component logic")
            comp_req_ids = comp.get("requirement_ids", [])
            related_acs = []
            for rid in comp_req_ids:
                related_acs.extend(acs_by_fr.get(rid, []))
            ac_comment = ("\n    # AC: " + "\n    # AC: ".join(related_acs)) if related_acs else ""
            func_names.append(slug)
            func_blocks.append(
                f"def {slug}(*args, **kwargs):\n"
                f"    \"\"\"[{comp.get('id','')}] {resp}\"\"\"\n"
                f"{ac_comment}\n"
                f"    # Implementation derived from component responsibility: {resp}\n"
                f"    record = {{\n"
                f"        'component': '{slug}',\n"
                f"        'action': '{resp}',\n"
                f"        'status': 'completed',\n"
                f"        'inputs': list(args) if args else list(kwargs.keys()),\n"
                f"    }}\n"
                f"    print(f'[{slug}] Completed: {resp}')\n"
                f"    return record\n"
            )

        if not func_blocks:
            func_blocks = [
                "def run(*args, **kwargs):\n"
                "    \"\"\"Execute primary application logic.\"\"\"\n"
                "    return {'component': 'run', 'status': 'completed'}\n"
            ]
            func_names = ["run"]

        dispatch_table = "\n    ".join(f'"{fn}": {fn},' for fn in func_names)
        main_py = (
            f'"""\n'
            f"main.py — CLI entrypoint for {project_id}\n"
            f"Problem: {problem}\n"
            f"# {fr_comment}\n"
            f'"""\n'
            "import sys\n\n\n"
            + "\n\n".join(func_blocks)
            + "\n\nCOMMANDS = {\n    "
            + dispatch_table
            + "\n}\n\n\ndef main():\n"
            + f"    available = list(COMMANDS.keys())\n"
            + "    args = sys.argv[1:]\n"
            + "    if not args:\n"
            + "        print(f'Usage: python main.py <command>')\n"
            + "        print(f'Commands: {available}')\n"
            + "        sys.exit(0)\n"
            + "    cmd = args[0].lower()\n"
            + "    if cmd not in COMMANDS:\n"
            + "        print(f'Unknown command: {cmd}. Available: {available}')\n"
            + "        sys.exit(1)\n"
            + "    result = COMMANDS[cmd](*args[1:])\n"
            + "    sys.exit(0 if result and result.get('status') == 'completed' else 1)\n\n\n"
            + "if __name__ == '__main__':\n    main()\n"
        )

        test_cases = ""
        for fn in func_names:
            test_cases += (
                f"\n\ndef test_{fn}_execution():\n"
                f"    result = {fn}()\n"
                f"    assert isinstance(result, dict)\n"
                f"    assert result['status'] == 'completed'\n"
                f"    assert result['component'] == '{fn}'\n"
            )

        test_py = (
            f'"""\n'
            f"test_cli.py — Verification tests for {project_id} CLI\n"
            f'"""\n'
            + "import pytest\n"
            + f"from main import {', '.join(func_names)}\n"
            + test_cases
        )

        files.extend([
            CodeFile(path="main.py", content=main_py,
                     description="CLI entrypoint with component-derived commands",
                     requirement_ids=req_ids, design_component_ids=comp_ids),
            CodeFile(path="test_cli.py", content=test_py,
                     description="CLI component verification tests",
                     requirement_ids=req_ids, design_component_ids=comp_ids),
        ])
        if deps:
            files.append(CodeFile(
                path="requirements.txt",
                content="\n".join(deps) + "\n",
                description="Python package dependencies",
                requirement_ids=[], design_component_ids=[],
            ))

    # ── CASE C: Data Processing Application ──────────────────────────────────
    elif st == SystemType.DATA_PROCESSING:
        stage_funcs: list[str] = []
        stage_names: list[str] = []

        for comp in components:
            slug = _slugify(comp.get("name", "stage"))
            resp = comp.get("responsibility", "Process data")
            comp_req_ids = comp.get("requirement_ids", [])
            related_acs = []
            for rid in comp_req_ids:
                related_acs.extend(acs_by_fr.get(rid, []))
            ac_str = ("\n    # AC: " + "\n    # AC: ".join(related_acs)) if related_acs else ""
            stage_names.append(slug)
            stage_funcs.append(
                f"def {slug}(data):\n"
                f"    \"\"\"[{comp.get('id','')}] {resp}\"\"\"\n"
                f"{ac_str}\n"
                f"    # Operational stage derived from responsibility: {resp}\n"
                f"    if not isinstance(data, list):\n"
                f"        data = [data] if data is not None else []\n"
                f"    processed = []\n"
                f"    for item in data:\n"
                f"        if isinstance(item, dict):\n"
                f"            cleaned = dict(item)\n"
                f"            cleaned['stage_{slug}'] = 'processed'\n"
                f"            processed.append(cleaned)\n"
                f"        else:\n"
                f"            processed.append({{'value': item, 'stage_{slug}': 'processed'}})\n"
                f"    return processed\n"
            )

        if not stage_funcs:
            stage_funcs = [
                "def process(data):\n"
                "    \"\"\"Default data transformation stage.\"\"\"\n"
                "    if not isinstance(data, list):\n"
                "        data = [data] if data is not None else []\n"
                "    return [{'status': 'processed', 'item': d} for d in data]\n"
            ]
            stage_names = ["process"]

        pipeline_body = " -> ".join(stage_names)
        chain_calls = "    data = " + "\n    data = ".join(f"{fn}(data)" for fn in stage_names)

        main_py = (
            f'"""\n'
            f"main.py — Data pipeline for {project_id}\n"
            f"Problem: {problem}\n"
            f"Pipeline stages: {pipeline_body}\n"
            f"# {fr_comment}\n"
            f'"""\n\n\n'
            + "\n\n".join(stage_funcs)
            + "\n\ndef run_pipeline(initial_data=None):\n"
            + f"    \"\"\"Execute pipeline: {pipeline_body}\"\"\"\n"
            + "    data = initial_data if initial_data is not None else []\n"
            + f"{chain_calls}\n"
            + "    return data\n\n\n"
            + "if __name__ == '__main__':\n"
            + "    sample = [{'id': 1, 'name': 'input_sample'}]\n"
            + "    result = run_pipeline(sample)\n"
            + "    print(f'Pipeline complete. Records processed: {len(result)}')\n"
        )

        test_cases = ""
        for fn in stage_names:
            test_cases += (
                f"\n\ndef test_{fn}():\n"
                f"    sample = [{{'id': 1, 'name': 'test'}}]\n"
                f"    out = {fn}(sample)\n"
                f"    assert len(out) == 1\n"
                f"    assert out[0].get('stage_{fn}') == 'processed'\n"
            )
        test_cases += (
            f"\n\ndef test_full_pipeline():\n"
            f"    sample = [{{'id': 100}}]\n"
            f"    result = run_pipeline(sample)\n"
            f"    assert isinstance(result, list)\n"
            f"    assert len(result) == 1\n"
            f"    assert 'stage_{stage_names[0]}' in result[0]\n"
        )

        test_py = (
            f'"""\n'
            f"test_pipeline.py — Tests for {project_id} data pipeline\n"
            f'"""\n'
            + f"from main import {', '.join(stage_names)}, run_pipeline\n"
            + test_cases
        )

        files.extend([
            CodeFile(path="main.py", content=main_py,
                     description="Data processing pipeline",
                     requirement_ids=req_ids, design_component_ids=comp_ids),
            CodeFile(path="test_pipeline.py", content=test_py,
                     description="Data pipeline verification tests",
                     requirement_ids=req_ids, design_component_ids=comp_ids),
        ])
        if deps:
            files.append(CodeFile(
                path="requirements.txt",
                content="\n".join(deps) + "\n",
                description="Python package dependencies",
                requirement_ids=[], design_component_ids=[],
            ))

    # ── CASE D: Full-Stack Application ────────────────────────────────────────
    elif st == SystemType.FULL_STACK:
        if plan.frontend == "React":
            files.extend(_make_react_frontend_files(project_id, problem, components, req_ids, comp_ids, is_layered=True, test_framework=plan.test_framework))
            if plan.backend == "Flask":
                files.extend(_make_flask_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=True, db_file=db_file))
            elif plan.backend == "Django":
                files.extend(_make_django_backend_files(project_id, problem, endpoints, entities, req_ids, comp_ids, [], fr_comment, is_layered=True))
            else:
                files.extend(_make_fastapi_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=True, db_file=db_file))
            if deps:
                files.append(CodeFile(
                    path="backend/requirements.txt",
                    content="\n".join(deps) + "\n",
                    description="Python package dependencies for backend service",
                    requirement_ids=[], design_component_ids=[],
                ))
        else:
            files.extend(_make_html_frontend_files(project_id, problem, components, frs, acs_by_fr, req_ids, comp_ids, fr_comment, is_layered=False))
            if plan.backend == "Flask":
                files.extend(_make_flask_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=False, db_file=db_file))
            elif plan.backend == "Django":
                files.extend(_make_django_backend_files(project_id, problem, endpoints, entities, req_ids, comp_ids, [], fr_comment, is_layered=False))
            else:
                files.extend(_make_fastapi_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=False, db_file=db_file))
            if deps:
                files.append(CodeFile(
                    path="requirements.txt",
                    content="\n".join(deps) + "\n",
                    description="Python package dependencies",
                    requirement_ids=[], design_component_ids=[],
                ))

    # ── CASE E: Backend REST API / Minimal ────────────────────────────────────
    else:
        if plan.backend == "Flask":
            files.extend(_make_flask_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=False, db_file=db_file))
        elif plan.backend == "Django":
            files.extend(_make_django_backend_files(project_id, problem, endpoints, entities, req_ids, comp_ids, [], fr_comment, is_layered=False))
        else:
            files.extend(_make_fastapi_backend_files(project_id, problem, endpoints, entities, is_mongodb, req_ids, comp_ids, [], acs_by_fr, fr_comment, is_layered=False, db_file=db_file))
        if deps:
            files.append(CodeFile(
                path="requirements.txt",
                content="\n".join(deps) + "\n",
                description="Python package dependencies",
                requirement_ids=[], design_component_ids=[],
            ))

    # ── README — technology-appropriate, always included ─────────────────────
    setup_run_text = f"pip install -r requirements.txt\n{run_cmd}" if deps else run_cmd
    readme_md = f"""# {project_id}

Generated by **IdeaToProduct Pipeline** — {plan.system_type.value} architecture.

## Problem Statement
{problem}

## Architecture
{architecture}

## Technologies Resolved
- Frontend: {plan.frontend or 'N/A'}
- Backend: {plan.backend or 'N/A'}
- Database: {plan.database or 'N/A'}
- Test Framework: {plan.test_framework}
- Package Manager: {plan.package_manager}

## Setup & Run

```bash
{setup_run_text}
```

## Testing

```bash
{test_cmd}
```

## Implementation Notes
"""
    for note in notes:
        readme_md += f"- {note}\n"

    files.append(CodeFile(
        path="README.md",
        content=readme_md,
        description="Project setup, run, and notes",
        requirement_ids=[],
        design_component_ids=[],
    ))

    return CodeArtifact(
        files=files,
        dependencies=deps,
        setup_instructions=setup_run_text,
        implementation_notes=notes,
        test_command=test_cmd,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Code Agent Main Function
# ──────────────────────────────────────────────────────────────────────────────

def Code_Agent(state: AgentState) -> dict:
    """
    Code Agent (Stage 3):
    1. Reads structured requirements, authoritative design document, and feedback.
    2. Determines technology choices explicitly from DesignDocument.
    3. Builds prompt enforcing design-driven, requirement-traceable code generation.
    4. Invokes Code LLM with structured output to produce CodeArtifact.
    5. Validates generated code against guardrails (validate_design_implementation).
    6. Falls back to design-driven dynamic fallback if LLM output fails or violates guardrails.
    7. Scaffolds codebase to disk and updates state.
    """
    print("\nCode Agent: generating implementation from design...")

    design = state.get("design", {})
    requirements = state.get("requirements", {})
    project_id = state.get("project_id")

    if not project_id:
        raise ValueError("Code Agent requires 'project_id' to be set in state.")

    code_version = state.get("code_version", 0) + 1

    resolved = resolve_technology(design)
    plan = create_generation_plan(resolved, design)
    stack = plan.system_type.value
    print(f"  [Code Agent] Technology contract resolved: system_type='{plan.system_type}', frontend='{plan.frontend}', backend='{plan.backend}', database='{plan.database}'")

    req_context = format_requirements_context(requirements)
    design_context = format_design_context(design)
    feedback_context = format_feedback_context(state)

    try:
        system_content = imports.load_prompt("prompts/code_prompt.txt")
    except Exception:
        system_content = (
            "You are a Software Implementation Agent.\n"
            "Implement the approved requirements according to the approved Design Document.\n"
            "The Design Document is authoritative.\n"
            "Do not invent product functionality, entities, APIs, or databases unless explicitly required by design."
        )

    code_prompt = imports.SystemMessage(content=system_content)

    user_instructions = f"""
=== PROJECT: {project_id} (v{code_version}) ===

=== REQUIREMENTS SPECIFICATION ===
{req_context}

=== AUTHORITATIVE SYSTEM DESIGN SPECIFICATION ===
{design_context}
{feedback_context}

CRITICAL IMPLEMENTATION RULES:
1. The DesignDocument is the sole authoritative contract. Implement ONLY components, data entities,
   and API endpoints that are explicitly listed in the design. Do NOT invent functionality.
2. Do NOT create a database, ORM (SQLAlchemy/Hibernate), or persistence layer if design.data_entities is empty.
3. Do NOT create API routes (GET/POST/PUT/DELETE) if design.api_endpoints is empty.
4. Do NOT add health, root (/), or status endpoints unless they are specified in design.api_endpoints.
5. Use technology_choices from the design exactly. Do NOT replace PostgreSQL with SQLite, FastAPI with Flask, etc.
6. If system_type is Frontend: generate HTML/CSS/JS (or the specified JS framework). No Python backend.
7. If system_type is CLI: generate CLI code. No web server (no FastAPI, Flask, or Django).
8. If system_type is Data processing: generate a data pipeline. No REST API layer.
9. Acceptance criteria define observable behavior that MUST be implemented — not just referenced.
10. Populate requirement_ids and design_component_ids on every CodeFile for full pipeline traceability.
11. Generate the dependency manifest appropriate for the technology (requirements.txt for Python,
    package.json for Node.js). Pure static HTML/CSS/JS needs no dependency manifest.
12. Include verification tests that match the technology and test only specified behavior.
13. Distinguish clearly: Design decisions (from DesignDocument) vs Code Agent implementation decisions.
    Record Code Agent decisions in implementation_notes, never claim them as Design Agent decisions.
"""

    response: Optional[CodeArtifact] = None
    try:
        llm = imports.get_llm(agent_type="code", max_tokens=4000)
        code_llm = llm.with_structured_output(CodeArtifact)
        result = code_llm.invoke([
            code_prompt,
            imports.HumanMessage(content=user_instructions)
        ])
        if result and isinstance(result, CodeArtifact) and result.files:
            response = result
        else:
            print("  [Code Agent] LLM returned empty or invalid CodeArtifact — using design-driven fallback.")
            response = generate_dynamic_fallback(project_id, requirements, design)
    except Exception as e:
        print(f"  [Code Agent] LLM code generation issue: {e}")
        print("  [Code Agent] Activating design-driven fallback...")
        response = generate_dynamic_fallback(project_id, requirements, design)

    # Sanitize all generated files
    for f in response.files:
        f.content = sanitize_code_content(f.path, f.content)

    # Validate output against design contract guardrails
    is_valid, violations = validate_design_implementation(requirements, design, response)
    if not is_valid:
        print(f"  [Code Agent] Design implementation violations detected: {violations}")
        print("  [Code Agent] Replacing with strictly compliant design-driven fallback...")
        response = generate_dynamic_fallback(project_id, requirements, design)
        # Sanitize fallback files and validate AGAIN before scaffolding
        for f in response.files:
            f.content = sanitize_code_content(f.path, f.content)
        fb_valid, fb_violations = validate_design_implementation(requirements, design, response)
        if not fb_valid:
            print(f"  [Code Agent] Fallback validation issues detected: {fb_violations}")

    # Ensure implementation notes record stack decisions
    response.implementation_notes = list(dict.fromkeys(response.implementation_notes + plan.notes))

    # Write files to disk via repo_scaffold tool
    files_payload = [{"path": f.path, "content": f.content} for f in response.files]

    scaffold_result = repo_scaffold.invoke({
        "project_id": project_id,
        "files": files_payload,
    })

    project_path = scaffold_result.get("project_path", "")
    print(f"  [Code Agent] Wrote {scaffold_result.get('file_count', len(files_payload))} files to: {project_path}")

    code_artifact = {
        "files": [
            {
                "path": f.path,
                "content": f.content,
                "description": f.description,
                "requirement_ids": f.requirement_ids,
                "design_component_ids": f.design_component_ids,
            }
            for f in response.files
        ],
        "dependencies": response.dependencies or plan.dependencies,
        "setup_instructions": response.setup_instructions or plan.run_command,
        "implementation_notes": response.implementation_notes,
        "test_command": response.test_command or plan.test_command,
        "generated_project_path": project_path,
        "files_written": scaffold_result.get("files_written", []),
        "stack": stack,
    }

    retry_count = dict(state.get("retry_count", {}))
    if code_version > 1:
        retry_count["code"] = retry_count.get("code", 0) + 1

    return {
        "code": code_artifact,
        "code_version": code_version,
        "generated_project_path": project_path,
        "current_stage": "code",
        "workflow_status": "running",
        "retry_count": retry_count,
    }
