---
name: test-c
description: Write executable C11 test harnesses for generated C projects using the real public headers and functions.
---

# C Testing

- Write the test harness as `test_verification.c`, using C11 and standard headers only.
- Include the actual project headers and call functions declared by those headers; do not copy implementation logic into the harness.
- Cover acceptance criteria with representative, boundary, and specified error cases using `assert`.
- Ensure the test plan maps every acceptance-criterion ID (or functional-requirement ID when no acceptance criteria exist) to at least one test case.
- Use each planned `test_function_name` for a test function and call every test function from the harness `main`.
- Compile the harness with the project `.c` sources, excluding the application `main` translation unit to avoid duplicate entry points.
- Use only names and contracts present in the supplied source files and public-interface list.
