import json
import re
import imports
from pydantic import BaseModel, Field
from State_definition import AgentState

class DesignComponent(BaseModel):
    id: str = Field(description="Unique ID in the form COMP-01, COMP-02, ...")
    name: str
    responsibility: str
    requirement_ids: list[str] = Field(default_factory=list)


class DataEntity(BaseModel):
    id: str
    name: str
    purpose: str
    attributes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)


class APIEndpoint(BaseModel):
    id: str
    method: str
    path: str
    description: str
    request_fields: list[str] = Field(
        default_factory=list,
        description="Input fields with type and validation rule, e.g. 'title: string, 1-100 chars'.")
    response_fields: list[str] = Field(
        default_factory=list,
        description="Success response body fields with type, e.g. 'id: integer'.")
    success_status: int = Field(default=200, description="Exact HTTP status on success, e.g. 201.")
    error_cases: list[str] = Field(
        default_factory=list,
        description="Failures as 'condition -> status', e.g. 'unknown id -> 404'.")
    requirement_ids: list[str] = Field(default_factory=list)


class DesignDecision(BaseModel):
    id: str
    decision: str
    reason: str
    requirement_ids: list[str] = Field(default_factory=list)


class EdgeCase(BaseModel):
    id: str
    description: str
    requirement_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)


class TechnologyChoice(BaseModel):
    category: str = Field(
        description="Core architecture category: 'language' (Python, Go, Java, TypeScript, Rust), 'backend' (FastAPI, Gin, Spring Boot, Flask, Express), 'frontend' (HTML/CSS/JS, React, Vue, Svelte), 'database' (PostgreSQL, MongoDB, SQLite, MySQL, Redis), 'testing' (pytest, go test, JUnit, Jest)"
    )
    technology: str = Field(description="Selected technology name, e.g. 'Go', 'Python', 'FastAPI', 'PostgreSQL', 'MongoDB', 'React'")
    reason: str = Field(description="Reason for selection")


class DesignDocument(BaseModel):
    system_type: str = Field(
        description="Type of system being built, e.g. 'Frontend web application', 'Backend REST API', 'CLI application', 'Data processing application'."
    )

    architecture: str = Field(
        description="2-3 full sentences: the major parts, what each is responsible for, and how they interact. Never a single word such as 'Monolithic'."
    )

    components: list[DesignComponent] = Field(
        default_factory=list
    )

    data_entities: list[DataEntity] = Field(
        default_factory=list
    )

    api_endpoints: list[APIEndpoint] = Field(
        default_factory=list
    )

    external_integrations: list[str] = Field(
        default_factory=list
    )

    technology_choices: list[TechnologyChoice] = Field(
        default_factory=list,
        description="Core architectural technology choices (language, frontend, backend, database, testing)."
    )

    libraries_and_tools: list[str] = Field(
        default_factory=list,
        description="Auxiliary libraries, HTTP clients, ORMs, styling toolkits, and utility packages (e.g. Axios, Pydantic, SQLAlchemy, TailwindCSS, Bcrypt, Requests). Never place these in frontend/backend."
    )

    design_decisions: list[DesignDecision] = Field(
        default_factory=list
    )

    edge_cases: list[EdgeCase] = Field(
        default_factory=list
    )


def generate_design_fallback(requirements: dict, idea: str = "") -> DesignDocument:
    """Deterministic fallback for DesignDocument when LLM fails or is unreachable."""
    problem = requirements.get("problem_statement", "Application")
    requested = _requested_language(requirements, idea)
    problem_lower = (problem + " " + idea).lower()

    # Determine system type and stack based on explicit language or problem keywords
    if requested == "HTML/CSS" or any(k in problem_lower for k in ["html", "css", "frontend", "ui", "dashboard", "visualize", "interface", "web app"]):
        system_type = "Frontend Web Application"
        tech_choices = [
            TechnologyChoice(category="frontend", technology="HTML/CSS/JS", reason="Lightweight responsive client-side interface."),
            TechnologyChoice(category="language", technology="JavaScript", reason="Client-side interactivity."),
            TechnologyChoice(category="backend", technology="none", reason="Static frontend without backend server."),
            TechnologyChoice(category="testing", technology="node:test", reason="Standard frontend testing framework.")
        ]
        api_endpoints = []
        data_entities = []
    elif requested in ("C", "C++"):
        system_type = "CLI Application"
        compiler = "gcc" if requested == "C" else "g++"
        tech_choices = [
            TechnologyChoice(category="language", technology=requested, reason=f"Explicitly requested {requested}."),
            TechnologyChoice(category="backend", technology="none", reason=f"Standalone {requested} application."),
            TechnologyChoice(category="testing", technology=compiler, reason=f"Standard {requested} test harness.")
        ]
        api_endpoints = []
        data_entities = []
    else:
        system_type = "Backend REST API"
        tech_choices = [
            TechnologyChoice(category="language", technology="Python", reason="Modern high-performance backend language."),
            TechnologyChoice(category="backend", technology="FastAPI", reason="Modern high-performance async Python framework."),
            TechnologyChoice(category="database", technology="SQLite", reason="Self-contained local relational database."),
            TechnologyChoice(category="testing", technology="pytest", reason="Standard Python test framework.")
        ]
        api_endpoints = [
            APIEndpoint(id="EP-01", method="POST", path="/api/items", description="Create a new item", requirement_ids=["FR-01"]),
            APIEndpoint(id="EP-02", method="GET", path="/api/items", description="List all items", requirement_ids=["FR-01"]),
            APIEndpoint(id="EP-03", method="GET", path="/api/items/{id}", description="Get item by ID", requirement_ids=["FR-01"])
        ]
        data_entities = [
            DataEntity(id="ENT-01", name="Item", purpose="Primary data entity", attributes=["id", "title", "created_at"], relationships=[], requirement_ids=["FR-01"])
        ]

    components = [
        DesignComponent(id="COMP-01", name="MainController", responsibility=f"Coordinates core functionality for {problem[:40]}.", requirement_ids=["FR-01"]),
        DesignComponent(id="COMP-02", name="DataService", responsibility="Manages state and operations.", requirement_ids=["FR-01"])
    ]

    decisions = [
        DesignDecision(id="DEC-01", decision="Layered Modular Architecture", reason="Clear separation of concerns.", requirement_ids=["FR-01"])
    ]

    edge_cases = [
        EdgeCase(id="EC-01", description="Empty or invalid input handling.", requirement_ids=["FR-01"], component_ids=["COMP-01"])
    ]

    return DesignDocument(
        system_type=system_type,
        architecture="Layered modular architecture adhering directly to requirement specifications.",
        components=components,
        data_entities=data_entities,
        api_endpoints=api_endpoints,
        external_integrations=[],
        technology_choices=tech_choices,
        design_decisions=decisions,
        edge_cases=edge_cases
    )


# Frameworks the test sandbox cannot build/run (no npm install, no bundler, node:test only).
UNBUILDABLE_FRONTENDS = ("react", "vue", "svelte", "angular", "next", "nuxt")


def _tech(design: dict, category: str) -> str:
    for c in design.get("technology_choices", []):
        if str(c.get("category", "")).lower() == category:
            return str(c.get("technology", "")).strip()
    return ""


def _requested_language(requirements: dict, idea: str = "") -> str:
    """Return an explicitly requested implementation language, if one is present."""
    values = [str(requirements.get("problem_statement", "")), idea]
    for key in ("constraints", "assumptions", "in_scope"):
        for item in requirements.get(key, []):
            values.append(str(item.get("description", item) if isinstance(item, dict) else item))
    text = " ".join(values).lower()

    if any(k in text for k in ("html and css", "html/css", "html5", "plain html", "html, css", "html css", "vanilla html")):
        return "HTML/CSS"
    if "c++" in text or "cpp" in text:
        return "C++"
    if re.search(r"\b(?:in\s+c\b|c\s+language|using\s+c\b|c\s+programming|\bc\s+code\b)", text) or re.search(r"(?<![a-z0-9_])c(?![a-z0-9_+#])", text):
        if "c#" not in text:
            return "C"

    languages = (
        ("typescript", "TypeScript"), ("javascript", "JavaScript"), ("c++", "C++"),
        ("rust", "Rust"), ("golang", "Go"), (" go ", "Go"), ("java", "Java"),
        ("python", "Python"), ("kotlin", "Kotlin"), ("swift", "Swift"),
        ("c#", "C#"), ("ruby", "Ruby"), ("php", "PHP"), ("html", "HTML/CSS"),
    )
    for marker, language in languages:
        if re.search(rf"(?<![a-z]){re.escape(marker.strip())}(?![a-z])", text):
            return language
    return ""


def _enforce_requested_language(design: dict, requirements: dict, idea: str = "") -> None:
    requested = _requested_language(requirements, idea)
    if not requested:
        return
    choices = design.setdefault("technology_choices", [])

    if requested == "HTML/CSS":
        design["system_type"] = "Frontend Web Application"
        frontend_choice = next((c for c in choices if str(c.get("category", "")).lower() == "frontend"), None)
        if frontend_choice:
            frontend_choice["technology"] = "HTML/CSS/JS"
            frontend_choice["reason"] = "Explicitly requested HTML/CSS."
        else:
            choices.insert(0, {"category": "frontend", "technology": "HTML/CSS/JS", "reason": "Explicitly requested HTML/CSS."})
        lang_choice = next((c for c in choices if str(c.get("category", "")).lower() == "language"), None)
        if lang_choice:
            lang_choice["technology"] = "JavaScript"
        else:
            choices.append({"category": "language", "technology": "JavaScript", "reason": "Client-side interactivity."})
        backend_choice = next((c for c in choices if str(c.get("category", "")).lower() == "backend"), None)
        if backend_choice:
            backend_choice["technology"] = "none"
        else:
            choices.append({"category": "backend", "technology": "none", "reason": "Client-side only application."})
        test_choice = next((c for c in choices if str(c.get("category", "")).lower() == "testing"), None)
        if test_choice:
            test_choice["technology"] = "node:test"
        else:
            choices.append({"category": "testing", "technology": "node:test", "reason": "node:test DOM verification."})
        design["api_endpoints"] = []
        design["data_entities"] = []
        return

    if requested in ("C", "C++"):
        design["system_type"] = "CLI Application"
        compiler = "gcc" if requested == "C" else "g++"
        lang_choice = next((c for c in choices if str(c.get("category", "")).lower() == "language"), None)
        if lang_choice:
            lang_choice["technology"] = requested
            lang_choice["reason"] = f"Explicitly requested {requested}."
        else:
            choices.insert(0, {"category": "language", "technology": requested, "reason": f"Explicitly requested {requested}."})
        backend_choice = next((c for c in choices if str(c.get("category", "")).lower() == "backend"), None)
        if backend_choice:
            backend_choice["technology"] = "none"
        else:
            choices.append({"category": "backend", "technology": "none", "reason": "Standalone binary."})
        test_choice = next((c for c in choices if str(c.get("category", "")).lower() == "testing"), None)
        if test_choice:
            test_choice["technology"] = compiler
        else:
            choices.append({"category": "testing", "technology": compiler, "reason": f"Standard {requested} test harness."})
        design["api_endpoints"] = []
        return

    language_choice = next(
        (choice for choice in choices if str(choice.get("category", "")).lower() == "language"),
        None,
    )
    if language_choice is None:
        choices.insert(0, {
            "category": "language",
            "technology": requested,
            "reason": "Explicitly requested by the user requirements.",
        })
    elif str(language_choice.get("technology", "")).strip().lower() != requested.lower():
        language_choice["technology"] = requested
        language_choice["reason"] = "Explicitly requested by the user requirements."


def normalize_design(design: dict, requirements: dict, idea: str = "") -> dict:
    """
    Deterministic consistency pass. Small LLMs often return contradictory designs
    (frontend-only app with an API and a database, React in a sandbox that cannot build it).
    Fix those contradictions instead of passing them downstream. Every change is recorded
    as a design decision so nothing happens silently.
    """
    changes = []
    _enforce_requested_language(design, requirements, idea)
    choices = design.get("technology_choices", [])
    backend = _tech(design, "backend").lower()
    frontend = _tech(design, "frontend").lower()
    req_text = str(requirements).lower()
    no_backend = backend in ("", "none", "null", "n/a")

    # 1. Framework the sandbox cannot execute, and the user never asked for it -> plain HTML/CSS/JS
    if any(k in frontend for k in UNBUILDABLE_FRONTENDS) and not any(k in req_text for k in UNBUILDABLE_FRONTENDS):
        for c in choices:
            cat = str(c.get("category", "")).lower()
            if cat == "frontend":
                c["technology"] = "HTML/CSS/JS"
                c["reason"] = "Plain HTML/CSS/JS runs and is testable without a build step."
            if cat == "language":
                c["technology"] = "JavaScript"
            if cat == "testing":
                c["technology"] = "node:test"
                c["reason"] = "Built-in Node test runner; no dependencies required."
        design["libraries_and_tools"] = []
        changes.append("Frontend simplified to plain HTML/CSS/JS (no build step available; framework not required by the requirements).")
        frontend = "html/css/js"

    # 2. No backend => no API endpoints and no server-side database
    if no_backend:
        if design.get("api_endpoints"):
            design["api_endpoints"] = []
            changes.append("Removed API endpoints: the design has no backend; data is provided by in-app sample data.")
        kept = [c for c in choices if str(c.get("category", "")).lower() != "database"]
        if len(kept) != len(choices):
            design["technology_choices"] = kept
            changes.append("Removed database choice: a frontend-only app keeps data in memory/sample data.")
        if "html" in frontend and design.get("libraries_and_tools"):
            design["libraries_and_tools"] = []

    # 3. Query strings belong in request_fields, never in the path
    for ep in design.get("api_endpoints", []):
        path, sep, query = str(ep.get("path", "")).partition("?")
        if sep:
            ep["path"] = path
            ep.setdefault("request_fields", []).append(f"Query Parameters: {query}")
            changes.append(f"Moved query string out of endpoint path '{path}' into request_fields.")

    # 4. Drop duplicate components (same name)
    seen, unique = set(), []
    for comp in design.get("components", []):
        key = str(comp.get("name", "")).strip().lower()
        if key and key in seen:
            continue
        seen.add(key)
        unique.append(comp)
    if len(unique) != len(design.get("components", [])):
        design["components"] = unique
        changes.append("Removed duplicate components.")

    if changes:
        design.setdefault("design_decisions", []).extend(
            {"id": f"DEC-N{i+1:02d}", "decision": text,
             "reason": "Automatic consistency check of the design.", "requirement_ids": []}
            for i, text in enumerate(changes)
        )
        for text in changes:
            print(f"  [Design Agent] consistency fix: {text}")
    return _renumber_ids(design)


def _renumber_ids(design: dict) -> dict:
    """Small models ignore ID formats (C1, EP-01, DEC-01). Force COMP/ENT/API/DD/EC-NN and keep references valid."""
    comp_map = {}
    for i, comp in enumerate(design.get("components", []), 1):
        new_id = f"COMP-{i:02d}"
        comp_map[comp.get("id")] = new_id
        comp["id"] = new_id
    for prefix, key in (("ENT", "data_entities"), ("API", "api_endpoints"), ("DD", "design_decisions")):
        for i, item in enumerate(design.get(key, []), 1):
            item["id"] = f"{prefix}-{i:02d}"
    for i, edge in enumerate(design.get("edge_cases", []), 1):
        edge["id"] = f"EC-{i:02d}"
        edge["component_ids"] = [comp_map.get(c, c) for c in edge.get("component_ids", [])]
    return design


def Design_Agent(state: AgentState) -> dict:
    print("\nDesign Agent received requirements")

    requirements = state.get("requirements", {})
    idea = state.get("idea", "")

    response = None
    try:
        llm = imports.get_llm(agent_type="design", max_tokens=6000)
        messages = [imports.SystemMessage(content=imports.load_prompt("prompts/design_prompt.txt"))]
        try:
            messages.append(imports.SystemMessage(content=imports.load_prompt("skills/design_skill.txt")))
        except OSError:
            print("  [Design Agent] skills/design_skill.txt not found - continuing with the prompt only.")
        messages.append(imports.HumanMessage(
            content=f"Original Product Idea:\n{idea}\n\nHere are the requirements produced by the Requirement Agent:\n\n"
                    + json.dumps(requirements, indent=1, ensure_ascii=False, default=str)
        ))
        result = imports.invoke_structured(llm, DesignDocument, messages)
        if result and isinstance(result, DesignDocument):
            response = result
        else:
            print("  [Design Agent] Structured response was empty or invalid — activating fallback.")
            response = generate_design_fallback(requirements, idea)
    except Exception as e:
        print(f"  [Design Agent] Design LLM invocation issue: {e}")
        print("  [Design Agent] Activating design-driven fallback...")
        response = generate_design_fallback(requirements, idea)

    design = normalize_design(response.model_dump(), requirements, idea)

    return {
        "design": design,
        "design_version": state.get("design_version", 0) + 1,
        "current_stage": "design",
        "workflow_status": "running"
    }