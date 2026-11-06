"""
Local MCP (Model Context Protocol) server for LMT-EYE.

The server runs inside the LMT-EYE process, in a background thread, and
listens on http://127.0.0.1:<port>/mcp (Streamable HTTP transport). MCP
clients such as Claude Code or Claude Desktop connect to that URL.

Everything MCP-related lives in this package:
    - settings.py   : persisted on/off preference and port
    - state.py      : data shared between the Qt interface and the server
    - tracker.py    : detection of connected MCP clients
    - tools.py      : MCP tools exposed to clients
    - controller.py : start / stop / status of the server
    - client_setup.py : automatic registration in Claude Code

Note: this folder is named ``mcp_server`` and not ``mcp`` on purpose: a
folder named ``mcp`` at the project root would hide the official MCP SDK
(the ``mcp`` package) when importing it.
"""

from mcp_server.controller import McpServerController, McpStatus, get_controller
from mcp_server.settings import McpSettings
from mcp_server.state import app_state

__all__ = [
    "McpServerController",
    "McpSettings",
    "McpStatus",
    "app_state",
    "get_controller",
]
