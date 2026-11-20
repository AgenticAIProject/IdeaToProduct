---
name: test-cpp
description: Write executable C++17 test harnesses for generated C++ projects using real public headers and APIs.
---

# C++ Testing

- Write the test harness as `test_verification.cpp`, using C++17 and standard headers unless the project requires another declared dependency.
- Include the actual project headers and call its public functions or classes; do not copy implementation logic into the harness.
- Cover acceptance criteria with representative, boundary, and specified error cases using `assert` or equivalent standard assertions.
- Ensure the test plan maps every acceptance-criterion ID (or functional-requirement ID when no acceptance criteria exist) to at least one test case.
- Use each planned `test_function_name` for a test function and call every test function from the harness `main`.
- Compile with `g++ -std=c++17` and project `.cpp` sources, excluding the application `main` translation unit to avoid duplicate entry points.
- Use only names and contracts present in the supplied source files and public-interface list.
