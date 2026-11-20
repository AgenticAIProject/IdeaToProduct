"""Supported generated-project stacks and their code/test execution configuration."""

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


@dataclass(frozen=True)
class TestStack:
    key: str
    name: str
    language: str
    language_aliases: tuple[str, ...]
    source_extensions: frozenset[str]
    code_skill_id: str
    skill_id: str
    test_filename: str
    test_command: str | None
    runtime_image: str


TEST_STACKS = {
    "javascript": TestStack(
        key="javascript",
        name="JavaScript / HTML / CSS",
        language="JavaScript",
        language_aliases=(
            "javascript", "js", "html", "css", "javascript/html/css",
            "html/css/javascript", "html/css/js",
        ),
        source_extensions=frozenset({".js", ".mjs", ".cjs", ".html", ".htm", ".css"}),
        code_skill_id="stack-static-frontend",
        skill_id="test-javascript",
        test_filename="verification.test.js",
        test_command="node --test verification.test.js",
        runtime_image="node:20-slim",
    ),
    "c": TestStack(
        key="c",
        name="C",
        language="C",
        language_aliases=("c",),
        source_extensions=frozenset({".c"}),
        code_skill_id="stack-c",
        skill_id="test-c",
        test_filename="test_verification.c",
        test_command=None,
        runtime_image="gcc:13",
    ),
    "cpp": TestStack(
        key="cpp",
        name="C++",
        language="C++",
        language_aliases=("c++", "cpp"),
        source_extensions=frozenset({".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"}),
        code_skill_id="stack-cpp",
        skill_id="test-cpp",
        test_filename="test_verification.cpp",
        test_command=None,
        runtime_image="gcc:13",
    ),
}

_LANGUAGE_ALIASES = {
    alias: stack.key
    for stack in TEST_STACKS.values()
    for alias in stack.language_aliases
}
_UNSUPPORTED_SOURCE_EXTENSIONS = {
    ".py", ".java", ".go", ".rs", ".ts", ".tsx", ".jsx", ".cs", ".php",
    ".rb", ".kt", ".swift",
}
_UNSUPPORTED_MANIFESTS = {
    "go.mod", "cargo.toml", "pom.xml", "build.gradle", "requirements.txt",
}
UNSUPPORTED_FRONTENDS = ("react", "vue", "svelte", "angular", "next", "nuxt", "vite", "webpack", "parcel")
UNSUPPORTED_NPM_PACKAGES = frozenset({
    "react", "react-dom", "vue", "@angular/core", "svelte", "next", "nuxt",
    "vite", "webpack", "parcel", "typescript", "ts-node", "tsx",
})


class UnsupportedTestStackError(ValueError):
    """Raised when a generated project is outside the supported test stacks."""


def normalize_stack_language(language: str) -> str | None:
    """Return a supported stack key for a language label or alias."""
    return _LANGUAGE_ALIASES.get(language.strip().lower().replace(" ", ""))


def _technology_choices(design: dict[str, Any]) -> dict[str, str]:
    return {
        str(choice.get("category", "")).strip().lower():
        str(choice.get("technology", "")).strip().lower()
        for choice in design.get("technology_choices", [])
        if isinstance(choice, dict)
    }


def declared_stack_key(design: dict[str, Any]) -> str | None:
    """Resolve the design's declared language or frontend using shared stack aliases."""
    choices = _technology_choices(design)
    frontend = choices.get("frontend", "")
    if any(marker in frontend for marker in UNSUPPORTED_FRONTENDS):
        raise UnsupportedTestStackError(
            f"Unsupported frontend '{frontend}'. Use plain JavaScript, HTML, and CSS."
        )

    language = choices.get("language", "")
    if normalized := normalize_stack_language(language):
        return normalized
    if language and language not in ("none", "null", "n/a"):
        raise UnsupportedTestStackError(
            f"Unsupported project language '{language}'. Supported generated projects: "
            "JavaScript/HTML/CSS, C, and C++."
        )

    if frontend and frontend not in ("none", "null", "n/a"):
        if any(marker in frontend for marker in ("html", "css", "javascript", "vanilla")):
            return "javascript"
        raise UnsupportedTestStackError(
            f"Unsupported frontend '{frontend}'. Use plain JavaScript, HTML, and CSS."
        )
    return None


def _paths(files: Any) -> list[str]:
    if isinstance(files, dict):
        return [str(path).lower() for path in files]
    if isinstance(files, list):
        return [
            str(entry.get("path", "") if isinstance(entry, dict) else entry).lower()
            for entry in files
            if (isinstance(entry, dict) and entry.get("path")) or isinstance(entry, str)
        ]
    return []


def _file_contents(files: Any) -> dict[str, str]:
    if isinstance(files, dict):
        return {
            str(path).lower(): content
            for path, content in files.items()
            if isinstance(content, str)
        }
    if isinstance(files, list):
        return {
            str(entry["path"]).lower(): entry.get("content", "")
            for entry in files
            if isinstance(entry, dict)
            and entry.get("path")
            and isinstance(entry.get("content", ""), str)
        }
    return {}


def _validate_package_manifest(files: Any) -> None:
    manifests = [
        (path, content)
        for path, content in _file_contents(files).items()
        if PurePosixPath(path).name == "package.json"
    ]
    for path, package_content in manifests:
        try:
            manifest = json.loads(package_content)
        except json.JSONDecodeError as exc:
            raise UnsupportedTestStackError(f"Invalid {path}: {exc.msg}.") from exc
        if not isinstance(manifest, dict):
            raise UnsupportedTestStackError(f"Invalid {path}: expected a JSON object.")

        dependencies: set[str] = set()
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            entries = manifest.get(section, {})
            if not isinstance(entries, dict):
                raise UnsupportedTestStackError(f"Invalid {path}: '{section}' must be an object.")
            dependencies.update(str(name).lower() for name in entries)

        unsupported = sorted(dependencies & UNSUPPORTED_NPM_PACKAGES)
        if unsupported:
            raise UnsupportedTestStackError(
                f"{path} uses unsupported frameworks/build tools or TypeScript packages: "
                f"{', '.join(unsupported)}."
            )
        if dependencies:
            raise UnsupportedTestStackError(
                f"{path} declares external npm dependencies, but generated projects run "
                "without installing packages or network access: "
                f"{', '.join(sorted(dependencies))}."
            )


def resolve_test_stack(
    code_files: Any,
    design: dict[str, Any] | None = None,
    declared_language: str | None = None,
) -> TestStack:
    """Resolve one supported stack from generated source paths, manifest contents, and design."""
    paths = _paths(code_files)
    declared = declared_stack_key(design or {})
    plan_language = normalize_stack_language(declared_language) if declared_language else None
    if declared_language and plan_language is None:
        raise UnsupportedTestStackError(
            f"Unsupported generated project language '{declared_language}'. "
            "Supported generated projects: JavaScript/HTML/CSS, C, and C++."
        )

    _validate_package_manifest(code_files)
    unsupported = sorted({
        path for path in paths
        if PurePosixPath(path).suffix in _UNSUPPORTED_SOURCE_EXTENSIONS
        or PurePosixPath(path).name in _UNSUPPORTED_MANIFESTS
    })
    if unsupported:
        raise UnsupportedTestStackError(
            f"Unsupported generated source file(s): {', '.join(unsupported)}. "
            "Supported generated projects: JavaScript/HTML/CSS, C, and C++."
        )

    detected = {
        key
        for key, stack in TEST_STACKS.items()
        if any(PurePosixPath(path).suffix in stack.source_extensions for path in paths)
    }
    if any(PurePosixPath(path).name == "package.json" for path in paths):
        detected.add("javascript")

    if len(detected) > 1:
        raise UnsupportedTestStackError(
            "A generated project must use one supported implementation stack; "
            f"found: {', '.join(sorted(detected))}."
        )
    file_stack = next(iter(detected), None)

    declared_stack = declared or plan_language
    has_c_header = any(PurePosixPath(path).suffix == ".h" for path in paths)
    if file_stack is None and has_c_header:
        if declared_stack is None:
            raise UnsupportedTestStackError(
                "A project containing only .h headers is ambiguous. Declare C or C++ in the design."
            )
        file_stack = declared_stack

    if declared and file_stack and declared != file_stack:
        raise UnsupportedTestStackError(
            f"Design selects {TEST_STACKS[declared].name}, but generated files indicate "
            f"{TEST_STACKS[file_stack].name}."
        )

    stack_key = file_stack or declared_stack
    if not stack_key:
        raise UnsupportedTestStackError(
            "Could not identify a supported project stack. Supported generated projects: "
            "JavaScript/HTML/CSS, C, and C++."
        )
    if plan_language and plan_language != stack_key:
        raise UnsupportedTestStackError(
            f"Code plan language '{declared_language}' does not match the selected "
            f"{TEST_STACKS[stack_key].name} project stack."
        )
    return TEST_STACKS[stack_key]
