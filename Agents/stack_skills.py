"""Pick the stack playbook for a design and return its CODE or TEST section."""

from skill_registry import load_skill


_STACK_SKILL_IDS = {
    "static_frontend": "stack-static-frontend",
    "c": "stack-c",
    "cpp": "stack-cpp",
}


def _choices(design: dict) -> dict:
    return {str(c.get("category", "")).lower(): str(c.get("technology", "")).lower()
            for c in (design or {}).get("technology_choices", []) if isinstance(c, dict)}


def stack_name(design: dict) -> str | None:
    tc = _choices(design)
    lang, backend, frontend = tc.get("language", ""), tc.get("backend", ""), tc.get("frontend", "")
    no_backend = backend in ("", "none", "null")
    if no_backend and any(k in frontend for k in ("html", "css", "vanilla", "javascript")):
        return "static_frontend"
    if "c++" in lang or "cpp" in lang:
        return "cpp"
    if lang == "c" or " c " in f" {lang} ":
        return "c"
    return None


def stack_skill(design: dict, section: str) -> str:
    """section: 'CODE' or 'TEST'. Returns '' when no playbook matches."""
    section = section.upper()
    if section not in ("CODE", "TEST"):
        raise ValueError(f"Unsupported stack skill section: {section!r}")

    name = stack_name(design)
    if not name:
        return ""
    skill = load_skill(_STACK_SKILL_IDS[name])
    parts = {"CODE": "", "TEST": ""}
    current = None
    for line in skill.instructions.splitlines():
        if line.strip() in ("## CODE", "## TEST"):
            current = line.strip()[3:]
            continue
        if current:
            parts[current] += line + "\n"
    body = parts.get(section, "").strip()
    return f"STACK PLAYBOOK ({name}, {section.lower()} rules):\n{body}" if body else ""