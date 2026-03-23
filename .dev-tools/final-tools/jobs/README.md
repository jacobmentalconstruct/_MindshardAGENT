# Jobs Folder

This folder holds example or reusable JSON job files for tool execution.

Use this pattern:

```powershell
python .final-tools\tools\workspace_audit.py run --input-file .final-tools\jobs\examples\workspace_audit.json
```

The goal is to make tool use mechanical and automation-friendly.

Tkinter-oriented example jobs belong here too, so repeated UI audits can be checked into a project and rerun.
