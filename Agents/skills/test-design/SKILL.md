---
name: test-design
description: Create executable tests that verify approved requirements and public contracts without assuming unspecified behavior.
---

# Test Design

- Derive assertions from the approved requirements, acceptance criteria, design, and exported interfaces.
- Test observable behavior, representative boundary cases, and relevant failure cases.
- Do not assert features, UI elements, fields, or functions that the artifacts do not specify.
- Use the project's existing test command and framework; keep tests executable in the generated project.
- When repairing tests, correct unsupported assumptions rather than weakening valid requirement-backed assertions.
