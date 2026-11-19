"""Read-only queries on LMT databases, used by the MCP tools.

Nothing here touches Qt or writes to a database: every function takes an
open (read-only) SQLite connection.

Event rules are the same as in LMT-EYE reports (lmtanalysis EventTimeLine,
used by DataframeConstructor):
    - an animal's event timeline is the union of all EVENT rows where the
      animal is IDANIMALA, whatever the partner;
    - rows are clipped to the analysis window;
    - overlapping or touching rows (end + 1 == next start) form one event;
    - events shorter than ``min_duration_frames`` are then removed
      (``removeEventsBelowLength``).
EventTimeLine does this with one dictionary entry per frame; the interval
arithmetic below gives the same events much faster on long experiments.
"""

import difflib
import itertools
import sqlite3
import statistics
from pathlib import Path
from typing import Any, Iterable, Literal

import pandas as pd

from scripts.binner import Binner

Interval = tuple[int, int]
"""(start_frame, end_frame), both included."""

GroupBy = Literal["animal", "pair", "cage"]

SENSOR_COLUMNS = (
    "TEMPERATURE",
    "HUMIDITY",
    "SOUND",
    "LIGHTVISIBLE",
    "LIGHTVISIBLEANDIR",
)


# ================ EXPERIMENT ================


def frame_bounds(connection: sqlite3.Connection) -> dict[str, int]:
    """First and last FRAMENUMBER and TIMESTAMP (ms) of the FRAME table."""
    row = connection.execute(
        "SELECT "
        "(SELECT FRAMENUMBER FROM FRAME ORDER BY FRAMENUMBER ASC LIMIT 1), "
        "(SELECT TIMESTAMP FROM FRAME ORDER BY FRAMENUMBER ASC LIMIT 1), "
        "(SELECT FRAMENUMBER FROM FRAME ORDER BY FRAMENUMBER DESC LIMIT 1), "
        "(SELECT TIMESTAMP FROM FRAME ORDER BY FRAMENUMBER DESC LIMIT 1)"
    ).fetchone()
    if row is None or row[0] is None:
        raise ValueError("The FRAME table is empty.")
    return {
        "first_frame": row[0],
        "first_timestamp": row[1],
        "last_frame": row[2],
        "last_timestamp": row[3],
    }


def measured_fps(bounds: dict[str, int]) -> float:
    """Frame rate measured between the first and last frame."""
    duration_ms = bounds["last_timestamp"] - bounds["first_timestamp"]
    if duration_ms <= 0:
        return 30.0
    return (bounds["last_frame"] - bounds["first_frame"]) / (
        duration_ms / 1000
    )


def database_info(connection: sqlite3.Connection, path: Path) -> dict:
    """Summary of an experiment (same values as
    ``DatabaseAnalyzer.get_informations``, read-only, plus a few extras)."""
    bounds = frame_bounds(connection)
    n_animals = connection.execute(
        "SELECT COUNT(DISTINCT RFID) FROM ANIMAL"
    ).fetchone()[0]
    tables = sorted(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    )
    frame_columns = {
        row[1].upper()
        for row in connection.execute("PRAGMA table_info(FRAME)")
    }

    start = pd.to_datetime(bounds["first_timestamp"], unit="ms")
    end = pd.to_datetime(bounds["last_timestamp"], unit="ms")
    analysis_folder = path.parent / f"{path.stem} - analysis"

    return {
        "database_path": str(path),
        "database_name": path.stem,
        "n_animals": int(n_animals),
        "start_time_utc": start.isoformat(),
        "end_time_utc": end.isoformat(),
        "duration_hours": round((end - start).total_seconds() / 3600, 2),
        "fps": round(measured_fps(bounds), 2),
        "first_frame": bounds["first_frame"],
        "last_frame": bounds["last_frame"],
        "tables": tables,
        "sensors_available": [
            c for c in SENSOR_COLUMNS if c in frame_columns
        ],
        "default_analysis_folder": (
            str(analysis_folder) if analysis_folder.is_dir() else None
        ),
    }


def animals(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """ANIMAL table by ID, with a short display label (NAME, else RFID)."""
    cursor = connection.execute("SELECT * FROM ANIMAL ORDER BY ID")
    columns = [d[0].upper() for d in cursor.description]
    result: dict[int, dict[str, Any]] = {}
    for row in cursor:
        record = dict(zip(columns, row))
        label = record.get("NAME") or record.get("RFID") or record["ID"]
        record["LABEL"] = str(label)
        result[int(record["ID"])] = record
    return result


# ================ EVENT TYPES ================


def _event_sources() -> dict[str, str]:
    """'official' or 'custom' for each event LMT-EYE can rebuild. Empty if
    the event modules cannot be imported."""
    try:
        from events.events_manager import (
            get_custom_events_name,
            get_official_events_name,
        )
    except Exception:
        return {}
    sources = {name: "custom" for name in get_custom_events_name()}
    sources.update({name: "official" for name in get_official_events_name()})
    return sources


def event_types(connection: sqlite3.Connection, fps: float) -> list[dict]:
    """One row per event name found in the EVENT table."""
    query = """
        SELECT
            NAME,
            COUNT(*),
            COUNT(DISTINCT IDANIMALA),
            MAX((IDANIMALA IS NOT NULL) + (IDANIMALB IS NOT NULL)
                + (IDANIMALC IS NOT NULL) + (IDANIMALD IS NOT NULL)),
            SUM(IDANIMALB IS NOT NULL AND IDANIMALA < IDANIMALB),
            SUM(IDANIMALB IS NOT NULL AND IDANIMALA > IDANIMALB),
            SUM(CASE WHEN IDANIMALB IS NOT NULL AND IDANIMALA < IDANIMALB
                THEN ENDFRAME - STARTFRAME + 1 ELSE 0 END),
            SUM(CASE WHEN IDANIMALB IS NOT NULL AND IDANIMALA > IDANIMALB
                THEN ENDFRAME - STARTFRAME + 1 ELSE 0 END),
            SUM(CASE WHEN STARTFRAME >= 0 AND ENDFRAME >= STARTFRAME
                THEN ENDFRAME - STARTFRAME + 1 ELSE 0 END),
            SUM(STARTFRAME < 0 OR ENDFRAME < STARTFRAME
                OR STARTFRAME IS NULL OR ENDFRAME IS NULL),
            MIN(CASE WHEN STARTFRAME >= 0 THEN STARTFRAME END),
            MAX(ENDFRAME)
        FROM EVENT
        GROUP BY NAME
        ORDER BY NAME
    """
    sources = _event_sources()
    result = []
    for (
        name,
        n_rows,
        n_animals,
        animals_per_row,
        rows_a_lt_b,
        rows_a_gt_b,
        frames_a_lt_b,
        frames_a_gt_b,
        total_frames,
        n_invalid,
        first_frame,
        last_frame,
    ) in connection.execute(query):
        pairwise_rows = (rows_a_lt_b or 0) + (rows_a_gt_b or 0)
        if pairwise_rows == 0 or animals_per_row != 2:
            both_directions = None
        else:
            # symmetric events (e.g. 'Contact') are written once as A->B
            # and once as B->A: both halves are then exactly equal
            both_directions = (
                rows_a_lt_b == rows_a_gt_b and frames_a_lt_b == frames_a_gt_b
            )
        result.append(
            {
                "name": name,
                "n_rows": n_rows,
                "n_animals": n_animals,
                "animals_per_row": animals_per_row,
                "stored_both_directions": both_directions,
                "raw_duration_s": round((total_frames or 0) / fps, 1),
                "first_frame": first_frame,
                "last_frame": last_frame,
                "n_invalid_rows": n_invalid or 0,
                "source": sources.get(name, "other"),
            }
        )
    return result


# ================ TIME WINDOW ================


def _parse_limit(value: str | int | None) -> int | pd.Timestamp | None:
    """Frame number, 'YYYY-MM-DD HH:MM:SS' text, or None (same input as the
    'Processing limits' fields of the analysis settings)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid time limit: {value!r}")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return pd.Timestamp(text)
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid time limit {value!r}: use a frame number or "
            "'YYYY-MM-DD HH:MM:SS'."
        )


def resolve_window(
    connection: sqlite3.Connection,
    start: str | int | None,
    end: str | int | None,
    fps: int,
    utc_offset: float,
) -> tuple[Interval, dict[str, Any]]:
    """Frame window and its description, with the same conversion and
    clamping rules as the analysis (``Binner``)."""
    last_frame, last_timestamp = Binner.get_last_frame(connection)
    binner = Binner(
        last_frame,
        last_timestamp,
        bin_size=last_frame,
        bin_rounding=False,
        limits=(_parse_limit(start), _parse_limit(end)),
        fps=fps,
        utc_offset=utc_offset,
    )
    lo, hi = binner.limits
    n_frames = hi - lo + 1
    return (lo, hi), {
        "start_frame": lo,
        "end_frame": hi,
        "start_time": binner.frame_to_time(lo).isoformat(
            timespec="milliseconds"
        ),
        "end_time": binner.frame_to_time(hi).isoformat(
            timespec="milliseconds"
        ),
        "utc_offset_hours": utc_offset,
        "duration_hours": round(n_frames / fps / 3600, 3),
    }


# ================ EVENTS ================


def merge_intervals(
    intervals: Iterable[Interval], window: Interval
) -> list[Interval]:
    """Union of frame intervals clipped to the window. Overlapping or
    touching intervals are merged (as ``EventTimeLine``)."""
    lo, hi = window
    clipped = sorted(
        (max(s, lo), min(e, hi))
        for s, e in intervals
        if s is not None and e is not None and e >= s and e >= lo and s <= hi
    )
    merged: list[Interval] = []
    for s, e in clipped:
        if merged and s <= merged[-1][1] + 1:
            if e > merged[-1][1]:
                merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def interval_stats(
    intervals: list[Interval], fps: float, window_frames: int
) -> dict[str, Any]:
    lengths = [e - s + 1 for s, e in intervals]
    n = len(lengths)
    total = sum(lengths)
    hours = window_frames / fps / 3600
    return {
        "count": n,
        "total_duration_s": round(total / fps, 2),
        "mean_duration_s": round(total / n / fps, 3) if n else None,
        "median_duration_s": (
            round(statistics.median(lengths) / fps, 3) if n else None
        ),
        "max_duration_s": round(max(lengths) / fps, 2) if n else None,
        "percent_of_window": round(100 * total / window_frames, 3),
        "events_per_hour": round(n / hours, 2) if hours > 0 else None,
    }


def load_event_rows(
    connection: sqlite3.Connection, event_name: str, window: Interval
) -> list[tuple]:
    """(start, end, idA, idB, idC, idD) of the rows touching the window."""
    return connection.execute(
        "SELECT STARTFRAME, ENDFRAME, IDANIMALA, IDANIMALB, IDANIMALC, "
        "IDANIMALD FROM EVENT "
        "WHERE NAME = ? AND ENDFRAME >= ? AND STARTFRAME <= ?",
        (event_name, window[0], window[1]),
    ).fetchall()


def event_exists(connection: sqlite3.Connection, event_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM EVENT WHERE NAME = ? LIMIT 1", (event_name,)
        ).fetchone()
        is not None
    )


def close_event_names(
    connection: sqlite3.Connection, event_name: str
) -> list[str]:
    names = [
        row[0] for row in connection.execute("SELECT DISTINCT NAME FROM EVENT")
    ]
    lower = {n.lower(): n for n in names if n}
    query = event_name.lower().strip()
    matches = difflib.get_close_matches(query, list(lower), n=3, cutoff=0.6)
    # also names containing the query, e.g. 'Move' -> 'Move isolated'
    matches += sorted(n for n in lower if query and query in n)
    return list(dict.fromkeys(lower[m] for m in matches))[:6]


def summarize_event(
    rows: list[tuple],
    event_name: str,
    group_by: GroupBy,
    directional: bool,
    animal_table: dict[int, dict[str, Any]],
    selected_ids: list[int] | None,
    window: Interval,
    fps: float,
    min_duration_frames: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Statistics of one event, grouped by animal, pair or for the whole
    cage. Returns (rows, notes)."""
    window_frames = window[1] - window[0] + 1
    all_ids = sorted(animal_table)
    chosen = set(selected_ids) if selected_ids else set(all_ids)
    notes: list[str] = []

    def finish(intervals: Iterable[Interval]) -> dict[str, Any]:
        merged = merge_intervals(intervals, window)
        kept = [
            (s, e) for s, e in merged if e - s + 1 >= min_duration_frames
        ]
        return interval_stats(kept, fps, window_frames)

    result: list[dict[str, Any]] = []

    if group_by != "cage" and any(row[2] is None for row in rows):
        notes.append(
            f"Some '{event_name}' rows have no animal ID (cage-level "
            "event): they only appear with group_by='cage'."
        )

    if group_by == "animal":
        by_animal: dict[int, list[Interval]] = {}
        for s, e, a, *_ in rows:
            by_animal.setdefault(a, []).append((s, e))
        for animal_id in all_ids:
            if animal_id not in chosen:
                continue
            animal = animal_table[animal_id]
            result.append(
                {
                    "event": event_name,
                    "animal_id": animal_id,
                    "animal": animal["LABEL"],
                    "rfid": animal.get("RFID"),
                    "genotype": animal.get("GENOTYPE"),
                    **finish(by_animal.get(animal_id, [])),
                }
            )

    elif group_by == "pair":
        if any(row[4] is not None for row in rows):
            notes.append(
                f"'{event_name}' involves 3 or more animals: pair statistics "
                "would be misleading, use group_by='animal' or 'cage'."
            )
            return result, notes
        if rows and all(row[3] is None for row in rows):
            notes.append(
                f"'{event_name}' has no partner animal (IDANIMALB): it is "
                "not a pairwise event, use group_by='animal'."
            )
            return result, notes

        by_pair: dict[tuple[int, int], list[Interval]] = {}
        for s, e, a, b, *_ in rows:
            if a is None or b is None:
                continue
            key = (a, b) if directional else (min(a, b), max(a, b))
            by_pair.setdefault(key, []).append((s, e))

        pairs = (
            itertools.permutations(all_ids, 2)
            if directional
            else itertools.combinations(all_ids, 2)
        )
        arrow = " -> " if directional else " - "
        for a, b in pairs:
            if a not in chosen and b not in chosen:
                continue
            result.append(
                {
                    "event": event_name,
                    "animal_a_id": a,
                    "animal_b_id": b,
                    "pair": animal_table[a]["LABEL"]
                    + arrow
                    + animal_table[b]["LABEL"],
                    **finish(by_pair.get((a, b), [])),
                }
            )

    else:  # cage
        intervals = [
            (s, e)
            for s, e, a, *_ in rows
            if selected_ids is None or a in chosen
        ]
        result.append(
            {
                "event": event_name,
                "group": (
                    "cage"
                    if selected_ids is None
                    else "animals " + ", ".join(map(str, sorted(chosen)))
                ),
                **finish(intervals),
            }
        )

    return result, notes


# ================ READ-ONLY SQL ================

# Operations a query may perform (sqlite3 authorizer action codes). Anything
# else (INSERT, UPDATE, DELETE, CREATE, DROP, ATTACH, writing PRAGMA, ...)
# is refused before the query runs.
_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),  # WITH RECURSIVE
}
# PRAGMA that only describe the database (their argument is a table or
# index name, they cannot change anything)
_ALLOWED_PRAGMAS = {
    "table_info",
    "table_xinfo",
    "table_list",
    "index_list",
    "index_info",
    "index_xinfo",
    "foreign_key_list",
}


def _read_only_authorizer(action, arg1, arg2, db_name, trigger):
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    if (
        action == sqlite3.SQLITE_PRAGMA
        and str(arg1).lower() in _ALLOWED_PRAGMAS
    ):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def run_read_only_query(
    connection: sqlite3.Connection,
    sql: str,
    params: list[Any] | None = None,
) -> dict[str, Any]:
    """Run one SQL statement that can only read, and return all its rows.

    Three locks keep the database untouched, whatever the SQL text:
    the connection is opened with mode=ro (by the caller), 'PRAGMA
    query_only' is switched on, and an authorizer refuses every operation
    other than reading (so INSERT, UPDATE, DELETE, CREATE, DROP, ATTACH or a
    PRAGMA that sets a value fail before running). sqlite3 also refuses
    several statements in one call.
    """
    connection.execute("PRAGMA query_only = ON")
    connection.set_authorizer(_read_only_authorizer)
    try:
        cursor = connection.execute(sql, params or [])
        if cursor.description is None:
            return {"columns": [], "rows": [], "n_rows": 0}
        columns = [d[0] for d in cursor.description]
        rows = [[_json_value(v) for v in row] for row in cursor.fetchall()]
    finally:
        connection.set_authorizer(None)
    return {"columns": columns, "rows": rows, "n_rows": len(rows)}
