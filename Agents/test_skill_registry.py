import pytest

from skill_registry import (
    AGENT_SKILLS,
    OPTIONAL_SKILLS_BY_AGENT,
    SkillFormatError,
    _parse_frontmatter,
    load_agent_skills,
    load_skill,
)
from stack_skills import stack_skill


def test_registered_role_skills_have_valid_metadata_and_instructions():
    for agent_type, skill_ids in AGENT_SKILLS.items():
        skills = load_agent_skills(agent_type)
        assert [skill.name for skill in skills] == list(skill_ids)
        assert all(skill.description and skill.instructions for skill in skills)


def test_stack_skill_returns_only_the_requested_section():
    design = {
        "technology_choices": [
            {"category": "language", "technology": "JavaScript"},
            {"category": "frontend", "technology": "HTML, CSS, JavaScript"},
            {"category": "backend", "technology": "none"},
        ]
    }

    code = stack_skill(design, "CODE")
    tests = stack_skill(design, "TEST")

    assert "logic.js" in code
    assert "node:test" not in code
    assert "node:test" in tests
    assert "CommonJS only" in tests


def test_stack_skill_preserves_c_and_cpp_selection():
    c_design = {"technology_choices": [{"category": "language", "technology": "C"}]}
    cpp_design = {"technology_choices": [{"category": "language", "technology": "C++"}]}

    assert "C11" in stack_skill(c_design, "CODE")
    assert "C++17" in stack_skill(cpp_design, "CODE")


def test_unregistered_optional_skill_is_rejected():
    with pytest.raises(ValueError, match="not registered as optional"):
        load_agent_skills("code", ("database",))


def test_registered_optional_skill_is_added_to_the_agent(monkeypatch):
    monkeypatch.setitem(OPTIONAL_SKILLS_BY_AGENT, "code", ("test-design",))

    skills = load_agent_skills("code", ("test-design",))

    assert [skill.name for skill in skills] == ["code-generation", "test-design"]


def test_skill_ids_cannot_escape_the_skills_directory():
    with pytest.raises(ValueError, match="Invalid skill ID"):
        load_skill("../outside")


def test_frontmatter_supports_folded_descriptions_and_rejects_missing_required_fields():
    metadata, body = _parse_frontmatter(
        "---\nname: sample-skill\ndescription: >-\n  First line\n  second line\n---\n\nDo the work.",
        "sample-skill",
    )

    assert metadata == {
        "name": "sample-skill",
        "description": "First line second line",
    }
    assert body == "Do the work."

    with pytest.raises(SkillFormatError, match="unterminated"):
        _parse_frontmatter("---\nname: missing-close", "broken")
