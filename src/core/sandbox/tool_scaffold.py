"""Tool scaffold — creates new sandbox-local tools with clean headers.

When the agent creates a tool, it goes under <sandbox_root>/_tools/
with standard metadata headers.
"""

from pathlib import Path

from src.core.sandbox.path_guard import PathGuard
from src.core.runtime.runtime_logger import get_logger

log = get_logger("tool_scaffold")

_TOOL_TEMPLATE = '''"""
Tool: {name}
Purpose: {purpose}
Usage: python _tools/{filename} [args]
Constraints: Runs only within sandbox root. No external writes.
Generated-by: AgenticTOOLBOX sandbox agent
Created: {created_at}
"""

import sys


def main():
    """Entry point for {name}."""
    # TODO: implement tool logic
    print(f"Tool '{name}' invoked with args: {{sys.argv[1:]}}")


if __name__ == "__main__":
    main()
'''


def create_tool_script(
    tools_dir: Path,
    guard: PathGuard,
    name: str,
    purpose: str,
    content: str | None = None,
) -> Path:
    """Create a new tool script in the sandbox tools directory.

    Args:
        tools_dir: Path to _tools/ directory
        guard: PathGuard to validate output path
        name: Tool name (used for filename)
        purpose: One-line description
        content: Optional full script content. If None, uses template.

    Returns:
        Path to the created tool file.
    """
    filename = f"{name}.py"
    target = tools_dir / filename
    guard.validate(target)

    if content is None:
        from src.core.utils.clock import utc_iso
        content = _TOOL_TEMPLATE.format(
            name=name, purpose=purpose, filename=filename, created_at=utc_iso())

    target.write_text(content, encoding="utf-8")
    log.info("Tool scaffold created: %s", target)
    return target
