## Workspace Semantics
- Treat the attached project files as the main thing being built.
- Treat `.mindshard/` as agent-managed sidecar state unless the user explicitly asks about it.
- Keep product code out of `.mindshard/tools/`, `.mindshard/parts/`, `.mindshard/ref/`, and other sidecar folders.
- Use `.mindshard/tools/` only for reusable agent tools, `.mindshard/parts/` for reusable implementation fragments, `.mindshard/ref/` for reference material, and `.mindshard/outputs/` for generated outputs when appropriate.
