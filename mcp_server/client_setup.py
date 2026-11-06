"""Automatic registration of the LMT-EYE server in MCP clients.

Today: Claude Code. LMT-EYE runs the official command

    claude mcp add --transport http --scope user lmt-eye <url>

so the user does not have to type it. The registration is "user" scope:
the server is available in every folder where Claude Code is used.

Presence is checked by READING Claude Code's config file (never written by
LMT-EYE). Writing always goes through the ``claude`` command, so the config
file format stays Claude Code's business.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "lmt-eye"


def find_claude_cli() -> str | None:
    """Path of the ``claude`` command, or None if Claude Code is not
    installed. Also looks in the usual install folders, in case they are
    not in the PATH of LMT-EYE (e.g. Claude Code installed after the
    terminal that launched LMT-EYE was opened)."""
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "claude.exe",  # native installer, Windows
        home / ".local" / "bin" / "claude",  # native installer, macOS/Linux
        home / ".claude" / "local" / "claude",  # older local install
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "npm" / "claude.cmd")  # npm, Windows
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _claude_config_file() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / ".claude.json"
    return Path.home() / ".claude.json"


def registered_url() -> str | None:
    """URL under which LMT-EYE is registered in Claude Code (user scope),
    or None if it is not registered."""
    try:
        with open(_claude_config_file(), "r", encoding="utf-8") as f:
            config = json.load(f)
        server = config.get("mcpServers", {}).get(SERVER_NAME)
        return server.get("url") if isinstance(server, dict) else None
    except (OSError, ValueError):
        return None


def _run_claude(cli: str, *args: str) -> subprocess.CompletedProcess:
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW  # no console window flashing
    return subprocess.run(
        [cli, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        creationflags=flags,
    )


def register_in_claude_code(url: str) -> tuple[bool, str]:
    """Register (or update) the LMT-EYE server in Claude Code.
    Return (success, message for the user)."""
    current = registered_url()
    if current == url:
        return True, "LMT-EYE is registered in Claude Code."

    cli = find_claude_cli()
    if cli is None:
        return False, (
            "Claude Code is not installed (command 'claude' not found). "
            "Install it, then use Menu > Register in Claude Code."
        )

    try:
        if current is not None:  # registered with another URL (port change)
            _run_claude(cli, "mcp", "remove", SERVER_NAME, "-s", "user")
        result = _run_claude(
            cli, "mcp", "add", "--transport", "http", "--scope", "user",
            SERVER_NAME, url,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Could not run Claude Code: {e}"

    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip()
        return False, f"Claude Code registration failed: {output}"

    logging.info(f"MCP server registered in Claude Code ({url}).")
    return True, (
        "LMT-EYE has been registered in Claude Code. Restart any open "
        "Claude Code session to use it."
    )
