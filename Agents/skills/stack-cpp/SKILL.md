---
name: stack-cpp
description: Code guidance for standalone C++17 projects.
---

## CODE
Standalone C++ project (C++17), compiles with g++.
- Modular architecture: Place class definitions and function declarations in header files (.hpp or .h) and implementation in .cpp files.
- Put main() in a separate file (e.g. `main.cpp`). Keep core classes and logic in separate files so tests can link against them without duplicate main() symbol errors.
- Include header guards (#pragma once or #ifndef ... #endif) in every header file.
- Use standard C++17 standard library: <iostream>, <string>, <vector>, <memory>, <algorithm>, <stdexcept>.
- No external packages or third-party dependencies required.
