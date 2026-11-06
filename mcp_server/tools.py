"""MCP tools exposed by LMT-EYE.

All tools are read-only. They run in a worker thread of the server (never
in the Qt thread) and open SQLite databases in read-only mode, because an
analysis may be writing to the same database at the same time.
"""

import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.state import app_state

MAX_ROWS = 500


def _resolve_database(database_path: str | None) -> Path:
    """Return the database to read: the given path, or the database
    currently loaded in LMT-EYE."""
    if database_path:
        path = Path(database_path).expanduser()
    else:
        loaded = app_state.database_path
        if loaded is None:
            raise ToolError(
                "No database is loaded in LMT-EYE. Load one with "
                "'Load Database' or pass 'database_path'."
            )
        path = loaded
    if not path.is_file():
        raise ToolError(f"Database not found: {path}")
    if path.suffix.lower() != ".sqlite":
        raise ToolError(f"Not an LMT .sqlite database: {path}")
    return path


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5)


def _rows_as_dicts(
    connection: sqlite3.Connection, query: str
) -> list[dict[str, Any]]:
    cursor = connection.execute(query)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchmany(MAX_ROWS)]


def build_server(app_version: str = "") -> MCPServer:
    """Create the MCP server and register LMT-EYE tools."""

    server = MCPServer(
        name="lmt-eye",
        title="LMT-EYE",
        version=app_version,
        instructions=(
            "Access to Live Mouse Tracker (LMT) experiments opened in "
            "LMT-EYE. Without 'database_path', tools use the database "
            "currently loaded in LMT-EYE."
        ),
    )

    @server.tool()
    def get_loaded_database() -> dict[str, Any]:
        """Return the path of the LMT database currently loaded in LMT-EYE,
        or null if none is loaded."""
        path = app_state.database_path
        return {"database_path": str(path) if path is not None else None}

    @server.tool()
    def get_database_info(database_path: str | None = None) -> dict[str, Any]:
        """Summary of an LMT experiment: number of animals, start and end
        (UTC), duration and frame rate."""
        # imported here: heavy module, only needed when the tool is called
        from scripts.db_analyzer import DatabaseAnalyzer

        path = _resolve_database(database_path)
        infos = DatabaseAnalyzer.get_informations(path)
        return {
            "database_path": str(path),
            "database_name": infos["database_name"],
            "n_animals": int(infos["n_animals"]),
            "start_time_utc": infos["start_time"].isoformat(),
            "end_time_utc": infos["end_time"].isoformat(),
            "duration_hours": round(
                infos["duration"].total_seconds() / 3600, 2
            ),
            "fps": round(float(infos["fps"]), 2),
        }

    @server.tool()
    def list_animals(database_path: str | None = None) -> list[dict[str, Any]]:
        """List the animals of an LMT experiment (content of the ANIMAL
        table: ID, RFID, name, genotype, ...)."""
        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            return _rows_as_dicts(connection, "SELECT * FROM ANIMAL")
        except sqlite3.Error as e:
            raise ToolError(f"Cannot read ANIMAL table: {e}")
        finally:
            connection.close()

    @server.tool()
    def list_event_types(
        database_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """List the behavioural event types present in an LMT database,
        with their number of occurrences."""
        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            return _rows_as_dicts(
                connection,
                "SELECT NAME AS name, COUNT(*) AS count "
                "FROM EVENT GROUP BY NAME ORDER BY NAME",
            )
        except sqlite3.Error as e:
            raise ToolError(f"Cannot read EVENT table: {e}")
        finally:
            connection.close()

    return server
