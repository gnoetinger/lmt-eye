"""Count a named event for one focal animal (IDANIMALA) in an inclusive window."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def count_bouts(connection, event, animal_id, start, end):
    if end < start:
        raise ValueError("end must be at least start")
    rows = connection.execute("""
        SELECT STARTFRAME, ENDFRAME FROM EVENT
        WHERE NAME = ? AND IDANIMALA = ? AND STARTFRAME <= ENDFRAME
          AND STARTFRAME <= ? AND ENDFRAME >= ?
        ORDER BY STARTFRAME, ENDFRAME
    """, (event, animal_id, end, start))
    count = occupied = 0
    last = None
    for first, final in rows:
        first, final = max(first, start), min(final, end)
        if last is None or first > last + 1:
            count += 1
            occupied += final - first + 1
        elif final > last:
            occupied += final - last
        last = final if last is None else max(final, last)
    return {"bout_count": count, "occupied_frames": occupied}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("event")
    parser.add_argument("animal_id", type=int)
    parser.add_argument("start", type=int)
    parser.add_argument("end", type=int)
    args = parser.parse_args()
    uri = args.database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        print(json.dumps(count_bouts(connection, args.event, args.animal_id, args.start, args.end)))
