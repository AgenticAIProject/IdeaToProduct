"""Pick the stack playbook for a design and return its CODE or TEST section."""
import imports


def _choices(design: dict) -> dict:
    return {str(c.get("category", "")).lower(): str(c.get("technology", "")).lower()
            for c in (design or {}).get("technology_choices", []) if isinstance(c, dict)}


def stack_name(design: dict) -> str | None:
    tc = _choices(design)
    lang, backend, frontend = tc.get("language", ""), tc.get("backend", ""), tc.get("frontend", "")
    no_backend = backend in ("", "none", "null")
    if any(k in backend for k in ("fastapi", "flask")):
        return "python_api"
    if no_backend and any(k in frontend for k in ("html", "css", "vanilla", "javascript")):
        return "static_frontend"
    if "c++" in lang or "cpp" in lang:
        return "cpp"
    if lang == "c" or " c " in f" {lang} ":
        return "c"
    if "python" in lang or "python" in backend or "cli" in backend:
        return "python_cli"
    return None


def stack_skill(design: dict, section: str) -> str:
    """section: 'CODE' or 'TEST'. Returns '' when no playbook matches."""
    name = stack_name(design)
    if not name:
        return ""
    try:
        text = imports.load_prompt(f"skills/stack_{name}.txt")
    except Exception:
        return ""
    parts = {"CODE": "", "TEST": ""}
    current = None
    for line in text.splitlines():
        if line.strip() in ("## CODE", "## TEST"):
            current = line.strip()[3:]
            continue
        if current:
            parts[current] += line + "\n"
    body = parts.get(section, "").strip()
    return f"STACK PLAYBOOK ({name}, {section.lower()} rules):\n{body}" if body else ""