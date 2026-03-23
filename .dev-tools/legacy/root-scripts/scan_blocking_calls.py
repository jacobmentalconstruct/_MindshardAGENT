"""scan_blocking_calls.py — AST scanner for blocking calls that can freeze a Tkinter UI.

Scans all Python files under a source directory and reports any calls to
subprocess.run/call/check_output/Popen, time.sleep, and similar blocking ops.

Usage:
    python .dev-tools/scan_blocking_calls.py [src_dir]

Output shows file:line  call() for every hit, sorted by file.
Useful for auditing which modules might block the main thread.
"""

import ast
import sys
from pathlib import Path


BLOCKING_DOTTED = {
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("subprocess", "Popen"),
    ("time", "sleep"),
    ("os", "system"),
}

BLOCKING_NAMES = {"urlopen", "sleep"}


def scan(src_dir: Path) -> list[tuple[str, int, str]]:
    results = []
    for py in sorted(src_dir.rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"PARSE ERROR {py}: {exc}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                pair = (func.value.id, func.attr)
                if pair in BLOCKING_DOTTED:
                    results.append((str(py), node.lineno, f"{func.value.id}.{func.attr}()"))
            elif isinstance(func, ast.Name) and func.id in BLOCKING_NAMES:
                results.append((str(py), node.lineno, f"{func.id}()"))
    return results


def main():
    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("src")
    if not src_dir.exists():
        print(f"Directory not found: {src_dir}", file=sys.stderr)
        sys.exit(1)

    results = scan(src_dir)
    if not results:
        print("No blocking calls found.")
        return

    print(f"Found {len(results)} blocking call(s) in {src_dir}:\n")
    for filepath, lineno, call in results:
        print(f"  {filepath}:{lineno}  {call}")


if __name__ == "__main__":
    main()
