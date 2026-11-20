---
name: test-javascript
description: Write isolated Node.js tests for generated JavaScript, HTML, and CSS projects using built-in modules only.
---

# JavaScript, HTML, and CSS Testing

- Write `verification.test.js` using CommonJS and only Node built-ins: `node:test`, `node:assert`, and `node:fs`.
- Use only files and exports present in the supplied project files and public-interface list. Resolve imports from those real paths; never assume a module.
- Test real exported behavior. Do not call internal helpers or test DOM-bound application scripts in Node.
- For markup and styles, read the supplied HTML/CSS files. Check attributes independently; HTML attribute order is not guaranteed.
- Before each test, call an actually exported reset/clear operation if one exists. Otherwise load each stateful CommonJS module fresh by deleting its actual path from `require.cache` before requiring it.
- If tests use shared setup hooks, ensure the reset/reload runs before every case. Do not assume a reset export or mutable state exists.
- Keep each test independent and trace it to an acceptance criterion or specified design edge case.
- Every test case must use a real `assert` call to verify an expected observable result; do not use empty tests or checks that only print values.
- Use the planned `test_function_name` in each `node:test` test label so the generated tests can be matched to the test plan.
