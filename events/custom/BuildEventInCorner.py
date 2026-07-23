"""
Created on 23 mai 2023

@author: eye
@modified on by xmousset
"""

import logging
import sqlite3
import numpy as np
from typing import Any

from lmtanalysis.TaskLogger import TaskLogger
from lmtanalysis.Parameters import get_scale_cm_over_px
from lmtanalysis.Event import deleteEventTimeLineInBase
from lmtanalysis.EventTimeLineCache import EventTimeLineCached
from lmtanalysis.Animal import Animal, AnimalPool, AnimalType, EventTimeLine
from lmtanalysis.Measure import oneSecond, oneMinute, oneHour, oneDay, oneWeek

# Event info
# ----------------

EVENTS_NAME: list[str] = [
    "Corner",
    "Corner NW",
    "Corner NE",
    "Corner SW",
    "Corner SE",
]

EVENTS_DESCRIPTION: str = """
    Detects when the animal is in one of the arena corners (NW, NE, SW, SE).
    Each corner is a 5 cm radius circle.
    Events require minimum 2 seconds duration, with gaps ≤3 frames merged.
    Corner coordinates (cm): NW(20,15), NE(70,15), SW(20,60), SE(70,60).
"""


# Rebuild function
# ----------------
def reBuildEvent(
    connection: sqlite3.Connection,
    file: Any | None = None,
    tmin: int | None = None,
    tmax: int | None = None,
    pool: AnimalPool | None = None,
    animalType: AnimalType = AnimalType.MOUSE,
) -> None:

    # Parameters
    # ----------------
    CM_OVER_PX = get_scale_cm_over_px(animalType)

    CORNERS_COORD = {
        "NW": (20, 15),
        "NE": (70, 15),
        "SW": (20, 60),
        "SE": (70, 60),
    }  # in cm

    RADIUS = 5  # cm radius around the corner
    MIN_DURATION = 2 * oneSecond  # minimum duration for valid event
    MERGING_GAP = 3  # merge events that are separated by 3 frames or less

    radius_px_2 = (RADIUS / CM_OVER_PX) ** 2
    corners_coord_px: dict[str, tuple[float, float]] = {}
    for k, v in CORNERS_COORD.items():
        coord_x = v[0] / CM_OVER_PX
        if v[1] < 0:
            coord_y = -v[1] / CM_OVER_PX
        else:
            coord_y = v[1] / CM_OVER_PX
        corners_coord_px[k] = (coord_x, coord_y)

    # Events creation
    # ----------------
    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)

    for animal in pool.animalDictionary.values():

        results: dict[str, dict[int, bool]] = {}
        corners_TL: dict[str, EventTimeLine] = {}

        for event_name in EVENTS_NAME:
            results[event_name] = {}
            corners_TL[event_name] = EventTimeLine(
                conn=None,
                eventName=event_name,
                idA=animal.baseId,
                loadEvent=False,
            )

        # ================ EVENT LOGIC ================

        for f, detection in sorted(animal.detectionDictionary.items()):
            for event_name in EVENTS_NAME[1:]:

                if detection is None:
                    break
                dir = event_name.split()[1]
                dx_2 = (detection.massX - corners_coord_px[dir][0]) ** 2
                dy_2 = (detection.massY - corners_coord_px[dir][1]) ** 2
                if dx_2 + dy_2 <= radius_px_2:
                    results[event_name][f] = True
                    results["Corner"][f] = True
                    break

        # ================ END OF LOGIC ================

        for event_name in EVENTS_NAME:
            corners_TL[event_name].reBuildWithDictionary(results[event_name])
            corners_TL[event_name].removeEventsBelowLength(MIN_DURATION)
            corners_TL[event_name].mergeCloseEvents(MERGING_GAP)
            corners_TL[event_name].endRebuildEventTimeLine(connection)

    # Do not modify
    # ----------------
    # log process for debugging and record keeping
    f = TaskLogger(connection)
    for event_name in EVENTS_NAME:
        if tmin is None or tmax is None:
            f.addLog(f"Build Event {event_name} (tmin or tmax is None)")
        else:
            f.addLog(f"Build Event {event_name}", tmin=tmin, tmax=tmax)
    logging.debug(f"Event rebuilding finished: {', '.join(EVENTS_NAME)}")


# Do not modify
# ----------------
def flush(connection) -> None:
    """Flush event in database"""
    for event_name in EVENTS_NAME:
        logging.info(f"Flushing event: {event_name}")
        deleteEventTimeLineInBase(connection, event_name)
