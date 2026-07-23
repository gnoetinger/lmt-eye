"""
Created on 6 sept. 2017

@author: Fab
@modified by: xmousset
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

EVENTS_NAME: list[str] = ["Floor sniffing"]

EVENTS_DESCRIPTION: str = """
    The animal is sniffing the floor. This event is detected when the animal's body slope 
    (frontZ - backZ) is between -25 and -15 (px), indicating the animal's head/front is lower 
    than its tail/back, characteristic of a downward sniffing posture.
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
    BODY_SLOPE_LIMITS = (-25, -15)  # px

    pool = AnimalPool()
    pool.loadAnimals(connection)
    pool.loadDetection(start=tmin, end=tmax)

    for animal in pool.animalDictionary.values():

        result = {}

        sniffFloorTimeLine = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            loadEvent=False,
        )

        # ================ EVENT LOGIC ================

        sorted_detections = sorted(animal.detectionDictionary.items())

        for f, detect in sorted_detections:
            body_slope = detect.getBodySlope()

            if body_slope == None:
                continue

            if (
                body_slope >= BODY_SLOPE_LIMITS[0]
                and body_slope <= BODY_SLOPE_LIMITS[1]
            ):
                result[f] = True

        # ================ END OF LOGIC ================

        sniffFloorTimeLine.reBuildWithDictionary(result)
        sniffFloorTimeLine.endRebuildEventTimeLine(connection)

    # Do not modify
    # ----------------
    # log process for debugging and record keeping
    t = TaskLogger(connection)
    for event_name in EVENTS_NAME:
        if tmin is None or tmax is None:
            t.addLog(f"Build Event {event_name} (tmin or tmax is None)")
        else:
            t.addLog(f"Build Event {event_name}", tmin=tmin, tmax=tmax)
    logging.debug(f"Event rebuilding finished: {', '.join(EVENTS_NAME)}")


# Do not modify
# ----------------
def flush(connection) -> None:
    """Flush event in database"""
    for event_name in EVENTS_NAME:
        logging.info(f"Flushing event: {event_name}")
        deleteEventTimeLineInBase(connection, event_name)
