"""File writer — direct file creation/reading/editing within the sandbox.

Solves the fundamental problem that small models cannot reliably create or
update multi-line files through shell quoting alone. Instead of fighting
platform-specific escaping, the model can use structured file tools that
operate directly on sandboxed paths.
"""

from pathlib import Path
from typing import Any

from src.core.runtime.activity_stream import ActivityStream
from src.core.runtime.runtime_logger import get_logger
from src.core.sandbox.audit_log import AuditLog
from src.core.sandbox.path_guard import PathGuard
from src.core.utils.clock import Stopwatch

log = get_logger("file_writer")

# Safety limits
MAX_WRITE_SIZE = 512_000     # 512 KB max per direct write
MAX_READ_SIZE = 1_024_000    # 1 MB max per read/edit surface
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".wsf", ".msi", ".scr", ".com"}


class FileWriter:
    """Read and write files within the sandbox boundary."""

    def __init__(self, guard: PathGuard, activity: ActivityStream,
                 audit_log: AuditLog | None = None):
        self._guard = guard
        self._activity = activity
        self._audit = audit_log

    def write_file(self, path: str, content: str,
                   mode: str = "write") -> dict[str, Any]:
        """Write content to a file within the sandbox."""
        sw = Stopwatch()

        try:
            resolved = self._guard.validate(path)
        except ValueError as e:
            self._log_audit("write_file", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}

        ext = resolved.suffix.lower()
        if ext in BLOCKED_EXTENSIONS:
            msg = f"Cannot write files with extension '{ext}' (security policy)"
            log.warning("WRITE BLOCKED: %s — %s", path, msg)
            self._activity.warn("file_writer", f"BLOCKED: {path} — {msg}")
            self._log_audit("write_file", path, "blocked", reason=msg)
            return {"path": path, "success": False, "error": msg}

        if len(content) > MAX_WRITE_SIZE:
            msg = f"Content too large ({len(content)} bytes, max {MAX_WRITE_SIZE})"
            self._log_audit("write_file", path, "blocked", reason=msg)
            return {"path": path, "success": False, "error": msg}

        resolved.parent.mkdir(parents=True, exist_ok=True)
        open_mode = "a" if mode == "append" else "w"
        action = "Appending to" if mode == "append" else "Writing"

        try:
            with open(resolved, open_mode, encoding="utf-8", newline="\n") as handle:
                handle.write(content)

            bytes_written = len(content.encode("utf-8"))
            elapsed = sw.elapsed_ms()
            log.info("%s %s (%d bytes, %.0fms)", action, resolved, bytes_written, elapsed)
            self._activity.tool("file_writer",
                                f"{action} {resolved.name} ({bytes_written} bytes)")
            self._log_audit("write_file", str(resolved), "executed",
                            exit_code=0, duration_ms=elapsed)
            return {
                "path": str(resolved),
                "success": True,
                "bytes_written": bytes_written,
                "action": mode,
            }
        except Exception as e:
            elapsed = sw.elapsed_ms()
            log.exception("Write failed: %s", path)
            self._activity.warn("file_writer", f"FAILED: {path} — {e}")
            self._log_audit("write_file", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        line_numbers: bool = False,
        show_whitespace: bool = False,
    ) -> dict[str, Any]:
        """Read a file from within the sandbox, optionally as an edit-oriented view."""
        sw = Stopwatch()

        try:
            resolved, content, file_size = self._read_text_file(path)
            rendered, resolved_start, resolved_end = self._render_read_view(
                content,
                start_line=start_line,
                end_line=end_line,
                line_numbers=line_numbers,
                show_whitespace=show_whitespace,
            )
        except ValueError as e:
            self._log_audit("read_file", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}
        except UnicodeDecodeError:
            msg = f"Cannot read binary file: {Path(path).name}"
            self._log_audit("read_file", path, "error", reason=msg)
            return {"path": path, "success": False, "error": msg}
        except Exception as e:
            elapsed = sw.elapsed_ms()
            log.exception("Read failed: %s", path)
            self._log_audit("read_file", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

        elapsed = sw.elapsed_ms()
        log.info("Read %s (%d bytes, %.0fms)", resolved, file_size, elapsed)
        self._activity.tool("file_writer", f"Read {resolved.name} ({file_size} bytes)")
        self._log_audit("read_file", str(resolved), "executed",
                        exit_code=0, duration_ms=elapsed)
        return {
            "path": str(resolved),
            "success": True,
            "content": rendered,
            "size": file_size,
            "start_line": resolved_start,
            "end_line": resolved_end,
            "line_numbers": line_numbers,
            "show_whitespace": show_whitespace,
        }

    def replace_in_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        expected_count: int | None = 1,
        replace_all: bool = False,
        context_lines: int = 2,
    ) -> dict[str, Any]:
        """Replace exact literal text within an existing sandbox file."""
        sw = Stopwatch()

        if old_text == "":
            return {"path": path, "success": False, "error": "old_text must not be empty"}

        try:
            resolved, content, _file_size = self._read_text_file(path)
        except ValueError as e:
            self._log_audit("replace_in_file", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}
        except UnicodeDecodeError:
            msg = f"Cannot read binary file: {Path(path).name}"
            self._log_audit("replace_in_file", path, "error", reason=msg)
            return {"path": path, "success": False, "error": msg}
        except Exception as e:
            elapsed = sw.elapsed_ms()
            self._log_audit("replace_in_file", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

        match_count = content.count(old_text)
        if match_count == 0:
            msg = "Exact target text was not found. Read the file and retry with the current content."
            return {"path": str(resolved), "success": False, "error": msg, "match_count": 0}

        if replace_all:
            if expected_count is not None and match_count != expected_count:
                msg = f"Expected {expected_count} match(es) but found {match_count}"
                return {
                    "path": str(resolved),
                    "success": False,
                    "error": msg,
                    "match_count": match_count,
                }
            replaced_count = match_count
            updated = content.replace(old_text, new_text)
        else:
            if expected_count is None:
                expected_count = 1
            if match_count != expected_count:
                if match_count > 1:
                    msg = (
                        f"Expected {expected_count} match(es) but found {match_count}. "
                        "Use replace_all or narrow the target text."
                    )
                else:
                    msg = f"Expected {expected_count} match(es) but found {match_count}"
                return {
                    "path": str(resolved),
                    "success": False,
                    "error": msg,
                    "match_count": match_count,
                }
            replaced_count = 1
            updated = content.replace(old_text, new_text, 1)

        new_size = len(updated.encode("utf-8"))
        if new_size > MAX_READ_SIZE:
            msg = f"Resulting file too large ({new_size} bytes, max {MAX_READ_SIZE})"
            return {"path": str(resolved), "success": False, "error": msg}

        anchor_index = content.find(old_text)
        focus_line = self._line_number_for_index(content, anchor_index)
        before_excerpt = self._excerpt_by_lines(
            content,
            focus_start=focus_line,
            focus_end=focus_line + old_text.count("\n"),
            context_lines=context_lines,
        )
        after_excerpt = self._excerpt_by_lines(
            updated,
            focus_start=focus_line,
            focus_end=focus_line + new_text.count("\n"),
            context_lines=context_lines,
        )

        try:
            resolved.write_text(updated, encoding="utf-8", newline="\n")
        except Exception as e:
            elapsed = sw.elapsed_ms()
            self._log_audit("replace_in_file", str(resolved), "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": str(resolved), "success": False, "error": str(e)}

        elapsed = sw.elapsed_ms()
        self._activity.tool("file_writer",
                            f"replace_in_file: {resolved.name} ({replaced_count} change)")
        self._log_audit("replace_in_file", str(resolved), "executed",
                        exit_code=0, duration_ms=elapsed)
        return {
            "path": str(resolved),
            "success": True,
            "match_count": match_count,
            "replaced_count": replaced_count,
            "bytes_written": new_size,
            "before_excerpt": before_excerpt,
            "after_excerpt": after_excerpt,
        }

    def replace_lines(
        self,
        path: str,
        start_line: int,
        end_line: int,
        new_text: str,
        context_lines: int = 2,
    ) -> dict[str, Any]:
        """Replace an inclusive line range within an existing sandbox file."""
        sw = Stopwatch()

        if start_line < 1 or end_line < start_line:
            return {"path": path, "success": False, "error": "Invalid line range"}

        try:
            resolved, content, _file_size = self._read_text_file(path)
        except ValueError as e:
            self._log_audit("replace_lines", path, "blocked", reason=str(e))
            return {"path": path, "success": False, "error": str(e)}
        except UnicodeDecodeError:
            msg = f"Cannot read binary file: {Path(path).name}"
            self._log_audit("replace_lines", path, "error", reason=msg)
            return {"path": path, "success": False, "error": msg}
        except Exception as e:
            elapsed = sw.elapsed_ms()
            self._log_audit("replace_lines", path, "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": path, "success": False, "error": str(e)}

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        if total_lines == 0:
            return {"path": str(resolved), "success": False, "error": "File is empty"}
        if end_line > total_lines:
            msg = f"Line range {start_line}-{end_line} is outside file length {total_lines}"
            return {"path": str(resolved), "success": False, "error": msg}

        before_excerpt = self._excerpt_by_lines(
            content,
            focus_start=start_line,
            focus_end=end_line,
            context_lines=context_lines,
        )

        replacement = new_text
        removed_block = "".join(lines[start_line - 1:end_line])
        if removed_block.endswith(("\r\n", "\n", "\r")) and not replacement.endswith(("\r\n", "\n", "\r")):
            if removed_block.endswith("\r\n"):
                replacement += "\r\n"
            elif removed_block.endswith("\n"):
                replacement += "\n"
            else:
                replacement += "\r"

        replacement_lines = replacement.splitlines(keepends=True)
        updated_lines = lines[:start_line - 1] + replacement_lines + lines[end_line:]
        updated = "".join(updated_lines)

        new_size = len(updated.encode("utf-8"))
        if new_size > MAX_READ_SIZE:
            msg = f"Resulting file too large ({new_size} bytes, max {MAX_READ_SIZE})"
            return {"path": str(resolved), "success": False, "error": msg}

        replacement_span = max(1, len(replacement.splitlines()) or (1 if replacement else 0))
        after_excerpt = self._excerpt_by_lines(
            updated,
            focus_start=start_line,
            focus_end=start_line + replacement_span - 1,
            context_lines=context_lines,
        )

        try:
            resolved.write_text(updated, encoding="utf-8", newline="\n")
        except Exception as e:
            elapsed = sw.elapsed_ms()
            self._log_audit("replace_lines", str(resolved), "error",
                            reason=str(e), duration_ms=elapsed)
            return {"path": str(resolved), "success": False, "error": str(e)}

        elapsed = sw.elapsed_ms()
        self._activity.tool("file_writer",
                            f"replace_lines: {resolved.name} ({start_line}-{end_line})")
        self._log_audit("replace_lines", str(resolved), "executed",
                        exit_code=0, duration_ms=elapsed)
        return {
            "path": str(resolved),
            "success": True,
            "start_line": start_line,
            "end_line": end_line,
            "bytes_written": new_size,
            "before_excerpt": before_excerpt,
            "after_excerpt": after_excerpt,
        }

    def list_files(self, path: str = "", depth: int = 3) -> dict[str, Any]:
        """Return a structured directory listing within the sandbox."""
        try:
            start = self._guard.validate(path) if path else self._guard.root
        except ValueError as e:
            return {"path": path, "success": False, "error": str(e)}

        if not start.exists():
            return {"path": str(start), "success": False, "error": "Path not found"}
        if not start.is_dir():
            return {"path": str(start), "success": False, "error": "Not a directory"}

        def _walk(directory: Path, current_depth: int) -> list:
            entries = []
            try:
                items = sorted(directory.iterdir(),
                               key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                return entries
            for item in items:
                if item.name.startswith(".") or item.name in (
                        "__pycache__", "venv", ".venv", "node_modules"):
                    continue
                rel = item.relative_to(self._guard.root)
                entry: dict[str, Any] = {
                    "name": item.name,
                    "path": str(rel).replace("\\", "/"),
                    "type": "dir" if item.is_dir() else "file",
                }
                if item.is_file():
                    entry["size"] = item.stat().st_size
                if item.is_dir() and current_depth > 1:
                    entry["children"] = _walk(item, current_depth - 1)
                entries.append(entry)
            return entries

        tree = _walk(start, depth)
        rel_start = str(start.relative_to(self._guard.root)).replace("\\", "/") if start != self._guard.root else ""
        self._activity.tool("file_writer", f"list_files: {rel_start or '.'} ({len(tree)} entries)")
        return {
            "path": rel_start or ".",
            "success": True,
            "tree": tree,
        }

    def _read_text_file(self, path: str) -> tuple[Path, str, int]:
        resolved = self._guard.validate(path)

        if not resolved.exists():
            raise ValueError(f"File not found: {resolved.name}")
        if not resolved.is_file():
            raise ValueError(f"Not a file: {resolved.name}")

        file_size = resolved.stat().st_size
        if file_size > MAX_READ_SIZE:
            raise ValueError(f"File too large ({file_size} bytes, max {MAX_READ_SIZE})")

        content = resolved.read_text(encoding="utf-8")
        return resolved, content, file_size

    def _render_read_view(
        self,
        content: str,
        *,
        start_line: int | None,
        end_line: int | None,
        line_numbers: bool,
        show_whitespace: bool,
    ) -> tuple[str, int | None, int | None]:
        full_view = start_line is None and end_line is None
        lines = content.splitlines()
        total_lines = len(lines)

        if full_view:
            resolved_start = 1 if total_lines else None
            resolved_end = total_lines if total_lines else None
            selected = lines
        else:
            if start_line is None:
                start_line = 1
            if end_line is None:
                end_line = total_lines
            if total_lines == 0:
                raise ValueError("File is empty")
            start_line = max(1, start_line)
            if end_line < start_line:
                end_line = start_line
            if start_line > total_lines:
                raise ValueError(f"Requested line range starts beyond file length {total_lines}")
            end_line = min(end_line, total_lines)
            resolved_start = start_line
            resolved_end = end_line
            selected = lines[start_line - 1:end_line]

        if not line_numbers and not show_whitespace:
            if full_view:
                return content, resolved_start, resolved_end
            return "\n".join(selected), resolved_start, resolved_end

        rendered: list[str] = []
        base_line = resolved_start or 1
        for offset, line in enumerate(selected):
            actual_line = base_line + offset
            display = self._format_line_for_display(line, show_whitespace=show_whitespace)
            if line_numbers:
                rendered.append(f"{actual_line:>4}| {display}")
            else:
                rendered.append(display)
        return "\n".join(rendered), resolved_start, resolved_end

    def _format_line_for_display(self, line: str, *, show_whitespace: bool) -> str:
        if not show_whitespace:
            return line

        indent_width = len(line) - len(line.lstrip(" \t"))
        indent = line[:indent_width]
        remainder = line[indent_width:]
        indent_spaces = indent.count(" ")
        indent_tabs = indent.count("\t")
        trailing_spaces = len(remainder) - len(remainder.rstrip(" "))
        core = remainder[:-trailing_spaces] if trailing_spaces else remainder
        core = core.replace("\t", "\\t")

        markers: list[str] = []
        if indent_spaces:
            markers.append(f"indent_spaces={indent_spaces}")
        if indent_tabs:
            markers.append(f"indent_tabs={indent_tabs}")
        if not markers:
            markers.append("indent=0")
        if trailing_spaces:
            markers.append(f"trailing_spaces={trailing_spaces}")
        return f"[{' '.join(markers)}] {core}"

    def _excerpt_by_lines(
        self,
        content: str,
        *,
        focus_start: int,
        focus_end: int,
        context_lines: int,
    ) -> str:
        lines = content.splitlines()
        if not lines:
            return ""
        start_line = max(1, focus_start - max(0, context_lines))
        end_line = min(len(lines), focus_end + max(0, context_lines))
        rendered: list[str] = []
        for line_no in range(start_line, end_line + 1):
            rendered.append(f"{line_no:>4}| {lines[line_no - 1]}")
        return "\n".join(rendered)

    def _line_number_for_index(self, content: str, index: int) -> int:
        return content.count("\n", 0, max(0, index)) + 1

    def _log_audit(self, operation: str, path: str, outcome: str,
                   exit_code: int | None = None, reason: str = "",
                   duration_ms: float = 0) -> None:
        """Record operation in audit log."""
        if self._audit:
            self._audit.record(
                command=f"{operation} {path}",
                cwd=str(self._guard.root),
                outcome=outcome,
                exit_code=exit_code,
                reason=reason,
                duration_ms=duration_ms,
            )
