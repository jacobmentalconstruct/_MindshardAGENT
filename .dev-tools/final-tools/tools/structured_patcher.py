"""
FILE: structured_patcher.py
ROLE: Agent-facing patch application tool.
WHAT IT DOES: Validates or applies JSON-defined hunk patches using the same JSON contract as the rest of the final toolset.
HOW TO USE:
  - Metadata: python .final-tools/tools/structured_patcher.py metadata
  - Run: python .final-tools/tools/structured_patcher.py run --input-file patch-job.json
INPUT OBJECT:
  - mode: "apply" or "validate"
  - patch_path: patch file path
  - targets: optional explicit target paths
  - root_dir: optional base for manifest paths
  - output_dir: optional redirected write root
  - dry_run: optional apply preview mode
  - backup: optional in-place backup flag
  - force_indent: optional exact-indent mode
NOTES:
  - When `targets` is empty, the patch file must be a manifest with `files[]`.
  - When `targets` is present, the patch file must have top-level `hunks`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result


FILE_METADATA = {
    "tool_name": "structured_patch",
    "version": "1.0.0",
    "entrypoint": "tools/structured_patcher.py",
    "category": "editing",
    "summary": "Validate or apply structured JSON patch jobs against one or many files.",
    "mcp_name": "structured_patch",
    "legacy_replaces": [
        ".dev-tools/tokenizing_patcher_with_cli.py"
    ],
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["apply", "validate"]},
            "patch_path": {"type": "string"},
            "targets": {"type": "array", "items": {"type": "string"}, "default": []},
            "root_dir": {"type": "string"},
            "output_dir": {"type": "string"},
            "dry_run": {"type": "boolean", "default": False},
            "backup": {"type": "boolean", "default": False},
            "force_indent": {"type": "boolean", "default": False}
        },
        "required": ["mode", "patch_path"],
        "additionalProperties": False
    },
    "patch_schema": {
        "single_patch": {
            "type": "object",
            "required": ["hunks"]
        },
        "manifest_patch": {
            "type": "object",
            "required": ["files"]
        }
    }
}


class PatchError(Exception):
    """Raised when a structured patch cannot be applied safely."""


class StructuredLine:
    __slots__ = ["indent", "content", "trailing"]

    def __init__(self, line: str):
        match = re.match(r"(^[ \t]*)(.*?)([ \t]*$)", line, re.DOTALL)
        if match:
            self.indent, self.content, self.trailing = match.group(1), match.group(2), match.group(3)
        else:
            self.indent, self.content, self.trailing = "", line, ""

    def reconstruct(self) -> str:
        return f"{self.indent}{self.content}{self.trailing}"


def _tokenize_text(text: str) -> tuple[list[StructuredLine], str]:
    newline = "\r\n" if "\r\n" in text else "\n"
    return [StructuredLine(line) for line in text.splitlines()], newline


def _locate_hunk(file_lines: list[StructuredLine], search_lines: list[StructuredLine], *, floating: bool) -> list[int]:
    if not search_lines:
        return []
    matches = []
    max_start = len(file_lines) - len(search_lines)
    for start in range(max_start + 1):
        matched = True
        for offset, search_line in enumerate(search_lines):
            current = file_lines[start + offset]
            if floating:
                if current.content != search_line.content:
                    matched = False
                    break
            else:
                if current.reconstruct() != search_line.reconstruct():
                    matched = False
                    break
        if matched:
            matches.append(start)
    return matches


def _common_indent(lines: list[StructuredLine]) -> str:
    prefix: str | None = None
    for line in lines:
        if not line.content:
            continue
        indent = line.indent
        if prefix is None:
            prefix = indent
            continue
        shared = 0
        limit = min(len(prefix), len(indent))
        while shared < limit and prefix[shared] == indent[shared]:
            shared += 1
        prefix = prefix[:shared]
    return prefix or ""


def _apply_patch_text(original_text: str, patch_obj: dict, *, force_indent: bool) -> str:
    hunks = patch_obj.get("hunks")
    if not isinstance(hunks, list):
        raise PatchError("Patch object must contain a 'hunks' list.")

    file_lines, newline = _tokenize_text(original_text)
    applications = []

    for index, hunk in enumerate(hunks, start=1):
        search_block = hunk.get("search_block")
        replace_block = hunk.get("replace_block")
        if search_block is None or replace_block is None:
            raise PatchError(f"Hunk {index} is missing search_block or replace_block.")

        search_lines = [StructuredLine(line) for line in search_block.splitlines()]
        replace_lines = [StructuredLine(line) for line in replace_block.splitlines()]
        matches = _locate_hunk(file_lines, search_lines, floating=False)
        if not matches:
            matches = _locate_hunk(file_lines, search_lines, floating=True)
        if not matches:
            raise PatchError(f"Hunk {index}: search block not found.")
        if len(matches) > 1:
            raise PatchError(f"Hunk {index}: ambiguous match ({len(matches)} matches).")

        applications.append({
            "start": matches[0],
            "end": matches[0] + len(search_lines),
            "replace_lines": replace_lines,
            "use_patch_indent": bool(hunk.get("use_patch_indent", force_indent)),
            "index": index,
        })

    applications.sort(key=lambda item: item["start"])
    for left, right in zip(applications, applications[1:]):
        if left["end"] > right["start"]:
            raise PatchError(f"Hunks {left['index']} and {right['index']} overlap.")

    for app in reversed(applications):
        matched_indent = file_lines[app["start"]].indent if app["start"] < len(file_lines) else ""
        patch_base_indent = _common_indent(app["replace_lines"])
        adjusted: list[StructuredLine] = []
        for source_line in app["replace_lines"]:
            line = StructuredLine(source_line.reconstruct())
            if not app["use_patch_indent"] and line.content:
                relative = line.indent[len(patch_base_indent):] if line.indent.startswith(patch_base_indent) else line.indent
                line.indent = matched_indent + relative
            adjusted.append(line)
        file_lines[app["start"]:app["end"]] = adjusted

    result = newline.join(line.reconstruct() for line in file_lines)
    if original_text.endswith(("\n", "\r\n")):
        result += newline
    return result


def _load_patch(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchError(f"Invalid JSON patch file: {exc}") from exc


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatchError(f"Unable to read file '{path}': {exc}") from exc


def _write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    except OSError as exc:
        raise PatchError(f"Unable to write file '{path}': {exc}") from exc


def _summary(original_text: str, patched_text: str, patch_obj: dict) -> dict:
    return {
        "changed": original_text != patched_text,
        "original_line_count": len(original_text.splitlines()),
        "patched_line_count": len(patched_text.splitlines()),
        "hunk_count": len(patch_obj.get("hunks", [])),
    }


def _patch_one(target: Path, patch_obj: dict, *, output_dir: Path | None, force_indent: bool, dry_run: bool, backup: bool) -> dict:
    original_text = _read_text(target)
    patched_text = _apply_patch_text(original_text, patch_obj, force_indent=force_indent)
    output_path = (output_dir / target) if output_dir else target
    payload = {"target": str(target), "output": str(output_path), **_summary(original_text, patched_text, patch_obj)}
    if dry_run:
        return {"status": "dry-run", **payload}
    if backup and output_path == target:
        _write_text(target.with_suffix(target.suffix + ".bak"), original_text)
    _write_text(output_path, patched_text)
    return {"status": "applied", **payload}


def _validate_one(target: Path, patch_obj: dict, *, force_indent: bool) -> dict:
    original_text = _read_text(target)
    patched_text = _apply_patch_text(original_text, patch_obj, force_indent=force_indent)
    return {"status": "valid", "target": str(target), **_summary(original_text, patched_text, patch_obj)}


def run(arguments: dict) -> dict:
    mode = arguments["mode"]
    patch_path = Path(arguments["patch_path"]).resolve()
    targets = [Path(item).resolve() for item in arguments.get("targets", [])]
    root_dir = Path(arguments["root_dir"]).resolve() if arguments.get("root_dir") else Path.cwd()
    output_dir = Path(arguments["output_dir"]).resolve() if arguments.get("output_dir") else None
    dry_run = bool(arguments.get("dry_run", False))
    backup = bool(arguments.get("backup", False))
    force_indent = bool(arguments.get("force_indent", False))
    patch_obj = _load_patch(patch_path)

    if mode not in {"apply", "validate"}:
        raise PatchError("mode must be 'apply' or 'validate'.")

    if targets:
        if not isinstance(patch_obj.get("hunks"), list):
            raise PatchError("When targets are supplied, the patch file must contain top-level 'hunks'.")
        if mode == "validate":
            result = {
                "mode": "multi-target",
                "results": [_validate_one(target, patch_obj, force_indent=force_indent) for target in targets]
            }
        else:
            result = {
                "mode": "multi-target",
                "results": [
                    _patch_one(
                        target,
                        patch_obj,
                        output_dir=output_dir,
                        force_indent=force_indent,
                        dry_run=dry_run,
                        backup=backup,
                    )
                    for target in targets
                ]
            }
        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    manifest_files = patch_obj.get("files")
    if not isinstance(manifest_files, list):
        raise PatchError("Without targets, the patch file must contain top-level 'files'.")

    manifest_default_indent = bool(patch_obj.get("default_use_patch_indent", False))
    results = []
    for entry in manifest_files:
        rel_path = entry.get("path")
        if not rel_path:
            raise PatchError("Manifest entry is missing 'path'.")
        entry_patch = {
            "hunks": [
                hunk if "use_patch_indent" in hunk else {**hunk, "use_patch_indent": bool(entry.get("default_use_patch_indent", manifest_default_indent))}
                for hunk in entry.get("hunks", [])
            ]
        }
        target = (root_dir / Path(rel_path)).resolve()
        if mode == "validate":
            results.append(_validate_one(target, entry_patch, force_indent=force_indent))
        else:
            results.append(
                _patch_one(
                    target,
                    entry_patch,
                    output_dir=output_dir,
                    force_indent=force_indent,
                    dry_run=dry_run,
                    backup=backup,
                )
            )

    return tool_result(FILE_METADATA["tool_name"], arguments, {"mode": "manifest", "results": results})


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
