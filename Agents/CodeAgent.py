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

class FilePlan(BaseModel):
    path: str = Field(description="Relative path, e.g. 'app.py', 'static/index.html', 'package.json'")
    purpose: str = Field(description="One line: what this file is responsible for")
    exports: list[str] = Field(
        default_factory=list,
        description="Public names other files/tests will use: functions, classes, routes, DOM ids",
    )
    requirement_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)


class CodePlan(BaseModel):
    language: str = Field(description="Main language, e.g. python, javascript, go, java")
    files: list[FilePlan] = Field(description="Every file needed to run the project. Do NOT include test files.")
    run_command: str = Field(default="", description="Command to run the project")
    test_command: str = Field(default="", description="Command to run tests, e.g. 'pytest --tb=short -v'")
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list, description="Implementation decisions NOT specified by the design")


class FixSelection(BaseModel):
    paths_to_change: list[str] = Field(description="Existing file paths that must be modified")
    new_files: list[FilePlan] = Field(default_factory=list, description="New files that must be added, if any")


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


def complete_text(llm, messages: list) -> str:
    """Plain-text completion that continues automatically if the model hit the token limit."""
    out = ""
    for _ in range(MAX_CONTINUATIONS + 1):
        msg = llm.invoke(messages)
        chunk = _text(msg)
        out += chunk
        finish = (getattr(msg, "response_metadata", None) or {}).get("finish_reason")
        if finish != "length":
            break
        messages = messages + [
            imports.AIMessage(content=chunk),
            imports.HumanMessage(content="You were cut off. Continue EXACTLY where you stopped. "
                                         "Output only the remaining code, no fences, no repetition."),
        ]
    return strip_fences(out)


def build_system_prompt(design: dict) -> str:
    base = imports.load_prompt("prompts/code_prompt.txt")
    playbook = stack_skill(design, "CODE")
    return base + f"""

OUTPUT FORMAT FOR FILE CALLS
- Output ONLY the raw content of the one requested file. No markdown fences, no commentary.
- The file must be COMPLETE. Never write "...", "rest of code", or TODO placeholders.
- Do NOT write test files. A separate QA agent writes tests against your code.
- Use exactly the names listed in the plan's `exports`, so imports and tests resolve.
- The project must run from its root directory with the plan's run_command.

{playbook}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Steps
# ──────────────────────────────────────────────────────────────────────────────

def make_plan(llm, req_ctx: str, design: dict) -> CodePlan:
    system = imports.SystemMessage(content=build_system_prompt(design))
    human = imports.HumanMessage(content=f"""Plan the codebase.

=== REQUIREMENTS ===
{req_ctx}

=== DESIGN (authoritative; follow its technology_choices) ===
{design_context(design)}

List every file needed to run this project (including the dependency manifest, e.g. requirements.txt
or package.json). Keep it minimal: no files the design does not need. Do NOT list test files.
For each file give the exact public names (`exports`) other files will rely on.
Set test_command for the project's language (python: 'pytest --tb=short -v').""")
    last_err = None
    for _ in range(2):
        try:
            plan = imports.invoke_structured(llm, CodePlan, [system, human])
            if plan and plan.files:
                return plan
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(f"Could not create a code plan: {last_err}")


def generate_one_file(llm, fp: FilePlan, plan: CodePlan, requirements: dict, design: dict,
                      written: dict[str, str], existing: Optional[str] = None, feedback: str = "") -> str:
    plan_overview = "\n".join(f"- {f.path}: {f.purpose} | exports: {f.exports}" for f in plan.files)
    interfaces = summarize_written_files(written, fp.path)
    file_req = file_requirements_context(fp, requirements)
    file_des = file_design_context(fp, design)

    if existing is not None:
        task = (f"MODIFY the existing file `{fp.path}` to fix the problems below. Keep everything that works. "
                f"Output the complete updated file.\n\n--- current {fp.path} ---\n{existing}\n\n"
                f"=== PROBLEMS TO FIX ===\n{feedback}")
    else:
        task = f"Write the complete file `{fp.path}` ({fp.purpose}). Exports: {fp.exports}."

    human = imports.HumanMessage(content=f"""=== REQUIREMENTS (FOR THIS COMPONENT) ===
{file_req}

=== ARCHITECTURE & TECH CHOICES ===
{file_des}

=== CODEBASE PLAN ===
{plan_overview}
run_command: {plan.run_command}

=== PREVIOUSLY GENERATED FILES (SIGNATURES & EXPORTS) ===
{interfaces or '(none yet - this is the first file)'}

=== TASK ===
{task}""")
    return complete_text(llm, [imports.SystemMessage(content=build_system_prompt(design)), human])


def write_file_to_disk(project_id: str, relative_path: str, content: str) -> str:
    """Persist the latest generated file immediately so intermediate generation is inspectable."""
    project_dir = WORKSPACE_ROOT / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    abs_path = project_dir / relative_path.lstrip("/")
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")
    return str(abs_path)


def generate_and_fix(llm, fp, plan, requirements, design, written, project_id: str, existing=None, feedback="") -> tuple[str, Optional[str]]:
    """Generate one file, validate it, repair with the real error up to MAX_REPAIR_ATTEMPTS."""
    content = generate_one_file(llm, fp, plan, requirements, design, written, existing, feedback)
    write_file_to_disk(project_id, fp.path, content)
    error = validate_file(fp.path, content)
    attempt = 0
    while error and attempt < MAX_REPAIR_ATTEMPTS:
        attempt += 1
        print(f"  [Code Agent] {fp.path} failed validation ({error[:120]}) - repair {attempt}/{MAX_REPAIR_ATTEMPTS}")
        content = generate_one_file(
            llm, fp, plan, requirements, design, written,
            existing=content,
            feedback=f"Validation error: {error}\nReturn the complete corrected file.",
        )
        write_file_to_disk(project_id, fp.path, content)
        error = validate_file(fp.path, content)
    return content, error


def order_files(files: list[FilePlan]) -> list[FilePlan]:
    """Manifests last, so they can list the imports that were actually used."""
    return sorted(files, key=lambda f: os.path.basename(f.path).lower() in MANIFESTS)


def expand_dependent_targets(targets: list[str], all_files: dict[str, str]) -> list[str]:
    """Ensure any file dependent on or paired with changed files is also updated to prevent desynchronization."""
    expanded = set(targets)
    changed = True
    while changed:
        changed = False
        for target in list(expanded):
            target_base = os.path.splitext(os.path.basename(target))[0]
            target_ext = os.path.splitext(target)[1].lower()

            # 1. Frontend coupling: logic.js and app.js must stay in sync
            if target == "logic.js" and "app.js" in all_files and "app.js" not in expanded:
                expanded.add("app.js")
                changed = True
            elif target == "app.js" and "logic.js" in all_files and "logic.js" not in expanded:
                expanded.add("logic.js")
                changed = True

            # 2. C / C++ coupling: .h and .c pairs, or files #including the target
            elif target_ext in (".h", ".hpp"):
                for ext in (".c", ".cpp", ".cc"):
                    impl = target_base + ext
                    if impl in all_files and impl not in expanded:
                        expanded.add(impl)
                        changed = True
                for other_path, other_content in all_files.items():
                    if other_path not in expanded and (f'"{target}"' in other_content or f'<{target}>' in other_content or target in other_content):
                        expanded.add(other_path)
                        changed = True
            elif target_ext in (".c", ".cpp", ".cc"):
                for ext in (".h", ".hpp"):
                    hdr = target_base + ext
                    if hdr in all_files and hdr not in expanded:
                        expanded.add(hdr)
                        changed = True

            # 3. Python coupling: any file importing the modified module
            elif target_ext == ".py":
                for other_path, other_content in all_files.items():
                    if other_path.endswith(".py") and other_path not in expanded:
                        if re.search(rf"\b(?:from|import)\s+{re.escape(target_base)}\b", other_content):
                            expanded.add(other_path)
                            changed = True

    # Upstream dependencies generated first so downstream files receive their updated signatures!
    def _rank(p: str) -> int:
        pl = p.lower()
        if pl.endswith((".h", ".hpp")):
            return 0
        if any(k in pl for k in ("logic", "model", "schema")):
            return 1
        if any(k in pl for k in ("store", "service", "calc", "db")):
            return 2
        if any(k in pl for k in ("app", "main", "cli", "server", "view")):
            return 3
        return 4

    return sorted(expanded, key=_rank)


# ──────────────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────────────

def Code_Agent(state: AgentState) -> dict:
    print("\nCode Agent: generating implementation from design...")

    project_id = state.get("project_id")
    if not project_id:
        from datetime import datetime
        project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    design = state.get("design", {})
    requirements = state.get("requirements", {})
    req_ctx = requirements_context(requirements)

    code_version = state.get("code_version", 0) + 1
    retry_count = dict(state.get("retry_count", {}))
    previous = state.get("code") or {}
    prev_files = {f["path"]: f["content"] for f in previous.get("files", []) if isinstance(f, dict)}
    is_rework = bool(prev_files) and code_version > 1
    is_review_retry = is_rework and state.get("approval_status") == "rejected"

    file_tokens = int(os.environ.get("CODE_MAX_TOKENS", "3000"))
    provider: Literal["ollama", "groq"] = "groq" if is_review_retry else "ollama"
    if is_review_retry:
        print("  [Code Agent] Review rejected the first implementation; using Groq for the targeted rework.")
    try:
        llm = imports.get_llm(agent_type="code", max_tokens=file_tokens, provider=provider)
        plan_llm = imports.get_llm(agent_type="code", max_tokens=2000, provider=provider)
    except Exception as exc:
        if provider != "groq":
            raise
        print(f"  [Code Agent] Groq unavailable ({exc}); falling back to Ollama.")
        provider = "ollama"
        llm = imports.get_llm(agent_type="code", max_tokens=file_tokens, provider=provider)
        plan_llm = imports.get_llm(agent_type="code", max_tokens=2000, provider=provider)

    written: dict[str, str] = {}
    meta: dict[str, FilePlan] = {}
    errors: dict[str, str] = {}

    try:
        if not is_rework:
            # ── First pass: plan, then generate file by file ───────────────────
            plan = make_plan(plan_llm, req_ctx, design)
            # Ensure requirements.txt is in the plan if this is a Python project
            is_py = (
                getattr(plan, "language", "").lower() == "python"
                or any(f.path.endswith(".py") for f in plan.files)
                or any("python" in str(c.get("technology", "")).lower() for c in design.get("technology_choices", []))
            )
            if is_py and not any(os.path.basename(f.path).lower() == "requirements.txt" for f in plan.files):
                print("  [Code Agent] Python project detected; injecting requirements.txt into the file plan.")
                plan.files.append(FilePlan(
                    path="requirements.txt",
                    purpose="List third-party Python package dependencies for pip install",
                    exports=[],
                ))
            print(f"  [Code Agent] Plan: {[f.path for f in plan.files]}")
            for fp in order_files(plan.files):
                content, err = generate_and_fix(llm, fp, plan, requirements, design, written, project_id)
                written[fp.path] = content
                meta[fp.path] = fp
                if err:
                    errors[fp.path] = err
        else:
            # ── Rework: only touch the files that need it ──────────────────────
            plan = CodePlan(**previous["plan"]) if previous.get("plan") else None
            feedback = feedback_context(state)
            if plan is None:
                plan = CodePlan(language="", files=[FilePlan(path=p, purpose="") for p in prev_files])
            meta = {f.path: f for f in plan.files}
            written = dict(prev_files)

            selection = None
            try:
                selection = imports.invoke_structured(plan_llm, FixSelection, [
                    imports.SystemMessage(content="Decide which files must change to fix the problems. "
                                                  "Prefer the smallest set. Do not include test files."),
                    imports.HumanMessage(content=f"Files: {list(prev_files)}\n\n{feedback}"),
                ])
            except Exception as e:  # noqa: BLE001
                print(f"  [Code Agent] File selection failed ({e}); regenerating all files.")

            targets = [p for p in (selection.paths_to_change if selection else []) if p in prev_files] or list(prev_files)
            targets = expand_dependent_targets(targets, prev_files)
            new_files = selection.new_files if selection else []
            print(f"  [Code Agent] Rework targets (with dependencies): {targets} (+{[f.path for f in new_files]} new)")

            for p in targets:
                fp = meta.get(p) or FilePlan(path=p, purpose="")
                content, err = generate_and_fix(llm, fp, plan, requirements, design, written, project_id,
                                                existing=prev_files[p], feedback=feedback)
                written[p] = content
                if err:
                    errors[p] = err
            for fp in new_files:
                plan.files.append(fp)
                meta[fp.path] = fp
                content, err = generate_and_fix(llm, fp, plan, requirements, design, written, project_id)
                written[fp.path] = content
                if err:
                    errors[fp.path] = err
    except Exception as e:  # noqa: BLE001
        # No template fallback: surface the real failure.
        print(f"  [Code Agent] Generation failed: {e}")
        if any(k in str(e).lower() for k in ("credit", "402", "401", "api key", "quota", "rate limit")):
            print("  [Code Agent] This is an account/provider problem (credits, key or rate limit), not a code problem. "
                  "Check openrouter.ai/credits, then re-run.")
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
    if "requirements.txt" in written and "requirements.txt" not in meta:
        meta["requirements.txt"] = FilePlan(path="requirements.txt", purpose="Project dependencies", exports=[])

    cross = check_cross_file(written)
    notes = list(plan.notes) + [f"[validation] {p}: {e}" for p, e in errors.items()] + [f"[imports] {c}" for c in cross]

    # ── Write to disk ────────────────────────────────────────────────────────
    scaffold = repo_scaffold.invoke({
        "project_id": project_id,
        "files": [{"path": p, "content": c} for p, c in written.items()],
    })
    project_path = scaffold.get("project_path", "")
    print(f"  [Code Agent] Wrote {len(written)} files to: {project_path}")

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
        "plan": plan.model_dump(),
        "dependencies": plan.dependencies,
        "setup_instructions": plan.run_command,
        "implementation_notes": notes,
        "test_command": plan.test_command,
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