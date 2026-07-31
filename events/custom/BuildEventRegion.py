"""
@author: xmousset
"""

import logging
import sqlite3
import numpy as np
from typing import Any

from lmtanalysis.TaskLogger import TaskLogger
from lmtanalysis.Parameters import convert_position_to_cm
from lmtanalysis.Event import deleteEventTimeLineInBase
from lmtanalysis.EventTimeLineCache import EventTimeLineCached
from lmtanalysis.Animal import Animal, AnimalPool, AnimalType, EventTimeLine
from lmtanalysis.Measure import oneSecond, oneMinute, oneHour, oneDay, oneWeek

# Event info
# ----------------

EVENTS_NAME: list[str] = ["RegionCenter", "RegionBorder", "RegionIntermediate"]

EVENTS_DESCRIPTION: str = """
    The animal (center of mass) is in the center (square of 20 cm sides),
    border (5 cm or less from the LMT sides), or intermediate region (between
    center and border).
    All values are doubled for rats.
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
    LMT_SIZE = 50  # cm
    BORDER_DIST = 5  # cm
    CENTER_DIST = 10  # cm

    if animalType == AnimalType.RAT:
        LMT_SIZE *= 2
        BORDER_DIST *= 2
        CENTER_DIST *= 2

    BORDER_LIMIT = LMT_SIZE / 2 - BORDER_DIST

    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)

    # Events creation
    # ----------------
    for animal in pool.animalDictionary.values():

        center_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            idB=None,
            idC=None,
            idD=None,
            loadEvent=False,
        )
        border_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[1],
            idA=animal.baseId,
            idB=None,
            idC=None,
            idD=None,
            loadEvent=False,
        )
        intermediate_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[2],
            idA=animal.baseId,
            idB=None,
            idC=None,
            idD=None,
            loadEvent=False,
        )

        result_center = {}
        result_border = {}
        result_intermediate = {}

        # ================ PROXIMITY LOGIC ================

        for f in animal.detectionDictionary.keys():

            x_px = animal.detectionDictionary[f].massX
            y_px = animal.detectionDictionary[f].massY

            x_cm, y_cm = convert_position_to_cm(x_px, y_px, animalType)
            x_cm_abs = abs(x_cm)
            y_cm_abs = abs(y_cm)

            if (x_cm_abs <= CENTER_DIST) and (y_cm_abs <= CENTER_DIST):
                result_center[f] = True
            elif (x_cm_abs >= BORDER_LIMIT) or (y_cm_abs >= BORDER_LIMIT):
                result_border[f] = True
            else:
                result_intermediate[f] = True

        # ================ END OF LOGIC ================

        center_TL.reBuildWithDictionary(result_center)
        center_TL.endRebuildEventTimeLine(connection)

        border_TL.reBuildWithDictionary(result_border)
        border_TL.endRebuildEventTimeLine(connection)

        intermediate_TL.reBuildWithDictionary(result_intermediate)
        intermediate_TL.endRebuildEventTimeLine(connection)

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
