---
name: stack-static-frontend
description: Code guidance for standalone HTML, CSS, and JavaScript projects without a build step.
---

## CODE
Static frontend (HTML/CSS/JS), no build step, works directly by opening index.html in a web browser.
- Files: `index.html`, `style.css`, `logic.js`, `app.js`, plus a minimal `package.json` (`{"name": "...", "version": "1.0.0", "scripts": {"test": "node --test"}}`).
- Stylesheet link: In `index.html`, link CSS using `<link rel="stylesheet" href="style.css">`.
- Script loading: In `index.html`, load logic before app:
  `<script src="logic.js"></script>`
  `<script src="app.js"></script>`
- `logic.js` holds ALL pure logic (calculations, parsing, validation, operations) and NO DOM access.
  End `logic.js` with dual Node/Browser export:
  ```javascript
  const _exports = { fnA, fnB, ... };
  if (typeof module !== 'undefined' && module.exports) { module.exports = _exports; }
  if (typeof window !== 'undefined') { window.logic = _exports; }
  ```
  Declare all functions at top level so both browser scripts and Node tests can access them.
- `app.js` runs in the browser for DOM binding only.
  CRITICAL RUNTIME RULE: NEVER write `const ... = require(...)` or `import` in `app.js`! `require()` does NOT exist in web browsers and will crash execution. In `app.js`, access logic directly from global scope or `window.logic`.
- Complete Controls: Never omit essential controls (e.g. a calculator MUST include all digits `0` to `9` including `#zero`, plus clear, operators, and equals).
- Stable IDs: Give every button, input, and display element a stable ID matching the plan's exports.
