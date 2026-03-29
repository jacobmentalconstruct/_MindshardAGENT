"""Deterministic guardrail for filesystem-affecting tool-agent turns.

Tracks file-tool evidence, classifies whether a user asked for filesystem work,
and evaluates whether the assistant's final claim is grounded in actual tool
results. This is intentionally deterministic and conservative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


_PATHLIKE_RE = re.compile(
    r"(?<![\w.-])(?:[A-Za-z]:[\\/])?[A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_. -]+)+"
)
_BACKTICK_PATH_RE = re.compile(r"`([^`\n]+)`")
_FRAGMENT_SPLIT_RE = re.compile(r"[\n\r]+|(?<=[.!?])\s+")
_FILE_NOUN_RE = re.compile(
    r"\b(file|files|folder|folders|directory|directories|path|paths|scaffold|module|package|readme|section|line|lines)\b"
)
_CREATE_RE = re.compile(r"\b(create|scaffold|setup|set up|make|build|add|write)\b")
_MODIFY_RE = re.compile(r"\b(update|edit|modify|change|rewrite|replace|patch)\b")
_CLAIM_VERB_RE = re.compile(
    r"\b(create|created|scaffold|scaffolded|make|made|build|built|write|wrote|"
    r"update|updated|edit|edited|modify|modified|change|changed|rewrite|rewrote|"
    r"replace|replaced|patch|patched|read|read back|verify|verified|confirm|confirmed|"
    r"inspect|inspected|open|opened)\b"
)
_CONTENT_REFERENCE_RE = re.compile(
    r"\b(list|listed|lists|contain|contains|contained|include|includes|included|"
    r"show|shows|showing|mention|mentions|mentioned)\b"
)
_VERIFY_CONTENT_RE = re.compile(
    r"(read it back|read back|read the file|read the files|check the file|verify the file|inspect the file|show me the file|confirm the content)"
)
_VERIFY_PATH_RE = re.compile(
    r"(make sure .* exists|check .* exists|verify .* exists|confirm .* created|check the path|verify the path|confirm the file|confirm the folder)"
)


def _normalize_path(path: str) -> str:
    normalized = path.strip().strip('"').strip("'").replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[0].lower() + normalized[1:]
    return normalized.rstrip("/")


def _path_aliases(path: str, sandbox_root: str = "") -> set[str]:
    aliases: set[str] = set()
    normalized = _normalize_path(path)
    if not normalized:
        return aliases
    aliases.add(normalized)
    if normalized.startswith("./"):
        aliases.add(normalized[2:])
    sandbox = _normalize_path(sandbox_root)
    if sandbox and (normalized == sandbox or normalized.startswith(f"{sandbox}/")):
        relative = normalized[len(sandbox):].lstrip("/")
        if relative:
            aliases.add(relative)
            aliases.add(f"./{relative}")
    return aliases


def _looks_like_file_path(token: str) -> bool:
    normalized = _normalize_path(token)
    if "/" in normalized:
        tail = normalized.rsplit("/", 1)[-1]
        return "." in tail or tail.lower() in {"readme", "makefile", "dockerfile"}
    return "." in normalized


def _extract_paths_from_fragment(fragment: str, sandbox_root: str = "") -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for match in _BACKTICK_PATH_RE.finditer(fragment or ""):
        token = match.group(1).strip()
        if not _looks_like_file_path(token):
            continue
        for alias in sorted(_path_aliases(token, sandbox_root)):
            if alias not in seen:
                ordered.append(alias)
                seen.add(alias)
    for match in _PATHLIKE_RE.finditer(fragment or ""):
        token = match.group(0).strip()
        if not _looks_like_file_path(token):
            continue
        for alias in sorted(_path_aliases(token, sandbox_root)):
            if alias not in seen:
                ordered.append(alias)
                seen.add(alias)
    return ordered


def extract_claimed_file_paths(text: str, sandbox_root: str = "") -> list[str]:
    """Extract file-like paths claimed as acted-upon files, not content examples."""
    candidates: set[str] = set()
    for fragment in _FRAGMENT_SPLIT_RE.split(text or ""):
        fragment = fragment.strip()
        if not fragment:
            continue
        if not _CLAIM_VERB_RE.search(fragment.lower()):
            continue
        fragment_paths = _extract_paths_from_fragment(fragment, sandbox_root)
        if not fragment_paths:
            continue
        # Sentences like "update BUILD_PLAN.md to list src/app.py and tests/test_app.py"
        # should treat BUILD_PLAN.md as the acted-on file while the listed paths are
        # content references, not unsupported edited-file claims.
        if _CONTENT_REFERENCE_RE.search(fragment.lower()) and len(fragment_paths) > 1:
            fragment_paths = fragment_paths[:1]
        candidates.update(fragment_paths)
    return sorted(candidates)


@dataclass(frozen=True)
class FilesystemIntent:
    create_file: bool = False
    modify_file: bool = False
    verify_path: bool = False
    verify_content: bool = False

    @property
    def requires_mutation(self) -> bool:
        return self.create_file or self.modify_file

    @property
    def any(self) -> bool:
        return self.requires_mutation or self.verify_path or self.verify_content


def classify_filesystem_intent(user_text: str) -> FilesystemIntent:
    """Classify whether a user request clearly asks for filesystem work."""
    lowered = (user_text or "").lower()
    has_pathlike = bool(_PATHLIKE_RE.search(user_text or ""))
    has_fs_noun = bool(_FILE_NOUN_RE.search(lowered))
    scoped = has_pathlike or has_fs_noun

    create_file = scoped and bool(_CREATE_RE.search(lowered))
    modify_file = scoped and bool(_MODIFY_RE.search(lowered))
    verify_content = scoped and bool(_VERIFY_CONTENT_RE.search(lowered))
    verify_path = scoped and bool(_VERIFY_PATH_RE.search(lowered))

    if verify_content:
        verify_path = True

    return FilesystemIntent(
        create_file=create_file,
        modify_file=modify_file,
        verify_path=verify_path,
        verify_content=verify_content,
    )


@dataclass
class FilesystemEvidence:
    file_tool_called: bool = False
    file_read_called: bool = False
    file_mutation_called: bool = False
    file_verification_called: bool = False
    successful_write_paths: set[str] = field(default_factory=set)
    successful_replace_paths: set[str] = field(default_factory=set)
    successful_read_paths: set[str] = field(default_factory=set)
    successful_run_paths: set[str] = field(default_factory=set)
    successful_list_files: set[str] = field(default_factory=set)
    mutation_count: int = 0
    read_count: int = 0
    _events: list[str] = field(default_factory=list, repr=False)

    def record_tool_result(self, tool_result: dict[str, Any], sandbox_root: str = "") -> None:
        tool_name = str(tool_result.get("tool_name", ""))
        result = tool_result.get("result", {}) or {}
        success = bool(tool_result.get("success"))

        if tool_name in {"write_file", "read_file", "replace_in_file", "replace_lines", "list_files"}:
            self.file_tool_called = True

        if not success:
            return

        if tool_name == "write_file":
            self.file_mutation_called = True
            self.mutation_count += 1
            self.successful_write_paths.update(_path_aliases(result.get("path", ""), sandbox_root))
            self._events.append("mutation")
            return

        if tool_name in {"replace_in_file", "replace_lines"}:
            self.file_mutation_called = True
            self.mutation_count += 1
            self.successful_replace_paths.update(_path_aliases(result.get("path", ""), sandbox_root))
            self._events.append("mutation")
            return

        if tool_name == "read_file":
            self.file_read_called = True
            self.file_verification_called = True
            self.read_count += 1
            self.successful_read_paths.update(_path_aliases(result.get("path", ""), sandbox_root))
            self._events.append("read")
            return

        if tool_name == "list_files":
            self.file_verification_called = True
            self.successful_list_files.update(_path_aliases(result.get("path", ""), sandbox_root))
            self._events.append("list")
            return

        if tool_name == "run_python_file":
            self.successful_run_paths.update(_path_aliases(result.get("path", ""), sandbox_root))

    def all_successful_paths(self) -> set[str]:
        return (
            set(self.successful_write_paths)
            | set(self.successful_replace_paths)
            | set(self.successful_read_paths)
            | set(self.successful_run_paths)
            | set(self.successful_list_files)
        )

    def has_verification_after_mutation(self, *, content: bool = False) -> bool:
        if not self.file_mutation_called:
            return self.file_read_called if content else self.file_verification_called

        last_mutation = -1
        for index, event in enumerate(self._events):
            if event == "mutation":
                last_mutation = index
        if last_mutation < 0:
            return False
        for event in self._events[last_mutation + 1:]:
            if content and event == "read":
                return True
            if not content and event in {"read", "list"}:
                return True
        return False

    def to_summary(self) -> dict[str, Any]:
        return {
            "file_tool_called": self.file_tool_called,
            "file_read_called": self.file_read_called,
            "file_mutation_called": self.file_mutation_called,
            "file_verification_called": self.file_verification_called,
            "successful_write_paths": sorted(self.successful_write_paths),
            "successful_replace_paths": sorted(self.successful_replace_paths),
            "successful_read_paths": sorted(self.successful_read_paths),
            "successful_run_paths": sorted(self.successful_run_paths),
            "successful_list_files": sorted(self.successful_list_files),
            "mutation_count": self.mutation_count,
            "read_count": self.read_count,
        }


@dataclass(frozen=True)
class FilesystemGuardrailEvaluation:
    triggered: bool
    intent: FilesystemIntent
    violations: list[str]
    claimed_paths: list[str]


def evaluate_filesystem_guardrail(
    *,
    user_text: str,
    assistant_text: str,
    evidence: FilesystemEvidence,
    sandbox_root: str = "",
) -> FilesystemGuardrailEvaluation:
    """Evaluate whether the assistant's filesystem claim is supported by evidence."""
    intent = classify_filesystem_intent(user_text)
    if not intent.any:
        return FilesystemGuardrailEvaluation(
            triggered=False,
            intent=intent,
            violations=[],
            claimed_paths=[],
        )

    violations: list[str] = []
    if intent.requires_mutation and not evidence.file_mutation_called:
        violations.append("mutation_requested_without_successful_file_mutation")

    if intent.verify_content and not evidence.has_verification_after_mutation(content=True):
        violations.append("content_verification_requested_without_successful_readback")
    elif intent.verify_path and not evidence.has_verification_after_mutation(content=False):
        violations.append("path_verification_requested_without_successful_verification")

    claimed_paths = extract_claimed_file_paths(assistant_text, sandbox_root)
    if claimed_paths:
        known = evidence.all_successful_paths()
        unmatched = [path for path in claimed_paths if path not in known]
        if unmatched:
            violations.append(
                "assistant_named_file_without_matching_tool_evidence:" + ", ".join(sorted(unmatched))
            )

    return FilesystemGuardrailEvaluation(
        triggered=bool(violations),
        intent=intent,
        violations=violations,
        claimed_paths=claimed_paths,
    )


def summarize_guardrail_violations(evaluation: FilesystemGuardrailEvaluation) -> str:
    if not evaluation.violations:
        return "No guardrail violations detected."
    parts = []
    for violation in evaluation.violations:
        if violation == "mutation_requested_without_successful_file_mutation":
            parts.append("the user asked for file creation or modification but no successful file mutation tool call occurred")
        elif violation == "content_verification_requested_without_successful_readback":
            parts.append("the user asked for readback verification but no successful read_file occurred after the mutation")
        elif violation == "path_verification_requested_without_successful_verification":
            parts.append("the user asked for file/path verification but no successful read_file or list_files occurred after the mutation")
        elif violation.startswith("assistant_named_file_without_matching_tool_evidence:"):
            names = violation.split(":", 1)[1]
            parts.append(f"the assistant named file path(s) without matching tool evidence: {names}")
        else:
            parts.append(violation)
    return "; ".join(parts)
