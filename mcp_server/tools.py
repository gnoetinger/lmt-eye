"""MCP tools exposed by LMT-EYE.

All tools are read-only. They run in a worker thread of the server (never
in the Qt thread) and open SQLite databases in read-only mode, because an
analysis may be writing to the same database at the same time.

The queries themselves live in ``mcp_server/lmt_queries.py``; this file
only declares the tools and checks their arguments. The user prompts that
the AI passes to ``record_user_prompt`` are written to
``mcp_server/logs/user_prompts.log`` (see ``query_log.py``).
"""

import sqlite3
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.state import app_state

MAX_EVENTS_PER_CALL = 30

# Sent to the client when it connects; the model reads it at the start of
# every session. Keep it short: details belong in tool descriptions.
INSTRUCTIONS = (
    "Access to Live Mouse Tracker (LMT) experiments opened in LMT-EYE. "
    "Without 'database_path', tools use the database currently loaded in "
    "LMT-EYE. No tool modifies the databases.\n"
    "Prompt log: before using LMT-EYE tools to answer a user message, call "
    "record_user_prompt once with that message copied word for word (no "
    "summary, no translation). Do not call it again for the other tool calls "
    "answering the same message.\n"
    "LMT database conventions:\n"
    "- Positions (MASS_X/Y, FRONT_*, BACK_*) are in pixels. Convert with "
    "10/57 cm per pixel for mice and 20/57 for rats. The y axis points down (camera view).\n"
    "- Frames are usually at 30 frames/s (see get_database_info). Time 0 "
    "is the first frame of the FRAME table.\n"
    "- MASS_Z is a relative height of the animal from the ground in millimeters: "
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
    "LMT-EYE reports:\n"
    "- To count or time events, use get_event_summary rather than counting "
    "EVENT rows: it applies the report rules (an animal's events merge all "
    "its partners, overlapping rows form one event, window clipping, "
    "minimum duration).\n"
    "- In report tables, summing EVENT_COUNT over time bins counts an event "
    "once in every bin it touches, so the sum is slightly too high. "
    "get_event_summary counts each event once.\n"
    "- 'Per day' report values are extrapolated from the experiment "
    "duration: check duration_hours in get_database_info before quoting "
    "them.\n"
    "- For anything else, query_database runs read-only SQL. Results are "
    "not limited in size: filter (WHERE), aggregate (GROUP BY) or use LIMIT, "
    "especially on DETECTION (one row per animal per frame)."
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
    """All rows of a query, as dictionaries."""
    cursor = connection.execute(query)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _sqlite_error(e: sqlite3.Error, what: str) -> ToolError:
    if "locked" in str(e).lower():
        return ToolError(
            f"Cannot read {what}: the database is locked, probably by an "
            "analysis running in LMT-EYE. Try again when it is finished."
        )
    return ToolError(f"Cannot read {what}: {e}")


def build_server(app_version: str = "") -> MCPServer:
    """Create the MCP server and register LMT-EYE tools."""

    server = MCPServer(
        name="lmt-eye",
        title="LMT-EYE",
        version=app_version,
        instructions=INSTRUCTIONS,
    )

    # local log of the user prompts (see record_user_prompt)
    from mcp_server import query_log

    query_log.setup()

    @server.tool()
    def record_user_prompt(prompt: str, ctx: Context) -> dict[str, Any]:
        """Record the user's message in LMT-EYE's local prompt log.

        Call it once per user message, before the other LMT-EYE tools, with
        the user's message copied word for word: no summary, no
        translation, no added context. Do not call it again for the other
        tool calls that answer the same message. It returns
        {"recorded": true} or the reason it was not recorded; either way,
        go on answering the user."""
        if not prompt or not prompt.strip():
            raise ToolError("Give the user's message in 'prompt'.")
        try:
            request_context = ctx.request_context
        except Exception:
            request_context = None
        return query_log.record_prompt(prompt, request_context)

    @server.tool()
    def get_loaded_database() -> dict[str, Any]:
        """Return the path of the LMT database currently loaded in LMT-EYE,
        or null if none is loaded."""
        path = app_state.database_path
        return {"database_path": str(path) if path is not None else None}

    @server.tool()
    def get_database_info(database_path: str | None = None) -> dict[str, Any]:
        """Summary of an LMT experiment: number of animals, start and end
        (UTC), duration, frame rate, first and last frame, tables, sensors
        available in the FRAME table, and the default LMT-EYE analysis
        folder ('<database> - analysis') if it exists."""
        # imported here: only needed when the tool is called
        from mcp_server import lmt_queries

        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            return lmt_queries.database_info(connection, path)
        except sqlite3.Error as e:
            raise _sqlite_error(e, "the database")
        except ValueError as e:
            raise ToolError(str(e))
        finally:
            connection.close()

    @server.tool()
    def list_animals(database_path: str | None = None) -> dict[str, Any]:
        """List the animals of an LMT experiment (content of the ANIMAL
        table: ID, RFID, name, genotype, ...)."""
        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            rows = _rows_as_dicts(
                connection, "SELECT * FROM ANIMAL ORDER BY ID"
            )
            return {"animals": rows}
        except sqlite3.Error as e:
            raise _sqlite_error(e, "the ANIMAL table")
        finally:
            connection.close()

    @server.tool()
    def list_event_types(
        database_path: str | None = None,
    ) -> dict[str, Any]:
        """List the behavioural event types present in an LMT database.

        For each event name: n_rows (EVENT rows; symmetric pairwise events
        such as 'Contact' have two rows per occurrence, A->B and B->A),
        n_animals, animals_per_row (1 = individual, 2 = pairwise,
        3-4 = group), stored_both_directions (true for symmetric pairwise
        events), raw_duration_s (sum of row durations, not merged), first
        and last frame, n_invalid_rows (negative or reversed frames, e.g.
        test annotations) and source ('official' or 'custom' if LMT-EYE can
        rebuild it, otherwise 'other', e.g. manual annotations).
        To count or time events, use get_event_summary."""
        from mcp_server import lmt_queries

        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            fps = lmt_queries.measured_fps(
                lmt_queries.frame_bounds(connection)
            )
            rows = lmt_queries.event_types(connection, fps)
        except sqlite3.Error as e:
            raise _sqlite_error(e, "the EVENT table")
        except ValueError as e:
            raise ToolError(str(e))
        finally:
            connection.close()
        return {
            "event_types": rows,
        }

    @server.tool()
    def get_event_summary(
        event_names: list[str],
        group_by: Literal["animal", "pair", "cage"] = "animal",
        directional: bool = False,
        animal_ids: list[int] | None = None,
        start: str | int | None = None,
        end: str | int | None = None,
        min_duration_frames: int = 1,
        utc_offset: float = 0.0,
        fps: int | None = None,
        database_path: str | None = None,
    ) -> dict[str, Any]:
        """Count and time behavioural events over a time window, with the
        same rules as LMT-EYE reports.

        group_by:
        - 'animal' (default): one row per animal. An animal's events are
          all EVENT rows where it is IDANIMALA, partners merged (as in the
          reports).
        - 'pair': one row per pair of animals, for events with a partner
          (IDANIMALB). A->B and B->A rows are merged into one timeline for
          the pair, unless directional=True (use it for oriented events
          such as 'Approach', 'Follow' or 'Social approach').
        - 'cage': one row: time during which the event happens for at least
          one animal.

        Rules: overlapping or touching rows form one event; events crossing
        the window limits are cut at the limits; events shorter than
        min_duration_frames are then dropped (same as 'event_min_duration'
        in an analysis settings.json; the app's 'Remove event <= N frames'
        field corresponds to N + 1). Each event is counted once over the
        window, unlike sums of report bins.

        animal_ids: restrict to these animal IDs (pairs: pairs including at
        least one of them). start / end: frame number or
        'YYYY-MM-DD HH:MM:SS' in local time (UTC + utc_offset hours);
        default is the whole experiment. fps: default is the measured frame
        rate, rounded.

        Returns the window used, the parameters, one row per event and group
        (count, total, mean, median and max duration in seconds,
        percent_of_window, events_per_hour) and notes."""
        from mcp_server import lmt_queries

        names = list(dict.fromkeys(n for n in event_names if n))
        if not names:
            raise ToolError("Give at least one event name.")
        if len(names) > MAX_EVENTS_PER_CALL:
            raise ToolError(
                f"At most {MAX_EVENTS_PER_CALL} events per call "
                f"({len(names)} given)."
            )
        if min_duration_frames < 1:
            raise ToolError("min_duration_frames must be at least 1.")
        if fps is not None and fps < 1:
            raise ToolError("fps must be at least 1.")

        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            animal_table = lmt_queries.animals(connection)
            if animal_ids:
                unknown = sorted(set(animal_ids) - set(animal_table))
                if unknown:
                    raise ToolError(
                        f"Unknown animal IDs: {unknown}. Known IDs: "
                        f"{sorted(animal_table)}."
                    )

            if fps is None:
                bounds = lmt_queries.frame_bounds(connection)
                fps = max(1, round(lmt_queries.measured_fps(bounds)))

            try:
                window, window_info = lmt_queries.resolve_window(
                    connection, start, end, fps, utc_offset
                )
            except ValueError as e:
                raise ToolError(str(e))

            rows: list[dict[str, Any]] = []
            notes: list[str] = []
            for name in names:
                event_rows = lmt_queries.load_event_rows(
                    connection, name, window
                )
                if not event_rows and not lmt_queries.event_exists(
                    connection, name
                ):
                    close = lmt_queries.close_event_names(connection, name)
                    hint = f" Did you mean: {close}?" if close else ""
                    notes.append(
                        f"No '{name}' event in this database (names are "
                        f"case-sensitive).{hint} See list_event_types."
                    )
                    continue
                event_result, event_notes = lmt_queries.summarize_event(
                    event_rows,
                    name,
                    group_by,
                    directional,
                    animal_table,
                    animal_ids,
                    window,
                    fps,
                    min_duration_frames,
                )
                rows.extend(event_result)
                notes.extend(event_notes)
        except sqlite3.Error as e:
            raise _sqlite_error(e, "the database")
        finally:
            connection.close()

        return {
            "database_path": str(path),
            "window": window_info,
            "params": {
                "group_by": group_by,
                "directional": directional,
                "animal_ids": animal_ids,
                "min_duration_frames": min_duration_frames,
                "fps": fps,
            },
            "rows": rows,
            "notes": notes,
        }

    @server.tool()
    def query_database(
        sql: str,
        params: list[Any] | None = None,
        database_path: str | None = None,
    ) -> dict[str, Any]:
        """Run one read-only SQL query (SQLite) on an LMT database and return
        all its rows: columns, rows (lists of values) and n_rows.

        The database cannot be modified: it is opened read-only and every
        operation other than reading is refused (INSERT, UPDATE, DELETE,
        CREATE, DROP, ATTACH, PRAGMA that set a value). PRAGMA table_info,
        index_list and similar descriptive PRAGMA are allowed. Use '?' in
        the SQL and pass the values in 'params'.

        Main tables: ANIMAL (ID, RFID, NAME, GENOTYPE...), FRAME (FRAMENUMBER,
        TIMESTAMP in ms UTC, sensors when present), DETECTION (FRAMENUMBER,
        ANIMALID, MASS_X/Y/Z, FRONT_*, BACK_* in pixels, REARING,
        LOOK_UP, LOOK_DOWN), EVENT (NAME, STARTFRAME, ENDFRAME, IDANIMALA..D,
        METADATA), LOG (rebuild history).

        There is no row limit: DETECTION holds one row per animal per frame
        (millions of rows over days), so filter, aggregate or use LIMIT.
        To count or time events with the report rules, prefer
        get_event_summary."""
        from mcp_server import lmt_queries

        if not sql or not sql.strip():
            raise ToolError("Give an SQL query.")
        path = _resolve_database(database_path)
        connection = _connect_read_only(path)
        try:
            result = lmt_queries.run_read_only_query(connection, sql, params)
        except sqlite3.Error as e:
            message = str(e)
            if (
                "not authorized" in message
                or "authorization denied" in message
                or "prohibited" in message
                or "readonly" in message
            ):
                raise ToolError(
                    f"Refused: query_database can only read ({message})."
                )
            if "locked" in message.lower():
                raise _sqlite_error(e, "the database")
            raise ToolError(f"SQL error: {message}")
        finally:
            connection.close()
        return {"database_path": str(path), **result}

    return server
