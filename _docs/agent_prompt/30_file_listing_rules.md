## File Listing Rules
- When the user asks to list or explore project files, exclude `.mindshard/` internals by default unless they explicitly ask for agent-managed files.
- Prefer grouped, high-signal listings over flat noisy dumps when the workspace is large.
- Surface the project structure first, then only mention internal sidecar paths if they are directly relevant to the task.
- If the user needs a complete inventory, make it explicit when internal folders are omitted or included.
