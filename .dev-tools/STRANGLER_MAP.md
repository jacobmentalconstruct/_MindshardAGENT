# Strangler Map

## Generalized Replacements

- `.dev-tools/analyze_timeline_schema.py`
  - replaced by `.final-tools/tools/data_shape_inspector.py`
- `.dev-tools/analyze_kml_schema.py`
  - replaced by `.final-tools/tools/data_shape_inspector.py`
- `.dev-tools/sql_schema_mapper.py`
  - folded into `.final-tools/tools/data_shape_inspector.py`
- `.dev-tools/tokenizing_patcher_with_cli.py`
  - replaced by `.final-tools/tools/structured_patcher.py`
- `.dev-tools/scan_blocking_calls.py`
  - replaced by `.final-tools/tools/python_risk_scan.py`

## Left Behind On Purpose

- `.dev-tools/dev_tools_hub.py`
  - UI-only
- `.dev-tools/cleanup_root_microservices_contract.py`
  - microservice-specific
- `.dev-tools/organize_library_layers.py`
  - architecture-specific

## New Agent-First Capability

- `.final-tools/tools/workspace_audit.py`
  - fast folder orientation for coding and data-curation work
- `.final-tools/mcp_server.py`
  - consistent MCP exposure for all final tools
