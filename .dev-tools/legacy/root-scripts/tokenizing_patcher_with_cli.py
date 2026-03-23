"""
tripartite/tokenizing_patcher.py — Whitespace-immune Hunk-based Patching

Extracted from _TokenizingPATCHER v4.3 (headless core only, no UI).
Includes a CLI for:
- single-file patching
- applying one patch to many targets
- multi-file manifest patching where each entry carries its own path

Supported patch JSON shapes

1) Single-file patch object:
{
  "hunks": [
    {
      "description": "Human-readable description of what this hunk does",
      "search_block": "exact text to find\\n(can span multiple lines)",
      "replace_block": "replacement text\\n(same or different line count)",
      "use_patch_indent": false
    }
  ]
}

2) Multi-file patch manifest:
{
  "files": [
    {
      "path": "src/module_a.py",
      "hunks": [ ...single-file hunks... ]
    },
    {
      "path": "src/module_b.py",
      "hunks": [ ...single-file hunks... ]
    }
  ]
}
"""
from __future__ import annotations

TOOL_METADATA = {
    "name": "Tokenizing Patcher",
    "description": "Whitespace-immune hunk-based patching utility for source files using structured JSON manifests.",
    "usage": "Select a JSON patch file and target files to safely validate or apply code modifications."
}

import argparse
import json
import re
import sys
from pathlib import Path


PATCH_HUNK_SCHEMA = {
    "name": "TokenizingPATCHER hunk schema",
    "type": "object",
    "required": ["hunks"],
    "properties": {
        "hunks": {
            "type": "array",
            "description": "Ordered list of non-overlapping patch hunks.",
            "items": {
                "type": "object",
                "required": ["search_block", "replace_block"],
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Optional human-readable note describing the hunk.",
                    },
                    "search_block": {
                        "type": "string",
                        "description": "Exact source text to locate. May span multiple lines.",
                    },
                    "replace_block": {
                        "type": "string",
                        "description": "Replacement text for the matched block. May span multiple lines.",
                    },
                    "use_patch_indent": {
                        "type": "boolean",
                        "description": (
                            "When true, preserve indentation from the patch text exactly. "
                            "When false, rebase the patch block onto the matched file indent."
                        ),
                        "default": False,
                    },
                },
                "additionalProperties": True,
            },
        }
    },
    "additionalProperties": True,
}

PATCH_MANIFEST_SCHEMA = {
    "name": "TokenizingPATCHER multi-file manifest schema",
    "type": "object",
    "required": ["files"],
    "properties": {
        "default_use_patch_indent": {
            "type": "boolean",
            "description": "Default indentation mode applied to file entries and hunks that do not set use_patch_indent.",
            "default": False,
        },
        "files": {
            "type": "array",
            "description": "Ordered list of file patch entries.",
            "items": {
                "type": "object",
                "required": ["path", "hunks"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": 'Target file path, e.g. "path/filename.py".',
                    },
                    "default_use_patch_indent": {
                        "type": "boolean",
                        "description": "Default indentation mode for hunks in this file entry when a hunk omits use_patch_indent.",
                        "default": False,
                    },
                    "hunks": PATCH_HUNK_SCHEMA["properties"]["hunks"],
                },
                "additionalProperties": True,
            },
        }
    },
    "additionalProperties": True,
}

PATCH_SCHEMA_EXAMPLES = {
    "single_file": {
        "hunks": [
            {
                "description": "Add deque import for ring buffer support",
                "search_block": "import argparse\nimport json\n",
                "replace_block": "import argparse\nimport json\nfrom collections import deque\n",
                "use_patch_indent": False,
            }
        ]
    },
    "multi_file": {
        "default_use_patch_indent": True,
        "files": [
            {
                "path": "src/module_a.py",
                "default_use_patch_indent": True,
                "hunks": [
                    {
                        "description": "Add deque import for ring buffer support",
                        "search_block": "import argparse\nimport json\n",
                        "replace_block": "import argparse\nimport json\nfrom collections import deque\n",
                        "use_patch_indent": False,
                    }
                ],
            },
            {
                "path": "src/module_b.py",
                "hunks": [
                    {
                        "description": "Rename variable",
                        "search_block": "old_name = 1\n",
                        "replace_block": "new_name = 1\n",
                        "use_patch_indent": False,
                    }
                ],
            },
        ]
    },
}

COMMAND_REFERENCE = {
    "apply": {
        "summary": "Apply a patch to one file, many files, or a multi-file manifest.",
        "usage": [
            "tokenizing_patcher_with_cli.py apply PATCH TARGET [TARGET ...]",
            "tokenizing_patcher_with_cli.py apply PATCH",
        ],
        "notes": [
            "If TARGETs are supplied, PATCH must be a single-file hunk object and the same patch is applied to each target.",
            "If no TARGETs are supplied, PATCH must be a multi-file manifest with files[].path entries.",
            "Use --output-dir to redirect writes for multi-target or manifest mode.",
        ],
    },
    "validate": {
        "summary": "Validate patch applicability for one file, many files, or a multi-file manifest.",
        "usage": [
            "tokenizing_patcher_with_cli.py validate PATCH TARGET [TARGET ...]",
            "tokenizing_patcher_with_cli.py validate PATCH",
        ],
        "notes": [
            "Does not write any files.",
            "Returns non-zero on missing, ambiguous, or overlapping hunks.",
        ],
    },
}


class PatchError(Exception):
    pass


class StructuredLine:
    __slots__ = ["indent", "content", "trailing", "original"]

    def __init__(self, line: str):
        self.original = line
        m = re.match(r"(^[ \t]*)(.*?)([ \t]*$)", line, re.DOTALL)
        if m:
            self.indent, self.content, self.trailing = m.group(1), m.group(2), m.group(3)
        else:
            self.indent, self.content, self.trailing = "", line, ""

    def reconstruct(self) -> str:
        return f"{self.indent}{self.content}{self.trailing}"


def tokenize_text(text: str):
    if "\r\n" in text:
        newline = "\r\n"
    elif "\n" in text:
        newline = "\n"
    else:
        newline = "\n"
    raw_lines = text.splitlines()
    lines = [StructuredLine(l) for l in raw_lines]
    return lines, newline


def locate_hunk(file_lines, search_lines, floating: bool = False):
    if not search_lines:
        return []
    matches = []
    max_start = len(file_lines) - len(search_lines)
    for start in range(max_start + 1):
        ok = True
        for i, s in enumerate(search_lines):
            f = file_lines[start + i]
            if floating:
                if f.content != s.content:
                    ok = False
                    break
            else:
                if f.reconstruct() != s.reconstruct():
                    ok = False
                    break
        if ok:
            matches.append(start)
    return matches


def _common_indent_prefix(lines):
    prefix = None
    for line in lines:
        if not line.content:
            continue
        indent = line.indent
        if prefix is None:
            prefix = indent
            continue
        i = 0
        max_i = min(len(prefix), len(indent))
        while i < max_i and prefix[i] == indent[i]:
            i += 1
        prefix = prefix[:i]
    return prefix or ""


def _strip_indent_prefix(indent: str, prefix: str) -> str:
    if prefix and indent.startswith(prefix):
        return indent[len(prefix):]
    return indent

def apply_patch_text(original_text: str, patch_obj: dict, global_force_indent: bool = False) -> str:
    if not isinstance(patch_obj, dict) or "hunks" not in patch_obj:
        raise PatchError("Patch must be a dict with a 'hunks' list.")

    hunks = patch_obj.get("hunks", [])
    if not isinstance(hunks, list):
        raise PatchError("'hunks' must be a list.")

    file_lines, newline = tokenize_text(original_text)
    applications = []

    for idx, hunk in enumerate(hunks, start=1):
        search_block = hunk.get("search_block")
        replace_block = hunk.get("replace_block")
        use_patch_indent = hunk.get("use_patch_indent", global_force_indent)

        if search_block is None or replace_block is None:
            raise PatchError(f"Hunk {idx}: Missing 'search_block' or 'replace_block'.")

        s_lines = [StructuredLine(l) for l in search_block.splitlines()]
        r_lines = [StructuredLine(l) for l in replace_block.splitlines()]

        matches = locate_hunk(file_lines, s_lines, floating=False)
        if not matches:
            matches = locate_hunk(file_lines, s_lines, floating=True)

        if not matches:
            raise PatchError(f"Hunk {idx}: Search block not found.")
        if len(matches) > 1:
            raise PatchError(f"Hunk {idx}: Ambiguous match ({len(matches)} found).")

        start = matches[0]
        applications.append({
            "start": start,
            "end": start + len(s_lines),
            "replace_lines": r_lines,
            "use_patch_indent": bool(use_patch_indent),
            "id": idx,
        })

    applications.sort(key=lambda a: a["start"])
    for i in range(len(applications) - 1):
        if applications[i]["end"] > applications[i + 1]["start"]:
            raise PatchError(
                f"Hunks {applications[i]['id']} and {applications[i + 1]['id']} overlap in the target file."
            )

    for app in reversed(applications):
        start = app["start"]
        end = app["end"]
        r_lines = app["replace_lines"]
        use_patch_indent = app["use_patch_indent"]

        matched_indent = file_lines[start].indent if start < len(file_lines) else ""
        patch_base_indent = _common_indent_prefix(r_lines)
        adjusted_lines = []
        for r in r_lines:
            line = StructuredLine(r.reconstruct())
            if not use_patch_indent:
                relative_indent = _strip_indent_prefix(line.indent, patch_base_indent)
                if line.content:
                    line.indent = matched_indent + relative_indent
                else:
                    line.indent = ""
            adjusted_lines.append(line)

        file_lines[start:end] = adjusted_lines

    result = newline.join(line.reconstruct() for line in file_lines)
    if original_text.endswith(("\n", "\r\n")):
        result += newline
    return result


def _load_patch_obj(patch_path: Path) -> dict:
    try:
        return json.loads(patch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PatchError(f"Invalid patch JSON: {exc}") from exc
    except OSError as exc:
        raise PatchError(f"Unable to read patch file '{patch_path}': {exc}") from exc


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatchError(f"Unable to read target file '{path}': {exc}") from exc


def _write_text_file(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    except OSError as exc:
        raise PatchError(f"Unable to write output file '{path}': {exc}") from exc


def _build_summary(original_text: str, patched_text: str, patch_obj: dict) -> dict:
    return {
        "changed": original_text != patched_text,
        "original_line_count": len(original_text.splitlines()),
        "patched_line_count": len(patched_text.splitlines()),
        "hunk_count": len(patch_obj.get("hunks", [])),
    }


def _is_manifest_patch(obj: dict) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("files"), list)


def _is_single_patch(obj: dict) -> bool:
    return isinstance(obj, dict) and isinstance(obj.get("hunks"), list)


def _resolve_output_path(target_path: Path, output_path: Path | None, output_dir: Path | None) -> Path:
    if output_path and output_dir:
        raise PatchError("Use either output_path or output_dir, not both.")
    if output_path:
        return output_path
    if output_dir:
        return output_dir / target_path
    return target_path


def patch_file(target_path: Path, patch_obj: dict, output_path: Path | None = None, output_dir: Path | None = None,
               force_indent: bool = False, dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Single-file patching requires a patch object with a 'hunks' list.")

    original_text = _read_text_file(target_path)
    patched_text = apply_patch_text(original_text, patch_obj, global_force_indent=force_indent)
    summary = _build_summary(original_text, patched_text, patch_obj)
    final_output = _resolve_output_path(target_path, output_path, output_dir)

    if dry_run:
        return {"status": "dry-run", "target": str(target_path), "output": str(final_output), **summary}

    if create_backup and final_output == target_path:
        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        _write_text_file(backup_path, original_text)

    _write_text_file(final_output, patched_text)
    return {"status": "applied", "target": str(target_path), "output": str(final_output), **summary}


def validate_patch(target_path: Path, patch_obj: dict, force_indent: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Single-file validation requires a patch object with a 'hunks' list.")
    original_text = _read_text_file(target_path)
    patched_text = apply_patch_text(original_text, patch_obj, global_force_indent=force_indent)
    return {"status": "valid", "target": str(target_path), **_build_summary(original_text, patched_text, patch_obj)}


def patch_many_files(targets, patch_obj: dict, output_dir: Path | None = None, force_indent: bool = False,
                     dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Multi-target mode requires a single-file patch object with a 'hunks' list.")
    results = []
    changed_count = 0
    for target in targets:
        res = patch_file(target, patch_obj, output_dir=output_dir, force_indent=force_indent,
                         dry_run=dry_run, create_backup=create_backup)
        changed_count += int(bool(res.get("changed")))
        results.append(res)
    return {
        "status": "dry-run" if dry_run else "applied",
        "mode": "multi-target",
        "target_count": len(targets),
        "changed_count": changed_count,
        "results": results,
    }


def validate_many_files(targets, patch_obj: dict, force_indent: bool = False) -> dict:
    if not _is_single_patch(patch_obj):
        raise PatchError("Multi-target validation requires a single-file patch object with a 'hunks' list.")
    results = [validate_patch(target, patch_obj, force_indent=force_indent) for target in targets]
    return {
        "status": "valid",
        "mode": "multi-target",
        "target_count": len(targets),
        "changed_count": sum(int(bool(r.get("changed"))) for r in results),
        "results": results,
    }


def patch_manifest(manifest: dict, root_dir: Path | None = None, output_dir: Path | None = None,
                   force_indent: bool = False, dry_run: bool = False, create_backup: bool = False) -> dict:
    if not _is_manifest_patch(manifest):
        raise PatchError("Manifest mode requires a patch object with a 'files' list.")
    root = root_dir or Path(".")
    manifest_default_use_patch_indent = bool(manifest.get("default_use_patch_indent", False))
    results = []
    changed_count = 0
    for idx, entry in enumerate(manifest.get("files", []), start=1):
        rel_path = entry.get("path")
        if not rel_path:
            raise PatchError(f"Manifest entry {idx} is missing 'path'.")
        target = root / Path(rel_path)
        file_default_use_patch_indent = entry.get("default_use_patch_indent", manifest_default_use_patch_indent)
        patch_obj = {
            "hunks": [
                {
                    **hunk,
                    **({} if "use_patch_indent" in hunk else {"use_patch_indent": file_default_use_patch_indent}),
                }
                for hunk in entry.get("hunks", [])
            ]
        }
        res = patch_file(target, patch_obj, output_dir=output_dir, force_indent=force_indent,
                         dry_run=dry_run, create_backup=create_backup)
        changed_count += int(bool(res.get("changed")))
        results.append(res)
    return {
        "status": "dry-run" if dry_run else "applied",
        "mode": "manifest",
        "target_count": len(results),
        "changed_count": changed_count,
        "results": results,
    }


def validate_manifest(manifest: dict, root_dir: Path | None = None, force_indent: bool = False) -> dict:
    if not _is_manifest_patch(manifest):
        raise PatchError("Manifest mode requires a patch object with a 'files' list.")
    root = root_dir or Path(".")
    manifest_default_use_patch_indent = bool(manifest.get("default_use_patch_indent", False))
    results = []
    for idx, entry in enumerate(manifest.get("files", []), start=1):
        rel_path = entry.get("path")
        if not rel_path:
            raise PatchError(f"Manifest entry {idx} is missing 'path'.")
        target = root / Path(rel_path)
        file_default_use_patch_indent = entry.get("default_use_patch_indent", manifest_default_use_patch_indent)
        patch_obj = {
            "hunks": [
                {
                    **hunk,
                    **({} if "use_patch_indent" in hunk else {"use_patch_indent": file_default_use_patch_indent}),
                }
                for hunk in entry.get("hunks", [])
            ]
        }
        results.append(validate_patch(target, patch_obj, force_indent=force_indent))
    return {
        "status": "valid",
        "mode": "manifest",
        "target_count": len(results),
        "changed_count": sum(int(bool(r.get("changed"))) for r in results),
        "results": results,
    }


def _render_schema_payload() -> dict:
    return {
        "single_file_schema": PATCH_HUNK_SCHEMA,
        "single_file_example": PATCH_SCHEMA_EXAMPLES["single_file"],
        "multi_file_schema": PATCH_MANIFEST_SCHEMA,
        "multi_file_example": PATCH_SCHEMA_EXAMPLES["multi_file"],
    }


def _render_command_payload(command_name: str | None = None) -> dict:
    if command_name:
        if command_name not in COMMAND_REFERENCE:
            raise PatchError(f"Unknown command reference '{command_name}'.")
        return {"command": command_name, "reference": COMMAND_REFERENCE[command_name], **_render_schema_payload()}
    return {"commands": COMMAND_REFERENCE, **_render_schema_payload()}


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Whitespace-immune hunk patcher for source files.")
    parser.add_argument("--schema", action="store_true", help="Print the supported patch JSON schema and examples, then exit.")
    parser.add_argument("--command", nargs="?", const="", metavar="NAME",
                        help="Print command reference info for all commands or one command, then exit.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON result to stdout.")

    subparsers = parser.add_subparsers(dest="subcommand")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("patch", type=Path, help="Path to the patch JSON file")
    common.add_argument("targets", nargs="*", type=Path,
                        help="Optional target paths. If omitted, PATCH must be a multi-file manifest with files[].path.")
    common.add_argument("--root-dir", type=Path,
                        help="Base directory used to resolve files[].path when PATCH is a multi-file manifest.")
    common.add_argument("--force-indent", action="store_true",
                        help="Use patch indentation exactly instead of rebasing to target indentation.")

    apply_parser = subparsers.add_parser("apply", parents=[common], help="Apply a patch.")
    apply_parser.add_argument("-o", "--output", type=Path,
                              help="Write patched content to a different path. Only valid for single-target mode.")
    apply_parser.add_argument("--output-dir", type=Path,
                              help="Write outputs under a separate directory, preserving target-relative paths.")
    apply_parser.add_argument("--dry-run", action="store_true",
                              help="Validate and compute the patch without writing output.")
    apply_parser.add_argument("--backup", action="store_true",
                              help="Create a .bak backup when patching target files in place.")

    subparsers.add_parser("validate", parents=[common], help="Validate that a patch can be applied cleanly.")
    return parser


def _emit_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))


def main(argv=None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    try:
        if args.schema:
            _emit_result(_render_schema_payload(), as_json=True if args.json else False)
            return 0
        if args.command is not None:
            command_name = args.command or None
            _emit_result(_render_command_payload(command_name), as_json=True if args.json else False)
            return 0
        if not args.subcommand:
            parser.print_help()
            return 2

        patch_obj = _load_patch_obj(args.patch)

        if args.subcommand == "apply":
            if args.output and len(args.targets) != 1:
                raise PatchError("--output is only valid when exactly one target path is supplied.")

            if args.targets:
                if not _is_single_patch(patch_obj):
                    raise PatchError("When targets are supplied, the patch file must contain a top-level 'hunks' list.")
                if len(args.targets) == 1:
                    result = patch_file(
                        target_path=args.targets[0],
                        patch_obj=patch_obj,
                        output_path=args.output,
                        output_dir=args.output_dir,
                        force_indent=args.force_indent,
                        dry_run=args.dry_run,
                        create_backup=args.backup,
                    )
                else:
                    result = patch_many_files(
                        targets=args.targets,
                        patch_obj=patch_obj,
                        output_dir=args.output_dir,
                        force_indent=args.force_indent,
                        dry_run=args.dry_run,
                        create_backup=args.backup,
                    )
            else:
                result = patch_manifest(
                    manifest=patch_obj,
                    root_dir=args.root_dir,
                    output_dir=args.output_dir,
                    force_indent=args.force_indent,
                    dry_run=args.dry_run,
                    create_backup=args.backup,
                )

            _emit_result(result, as_json=args.json)
            return 0

        if args.subcommand == "validate":
            if args.targets:
                if not _is_single_patch(patch_obj):
                    raise PatchError("When targets are supplied, the patch file must contain a top-level 'hunks' list.")
                if len(args.targets) == 1:
                    result = validate_patch(args.targets[0], patch_obj, force_indent=args.force_indent)
                else:
                    result = validate_many_files(args.targets, patch_obj, force_indent=args.force_indent)
            else:
                result = validate_manifest(patch_obj, root_dir=args.root_dir, force_indent=args.force_indent)

            _emit_result(result, as_json=args.json)
            return 0

        parser.error(f"Unknown subcommand: {args.subcommand}")
        return 2

    except PatchError as exc:
        error = {"status": "error", "message": str(exc)}
        if getattr(args, "json", False):
            print(json.dumps(error, indent=2), file=sys.stderr)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
