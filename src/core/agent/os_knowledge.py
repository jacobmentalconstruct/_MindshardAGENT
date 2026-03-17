"""OS knowledge module — teaches the agent about operating system fundamentals.

This gets injected into the system prompt so the agent understands:
- What a filesystem is and how it works
- What directories and files are
- What a command prompt / terminal / shell is
- How to navigate and manipulate files
- What the available commands do and how to use them
- Common patterns for accomplishing tasks

This is essential for small models (2B-4B) that may not have strong
implicit OS knowledge.
"""


OS_FUNDAMENTALS = """
## Operating System Fundamentals

You are running commands on a Windows computer. Here is what you need to know:

### What is a Filesystem?
A filesystem is how a computer organizes stored data. Think of it like a filing cabinet:
- **Drives** are the cabinets (C:, D:, etc.)
- **Directories (folders)** are the drawers and dividers inside
- **Files** are the individual documents stored in folders
- Every file has a **path** — its full address, like `C:\\Users\\jacob\\Documents\\myfile.txt`

### What is a Directory?
A directory (also called a "folder") is a container that holds files and other directories.
- Directories can be nested inside each other, creating a tree structure
- The **root** of a drive is the top level: `C:\\`
- A **subdirectory** is a directory inside another directory
- `.` means "the current directory"
- `..` means "the parent directory" (one level up)

### What is a Terminal / Command Prompt?
A terminal (or "command prompt" or "shell") is a text interface where you type commands to interact with the computer. Instead of clicking with a mouse, you type instructions.
- You type a command and press Enter
- The computer executes it and shows the output
- You are working inside a **current directory** (your location in the filesystem)

### How Paths Work
- **Absolute path**: Full address from the drive root: `C:\\Users\\jacob\\sandbox\\myfile.txt`
- **Relative path**: Address relative to where you are now: `myfile.txt` or `subfolder\\data.csv`
- **Path separator**: Windows uses `\\` but also accepts `/`
- **File extension**: The part after the last dot tells you the file type: `.txt`, `.py`, `.json`

### YOUR Sandbox
You are confined to a sandbox directory. This is your safe workspace:
- You can only read, write, and execute commands INSIDE the sandbox
- You cannot access files outside the sandbox
- If you try to escape the sandbox, the command will be blocked
- The sandbox has standard subdirectories:
  - `_tools/` — where you can create new tool scripts
  - `_sessions/` — saved conversation data
  - `_outputs/` — files you generate
  - `_logs/` — log files

### Common Task Patterns

**See what's in a directory:**
Use cli_in_sandbox with: `dir`

**See the full tree of a directory:**
Use cli_in_sandbox with: `tree /f`

**Create a file (ALWAYS use the write_file tool for this!):**
Use the write_file tool — NOT echo, NOT python -c. The write_file tool handles multi-line content, special characters, and quoting automatically.

**Read a file (ALWAYS use the read_file tool for this!):**
Use the read_file tool — NOT type, NOT cat. The read_file tool works reliably on all platforms.

**Create a directory:**
Use cli_in_sandbox with: `mkdir my_new_folder`

**Copy a file:**
Use cli_in_sandbox with: `copy source.txt destination.txt`

**Move/rename a file:**
Use cli_in_sandbox with: `move oldname.txt newname.txt`

**Delete a file:**
Use cli_in_sandbox with: `del unwanted.txt`

**Search for text inside files:**
Use cli_in_sandbox with: `findstr /s /i "search_term" *.txt`

**Run a Python script:**
Use cli_in_sandbox with: `python myscript.py`

**Create and run a Python script (two steps):**
Step 1 — use write_file to create the script
Step 2 — use cli_in_sandbox with: `python myscript.py`
"""


DOCKER_FUNDAMENTALS = """
## Operating System Fundamentals

You are running commands inside a Linux container (Docker). Here is what you need to know:

### Your Environment
- **Shell**: bash
- **OS**: Debian Linux (slim)
- **Python**: python3 / python (both work)
- **Package manager**: pip is available (use `pip install <package>`)
- **Working directory**: /sandbox

### Filesystem
- Directories use `/` as separator: `/sandbox/myfile.txt`
- `.` means "the current directory"
- `..` means "the parent directory"
- Everything is inside `/sandbox` — your workspace

### YOUR Sandbox
You are inside a container with /sandbox as your workspace:
- The sandbox has standard subdirectories:
  - `_tools/` — where you can create new tool scripts
  - `_sessions/` — saved conversation data
  - `_outputs/` — files you generate
  - `_logs/` — log files

### Common Task Patterns

**See what's in a directory:**
Use cli_in_sandbox with: `ls -la`

**See the full tree of a directory:**
Use cli_in_sandbox with: `tree`

**Create a file (ALWAYS use the write_file tool for this!):**
Use the write_file tool — NOT echo, NOT cat, NOT python -c. The write_file tool handles multi-line content, special characters, and quoting automatically.

**Read a file (ALWAYS use the read_file tool for this!):**
Use the read_file tool — NOT cat, NOT less, NOT head. The read_file tool works reliably.

**Create a directory:**
Use cli_in_sandbox with: `mkdir -p my_new_folder`

**Copy a file:**
Use cli_in_sandbox with: `cp source.txt destination.txt`

**Move/rename a file:**
Use cli_in_sandbox with: `mv oldname.txt newname.txt`

**Delete a file:**
Use cli_in_sandbox with: `rm unwanted.txt`

**Search for text inside files:**
Use cli_in_sandbox with: `grep -r "search_term" .`

**Install a Python package:**
Use cli_in_sandbox with: `pip install package_name`

**Run a Python script:**
Use cli_in_sandbox with: `python myscript.py`

**Create and run a Python script (two steps):**
Step 1 — use write_file to create the script
Step 2 — use cli_in_sandbox with: `python myscript.py`
"""


def get_os_knowledge(docker_mode: bool = False) -> str:
    """Return the OS fundamentals knowledge block."""
    return DOCKER_FUNDAMENTALS if docker_mode else OS_FUNDAMENTALS


def get_command_teaching(command_reference: str, docker_mode: bool = False) -> str:
    """Combine OS fundamentals with command reference."""
    fundamentals = DOCKER_FUNDAMENTALS if docker_mode else OS_FUNDAMENTALS

    if docker_mode:
        return f"""{fundamentals}

## Command Environment
You are inside a Docker container with full bash access.
Most standard Linux commands are available (ls, cp, mv, rm, grep, find, etc.).
Python 3 and pip are available for package installation and script execution.
Git is available for version control.

### Safety Rules
- You are inside a container — the container IS the boundary
- You cannot access the host system
- When in doubt, use `ls` to look around and `read_file` to read files
"""
    else:
        return f"""{fundamentals}

## Allowed Commands Reference

You may ONLY use the following commands. Any other command will be blocked.
{command_reference}

### Security Rules
- You CANNOT use PowerShell, cmd, curl, wget, pip, npm, or other system tools
- You CANNOT chain commands with ; & | operators
- You CANNOT use backticks or $() for subshell execution
- You CANNOT use absolute paths outside the sandbox
- You CANNOT use .. to escape the sandbox directory
- If a command is blocked, try a different approach using allowed commands
- When in doubt, use `dir` to look around and `read_file` to read files
"""
