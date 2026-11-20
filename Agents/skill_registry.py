"""Load Agent Skills-format instructions registered for each workflow agent."""

import json
import re
from dataclasses import dataclass
from pathlib import Path


AGENT_SKILLS = {
    "requirement": ("requirement-engineering",),
    "design": ("software-design",),
    "code": ("code-generation",),
    "test": ("test-design",),
    "review": ("code-review",),
    "documentation": ("project-documentation",),
}

# Add task-specific skills here, then select them in agent code when applicable.
OPTIONAL_SKILLS_BY_AGENT = {
    "requirement": (),
    "design": (),
    "code": (),
    "test": (),
    "review": (),
    "documentation": (),
}

_SKILL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str


class SkillFormatError(ValueError):
    """Raised when a registered SKILL.md does not follow the expected format."""


def _yaml_scalar(value: str, field: str, skill_id: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SkillFormatError(f"Invalid quoted {field} in skill '{skill_id}'.") from exc
        if not isinstance(parsed, str):
            raise SkillFormatError(f"Skill '{skill_id}' has a non-string {field}.")
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise SkillFormatError(f"Invalid quoted {field} in skill '{skill_id}'.")
        return value[1:-1].replace("''", "'")
    return re.sub(r"\s+#.*$", "", value).strip()


def _parse_frontmatter(content: str, skill_id: str) -> tuple[dict[str, str], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillFormatError(f"Skill '{skill_id}' must start with YAML frontmatter.")

    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise SkillFormatError(f"Skill '{skill_id}' has unterminated YAML frontmatter.") from exc

    metadata: dict[str, str] = {}
    index = 1
    while index < end:
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            index += 1
            continue
        key, separator, raw_value = line.partition(":")
        if not separator:
            raise SkillFormatError(f"Invalid frontmatter field in skill '{skill_id}': {line}")
        if key in ("name", "description"):
            if key in metadata:
                raise SkillFormatError(f"Skill '{skill_id}' has duplicate '{key}' metadata.")
            if key == "description" and raw_value.strip() in (">", ">-", ">+", "|", "|-", "|+"):
                block_lines = []
                index += 1
                while index < end and (not lines[index].strip() or lines[index][:1].isspace()):
                    block_lines.append(lines[index].strip())
                    index += 1
                if raw_value.strip().startswith(">"):
                    metadata[key] = " ".join(part for part in block_lines if part)
                else:
                    metadata[key] = "\n".join(block_lines).strip()
                continue
            metadata[key] = _yaml_scalar(raw_value, key, skill_id)
        index += 1

    body = "\n".join(lines[end + 1:]).strip()
    return metadata, body


def load_skill(skill_id: str) -> Skill:
    """Load one registered-by-name skill directory and validate its metadata."""
    if not _SKILL_ID.fullmatch(skill_id):
        raise ValueError(f"Invalid skill ID: {skill_id!r}")

    path = Path(__file__).resolve().parent / "skills" / skill_id / "SKILL.md"
    content = path.read_text(encoding="utf-8")
    metadata, instructions = _parse_frontmatter(content, skill_id)
    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not name or len(name) > 64 or not _SKILL_ID.fullmatch(name):
        raise SkillFormatError(f"Skill '{skill_id}' must have a valid frontmatter name (1-64 characters).")
    if name != skill_id:
        raise SkillFormatError(
            f"Skill directory '{skill_id}' does not match frontmatter name '{name}'."
        )
    if not description or len(description) > 1024:
        raise SkillFormatError(f"Skill '{skill_id}' must have a description (1-1024 characters).")
    if not instructions:
        raise SkillFormatError(f"Skill '{skill_id}' has no instruction body.")

    return Skill(name=name, description=description, instructions=instructions)


def load_agent_skills(agent_type: str, optional_skill_ids: tuple[str, ...] = ()) -> list[Skill]:
    """Load an agent's fixed skills plus explicitly selected, code-approved optional skills."""
    if agent_type not in AGENT_SKILLS:
        raise ValueError(f"Unknown agent type: {agent_type!r}")

    allowed_optional = OPTIONAL_SKILLS_BY_AGENT.get(agent_type, ())
    invalid = set(optional_skill_ids) - set(allowed_optional)
    if invalid:
        raise ValueError(
            f"Skills {sorted(invalid)} are not registered as optional for the '{agent_type}' agent."
        )

    skill_ids = dict.fromkeys((*AGENT_SKILLS[agent_type], *optional_skill_ids))
    return [load_skill(skill_id) for skill_id in skill_ids]
