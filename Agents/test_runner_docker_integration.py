import pytest

from test_runner import _docker_available, run_code_tests
from test_stacks import TEST_STACKS


@pytest.mark.parametrize(
    ("stack_key", "sources", "tests"),
    [
        (
            "javascript",
            [{
                "path": "sample_logic.js",
                "content": "function identity(value) { return value; }\nmodule.exports = { identity };\n",
            }],
            {
                "verification.test.js": (
                    "const assert = require('node:assert/strict');\n"
                    "const test = require('node:test');\n"
                    "const { identity } = require('./sample_logic.js');\n"
                    "test('identity preserves a value', () => assert.equal(identity('sample'), 'sample'));\n"
                ),
            },
        ),
        (
            "c",
            [
                {"path": "sample.h", "content": "int identity(int value);\n"},
                {
                    "path": "sample.c",
                    "content": '#include "sample.h"\nint identity(int value) { return value; }\n',
                },
            ],
            {
                "test_verification.c": (
                    '#include "sample.h"\n#include <assert.h>\n'
                    "int main(void) { assert(identity(7) == 7); return 0; }\n"
                ),
            },
        ),
        (
            "cpp",
            [
                {"path": "sample.hpp", "content": "int identity(int value);\n"},
                {
                    "path": "sample.cpp",
                    "content": '#include "sample.hpp"\nint identity(int value) { return value; }\n',
                },
            ],
            {
                "test_verification.cpp": (
                    '#include "sample.hpp"\n#include <cassert>\n'
                    "int main() { assert(identity(7) == 7); }\n"
                ),
            },
        ),
    ],
)
def test_docker_executes_supported_stack_end_to_end(stack_key, sources, tests):
    if not _docker_available():
        pytest.skip("Docker daemon is unavailable.")

    result = run_code_tests(
        files=sources,
        test_files=tests,
        test_command=TEST_STACKS[stack_key].test_command,
        timeout_seconds=60,
    )

    assert result["execution_status"] == "passed", result
    assert result["success"] is True
    assert result["failed_tests"] == 0
