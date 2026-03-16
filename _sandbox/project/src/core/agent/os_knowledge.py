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
```
dir
```

**See the full tree of a directory:**
```
tree /f
```

**Read a file:**
```
type filename.txt
```

**Create a new file with content:**
```
echo Hello, this is my file content > newfile.txt
```

**Append to a file:**
```
echo More content >> existingfile.txt
```

**Create a directory:**
```
mkdir my_new_folder
```

**Copy a file:**
```
copy source.txt destination.txt
```

**Move/rename a file:**
```
move oldname.txt newname.txt
```

**Delete a file:**
```
del unwanted.txt
```

**Search for text inside files:**
```
findstr /s /i "search_term" *.txt
```

**Run a Python script:**
```
python myscript.py
```

**Write a Python script and run it:**
```
echo print("Hello from Python!") > hello.py
python hello.py
```
"""


def get_os_knowledge() -> str:
    """Return the full OS fundamentals knowledge block."""
    return OS_FUNDAMENTALS


def get_command_teaching(command_reference: str) -> str:
    """Combine OS fundamentals with the specific allowed command reference."""
    return f"""{OS_FUNDAMENTALS}

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
- When in doubt, use `dir` to look around and `type` to read files
"""
