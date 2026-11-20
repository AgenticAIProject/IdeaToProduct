"""Pick the stack playbook for a design and return its CODE or TEST section."""

from skill_registry import load_skill
from test_stacks import TEST_STACKS, declared_stack_key


def stack_name(design: dict) -> str | None:
    try:
        key = declared_stack_key(design or {})
    except ValueError:
        return None
    backend = next(
        (
            str(choice.get("technology", "")).strip().lower()
            for choice in (design or {}).get("technology_choices", [])
            if isinstance(choice, dict) and str(choice.get("category", "")).strip().lower() == "backend"
        ),
        "",
    )
    no_backend = backend in ("", "none", "null")
    if key == "javascript":
        return "static_frontend" if no_backend else None
    return key


def stack_skill(design: dict, section: str) -> str:
    """Return the CODE section for a matching stack playbook."""
    section = section.upper()
    if section != "CODE":
        raise ValueError(f"Unsupported stack skill section: {section!r}")

    name = stack_name(design)
    if not name:
        return ""
    stack_key = "javascript" if name == "static_frontend" else name
    skill = load_skill(TEST_STACKS[stack_key].code_skill_id)
    body = []
    current = None
    for line in skill.instructions.splitlines():
        if line.strip() == "## CODE":
            current = line.strip()[3:]
            continue
        if line.startswith("## "):
            current = None
        elif current:
            body.append(line)
    body = "\n".join(body).strip()
    return f"STACK PLAYBOOK ({name}, {section.lower()} rules):\n{body}" if body else ""