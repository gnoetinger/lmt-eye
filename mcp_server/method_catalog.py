"""Read-only discovery of the bundled example and its replayable source."""

import hashlib
import json
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError


def register_catalog(server):
    folder = Path(__file__).resolve().parents[1] / "res" / "methods"

    @server.tool()
    def list_analysis_methods() -> list[dict[str, Any]]:
        """Discover available analysis methods by ID, version and research question."""
        entry = json.loads((folder / "animal_bouts.json").read_text(encoding="utf-8"))
        return [{key: entry[key] for key in ("id", "version", "question")}]

    @server.tool()
    def get_analysis_method(method_id: str, version: str) -> dict[str, Any]:
        """Get one method's definition, Python source, SHA-256 and validation fixture.

        Hash the UTF-8 bytes of the returned source string to verify a download.
        """
        entry = json.loads((folder / "animal_bouts.json").read_text(encoding="utf-8"))
        if (method_id, version) != (entry["id"], entry["version"]):
            raise ToolError(f"Unknown analysis method or version: {method_id} {version}")
        source = (folder / "animal_bouts.py").read_text(encoding="utf-8")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != entry["sha256"]:
            raise ToolError("Bundled source does not match the method manifest")
        return {**entry, "source": source}
