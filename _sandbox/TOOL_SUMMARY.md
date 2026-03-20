# Available Tools Summary

## Working Tools (3 tools)

### 1. cli_in_sandbox
- **Purpose**: Execute shell commands within the sandbox environment
- **Parameters**:
  - `command`: The shell command to execute (required)
  - `cwd`: Working directory relative to sandbox root (optional)
- **Returns**: stdout, stderr, exit code
- **Capabilities**: ls, cat, cp, mv, rm, grep, find, python, pip, git, etc.

### 2. write_file
- **Purpose**: Create or overwrite files within the sandbox
- **Parameters**:
  - `path`: File path relative to sandbox root (required)
  - `content`: The text content to write (required)
  - `mode`: 'write' (create/overwrite) or 'append' (default: 'write')
- **Returns**: Confirmation with file size and path
- **Note**: Handles multi-line content and special characters automatically

### 3. read_file
- **Purpose**: Read file contents within the sandbox
- **Parameters**:
  - `path`: File path relative to sandbox root (required)
- **Returns**: Full text content of the file
- **Note**: Works reliably on all operating systems

## _PyOhSYMLANG Purpose

_PyOhSYMLANG appears to be an **agent framework** for building and running AI agents in a sandbox environment. Based on the file structure and logs:

### Key Components:
- **Sandbox System**: Docker-based isolated environment for agent development
- **Session Management**: SQLite database (_sessions/sessions.db) for persisting agent conversations
- **Action Logging**: JSONL files for tracking agent actions (_logs/action_journal.jsonl)
- **Audit Trail**: Security/audit logging (_logs/audit.jsonl)
- **Tool System**: Modular tool registry for agent capabilities
- **Builder Widget**: UI component for building agents (_tools/builder_widget/)

### Typical Use Cases:
1. **Agent Development**: Build and test AI agents in isolated containers
2. **Tool Creation**: Create custom tools for agents (_tools/ directory)
3. **Session Persistence**: Save and restore agent conversation states
4. **Logging & Debugging**: Track agent actions and debug issues
5. **Sandbox Testing**: Safely test agent behaviors in isolated environments

## Environment Details
- **OS**: Linux (Debian slim) inside Docker container
- **Python**: 3.10.20
- **Shell**: bash
- **Working Directory**: /sandbox
- **Root User**: Container runs as root

## Directory Structure
- `/sandbox/` - Root workspace
- `/sandbox/_tools/` - Tool scripts and builders
- `/sandbox/_sessions/` - Session state (SQLite DB)
- `/sandbox/_outputs/` - Generated files
- `/sandbox/_logs/` - Logs and audit trails
