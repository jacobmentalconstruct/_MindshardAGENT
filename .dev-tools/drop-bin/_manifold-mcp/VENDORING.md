# Vendoring

This folder is designed to be copied or zipped as a standalone tool project.

## What To Vendor

Vendor the whole `_manifold-mcp` folder, not individual scripts.

Required contents:

- `tools/`
- `lib/`
- `sdk/`
- `common.py`
- `mcp_server.py`
- `tool_manifest.json`
- `README.md`
- `CONTRACT.md`
- `smoke_test.py`

Optional but recommended:

- `jobs/`
- `templates/`
- `ROADMAP.md`
- `drop-bin/`

Runtime output only:

- `artifacts/`

You may ship an empty `artifacts/` folder or let it be created on first use.

## Why Whole-Folder Vendoring Matters

- the MCP server imports local tools directly
- the SDK imports local library modules directly
- the package contract is documented in the root files
- keeping the folder intact avoids path drift across agent ecosystems

## Agent Use Modes

### MCP Mode

Run:

```powershell
python _manifold-mcp\mcp_server.py
```

Expose this folder as a stdio MCP server to any agent that can call MCP tools.

### SDK Mode

Use when an agent needs a thin object API instead of tool calls.

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".../.dev-tools/_manifold-mcp").resolve()))
from sdk.evidence_package import EvidencePackage
```

## Consumer Rule

Consumer applications should depend on this package from `.dev-tools`.

Do this:

- import `sdk.EvidencePackage`
- or call the MCP server

Avoid this:

- copying `lib/` internals into app code
- moving the thin adapter into an app-local module
- forking the reversible data contract in consumers

## Verification After Vendoring

Run:

```powershell
python _manifold-mcp\smoke_test.py
```

If this passes, the vendored package is mechanically intact.
