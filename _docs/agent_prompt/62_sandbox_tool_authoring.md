# Sandbox Tool Authoring

You can create new tools that become available in your tool catalog without
restarting the application. This is useful when you need a reusable capability
that the built-in tools don't cover.

## Where to Put Tools

New tools go in `.mindshard/tools/` inside the sandbox root.

```
<sandbox_root>/
  .mindshard/
    tools/
      my_tool.py    ← your new tool here
```

Files starting with `_` are ignored.

## Required Format

Every tool file must have a module-level docstring with this exact structure:

```python
"""
Tool: tool_name_here
Description: One sentence explaining what this tool does and when to use it.
Parameters: param1:string:required, param2:int, param3:string
"""

def run(args: dict) -> dict:
    """Execute the tool. Return a dict result."""
    # your implementation here
    param1 = args.get("param1", "")
    param2 = args.get("param2", 0)
    # ...
    return {"result": "...", "success": True}
```

**Parameter format:** `name:type`, comma-separated. Add `:required` to mark required params.
Valid types: `string`, `int`, `float`, `bool`.

**Return format:** Always return a dict. Include `"error": "message"` for failures.
Never raise exceptions — catch them and return `{"error": str(exc)}`.

## After Creating a Tool

Call `reload_tools` immediately after writing the file:
```
{"tool": "reload_tools", "args": {}}
```

The tool will appear in the catalog and be available for use in the same session.

## Example: A Word Count Tool

```python
"""
Tool: word_count
Description: Count words, lines, and characters in a text string or file.
Parameters: text:string, file_path:string
"""

def run(args: dict) -> dict:
    text = args.get("text", "")
    file_path = args.get("file_path", "")

    if not text and file_path:
        try:
            from pathlib import Path
            text = Path(file_path).read_text(encoding="utf-8")
        except Exception as exc:
            return {"error": str(exc)}

    if not text:
        return {"error": "Provide either 'text' or 'file_path'"}

    lines = text.splitlines()
    words = text.split()
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
    }
```

## Rules for Sandbox Tools

1. No writes outside `.mindshard/` or the sandbox root — do not touch `src/`
2. No network calls without explicit user approval
3. No `os.system()` or `subprocess` without documenting why
4. Always handle exceptions — return `{"error": "..."}` instead of crashing
5. Keep tools focused — one capability per file, under 100 lines
6. Name the file to match the tool name: `word_count` → `word_count.py`
