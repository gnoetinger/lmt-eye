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

# Sent to the client when it connects; the model reads it at the start of
# every session. Keep it short: details belong in tool descriptions.
INSTRUCTIONS = (
    "Access to Live Mouse Tracker (LMT) experiments opened in LMT-EYE. "
    "Without 'database_path', tools use the database currently loaded in "
    "LMT-EYE. All tools are read-only.\n"
    "LMT database conventions:\n"
    "- Positions (MASS_X/Y, FRONT_*, BACK_*) are in pixels. Convert with "
    "10/57 cm per pixel for mice and 20/57 for rats. The y axis points down (camera view).\n"
    "- Frames are usually at 30 frames/s (see get_database_info). Time 0 "
    "is the first frame of the FRAME table.\n"
    "- MASS_Z is a relative height of the animal from the ground in millimeters."
    "low on the floor, higher on raised objects such as a house roof. "
    "Check the levels in each setup.\n"
    "- Pairwise events (e.g. 'Oral-oral Contact', 'Contact') are stored "
    "once per animal of the pair (A->B and B->A). Merge them before "
    "counting contacts between two animals.\n"
    "- A centre-of-mass step longer than 85.5 px between two consecutive "
    "frames is a tracking error. Exclude it from distances.\n"
    "- Even when an animal is stopped, the tracking may still move a little around the animal, which provides overestimated distances.\n"
    "- Identity switches can happen when two mice are close: the tracked "
    "position jumps by several cm in one frame. Check for them before "
    "trusting a rare event.\n"
    "- for data analysis report, prefer a webpage using plotly for figures\n"
    "- if events are missing in the database, the rebuild all events function compute them. The table LOG displays in each row the last time the event has been computed, and for which time range (in frame).\n"
    "- in the table events, the IDANIMAL* represents the animals in the order of the event description: (e.g Oral-genital Contact means contact of the oral part of IDANIMALA with genital of IDANIMALB)."
    "One exception for nest3*: the idanimalA is the one that is not in the nest. Nest3 only work if 4 animals are in the database\n"
    
    "Quality control:\n"
    "- The frame should be at 30fps\n"
    "- Check duplicated databases\n"
    
    "Analysis:\n"
    "- The events can be analyzed in term of number, duration and frequency\n"
    "- for the distance between animals, use the mass center X and Y"
    "- for the sake of reproducibility, generate python codes"
    "- it is not parameters but variables"
    "- stats: mice of a same experiment are not independent"
    
    "Color conventions:\n"
    "- animal A is red, B:green, C:purple D:orange\n"
        
)


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
        instructions=INSTRUCTIONS,
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
