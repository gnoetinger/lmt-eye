"""
@author: xmousset
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

EVENTS_NAME: list[str] = ["Proximity", "Farness"]

EVENTS_DESCRIPTION: str = """
    The animal is in proximity or far from another one. Those events are
    detected when the distance between the two animals is:
    - less or equal to 10 cm (20 cm for rats) for Proximity
    - strictly greater than 10 cm (20 cm for rats) for Farness
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
    CM_OVER_PX = get_scale_cm_over_px(animalType)  # px <-> cm conversion

    MAX_DIST_CM = 10  # cm
    if animalType == AnimalType.RAT:
        MAX_DIST_CM = 20  # cm

    max_dist2 = (MAX_DIST_CM / CM_OVER_PX) ** 2

    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)

    # Events creation
    # ----------------
    for animal_1 in pool.animalDictionary.values():

        for animal_2 in pool.animalDictionary.values():
            if animal_1.baseId == animal_2.baseId:
                continue

            proximity_TL = EventTimeLine(
                conn=None,
                eventName=EVENTS_NAME[0],
                idA=animal_1.baseId,
                idB=animal_2.baseId,
                idC=None,
                idD=None,
                loadEvent=False,
            )
            farness_TL = EventTimeLine(
                conn=None,
                eventName=EVENTS_NAME[1],
                idA=animal_1.baseId,
                idB=animal_2.baseId,
                idC=None,
                idD=None,
                loadEvent=False,
            )

            result_p = {}
            result_f = {}

            # ================ PROXIMITY LOGIC ================

            for f in animal_1.detectionDictionary.keys():
                if f in animal_2.detectionDictionary:

                    x_1 = animal_1.detectionDictionary[f].massX
                    y_1 = animal_1.detectionDictionary[f].massY
                    x_2 = animal_2.detectionDictionary[f].massX
                    y_2 = animal_2.detectionDictionary[f].massY

                    dist2 = (x_1 - x_2) ** 2 + (y_1 - y_2) ** 2

                    if dist2 <= max_dist2:
                        result_p[f] = True
                    else:
                        result_f[f] = True

            # ================ END OF LOGIC ================

            proximity_TL.reBuildWithDictionary(result_p)
            proximity_TL.endRebuildEventTimeLine(connection)

            farness_TL.reBuildWithDictionary(result_f)
            farness_TL.endRebuildEventTimeLine(connection)

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
