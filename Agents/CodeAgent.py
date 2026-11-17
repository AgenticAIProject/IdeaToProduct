"""
CodeAgent.py - lean, design-driven code generation.

Pipeline
    1. PLAN      one small structured call -> list of files to write (+ exports)
    2. GENERATE  one plain-text call PER FILE (no JSON wrapping, truncation-safe)
    3. VALIDATE  deterministic checks (ast / json / node --check / truncation markers)
    4. REPAIR    feed the real error back to the LLM for that one file (max 2 tries)
    5. WRITE     repo_scaffold -> disk

Rework (review rejected / tests failed)
    - Re-use the previous plan, ask the LLM WHICH files must change,
      regenerate ONLY those files with the failing test output as context.

There is deliberately NO template fallback. A generic template that ignores the
requirements always fails the tests; it just hides the real problem. If generation
fails, the agent says so and the real error flows to the next stage.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Literal, Optional

from pydantic import BaseModel, Field

import imports
from State_definition import AgentState
from stack_skills import stack_skill
from tools import WORKSPACE_ROOT, repo_scaffold

MAX_REPAIR_ATTEMPTS = 2
MAX_CONTINUATIONS = 2          # how often we ask the model to continue a cut-off file
MANIFESTS = {"requirements.txt", "package.json", "go.mod", "pom.xml", "cargo.toml"}
PLACEHOLDER_MARKERS = (
    "rest of the code", "your code here", "implement this", "implementation goes here",
    "same as before", "remains unchanged", "# ...", "// ...",
)


# ──────────────────────────────────────────────────────────────────────────────
# Schemas (small on purpose)
# ──────────────────────────────────────────────────────────────────────────────

class GeneratedFile(BaseModel):
    path: str = Field(description="Relative path, e.g. 'app.py', 'models.py', 'schemas.py', 'database.py', 'requirements.txt', 'static/index.html'")
    purpose: str = Field(default="", description="One line: what this file is responsible for")
    exports: list[str] = Field(
        default_factory=list,
        description="Public names other files/tests will use: functions, classes, routes, DOM ids",
    )
    content: str = Field(default="", description="Complete source code. No placeholders, no ellipses, no '# ...'.")
    requirement_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)


FilePlan = GeneratedFile


class RepositoryGeneration(BaseModel):
    language: str = Field(default="python", description="Main language, e.g. python, javascript, go, java")
    run_command: str = Field(default="python app.py", description="Command to run the project")
    test_command: str = Field(default="pytest --tb=short -v", description="Command to run tests, e.g. 'pytest --tb=short -v'")
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list, description="Implementation decisions and architectural notes")
    files: list[GeneratedFile] = Field(description="Every file needed to run the project. Do NOT include test files.")


CodePlan = RepositoryGeneration


class RepositoryRework(BaseModel):
    notes: list[str] = Field(default_factory=list, description="Explanation of what was fixed")
    files: list[GeneratedFile] = Field(description="Modified or new files that fix the errors and defects. Only include files that were updated or added.")


class LayerGeneration(BaseModel):
    notes: list[str] = Field(default_factory=list, description="Layer implementation decisions and exports")
    files: list[GeneratedFile] = Field(description="Complete source files for this layer. No placeholders, no ellipses, no '# ...'.")


class FixSelection(BaseModel):
    paths_to_change: list[str] = Field(description="Existing file paths that must be modified")
    new_files: list[GeneratedFile] = Field(default_factory=list, description="New files that must be added, if any")


# ──────────────────────────────────────────────────────────────────────────────
# Context builders (compact; no per-stack hardcoding)
# ──────────────────────────────────────────────────────────────────────────────

def _compact(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, default=str)


def requirements_context(req: dict) -> str:
    keep = {k: req.get(k) for k in (
        "problem_statement", "functional_requirements", "acceptance_criteria",
        "non_functional_requirements", "constraints", "assumptions", "in_scope", "out_of_scope",
    ) if req.get(k)}
    return _compact(keep)


def design_context(design: dict) -> str:
    return _compact({k: v for k, v in design.items() if v})


def extract_file_interface(path: str, content: str) -> str:
    """Extract public signatures, types, and exports instead of full source code to save context."""
    ext = os.path.splitext(path)[1].lower()

    # Python files: extract class/func signatures
    if ext == ".py":
        try:
            tree = ast.parse(content)
            signatures = []
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = ast.unparse(node.args) if hasattr(ast, "unparse") else "..."
                    ret = f" -> {ast.unparse(node.returns)}" if getattr(node, "returns", None) and hasattr(ast, "unparse") else ""
                    signatures.append(f"def {node.name}({args}){ret}: ...")
                elif isinstance(node, ast.ClassDef):
                    signatures.append(f"class {node.name}:")
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            args = ast.unparse(item.args) if hasattr(ast, "unparse") else "..."
                            ret = f" -> {ast.unparse(item.returns)}" if getattr(item, "returns", None) and hasattr(ast, "unparse") else ""
                            signatures.append(f"    def {item.name}({args}){ret}: ...")
            if signatures:
                return "\n".join(signatures)
        except Exception:
            lines = [line.strip() for line in content.splitlines() if line.strip().startswith(("def ", "class ", "@app."))]
            if lines:
                return "\n".join(lines[:30])
        return content[:500]

    # C / C++ files:
    if ext in (".h", ".hpp"):
        return content[:1500]
    if ext in (".c", ".cpp", ".cc"):
        lines = []
        for line in content.splitlines():
            s = line.strip()
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_* ]+\s+[a-zA-Z_][a-zA-Z0-9_]*\s*\(.*\)", s):
                clean = re.sub(r"\s*\{.*$", ";", s)
                lines.append(clean)
        if lines:
            return "\n".join(lines)
        return f"{path}: (C/C++ implementation)"

    # HTML files: extract element IDs and form controls
    if ext in (".html", ".htm"):
        tags = re.findall(r'<(button|input|form|select|textarea|table|div)[^>]*id=["\']([^"\']+)["\'][^>]*>', content)
        if tags:
            return "HTML Elements:\n" + "\n".join(f"- <{t[0]} id=\"{t[1]}\">" for t in tags[:25])
        ids = re.findall(r'id=["\']([^"\']+)["\']', content)
        if ids:
            return f"HTML element IDs: {ids[:25]}"
        return f"{path}: (HTML structure)"

    # JS files: extract exported functions
    if ext in (".js", ".ts", ".mjs"):
        lines = []
        for line in content.splitlines():
            s = line.strip()
            if s.startswith(("function ", "const ", "let ", "exports.", "module.exports")):
                lines.append(s[:100])
        if lines:
            return "\n".join(lines[:25])
        return content[:500]

    if os.path.basename(path).lower() in ("requirements.txt", "package.json"):
        return content[:500]

    return content[:300]


def summarize_written_files(written: dict[str, str], current_path: str) -> str:
    """Produce a compact interface summary of previously written files."""
    parts = []
    for path, content in written.items():
        if path == current_path:
            continue
        interface = extract_file_interface(path, content)
        parts.append(f"--- {path} (interfaces & signatures) ---\n{interface}")
    return "\n\n".join(parts)


def file_requirements_context(fp: FilePlan, req: dict) -> str:
    """Keep requirements compact and focused for individual file generation."""
    problem = req.get("problem_statement", "")
    constraints = [c.get("description", c) if isinstance(c, dict) else str(c) for c in req.get("constraints", [])]

    frs = req.get("functional_requirements", [])
    acs = req.get("acceptance_criteria", [])

    if fp.requirement_ids:
        matched_frs = [f for f in frs if isinstance(f, dict) and f.get("id") in fp.requirement_ids]
        matched_acs = [a for a in acs if isinstance(a, dict) and a.get("requirement_id") in fp.requirement_ids]
    else:
        matched_frs = frs[:5]
        matched_acs = acs[:8]

    compact_data = {
        "problem": problem,
        "constraints": constraints,
        "functional_requirements": [
            f"{f.get('id', '')}: {f.get('description', '')}" if isinstance(f, dict) else str(f)
            for f in (matched_frs or frs[:6])
        ],
        "acceptance_criteria": [
            f"{a.get('requirement_id', '')}: {a.get('description', '')}" if isinstance(a, dict) else str(a)
            for a in (matched_acs or acs[:8])
        ]
    }
    return json.dumps(compact_data, indent=1, ensure_ascii=False)


def file_design_context(fp: FilePlan, design: dict) -> str:
    """Keep design compact and relevant to the file being generated."""
    tech = [
        f"{c.get('category')}: {c.get('technology')}"
        for c in design.get("technology_choices", [])
        if isinstance(c, dict)
    ]
    compact = {
        "system_type": design.get("system_type", ""),
        "architecture": design.get("architecture", ""),
        "technology_choices": tech,
    }
    if any(k in fp.path.lower() for k in ("app", "api", "route", "server", "main")):
        if design.get("api_endpoints"):
            compact["api_endpoints"] = [
                f"{ep.get('method')} {ep.get('path')}: {ep.get('description')}"
                for ep in design.get("api_endpoints", [])[:5] if isinstance(ep, dict)
            ]
    return json.dumps(compact, indent=1, ensure_ascii=False)


def feedback_context(state: AgentState) -> str:
    """Review defects + the REAL failing test output (and the tests themselves)."""
    review = state.get("review") or {}
    tr = state.get("test_results") or {}
    parts = []

    if review.get("defects"):
        parts.append("Review defects:\n" + "\n".join(f"- {d}" for d in review["defects"]))
    if review.get("feedback"):
        parts.append("Review feedback:\n" + "\n".join(f"- {d}" for d in review["feedback"]))

    if tr and (tr.get("failed_tests", 0) > 0 or tr.get("errors") or tr.get("success") is False):
        raw = "\n".join((tr.get("raw_output") or "").strip().splitlines()[-60:])
        parts.append(f"Test run: {tr.get('summary', '')}\nErrors: {tr.get('errors', [])}\nOutput tail:\n{raw}")
        for name, content in (tr.get("test_files") or {}).items():
            parts.append(f"--- Test file the code must satisfy: {name} ---\n{content[:4000]}")

    return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# Validation (deterministic, language-aware, no keyword-guessing of the design)
# ──────────────────────────────────────────────────────────────────────────────

def strip_fences(text: str) -> str:
    """Extract raw code from LLM output that may contain preamble, fences, and postamble.

    Handles patterns like:
      - "Certainly! Here is the file:\n```js\n<code>\n```\n### Explanation..."
      - "```\n<code>\n```"
      - Raw code with no fences
    """
    t = text.strip()
    # 1. Try to extract content from code fences anywhere in the text
    m = re.search(r"```[\w+-]*\n(.*?)\n```", t, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 2. No fences found — strip common preamble lines (model commentary before the code)
    lines = t.splitlines()
    # Drop leading lines that look like commentary (not code)
    while lines and _is_commentary(lines[0]):
        lines.pop(0)
    # Drop trailing lines that look like commentary
    while lines and _is_commentary(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


def _is_commentary(line: str) -> bool:
    """True if a line looks like model commentary rather than code."""
    s = line.strip()
    if not s:
        return True
    # Markdown headings, "Certainly!", "Here is...", "Below is...", "It appears..."
    commentary_starts = (
        "#", "certainly", "sure", "here is", "here's", "below is", "below are",
        "it appears", "it seems", "the complete", "the file", "note:", "explanation",
        "---",
    )
    return s.lower().startswith(commentary_starts)


def validate_file(path: str, content: str) -> Optional[str]:
    """Return an error string, or None if the file looks fine."""
    if len(content.strip()) < 10:
        return "File is empty."

    low = content.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker in low:
            return f"File contains a placeholder/elision ('{marker}'). Write the complete file."

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".py":
            try:
            # Check for raw compilation typos
                ast.parse(content, filename=path)
                
                # Check for common missing imports before sending to test_runner
                if "os.environ" in content and "import os" not in content:
                    return "SyntaxError: 'os' module is used (os.environ) but 'import os' is missing."
                if "sqlite3.connect" in content and "import sqlite3" not in content:
                    return "SyntaxError: 'sqlite3' module is used but 'import sqlite3' is missing."
                
            except SyntaxError as e:
                return f"SyntaxError line {e.lineno}: {e.msg}"

        elif ext == ".json":
            json.loads(content)
        elif ext in (".html", ".htm"):
            if "</html>" not in low:
                return "HTML file is truncated (no closing </html>)."
        elif ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
            with tempfile.NamedTemporaryFile("w", suffix=ext, delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                r = subprocess.run(["node", "--check", tmp_path], capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    return r.stderr.strip()[:500]
            finally:
                os.unlink(tmp_path)
    except SyntaxError as e:
        return f"SyntaxError line {e.lineno}: {e.msg}"
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Validation error: {e}"
    return None


def validate_c_project(files: dict[str, str]) -> list[str]:
    """Compile-check all C translation units together with their generated headers available."""
    sources = [path for path in files if path.lower().endswith(".c")]
    if not sources:
        return []
    if not shutil.which("gcc"):
        return ["gcc is not installed; C project compile check was skipped."]

    with tempfile.TemporaryDirectory() as temp_dir:
        include_dirs = {temp_dir}
        for path, content in files.items():
            normalized = os.path.normpath(path)
            if os.path.isabs(normalized) or normalized == ".." or normalized.startswith(".." + os.sep):
                return [f"Unsafe generated path in C project: {path}"]
            full_path = os.path.join(temp_dir, normalized)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as generated_file:
                generated_file.write(content)
            if path.lower().endswith((".c", ".h")):
                include_dirs.add(os.path.dirname(full_path))

        command = ["gcc", "-std=c11", "-Wall", "-Wextra", "-fsyntax-only"]
        for include_dir in sorted(include_dirs):
            command.extend(["-I", include_dir])
        command.extend(os.path.join(temp_dir, os.path.normpath(path)) for path in sources)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return ["gcc C project compile check timed out after 30 seconds."]
        if result.returncode != 0:
            return [result.stderr.strip()[:2000] or "gcc C project compile check failed."]
    return []


def check_cross_file(files: dict[str, str]) -> list[str]:
    """Warn when a Python file imports a module that is neither generated, stdlib, nor in requirements.txt."""
    import sys
    problems = []
    local = {os.path.splitext(p)[0].split("/")[0] for p in files if p.endswith(".py")}
    reqs = files.get("requirements.txt", "").lower().replace("_", "-")
    stdlib = getattr(sys, "stdlib_module_names", set())
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [node.module.split(".")[0]]
            elif isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            for n in names:
                if n in stdlib or n in local or n.lower().replace("_", "-") in reqs:
                    continue
                problems.append(f"{path}: imports '{n}' (not generated, not stdlib, not in requirements.txt)")
    return sorted(set(problems))


def write_file_to_disk(project_id: str, relative_path: str, content: str) -> str:
    """Persist the latest generated file immediately so intermediate generation is inspectable."""
    project_dir = WORKSPACE_ROOT / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    abs_path = project_dir / relative_path.lstrip("/").replace("\\", "/")
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return str(abs_path)


def ensure_requirements_txt(written: dict[str, str], plan: CodePlan, project_id: str) -> None:
    """Ensure requirements.txt exists and contains all imported third-party modules."""
    import sys
    is_python_project = (
        getattr(plan, "language", "").lower() == "python"
        or any(p.endswith(".py") for p in written.keys())
        or any(f.path.endswith(".py") for f in getattr(plan, "files", []))
    )
    if not is_python_project:
        return

    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    stdlib.update({
        "os", "sys", "re", "json", "time", "datetime", "math", "random", "typing", "collections",
        "itertools", "functools", "pathlib", "sqlite3", "subprocess", "tempfile", "shutil", "ast",
        "unittest", "http", "urllib", "logging", "hashlib", "base64", "uuid", "io", "copy", "threading",
        "builtins", "abc", "contextlib", "dataclasses", "enum", "inspect", "operator", "string",
    })

    local_modules = {os.path.splitext(os.path.basename(p))[0] for p in written.keys()}
    discovered_deps = set(plan.dependencies or [])

    for p, content in written.items():
        if not p.endswith(".py"):
            continue
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module.split(".")[0]]
                elif isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                for name in names:
                    clean = name.lower()
                    if clean not in stdlib and clean not in local_modules:
                        discovered_deps.add(clean)
        except Exception:
            pass

    package_map = {
        "fastapi": "fastapi",
        "pydantic": "pydantic",
        "sqlalchemy": "sqlalchemy",
        "requests": "requests",
        "flask": "flask",
        "uvicorn": "uvicorn",
        "httpx": "httpx",
        "dotenv": "python-dotenv",
        "jose": "python-jose",
        "jwt": "pyjwt",
        "bcrypt": "bcrypt",
        "pytest": "pytest",
        "jinja2": "jinja2",
    }

    current_reqs = written.get("requirements.txt", "").strip()
    existing_lines = {
        re.split(r"[=<>]", line)[0].strip().lower()
        for line in current_reqs.splitlines()
        if line.strip() and not line.startswith("#")
    }

    new_packages = set()
    for dep in discovered_deps:
        mapped = package_map.get(dep, dep)
        if mapped not in existing_lines:
            new_packages.add(mapped)

    # If FastAPI is used, ensure uvicorn, pytest, httpx are included for tests
    if "fastapi" in existing_lines or "fastapi" in new_packages:
        for extra in ("uvicorn", "pytest", "httpx"):
            if extra not in existing_lines:
                new_packages.add(extra)

    if new_packages or "requirements.txt" not in written or not written.get("requirements.txt", "").strip():
        all_lines = [line.strip() for line in current_reqs.splitlines() if line.strip()]
        for pkg in sorted(new_packages):
            if pkg not in all_lines:
                all_lines.append(pkg)
        final_content = "\n".join(all_lines) + "\n"
        written["requirements.txt"] = final_content
        write_file_to_disk(project_id, "requirements.txt", final_content)
        print(f"  [Code Agent] Ensured requirements.txt with dependencies: {sorted(existing_lines | new_packages)}")


# ──────────────────────────────────────────────────────────────────────────────
# LLM helpers
# ──────────────────────────────────────────────────────────────────────────────

def _text(msg) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)


def extract_files_from_markdown(text: str) -> list[GeneratedFile]:
    """Fallback extractor if model returns Markdown formatted with file headers and code fences."""
    files: list[GeneratedFile] = []
    seen_paths = set()

    pat_header = re.compile(
        r"(?:###\s*(?:[Ff]ile:\s*)?|(?:\*\*|__)(?:[Ff]ile:\s*)?|[Ff]ile:\s*`?)([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)(?:`?|\*\*|__)?\s*[:\n]+```[a-zA-Z0-9_\-]*\n([\s\S]*?)\n```",
        re.MULTILINE
    )
    for path, content in pat_header.findall(text):
        clean_path = path.strip().strip("`*\"'").lstrip("/").replace("\\", "/")
        if clean_path and clean_path not in seen_paths and content.strip():
            seen_paths.add(clean_path)
            files.append(GeneratedFile(
                path=clean_path,
                purpose=f"Implementation file {clean_path}",
                exports=[],
                content=content.strip(),
            ))

    if not files:
        pat_fence = re.compile(r"```[a-zA-Z0-9_\-]*\n(?:#|//|<!--)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9_]+)\s*(?:-->)?\n([\s\S]*?)\n```")
        for path, content in pat_fence.findall(text):
            clean_path = path.strip().strip("`*\"'").lstrip("/").replace("\\", "/")
            if clean_path and clean_path not in seen_paths and content.strip():
                seen_paths.add(clean_path)
                files.append(GeneratedFile(
                    path=clean_path,
                    purpose=f"Implementation file {clean_path}",
                    exports=[],
                    content=content.strip(),
                ))

    return files


def generate_repository_single_shot(
    llm,
    requirements: dict,
    design: dict,
    project_id: str,
) -> tuple[RepositoryGeneration, dict[str, str]]:
    req_ctx = requirements_context(requirements)
    des_ctx = design_context(design)
    playbook = stack_skill(design, "CODE")

    base_prompt = imports.load_prompt("prompts/code_prompt.txt")
    system_prompt = base_prompt + f"\n\n{playbook}"

    human_prompt = f"""Generate the COMPLETE source code repository for this project in ONE response.

=== REQUIREMENTS & ACCEPTANCE CRITERIA ===
{req_ctx}

=== ARCHITECTURE & SYSTEM DESIGN (AUTHORITATIVE) ===
{des_ctx}

=== CRITICAL IMPLEMENTATION RULES ===
1. Generate EVERY file required for the project to execute and pass tests (e.g. models, schemas, database, crud, app/main, requirements.txt, frontend assets if applicable).
2. DO NOT include test files. A separate QA agent writes test suites.
3. Every file must be COMPLETE. Do NOT leave TODOs, placeholders, elisions, or '# ...'.
4. Ensure 100% internal consistency across all files:
   - Match all imported class and function names with their definitions.
   - For FastAPI apps:
     * Populate ALL response model fields. Never return empty strings or None where a value is expected (e.g. compute short_url, long_url, created_at, tags).
     * For redirects: return RedirectResponse(url=link.long_url), NEVER pass raw ORM objects or models to url.
     * Implement required status codes: 201 Created for creation, 307/302 for redirects, 400 for invalid inputs (e.g. invalid URL scheme), 404 for not found, 410 for expired items.
   - For Python projects, always include 'requirements.txt' with all third-party dependencies (fastapi, uvicorn, httpx, pytest, sqlalchemy, etc.).
"""

    messages = [
        imports.SystemMessage(content=system_prompt),
        imports.HumanMessage(content=human_prompt),
    ]

    print("  [Code Agent] Generating complete repository in a single shot...")
    repo = None
    last_err = None
    try:
        repo = imports.invoke_structured(llm, RepositoryGeneration, messages)
    except Exception as e:
        last_err = e
        print(f"  [Code Agent] Structured generation exception ({e}); attempting fallback extraction...")
        try:
            raw_msg = llm.invoke(messages)
            raw_text = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
            parsed_json = imports._extract_json_from_text(raw_text)
            if isinstance(parsed_json, dict) and "files" in parsed_json:
                repo = RepositoryGeneration.model_validate(parsed_json)
            else:
                extracted = extract_files_from_markdown(raw_text)
                if extracted:
                    repo = RepositoryGeneration(language="python", files=extracted)
        except Exception as e2:
            last_err = f"{last_err} | {e2}"

    if not repo or not repo.files:
        raise RuntimeError(f"Code Agent failed to generate repository files: {last_err}")

    written: dict[str, str] = {}
    for f in repo.files:
        clean_content = strip_fences(f.content)
        f.content = clean_content
        written[f.path] = clean_content
        write_file_to_disk(project_id, f.path, clean_content)

    return repo, written


def needs_frontend_layer(design: dict, requirements: dict) -> bool:
    """True if the system design or requirements call for static HTML/JS frontend assets."""
    techs = " ".join(str(c.get("technology", "")) for c in design.get("technology_choices", []) if isinstance(c, dict)).lower()
    system_type = str(design.get("system_type", "")).lower()
    arch = str(design.get("architecture", "")).lower()
    ui_desc = str(design.get("ui_description", "")).lower()
    combined = f"{techs} {system_type} {arch} {ui_desc}"
    return any(k in combined for k in ("frontend", "html", "web ui", "dashboard", "browser", "css", "static", "vanilla js", "react"))


def generate_repository_layered(
    llm,
    requirements: dict,
    design: dict,
    project_id: str,
) -> tuple[RepositoryGeneration, dict[str, str]]:
    """
    Hierarchical 3-Phase Generation:
    1. Core Data Layer (models, schemas, database, requirements.txt)
    2. Logic & Routes (crud, app/main) - given Layer 1's actual code
    3. Frontend Assets (index.html, script.js, style.css) - given Layer 2's API endpoints
    Keeps each call comfortably within 2k tokens and guarantees cross-file synchronization.
    """
    req_ctx = requirements_context(requirements)
    des_ctx = design_context(design)
    playbook = stack_skill(design, "CODE")
    base_prompt = imports.load_prompt("prompts/code_prompt.txt")
    system_prompt = base_prompt + f"\n\n{playbook}"

    written: dict[str, str] = {}
    all_files: list[GeneratedFile] = []
    all_notes: list[str] = []

    # ── Layer 1: Data Contracts, Schemas & Core Storage ─────────────────────
    print("  [Code Agent] [Adaptive Layer 1/3] Generating Data Contracts & Schemas...")
    prompt_p1 = f"""=== REQUIREMENTS ===
{req_ctx}

=== ARCHITECTURE & SYSTEM DESIGN ===
{des_ctx}

=== PHASE 1 TASK: DATA CONTRACTS & STORAGE LAYER ===
Generate the foundational data and contract files:
- For Python: database.py, models.py, schemas.py (Pydantic / ORM models), and requirements.txt.
- Define all database tables, columns, indexes, relationships, and request/response validation schemas.
- Ensure all field names and types match the design specification.
- Every file must be COMPLETE. Do NOT leave placeholders or TODOs.
"""
    try:
        p1 = imports.invoke_structured(llm, LayerGeneration, [
            imports.SystemMessage(content=system_prompt),
            imports.HumanMessage(content=prompt_p1),
        ])
        for f in p1.files:
            clean = strip_fences(f.content)
            f.content = clean
            written[f.path] = clean
            all_files.append(f)
            write_file_to_disk(project_id, f.path, clean)
        all_notes.extend(p1.notes)
    except Exception as e:
        print(f"  [Code Agent] Layer 1 error ({e}); attempting markdown extraction...")
        raw = llm.invoke([imports.SystemMessage(content=system_prompt), imports.HumanMessage(content=prompt_p1)])
        text = raw.content if hasattr(raw, "content") else str(raw)
        extracted = extract_files_from_markdown(text)
        for f in extracted:
            written[f.path] = f.content
            all_files.append(f)
            write_file_to_disk(project_id, f.path, f.content)

    # ── Layer 2: Business Logic & API Endpoints ──────────────────────────────
    print("  [Code Agent] [Adaptive Layer 2/3] Generating Business Logic & REST Endpoints...")
    p1_code_summary = "\n\n".join(f"--- {p} ---\n{c}" for p, c in written.items())
    prompt_p2 = f"""=== REQUIREMENTS ===
{req_ctx}

=== ARCHITECTURE & SYSTEM DESIGN ===
{des_ctx}

=== UPSTREAM DATA CONTRACTS (FROM PHASE 1) ===
{p1_code_summary}

=== PHASE 2 TASK: BUSINESS LOGIC & API ENDPOINTS ===
Generate the server and logic files:
- For Python: crud.py (database query and mutation operations) and app.py (FastAPI application with all REST routes).
- IMPORT AND USE the exact models and schemas defined in Phase 1 above!
- In app.py:
  * Implement ALL required endpoints, route paths, and HTTP methods.
  * For redirects: return RedirectResponse(url=link.long_url), NEVER pass raw ORM objects or records to url.
  * Populate ALL response schema fields (never return empty string or None for required fields like short_url, long_url, created_at).
  * Enforce all acceptance criteria and status codes: 201 Created, 307/302 for redirects, 400 for invalid inputs, 404 for missing items, 410 for expired items, 409 for conflicts.
- Every file must be COMPLETE. Do NOT leave placeholders or TODOs.
"""
    try:
        p2 = imports.invoke_structured(llm, LayerGeneration, [
            imports.SystemMessage(content=system_prompt),
            imports.HumanMessage(content=prompt_p2),
        ])
        for f in p2.files:
            clean = strip_fences(f.content)
            f.content = clean
            written[f.path] = clean
            all_files.append(f)
            write_file_to_disk(project_id, f.path, clean)
        all_notes.extend(p2.notes)
    except Exception as e:
        print(f"  [Code Agent] Layer 2 error ({e}); attempting markdown extraction...")
        raw = llm.invoke([imports.SystemMessage(content=system_prompt), imports.HumanMessage(content=prompt_p2)])
        text = raw.content if hasattr(raw, "content") else str(raw)
        extracted = extract_files_from_markdown(text)
        for f in extracted:
            written[f.path] = f.content
            all_files.append(f)
            write_file_to_disk(project_id, f.path, f.content)

    # ── Layer 3: Frontend & Static UI (if web app) ───────────────────────────
    if needs_frontend_layer(design, requirements):
        print("  [Code Agent] [Adaptive Layer 3/3] Generating Frontend & Static UI...")
        api_routes = [p for p in written.keys() if "app" in p or "main" in p or "api" in p]
        app_code = "\n\n".join(f"--- {p} ---\n{written[p][:1500]}" for p in api_routes)
        prompt_p3 = f"""=== REQUIREMENTS ===
{req_ctx}

=== SERVER API ENDPOINTS (FROM PHASE 2) ===
{app_code}

=== PHASE 3 TASK: FRONTEND & STATIC UI ===
Generate the client files:
- static/index.html (semantic, responsive UI layout with all required forms, controls, and containers)
- static/script.js (JavaScript to interact with the backend API via fetch, handle events, update DOM)
- static/style.css (clean, modern styling)
- Connect all fetch() calls to the EXACT endpoint paths and JSON structures implemented in Phase 2.
- Every file must be COMPLETE.
"""
        try:
            p3 = imports.invoke_structured(llm, LayerGeneration, [
                imports.SystemMessage(content=system_prompt),
                imports.HumanMessage(content=prompt_p3),
            ])
            for f in p3.files:
                clean = strip_fences(f.content)
                f.content = clean
                written[f.path] = clean
                all_files.append(f)
                write_file_to_disk(project_id, f.path, clean)
            all_notes.extend(p3.notes)
        except Exception as e:
            print(f"  [Code Agent] Layer 3 error ({e}); attempting markdown extraction...")
            raw = llm.invoke([imports.SystemMessage(content=system_prompt), imports.HumanMessage(content=prompt_p3)])
            text = raw.content if hasattr(raw, "content") else str(raw)
            extracted = extract_files_from_markdown(text)
            for f in extracted:
                written[f.path] = f.content
                all_files.append(f)
                write_file_to_disk(project_id, f.path, f.content)

    repo = RepositoryGeneration(
        language="python",
        run_command="python app.py",
        test_command="pytest --tb=short -v",
        dependencies=[],
        notes=all_notes,
        files=all_files,
    )
    return repo, written


def generate_repository_adaptive(
    llm,
    requirements: dict,
    design: dict,
    project_id: str,
) -> tuple[RepositoryGeneration, dict[str, str]]:
    """Adaptive code generator: uses single-shot for focused backend apps, layered for full-stack apps or upon truncation."""
    has_frontend = needs_frontend_layer(design, requirements)
    if has_frontend:
        print("  [Code Agent] Full-stack / UI requirements detected; selecting Layered Repository Generation.")
        return generate_repository_layered(llm, requirements, design, project_id)

    print("  [Code Agent] Focused backend architecture detected; selecting Single-Shot Repository Generation.")
    try:
        repo, written = generate_repository_single_shot(llm, requirements, design, project_id)
        if repo and repo.files and all(len(f.content.strip()) > 20 for f in repo.files):
            return repo, written
        print("  [Code Agent] Single-shot output incomplete; falling back to Layered Repository Generation.")
    except Exception as e:
        print(f"  [Code Agent] Single-shot generation exception ({e}); switching to Layered Repository Generation.")

    return generate_repository_layered(llm, requirements, design, project_id)


def rework_repository_single_shot(
    llm,
    requirements: dict,
    design: dict,
    prev_files: dict[str, str],
    prev_plan: Optional[RepositoryGeneration],
    state: AgentState,
    project_id: str,
) -> tuple[RepositoryGeneration, dict[str, str]]:
    req_ctx = requirements_context(requirements)
    des_ctx = design_context(design)
    feedback = feedback_context(state)
    playbook = stack_skill(design, "CODE")

    base_prompt = imports.load_prompt("prompts/code_prompt.txt")
    system_prompt = base_prompt + f"\n\n{playbook}"

    file_dump = "\n\n".join(
        f"=== FILE: {p} ===\n{content}" for p, content in prev_files.items()
    )

    human_prompt = f"""The previous code implementation failed automated tests or quality review.
Analyze the exact failures below and return the COMPLETE modified or newly created files that fix all issues.

=== REQUIREMENTS ===
{req_ctx}

=== DESIGN ===
{des_ctx}

=== CURRENT CODEBASE ===
{file_dump}

=== PROBLEMS TO FIX (FAILING TESTS & REVIEW DEFECTS) ===
{feedback}

=== INSTRUCTIONS ===
1. Analyze the failing test assertions, error messages, and review defects.
2. Provide the COMPLETE updated code for all files that need changes to make all tests pass and resolve defects.
3. Keep everything that already works. Do NOT omit code with placeholders or '...'.
4. Ensure response schema fields, redirect URLs, status codes, and imports are fully corrected.
"""

    messages = [
        imports.SystemMessage(content=system_prompt),
        imports.HumanMessage(content=human_prompt),
    ]

    print("  [Code Agent] Reworking repository in a single shot...")
    rework = None
    try:
        rework = imports.invoke_structured(llm, RepositoryRework, messages)
    except Exception as e:
        print(f"  [Code Agent] Structured rework exception ({e}); attempting fallback extraction...")
        try:
            raw_msg = llm.invoke(messages)
            raw_text = raw_msg.content if hasattr(raw_msg, "content") else str(raw_msg)
            parsed_json = imports._extract_json_from_text(raw_text)
            if isinstance(parsed_json, dict) and "files" in parsed_json:
                rework = RepositoryRework.model_validate(parsed_json)
            else:
                extracted = extract_files_from_markdown(raw_text)
                if extracted:
                    rework = RepositoryRework(files=extracted)
        except Exception as e2:
            print(f"  [Code Agent] Rework fallback extraction failed: {e2}")

    written = dict(prev_files)
    if rework and rework.files:
        for f in rework.files:
            clean_content = strip_fences(f.content)
            f.content = clean_content
            written[f.path] = clean_content
            write_file_to_disk(project_id, f.path, clean_content)
        print(f"  [Code Agent] Rework updated {len(rework.files)} files: {[f.path for f in rework.files]}")

    plan = prev_plan or RepositoryGeneration(language="python", files=[])
    plan_file_map = {f.path: f for f in plan.files}
    if rework and rework.files:
        for f in rework.files:
            plan_file_map[f.path] = f
    plan.files = list(plan_file_map.values())
    if rework and rework.notes:
        plan.notes.extend(rework.notes)

    return plan, written


def repair_single_file(llm, path: str, content: str, error: str, project_id: str) -> str:
    """Targeted 1-shot repair if a single file has an unparseable syntax error."""
    # Deterministic auto-fixes first
    if "SyntaxError: 'os' module is used" in error and "import os" not in content:
        fixed = "import os\n" + content
        write_file_to_disk(project_id, path, fixed)
        return fixed
    if "SyntaxError: 'sqlite3' module is used" in error and "import sqlite3" not in content:
        fixed = "import sqlite3\n" + content
        write_file_to_disk(project_id, path, fixed)
        return fixed

    prompt = f"""The file `{path}` has a validation error:
{error}

Here is the current content of `{path}`:
{content}

Please return the COMPLETE, corrected file content. Do NOT include markdown commentary or placeholders."""

    try:
        msg = llm.invoke([
            imports.SystemMessage(content="You are an expert software developer. Fix the syntax/validation error and output ONLY the complete corrected file."),
            imports.HumanMessage(content=prompt),
        ])
        repaired = strip_fences(_text(msg))
        if repaired and not validate_file(path, repaired):
            write_file_to_disk(project_id, path, repaired)
            return repaired
    except Exception as e:
        print(f"  [Code Agent] Single-file repair failed for {path}: {e}")

    return content


def Code_Agent(state: AgentState) -> dict:
    print("\nCode Agent: generating implementation from design...")

    project_id = state.get("project_id")
    if not project_id:
        from datetime import datetime
        project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    design = state.get("design", {})
    requirements = state.get("requirements", {})

    code_version = state.get("code_version", 0) + 1
    retry_count = dict(state.get("retry_count", {}))
    previous = state.get("code") or {}
    prev_files = {f["path"]: f["content"] for f in previous.get("files", []) if isinstance(f, dict)}
    is_rework = bool(prev_files) and code_version > 1

    file_tokens = int(os.environ.get("CODE_MAX_TOKENS", "8000"))
    provider = os.environ.get("PROVIDER_CODE") or ("deepseek" if os.environ.get("DEEPSEEK_API_KEY") else ("groq" if os.environ.get("GROQ_API_KEY") else None))
    print(f"  [Code Agent] Requesting provider: {provider or 'default'}")
    llm = imports.get_llm(agent_type="code", max_tokens=file_tokens, provider=provider)

    written: dict[str, str] = {}
    errors: dict[str, str] = {}
    plan: Optional[RepositoryGeneration] = None

    try:
        if not is_rework:
            plan, written = generate_repository_adaptive(llm, requirements, design, project_id)
        else:
            prev_plan = RepositoryGeneration(**previous["plan"]) if previous.get("plan") else None
            plan, written = rework_repository_single_shot(llm, requirements, design, prev_files, prev_plan, state, project_id)

        # Validate each file and run targeted repair if needed
        for path, content in list(written.items()):
            err = validate_file(path, content)
            if err:
                print(f"  [Code Agent] {path} failed validation ({err[:100]}) - running targeted fix...")
                fixed_content = repair_single_file(llm, path, content, err, project_id)
                written[path] = fixed_content
                re_err = validate_file(path, fixed_content)
                if re_err:
                    errors[path] = re_err
    except Exception as e:  # noqa: BLE001
        print(f"  [Code Agent] Generation failed: {e}")
        if any(k in str(e).lower() for k in ("credit", "402", "401", "api key", "quota", "rate limit")):
            print("  [Code Agent] This is an account/provider problem (credits, key or rate limit), not a code problem. "
                  "Check openrouter.ai/credits or API keys, then re-run.")
        return {
            "code": {"files": [], "generation_error": str(e)},
            "code_version": code_version,
            "current_stage": "code",
            "workflow_status": "failed",
            "retry_count": {**retry_count, "code": retry_count.get("code", 0) + 1},
        }

    c_compile_errors = validate_c_project(written)
    if c_compile_errors:
        errors["C project compile check"] = "\n".join(c_compile_errors)

    # ── Ensure Python projects have a valid requirements.txt with all detected imports ──
    ensure_requirements_txt(written, plan, project_id)

    cross = check_cross_file(written)
    notes = list(plan.notes if plan else []) + [f"[validation] {p}: {e}" for p, e in errors.items()] + [f"[imports] {c}" for c in cross]

    # ── Write to disk ────────────────────────────────────────────────────────
    scaffold = repo_scaffold.invoke({
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in written.items()],
    })
    project_path = scaffold.get("project_path", "")
    print(f"  [Code Agent] Wrote {len(written)} files to: {project_path}")

    meta = {f.path: f for f in (plan.files if plan else [])}
    for p in written:
        if p not in meta:
            meta[p] = GeneratedFile(path=p, purpose="Project file", exports=[], content=written[p])

    code_artifact = {
        "files": [
            {
                "path": p,
                "content": c,
                "description": meta[p].purpose if p in meta else "",
                "requirement_ids": meta[p].requirement_ids if p in meta else [],
                "design_component_ids": meta[p].component_ids if p in meta else [],
                "exports": meta[p].exports if p in meta else [],
            }
            for p, c in written.items()
        ],
        "plan": plan.model_dump() if plan else {},
        "dependencies": plan.dependencies if plan else [],
        "setup_instructions": plan.run_command if plan else "python app.py",
        "implementation_notes": notes,
        "test_command": plan.test_command if plan else "pytest --tb=short -v",
        "generated_project_path": project_path,
        "files_written": scaffold.get("files_written", []),
        "validation_errors": errors,
    }

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