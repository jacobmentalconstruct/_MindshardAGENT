# SDK

This folder contains thin in-process adapters for agents that want to use the manifold suite without going through MCP calls.

## Current SDK Surface

- `EvidencePackage`

## Import Pattern

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".../.dev-tools/_manifold-mcp").resolve()))
from sdk.evidence_package import EvidencePackage
```

## Why This Exists

- some agents need direct object APIs instead of tool calls
- the package still remains fully usable through MCP
- the SDK keeps the evidence-bag contract stable across agent ecosystems

## Consumer Rule

Use this SDK from the vendored `_manifold-mcp` folder itself.

- good: import `sdk.evidence_package` from `.dev-tools/_manifold-mcp`
- avoid: copying `EvidencePackage` into an app-local module unless you are deliberately forking the package
