"""Persisted preferences of the local MCP server.

Stored in ``~/Documents/LMT-EYE_settings/mcp_settings.json``, next to the
analysis settings, but in a separate file: this is an application setting,
not an analysis parameter, so it must not end up in analysis reports.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

SETTINGS_DIR = Path.home() / "documents" / "LMT-EYE_settings"
SETTINGS_FILE = SETTINGS_DIR / "mcp_settings.json"

DEFAULT_PORT = 8765


@dataclass
class McpSettings:
    enabled: bool = False
    port: int = DEFAULT_PORT
    register_claude_code: bool = True
    """Register the server in Claude Code automatically when it starts."""

    @staticmethod
    def exists(file_path: Path = SETTINGS_FILE) -> bool:
        """True once the user has answered the activation question."""
        return file_path.is_file()

    @classmethod
    def load(cls, file_path: Path = SETTINGS_FILE) -> "McpSettings":
        if not file_path.is_file():
            return cls()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                enabled=bool(data.get("enabled", False)),
                port=int(data.get("port", DEFAULT_PORT)),
                register_claude_code=bool(
                    data.get("register_claude_code", True)
                ),
            )
        except Exception as e:
            logging.error(f"Failed to load MCP settings ({file_path}): {e}")
            return cls()

    def save(self, file_path: Path = SETTINGS_FILE) -> None:
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save MCP settings ({file_path}): {e}")
