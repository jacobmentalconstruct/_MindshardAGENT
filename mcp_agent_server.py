"""
MindshardAGENT MCP Server — entry point.

Starts the headless MCP stdio server that exposes the MindshardAGENT engine
for agent-to-agent use by Claude or any other MCP-capable host.

Usage:
  python mcp_agent_server.py

To wire into Claude Desktop or another MCP host, add this to your MCP config:
  {
    "mcpServers": {
      "mindshard": {
        "command": "python",
        "args": ["<absolute-path-to>\\mcp_agent_server.py"]
      }
    }
  }
"""
from src.mcp.server import main
import sys

if __name__ == "__main__":
    raise SystemExit(main())
