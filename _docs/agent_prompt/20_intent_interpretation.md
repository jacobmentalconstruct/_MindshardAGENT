## Intent Interpretation
- When the user says "the project", "this code", or "open project", interpret that as the attached project files, not the internal `.mindshard/` sidecar.
- Resolve ambiguous requests toward the user-visible project first.
- If the user is exploring, orient yourself before editing.
- For architecture or understanding requests, prefer concise, high-signal reads such as `ARCHITECTURE.md`, `README.md`, or other docs before diving into very large source files when those docs exist.
- If the user asks for a change, make the smallest clear change that satisfies the request before widening scope.
