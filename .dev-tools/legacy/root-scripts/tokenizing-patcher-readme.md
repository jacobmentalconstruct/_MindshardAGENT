# Tokenizing Patcher CLI

A patching utility for applying structured JSON patch objects to source files.

This tool is designed for deterministic, auditable patching of text files using anchored hunks instead of whole-file regeneration. It supports both single-file and multi-file patch manifests.

---

## What it is for

`tokenizing_patcher_with_cli.py` applies structured patch objects to files on disk.

It is useful when you want:

- small, controlled edits instead of replacing entire files
- a patch format another agent can generate mechanically
- dry-run validation before writing changes
- multi-file patch execution from a single manifest
- machine-readable introspection of command and schema expectations

---

## Core concepts

The patcher works by applying one or more **hunks**.

A hunk contains:

- a human-readable description
- a `search_block` that must be found in the target text
- a `replace_block` that replaces the matched text
- an optional indentation behavior flag

The engine attempts to patch text in a careful way:

1. strict search first
2. whitespace-tolerant / floating fallback if needed
3. ambiguity and collision checks where possible

This makes it more reliable than naive global find/replace while still remaining simple and inspectable.

---

## Supported patch modes

There are two main ways to use the patcher.

### 1. Single patch object applied to one or more target files

You provide:

- one patch JSON file containing top-level `hunks`
- one or more file paths on the command line

This is useful when the exact same patch must be attempted against multiple files.

### 2. Multi-file patch manifest

You provide:

- one patch JSON file containing top-level `files`
- each file entry contains its own `path` and `hunks`

This is useful when many files each need their own targeted hunks.

---

## Command overview

### Show help

```bash
python tokenizing_patcher_with_cli.py --help
```

### Show schema

```bash
python tokenizing_patcher_with_cli.py --schema
```

### Show command reference

```bash
python tokenizing_patcher_with_cli.py --command
python tokenizing_patcher_with_cli.py --command apply
python tokenizing_patcher_with_cli.py --command validate
```

### Emit schema/command info as JSON

```bash
python tokenizing_patcher_with_cli.py --schema --json
python tokenizing_patcher_with_cli.py --command apply --json
```

### Validate a patch against one or more files

```bash
python tokenizing_patcher_with_cli.py validate patch.json file1.py
python tokenizing_patcher_with_cli.py validate patch.json file1.py file2.py file3.py
```

### Apply a patch to one or more files

```bash
python tokenizing_patcher_with_cli.py apply patch.json file1.py
python tokenizing_patcher_with_cli.py apply patch.json file1.py file2.py
```

### Dry-run a patch

```bash
python tokenizing_patcher_with_cli.py apply patch.json file1.py --dry-run
```

### Apply a multi-file manifest

```bash
python tokenizing_patcher_with_cli.py apply patch_manifest.json
```

### Validate a multi-file manifest

```bash
python tokenizing_patcher_with_cli.py validate patch_manifest.json
```

### Use a root directory for relative paths in a manifest

```bash
python tokenizing_patcher_with_cli.py apply patch_manifest.json --root-dir /path/to/project
```

### Write outputs to a separate directory instead of overwriting originals

```bash
python tokenizing_patcher_with_cli.py apply patch_manifest.json --root-dir /path/to/project --output-dir /tmp/patched_out
```

### Create backups when writing in place

```bash
python tokenizing_patcher_with_cli.py apply patch_manifest.json --backup
```

---

## Patch schema: single patch object

Use this shape when the patch JSON will be applied to files named on the command line.

```json
{
  "hunks": [
    {
      "description": "Add import",
      "search_block": "import json\n",
      "replace_block": "import json\nfrom collections import deque\n",
      "use_patch_indent": false
    }
  ]
}
```

### Field meanings

#### `hunks`
Required. A list of patch hunk objects.

#### `description`
Required. Human-readable explanation of what the hunk is meant to do.

#### `search_block`
Required. Exact or near-exact text block to locate in the target file.

#### `replace_block`
Required. Text that replaces the matched block.

#### `use_patch_indent`
Optional boolean. When `false` (default), the patcher rebases replacement indentation onto the matched block while preserving relative nested indentation. When `true`, replacement indentation is used exactly as written in the patch.

If a hunk omits this field inside a multi-file manifest, the patcher now falls back to `default_use_patch_indent` from the file entry first, then the manifest root, and finally `false`.

---

## Patch schema: multi-file manifest

Use this shape when the patch JSON contains its own file paths.

```json
{
  "default_use_patch_indent": true,
  "files": [
    {
      "path": "src/module_a.py",
      "default_use_patch_indent": true,
      "hunks": [
        {
          "description": "Add import",
          "search_block": "import json\n",
          "replace_block": "import json\nfrom collections import deque\n"
        }
      ]
    },
    {
      "path": "src/module_b.py",
      "hunks": [
        {
          "description": "Rename variable",
          "search_block": "old_name = 1\n",
          "replace_block": "new_name = 1\n",
          "use_patch_indent": false
        }
      ]
    }
  ]
}
```

### Manifest field meanings

#### `default_use_patch_indent`
Optional boolean at the manifest root. Provides the default indentation policy for every file entry and hunk that does not set `use_patch_indent` explicitly.

This is useful for Python-heavy multi-file transforms where preserving literal patch indentation is safer than rebasing each hunk individually.

#### `files`
Required. List of file patch entries.

#### `path`
Required. Target file path such as `src/module_a.py`.

This may be:

- absolute
- relative to the current working directory
- relative to `--root-dir` if provided

#### `default_use_patch_indent`
Optional boolean at the file-entry level. Provides the default indentation policy for hunks in that file entry when a hunk omits `use_patch_indent`.

#### `hunks`
Required. List of hunk objects for that file.

---

## Behavioral rules

### If target files are supplied on the command line

The patch file must contain top-level:

```json
{ "hunks": [...] }
```

### If no target files are supplied

The patch file must contain top-level:

```json
{ "files": [...] }
```

This split avoids ambiguity.

---

## Exit behavior and workflow expectations

Typical workflow:

1. generate patch JSON
2. run `validate`
3. run `apply --dry-run`
4. inspect results
5. run `apply` for real
6. optionally back up originals or write to a separate output directory

Recommended operational habit:

- use `validate` first for every generated patch
- use `--backup` when patching in place
- use `--output-dir` if you want a staging area instead of directly modifying source files

---

## Example workflows

### Example 1: patch one file

```bash
python tokenizing_patcher_with_cli.py validate add_import_patch.json src/tool.py
python tokenizing_patcher_with_cli.py apply add_import_patch.json src/tool.py --backup
```

### Example 2: patch many files with the same patch

```bash
python tokenizing_patcher_with_cli.py validate rename_patch.json src/a.py src/b.py src/c.py
python tokenizing_patcher_with_cli.py apply rename_patch.json src/a.py src/b.py src/c.py --dry-run
```

### Example 3: patch many files from a manifest

```bash
python tokenizing_patcher_with_cli.py validate migration_manifest.json --root-dir /repo/project
python tokenizing_patcher_with_cli.py apply migration_manifest.json --root-dir /repo/project --backup
```

### Example 4: stage patched outputs instead of overwriting originals

```bash
python tokenizing_patcher_with_cli.py apply migration_manifest.json --root-dir /repo/project --output-dir /tmp/migration_stage
```

---

## Failure modes to expect

A patch may fail if:

- `search_block` is not found
- multiple possible matches create ambiguity
- earlier hunks modify text in a way that prevents later hunks from matching
- the wrong file path is targeted
- the patch was generated against an outdated file version

When a patch fails, inspect:

- the exact file contents
- line endings / indentation differences
- whether the source drifted since the patch was generated
- whether the search block is too broad or too brittle

---

## Guidance for agent-generated patches

If another agent is generating patches for this tool, it should follow these principles:

- make hunks small and anchored
- avoid giant whole-file replacement blocks
- ensure `search_block` includes enough local context to be unique
- avoid overlapping hunks unless the sequence is intentionally dependent
- prefer deterministic blocks over fuzzy natural-language descriptions
- validate generated patches before applying them automatically

Good patch generation tends to use:

- local imports
- exact function signatures
- short but distinctive code neighborhoods
- one conceptual edit per hunk where possible

---

## Suggested integration with migration tooling

This patcher is a good fit for a migration engine that wants to:

- inspect files
- generate patch objects instead of full replacement files
- dry-run and validate changes before writing
- stage outputs for human review
- apply multi-file migrations from a single manifest

A migration runner can integrate it in either of two ways:

1. import the patching functions directly
2. shell out to the CLI and consume JSON/text results

Direct import is usually cleaner for orchestration.

---

## File naming suggestions

Example patch filenames:

- `rename_service_imports.patch.json`
- `phase_ui_migration_manifest.json`
- `adapter_split_pass_01.json`

Example readme/tool pairing:

- `tokenizing_patcher_with_cli.py`
- `tokenizing-patcher-readme.md`

---

## In plain terms

This tool gives you a controlled middle ground between:

- brittle search-and-replace scripts
- and over-aggressive whole-file regeneration

It is built for structured, inspectable text transformation.
