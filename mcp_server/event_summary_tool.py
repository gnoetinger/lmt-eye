"""Read-only MCP entry point for the existing interval-based event summary."""

import math
import sqlite3
from contextlib import closing
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp_server import lmt_queries as queries


def register_event_summary(server):
    from mcp_server.tools import _connect_read_only, _resolve_database

    @server.tool()
    def get_event_summary(
        event_name: str,
        fps: float,
        group_by: Literal["animal", "pair", "cage"] = "animal",
        directional: bool | None = None,
        animal_ids: list[int] | None = None,
        start_frame: int | None = None,
        end_frame: int | None = None,
        min_duration_frames: int = 1,
        database_path: str | None = None,
    ) -> dict[str, Any]:
        """Summarize bouts touching an inclusive frame window at the supplied FPS.

        Use the recording's measured or calibrated FPS. Overlapping or adjacent
        intervals merge before filtering by duration. Animal grouping uses the
        focal IDANIMALA. For pairs explicitly choose directed or undirected.
        Repeating the returned tool arguments replays the same analysis on the
        same version of the recording.
        """
        if not math.isfinite(fps) or fps <= 0 or min_duration_frames < 1:
            raise ToolError("FPS must be finite and positive and minimum duration at least one frame.")
        if (group_by == "pair") != (directional is not None):
            raise ToolError("Specify directional=true or false only for pair summaries.")
        path = _resolve_database(database_path).resolve()
        try:
            with closing(_connect_read_only(path)) as conn:
                conn.execute("BEGIN")  # read a single snapshot even if the GUI is writing
                bounds = queries.frame_bounds(conn)
                first, last = bounds["first_frame"], bounds["last_frame"]
                lo = first if start_frame is None else start_frame
                hi = last if end_frame is None else end_frame
                if not first <= lo <= hi <= last:
                    raise ToolError(f"Choose an inclusive frame window within {first}–{last}.")
                animals = queries.animals(conn)
                if animal_ids is not None and (not animal_ids or set(animal_ids) - animals.keys()):
                    raise ToolError("Select at least one known animal ID or omit animal_ids.")
                if not queries.event_exists(conn, event_name):
                    raise ToolError(f"Unknown event: {event_name}")
                rows = queries.load_event_rows(conn, event_name, (lo, hi))
                results, notes = queries.summarize_event(
                    rows, event_name, group_by, bool(directional), animals, animal_ids,
                    (lo, hi), fps, min_duration_frames,
                )
        except (sqlite3.Error, ValueError) as exc:
            raise ToolError(f"Cannot summarize this recording: {exc}") from exc
        return {
            "method": "lmt.event_summary", "version": "1.0.0",
            "recording": {"path": str(path), **bounds},
            "tool": "get_event_summary",
            "arguments": {
                "database_path": str(path), "event_name": event_name, "fps": fps,
                "group_by": group_by, "directional": directional, "animal_ids": animal_ids,
                "start_frame": lo, "end_frame": hi, "min_duration_frames": min_duration_frames,
            },
            "units": {"duration": "seconds", "events_per_hour": "bouts/hour",
                      "percent_of_window": "percent", "fps": "frames/second"},
            "results": results, "notes": notes,
        }
