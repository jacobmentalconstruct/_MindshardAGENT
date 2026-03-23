# Vending And Archiving

This folder is meant to be portable.

## Intended Use

You should be able to:

- zip the folder
- archive it
- copy it into a new project
- unzip it later
- run a self-test
- start extending it again

## Recommended Workflow

1. Keep the folder together as one unit.
2. Copy or unzip it into a new project root.
3. Run the self-test:

```powershell
python .final-tools\smoke_test.py
```

4. Run a quick inventory:

```powershell
python .final-tools\tools\workspace_audit.py run --input-json "{\"root\": \".\"}"
```

## Portability Rules

- The toolkit should rely only on the Python standard library unless there is a very good reason otherwise.
- Avoid absolute paths in source files and docs.
- Keep generated files in `artifacts/`, not mixed into tool code.
- Keep raw incoming scripts in `drop-bin/` until they are normalized.
- Keep machine-specific caches out of the archive.

## Renaming The Folder

The code is written to resolve imports relative to the file locations, so the folder can be renamed.

That said, keeping the same folder name across projects is simpler because:

- example commands remain accurate
- habits stay consistent
- vending instructions stay stable

## Before Creating A Zip

- Run `python .final-tools\smoke_test.py`
- Remove generated artifacts you do not want archived
- Make sure `__pycache__` folders are gone
