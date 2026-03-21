"""Command security policy — allowlist-based command validation.

The sandbox CLI runner is only as secure as the commands it permits.
Path guarding alone is insufficient: an agent with arbitrary shell access
can curl, powershell, net, reg, or otherwise escape the sandbox entirely.

This module enforces an explicit allowlist. Commands not on the list are
blocked. Commands on the blocklist are always blocked even if allowlisted.

Security model:
  - ALLOWLIST: only these command bases may execute
  - BLOCKLIST: these are always blocked (overrides allowlist)
  - PATTERN_BLOCKS: regex patterns that are always rejected
  - Mode: "allowlist" (default, strict) or "blocklist" (permissive, dangerous)
"""

import re
import shlex
from typing import Any

from src.core.runtime.runtime_logger import get_logger

log = get_logger("command_policy")


# ── Always blocked — system-destructive or escape-capable ─────
ALWAYS_BLOCKED = {
    # System destructive
    "format", "shutdown", "restart", "reboot", "diskpart",
    # Privilege escalation
    "runas", "sudo", "su",
    # Account manipulation
    "net", "net1",
    # Registry manipulation
    "reg", "regedit",
    # Service manipulation
    "sc", "schtasks",
    # Remote execution
    "psexec", "wmic", "winrm",
    # Scripting engines (can bypass any restriction)
    "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "cmd", "cmd.exe",
    "cscript", "wscript", "mshta",
    # Network exfiltration
    "curl", "wget", "invoke-webrequest", "invoke-restmethod",
    "ftp", "sftp", "scp", "ssh", "telnet", "nslookup",
    # Package managers (can install arbitrary code)
    "pip", "pip3", "npm", "yarn", "choco", "winget", "scoop",
    # Dangerous file ops at system level
    "takeown", "icacls", "cacls", "attrib",
    "mklink",  # symlink creation
}

# ── Allowed commands — the agent may only use these ───────────
# Organized by category for teachability
ALLOWED_COMMANDS: dict[str, dict[str, str]] = {
    # ── File navigation ───────────────────────────────
    "dir": {
        "category": "navigation",
        "description": "List directory contents",
        "usage": "dir [path] [/b] [/s] [/w]",
        "notes": "/b = bare format, /s = recursive, /w = wide format",
    },
    "ls": {
        "category": "navigation",
        "description": "List directory contents (Git Bash / Unix-style)",
        "usage": "ls [-la] [path]",
        "notes": "-l = long format, -a = show hidden files",
    },
    "cd": {
        "category": "navigation",
        "description": "Change current directory (for display only — cwd is sandbox-locked)",
        "usage": "cd [path]",
        "notes": "Working directory is always within sandbox root",
    },
    "pwd": {
        "category": "navigation",
        "description": "Print current working directory",
        "usage": "pwd",
        "notes": "Shows the sandbox working directory",
    },
    "tree": {
        "category": "navigation",
        "description": "Display directory tree structure",
        "usage": "tree [path] [/f] [/a]",
        "notes": "/f = show files, /a = ASCII characters",
    },

    # ── File reading ──────────────────────────────────
    "type": {
        "category": "file_read",
        "description": "Display contents of a text file",
        "usage": "type <filename>",
        "notes": "Windows equivalent of cat",
    },
    "cat": {
        "category": "file_read",
        "description": "Display file contents (Git Bash)",
        "usage": "cat <filename>",
        "notes": "Unix-style file display",
    },
    "head": {
        "category": "file_read",
        "description": "Show first lines of a file (Git Bash)",
        "usage": "head [-n N] <filename>",
        "notes": "-n N = show first N lines",
    },
    "tail": {
        "category": "file_read",
        "description": "Show last lines of a file (Git Bash)",
        "usage": "tail [-n N] <filename>",
        "notes": "-n N = show last N lines",
    },
    "more": {
        "category": "file_read",
        "description": "Display file contents page by page",
        "usage": "more <filename>",
        "notes": "Paginated output",
    },
    "find": {
        "category": "file_read",
        "description": "Search for text in files (Windows) or find files (Unix)",
        "usage": 'find "text" <filename>  OR  find <path> -name "pattern"',
        "notes": "Windows find searches content; Unix find searches filenames",
    },
    "findstr": {
        "category": "file_read",
        "description": "Search for strings in files (like grep)",
        "usage": 'findstr /s /i "pattern" *.txt',
        "notes": "/s = recursive, /i = case-insensitive",
    },
    "grep": {
        "category": "file_read",
        "description": "Search file contents with regex (Git Bash)",
        "usage": 'grep [-r] [-i] "pattern" <path>',
        "notes": "-r = recursive, -i = case-insensitive",
    },

    # ── File writing / creation ───────────────────────
    "echo": {
        "category": "file_write",
        "description": "Print text or write text to a file",
        "usage": "echo text > file.txt  OR  echo text >> file.txt",
        "notes": "> overwrites, >> appends",
    },
    "copy": {
        "category": "file_write",
        "description": "Copy files",
        "usage": "copy <source> <destination>",
        "notes": "Windows file copy",
    },
    "cp": {
        "category": "file_write",
        "description": "Copy files (Git Bash)",
        "usage": "cp [-r] <source> <destination>",
        "notes": "-r = recursive (for directories)",
    },
    "move": {
        "category": "file_write",
        "description": "Move or rename files",
        "usage": "move <source> <destination>",
        "notes": "Windows move/rename",
    },
    "mv": {
        "category": "file_write",
        "description": "Move or rename files (Git Bash)",
        "usage": "mv <source> <destination>",
        "notes": "Unix-style move/rename",
    },
    "mkdir": {
        "category": "file_write",
        "description": "Create a new directory",
        "usage": "mkdir <dirname>",
        "notes": "Creates directory inside sandbox",
    },
    "md": {
        "category": "file_write",
        "description": "Create a new directory (Windows alias)",
        "usage": "md <dirname>",
        "notes": "Same as mkdir",
    },
    "del": {
        "category": "file_write",
        "description": "Delete files",
        "usage": "del <filename>",
        "notes": "Windows file delete. Be careful.",
    },
    "rm": {
        "category": "file_write",
        "description": "Remove files (Git Bash)",
        "usage": "rm [-r] <path>",
        "notes": "-r = recursive. Be careful.",
    },
    "rmdir": {
        "category": "file_write",
        "description": "Remove empty directory",
        "usage": "rmdir <dirname>",
        "notes": "Directory must be empty",
    },
    "ren": {
        "category": "file_write",
        "description": "Rename a file",
        "usage": "ren <oldname> <newname>",
        "notes": "Windows rename",
    },
    "touch": {
        "category": "file_write",
        "description": "Create empty file or update timestamp (Git Bash)",
        "usage": "touch <filename>",
        "notes": "Creates file if it doesn't exist",
    },

    # ── Python execution ──────────────────────────────
    "python": {
        "category": "execution",
        "description": "Run a Python script or command",
        "usage": "python <script.py>  OR  python -c \"code\"",
        "notes": "Runs Python interpreter. Scripts must be inside sandbox.",
    },
    "py": {
        "category": "execution",
        "description": "Python launcher (Windows)",
        "usage": "py <script.py>  OR  py -3.10 <script.py>",
        "notes": "Windows Python launcher with version selection",
    },

    # ── Text processing ───────────────────────────────
    "sort": {
        "category": "text",
        "description": "Sort lines of text",
        "usage": "sort <filename>  OR  command | sort",
        "notes": "Sorts alphabetically by default",
    },
    "wc": {
        "category": "text",
        "description": "Count lines, words, characters (Git Bash)",
        "usage": "wc [-l] [-w] [-c] <filename>",
        "notes": "-l = lines, -w = words, -c = chars",
    },
    "diff": {
        "category": "text",
        "description": "Compare two files (Git Bash)",
        "usage": "diff <file1> <file2>",
        "notes": "Shows differences between files",
    },

    # ── System info (read-only, safe) ─────────────────
    "date": {
        "category": "info",
        "description": "Display current date/time",
        "usage": "date /t  (Windows)  OR  date (Unix)",
        "notes": "Read-only time display",
    },
    "whoami": {
        "category": "info",
        "description": "Display current username",
        "usage": "whoami",
        "notes": "Shows who is running the process",
    },
    "hostname": {
        "category": "info",
        "description": "Display computer name",
        "usage": "hostname",
        "notes": "Read-only system info",
    },
    "where": {
        "category": "info",
        "description": "Locate a program on PATH (Windows)",
        "usage": "where <program>",
        "notes": "Like Unix 'which'",
    },
    "which": {
        "category": "info",
        "description": "Locate a program on PATH (Git Bash)",
        "usage": "which <program>",
        "notes": "Shows full path to executable",
    },

    # ── Git (read operations primarily) ───────────────
    "git": {
        "category": "version_control",
        "description": "Git version control",
        "usage": "git status, git log, git diff, git add, git commit",
        "notes": "Full git available inside sandbox for project management",
    },
}

# ── Patterns that indicate escape attempts ────────────────────
ESCAPE_PATTERNS = [
    (re.compile(r"[;&|]"), "command chaining operators (;, &, |)"),
    (re.compile(r"`"), "backtick execution"),
    (re.compile(r"\$\("), "subshell execution $()"),
    (re.compile(r">\s*/dev/"), "redirection to device files"),
    (re.compile(r"\.\.[/\\]"), "directory traversal (..\\ or ../)"),
    (re.compile(r"//[a-zA-Z]"), "UNC-style network paths"),
    (re.compile(r"[A-Z]:\\", re.I), "absolute Windows paths"),
]


DESTRUCTIVE_COMMANDS = {"del", "rm", "rmdir"}


class CommandPolicy:
    """Validates commands against the security policy."""

    def __init__(self, mode: str = "allowlist"):
        """
        Args:
            mode: "allowlist" (strict, default) or "permissive" (blocklist only)
        """
        self.mode = mode
        self._base_allowed = set(ALLOWED_COMMANDS.keys())
        self._allowed = set(self._base_allowed)
        self._blocked = set(ALWAYS_BLOCKED)
        self._destructive = set(DESTRUCTIVE_COMMANDS)
        self._session_overrides: dict = {}

    def apply_session_overrides(self, overrides: dict) -> None:
        """Apply per-session command policy overrides.

        Args:
            overrides: {"allow_add": [...], "allow_remove": [...]}
                       allow_add: extra commands to permit (cannot override ALWAYS_BLOCKED)
                       allow_remove: global-allowed commands to block for this session
        """
        # Reset to base
        self._allowed = set(self._base_allowed)
        self._session_overrides = overrides

        for cmd in overrides.get("allow_add", []):
            cmd_lower = cmd.lower().strip()
            # Never allow ALWAYS_BLOCKED commands regardless of session policy
            if cmd_lower not in self._blocked:
                self._allowed.add(cmd_lower)

        for cmd in overrides.get("allow_remove", []):
            cmd_lower = cmd.lower().strip()
            self._allowed.discard(cmd_lower)

        log.info("Session policy applied: +%s -%s",
                 overrides.get("allow_add", []),
                 overrides.get("allow_remove", []))

    def clear_session_overrides(self) -> None:
        """Reset to default global policy."""
        self._allowed = set(self._base_allowed)
        self._session_overrides = {}
        log.info("Session policy cleared — using global defaults")

    def validate(self, command: str) -> tuple[bool, str]:
        """Check if a command is permitted.

        Returns:
            (allowed: bool, reason: str)
        """
        stripped = command.strip()
        if not stripped:
            return False, "Empty command"

        # Extract the base command (first word, lowercase)
        parts = stripped.split()
        base_cmd = parts[0].lower()

        # Strip .exe suffix if present
        if base_cmd.endswith(".exe"):
            base_cmd = base_cmd[:-4]

        # Always-blocked check
        if base_cmd in self._blocked:
            return False, f"Command '{base_cmd}' is blocked (security policy)"

        # Escape pattern check
        for pattern, label in ESCAPE_PATTERNS:
            if pattern.search(stripped):
                return False, f"Command contains blocked pattern: {label}"

        # Allowlist check (strict mode)
        if self.mode == "allowlist" and base_cmd not in self._allowed:
            return False, (
                f"Command '{base_cmd}' is not in the allowed commands list. "
                f"Allowed: {', '.join(sorted(self._allowed))}"
            )

        return True, "OK"

    def is_destructive(self, command: str) -> bool:
        """Check if a command is destructive (del, rm, rmdir)."""
        stripped = command.strip()
        if not stripped:
            return False
        base_cmd = stripped.split()[0].lower()
        if base_cmd.endswith(".exe"):
            base_cmd = base_cmd[:-4]
        return base_cmd in self._destructive

    def get_allowed_commands(self) -> dict[str, dict[str, str]]:
        """Return the full allowed command reference."""
        return dict(ALLOWED_COMMANDS)

    def get_command_reference(self) -> str:
        """Format the allowed commands as a readable reference for the agent."""
        lines = []
        categories: dict[str, list[str]] = {}

        for cmd, info in sorted(ALLOWED_COMMANDS.items()):
            cat = info["category"]
            categories.setdefault(cat, []).append(cmd)

        category_labels = {
            "navigation": "Directory Navigation",
            "file_read": "Reading Files",
            "file_write": "Writing & Managing Files",
            "execution": "Running Scripts",
            "text": "Text Processing",
            "info": "System Information",
            "version_control": "Version Control",
        }

        for cat, cmds in categories.items():
            label = category_labels.get(cat, cat.title())
            lines.append(f"\n### {label}")
            for cmd in sorted(cmds):
                info = ALLOWED_COMMANDS[cmd]
                lines.append(f"- `{info['usage']}` — {info['description']}")
                if info.get("notes"):
                    lines.append(f"  ({info['notes']})")

        return "\n".join(lines)
