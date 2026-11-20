import pytest

from test_runner import (
    RUNTIME_IMAGES,
    _build_run_cmd,
    _detect_docker_image,
    run_code_tests,
)


@pytest.mark.parametrize(
    ("files", "expected_image"),
    [
        ([{"path": "index.html"}, {"path": "style.css"}], RUNTIME_IMAGES["javascript"]),
        ([{"path": "main.c"}], RUNTIME_IMAGES["c"]),
        ([{"path": "main.cpp"}], RUNTIME_IMAGES["cpp"]),
    ],
)
def test_runner_detects_only_supported_runtime_images(files, expected_image):
    assert _detect_docker_image(files, {}) == expected_image


@pytest.mark.parametrize("unsupported_path", ["app.py", "Main.java", "index.ts"])
def test_runner_rejects_unsupported_project_languages(unsupported_path):
    with pytest.raises(ValueError, match="Unsupported"):
        _detect_docker_image([{"path": unsupported_path}], {})


def test_node_runner_uses_node_test_command():
    command = _build_run_cmd(
        "node --test verification.test.js",
        {"verification.test.js": "test('example', () => {});"},
        ["logic.js"],
        {},
    )

    assert command == "node --test verification.test.js"


def test_native_runner_compiles_c_and_cpp_with_their_standards():
    c_command = _build_run_cmd(
        None,
        {"test_verification.c": "int main(void) { return 0; }"},
        ["main.c"],
        {"main.c": "int main(void) { return 0; }"},
    )
    cpp_command = _build_run_cmd(
        None,
        {"test_verification.cpp": "int main() { return 0; }"},
        ["main.cpp"],
        {"main.cpp": "int main() { return 0; }"},
    )

    assert "gcc -std=c11" in c_command
    assert "main.c" not in c_command
    assert "g++ -std=c++17" in cpp_command
    assert "main.cpp" not in cpp_command


def test_run_code_tests_returns_unsupported_without_docker_or_execution():
    result = run_code_tests(
        files=[{"path": "app.py", "content": "print('not supported')"}],
        test_files={},
    )

    assert result["execution_status"] == "unsupported_stack"
    assert result["success"] is False


def test_runner_rejects_model_supplied_shell_commands_before_docker():
    result = run_code_tests(
        files=[{"path": "logic.js", "content": "module.exports = {};"}],
        test_files={"verification.test.js": "test('example', () => {});"},
        test_command="node --test verification.test.js; touch /tmp/unexpected",
    )

    assert result["execution_status"] == "command_rejected"
    assert result["success"] is False


def test_command_builder_rejects_non_configured_javascript_commands():
    with pytest.raises(ValueError, match="Custom JavaScript test commands"):
        _build_run_cmd(
            "node -e 'process.exit(0)'",
            {"verification.test.js": "test('example', () => {});"},
        )


def test_command_builder_uses_the_configured_test_file_only():
    command = _build_run_cmd(
        None,
        {
            "verification.test.js": "test('example', () => {});",
            "unexpected.test.js": "test('other', () => {});",
        },
    )

    assert command == "node --test verification.test.js"
