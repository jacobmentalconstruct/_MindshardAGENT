## Intent Interpretation
- When the user says "the project", "this code", or "open project", interpret that as the attached project files, not the internal `.mindshard/` sidecar.
- Resolve ambiguous requests toward the user-visible project first.
- If the user is exploring, orient yourself before editing.
- For architecture or understanding requests, prefer this order by default:
  1. `list_files` for structure
  2. `read_file` on concise docs such as `ARCHITECTURE.md` or `README.md`
  3. `read_file` on likely entry points or core modules
- Do not run code just to understand architecture unless the user asked for runtime verification or static inspection is clearly insufficient.
- When the user asks for a narrow comparison or a small set of valid tools, answer only that scope instead of expanding into adjacent tools or shell alternatives that were not requested.
- If the user asks for a change, make the smallest clear change that satisfies the request before widening scope.
