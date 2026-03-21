## Workspace Semantics
- Treat the attached project files as the main thing being built.
- When the active project root is the sandbox root, refer to files with root-relative paths like `src/app.py`, not invented prefixes like `project/src/app.py`.
- Treat `.mindshard/` as agent-managed sidecar state unless the user explicitly asks about it.
- Keep product code out of `.mindshard/tools/`, `.mindshard/parts/`, `.mindshard/ref/`, and other sidecar folders.
- Use `.mindshard/tools/` only for reusable agent tools, `.mindshard/parts/` for reusable implementation fragments, `.mindshard/ref/` for reference material, and `.mindshard/outputs/` for generated outputs when appropriate.
