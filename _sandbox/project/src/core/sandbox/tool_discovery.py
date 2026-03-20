"""Tool discovery — scans sandbox _tools/ for Python scripts with metadata headers.

Tools must have a docstring header block containing structured metadata:
    '''
    Tool: my_tool_name
    Description: What this tool does
    Parameters: param1:string:required, param2:int
    '''

Discovered tools are registered as ToolEntry objects in the catalog.
Inspired by _TheCELL's @service_metadata pattern, simplified for file-based tools.
"""

import re
import ast
from pathlib import Path
from typing import Any

from src.core.sandbox.tool_catalog import ToolCatalog, ToolEntry
from src.core.runtime.runtime_logger import get_logger

log = get_logger("tool_discovery")

# Regex for metadata in docstrings or comment headers
_META_PATTERN = re.compile(
    r"(?:Tool|Name)\s*:\s*(.+)",
    re.IGNORECASE,
)
_DESC_PATTERN = re.compile(
    r"Description\s*:\s*(.+)",
    re.IGNORECASE,
)
_PARAMS_PATTERN = re.compile(
    r"Parameters?\s*:\s*(.+)",
    re.IGNORECASE,
)


def _parse_docstring_meta(source: str) -> dict[str, Any] | None:
    """Extract tool metadata from a Python file's module docstring or comment header.

    Returns dict with keys: name, description, parameters — or None if no metadata found.
    """
    # Try to extract module docstring via AST
    docstring = ""
    try:
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree) or ""
    except SyntaxError:
        pass

    # Fall back to scanning comment headers (# Tool: ..., # Description: ...)
    search_text = docstring if docstring else source[:2000]

    name_match = _META_PATTERN.search(search_text)
    if not name_match:
        return None

    name = name_match.group(1).strip()
    desc = ""
    params: dict[str, dict[str, Any]] = {}

    desc_match = _DESC_PATTERN.search(search_text)
    if desc_match:
        desc = desc_match.group(1).strip()

    params_match = _PARAMS_PATTERN.search(search_text)
    if params_match:
        raw = params_match.group(1).strip()
        for chunk in raw.split(","):
            parts = [p.strip() for p in chunk.strip().split(":")]
            if not parts or not parts[0]:
                continue
            pname = parts[0]
            ptype = parts[1] if len(parts) > 1 else "string"
            required = len(parts) > 2 and parts[2].lower() == "required"
            params[pname] = {
                "type": ptype,
                "description": f"Parameter: {pname}",
                "required": required,
            }

    return {"name": name, "description": desc, "parameters": params}


def discover_tools(sandbox_root: str | Path) -> list[ToolEntry]:
    """Scan _tools/ directory for Python scripts with tool metadata.

    Args:
        sandbox_root: Path to the sandbox root directory.

    Returns:
        List of discovered ToolEntry objects.
    """
    tools_dir = Path(sandbox_root) / "_tools"
    if not tools_dir.exists():
        tools_dir.mkdir(parents=True, exist_ok=True)
        log.info("Created _tools/ directory at %s", tools_dir)
        return []

    discovered = []
    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            meta = _parse_docstring_meta(source)
            if meta:
                entry = ToolEntry(
                    name=meta["name"],
                    description=meta.get("description", f"Sandbox tool: {py_file.stem}"),
                    source="sandbox_local",
                    callable_name=py_file.stem,
                    parameters=meta.get("parameters", {}),
                )
                discovered.append(entry)
                log.info("Discovered sandbox tool: %s (%s)", meta["name"], py_file.name)
            else:
                log.debug("No metadata in %s, skipping", py_file.name)
        except Exception as e:
            log.warning("Failed to parse tool %s: %s", py_file.name, e)

    return discovered


def register_discovered_tools(catalog: ToolCatalog, sandbox_root: str | Path) -> int:
    """Discover and register sandbox tools into the catalog.

    Args:
        catalog: The ToolCatalog to register tools into.
        sandbox_root: Path to the sandbox root directory.

    Returns:
        Number of tools registered.
    """
    tools = discover_tools(sandbox_root)
    for entry in tools:
        catalog.register(entry)
    if tools:
        log.info("Registered %d sandbox tool(s)", len(tools))
    return len(tools)
