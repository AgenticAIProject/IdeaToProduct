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
from stack_skills import stack_name
from test_stacks import TEST_STACKS, UnsupportedTestStackError, resolve_test_stack


def test_registered_role_skills_have_valid_metadata_and_instructions():
    for agent_type, skill_ids in AGENT_SKILLS.items():
        skills = load_agent_skills(agent_type)
        assert [skill.name for skill in skills] == list(skill_ids)
        assert all(skill.description and skill.instructions for skill in skills)


def test_code_stack_playbook_returns_code_guidance_only():
    design = {
        "technology_choices": [
            {"category": "language", "technology": "JavaScript"},
            {"category": "frontend", "technology": "HTML, CSS, JavaScript"},
            {"category": "backend", "technology": "none"},
        ]
    }

    code = stack_skill(design, "CODE")
    assert "logic.js" in code
    assert "## TEST" not in code


def test_code_stack_playbook_preserves_c_and_cpp_selection():
    c_design = {"technology_choices": [{"category": "language", "technology": "C"}]}
    cpp_design = {"technology_choices": [{"category": "language", "technology": "C++"}]}

    assert "C11" in stack_skill(c_design, "CODE")
    assert "C++17" in stack_skill(cpp_design, "CODE")


def test_code_playbooks_and_test_skills_come_from_shared_stack_configuration():
    for stack in TEST_STACKS.values():
        design = {"technology_choices": [{"category": "language", "technology": stack.language}]}
        selected_name = stack_name(design)
        if stack.key == "javascript":
            design["technology_choices"].append({"category": "frontend", "technology": "HTML/CSS/JavaScript"})
            selected_name = stack_name(design)
        assert load_skill(stack.code_skill_id).name
        assert load_skill(stack.skill_id).name
        assert selected_name == ("static_frontend" if stack.key == "javascript" else stack.key)


def test_test_stack_selection_accepts_only_javascript_c_and_cpp():
    assert resolve_test_stack([{"path": "index.html"}, {"path": "style.css"}]).skill_id == "test-javascript"
    assert resolve_test_stack(
        [{"path": "main.c"}],
        {"technology_choices": [{"category": "language", "technology": "C"}]},
    ).skill_id == "test-c"
    assert resolve_test_stack([{"path": "main.cpp"}]).skill_id == "test-cpp"


def test_test_stack_selection_rejects_other_and_mixed_languages():
    with pytest.raises(UnsupportedTestStackError, match="Unsupported"):
        resolve_test_stack([{"path": "main.java"}])
    with pytest.raises(UnsupportedTestStackError, match="one supported"):
        resolve_test_stack([{"path": "main.cpp"}, {"path": "logic.js"}])


def test_test_stack_selection_rejects_declared_unsupported_language():
    with pytest.raises(UnsupportedTestStackError, match="Unsupported project language"):
        resolve_test_stack(
            [{"path": "main.c"}],
            {"technology_choices": [{"category": "language", "technology": "Java"}]},
        )


def test_package_manifest_rejects_frameworks_typescript_and_uninstalled_dependencies():
    with pytest.raises(UnsupportedTestStackError, match="unsupported frameworks"):
        resolve_test_stack([{
            "path": "package.json",
            "content": '{"devDependencies": {"typescript": "^5.0.0"}}',
        }])
    with pytest.raises(UnsupportedTestStackError, match="without installing packages"):
        resolve_test_stack([{
            "path": "package.json",
            "content": '{"dependencies": {"lodash": "^4.0.0"}}',
        }])
    with pytest.raises(UnsupportedTestStackError, match="Invalid package.json"):
        resolve_test_stack([{"path": "package.json", "content": "not-json"}])


def test_design_frontend_framework_is_rejected_even_when_language_is_javascript():
    with pytest.raises(UnsupportedTestStackError, match="Unsupported frontend"):
        resolve_test_stack(
            ["index.html", "app.js"],
            {
                "technology_choices": [
                    {"category": "language", "technology": "JavaScript"},
                    {"category": "frontend", "technology": "React"},
                ]
            },
        )


def test_header_only_project_requires_an_explicit_native_language():
    with pytest.raises(UnsupportedTestStackError, match="ambiguous"):
        resolve_test_stack(["include/project.h"])
    assert resolve_test_stack(
        ["include/project.h"],
        {"technology_choices": [{"category": "language", "technology": "C++"}]},
    ).key == "cpp"


def test_code_plan_language_must_match_supported_generated_files():
    assert resolve_test_stack(["main.cpp"], declared_language="C++").skill_id == "test-cpp"
    with pytest.raises(UnsupportedTestStackError, match="Unsupported generated project language"):
        resolve_test_stack(["main.c"], declared_language="Python")
    with pytest.raises(UnsupportedTestStackError, match="does not match"):
        resolve_test_stack(["main.cpp"], declared_language="C")


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
