"""
Created on 6 sept. 2017

@author: Fab
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

EVENTS_NAME: list[str] = ["Water Zone", "Water Stop"]

EVENTS_DESCRIPTION: str = """
    Water Zone: The animal is in the zone around the water source.
    Detected when the animal is within 10 cm from the water source position (398, 353).
    
    Water Stop: The animal is stopped and drinking at the water point.
    Detected when the animal is within 5 cm from the water source position and 
    the animal is in a "Stop" event for at least 2 seconds.
"""


# Rebuild function
# ----------------
def reBuildEvent(
    connection: sqlite3.Connection,
    file=None,
    tmin: int | None = None,
    tmax: int | None = None,
    pool: AnimalPool | None = None,
    animalType=AnimalType.MOUSE,
) -> None:

    # Parameters
    # ----------------
    CM_OVER_PX = get_scale_cm_over_px(animalType)
    WATER_POINT_POSITION = (398, 353)  # water source position
    WATER_ZONE_DISTANCE = 10 / CM_OVER_PX  # zone around water: 10 cm
    WATER_STOP_DISTANCE = 5 / CM_OVER_PX  # tight zone for drinking: 5 cm
    WATER_STOP_MIN_DURATION = 2 * oneSecond  # minimum duration for drinking

    # Events creation
    # ----------------
    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)

    for animal in pool.animalDictionary.values():

        result_wzone = {}
        result_wstop = {}

        water_zone_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            loadEvent=False,
        )
        water_stop_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[1],
            idA=animal.baseId,
            loadEvent=False,
        )

        # ================ EVENT LOGIC ================

        stop_dict = EventTimeLine(
            conn=connection,
            eventName="Stop",
            idA=animal.baseId,
        ).getDictionary()

        sorted_detections = sorted(animal.detectionDictionary.items())

        for f, detect in sorted_detections:
            dist = detect.getDistanceToPoint(
                xPoint=WATER_POINT_POSITION[0], yPoint=WATER_POINT_POSITION[1]
            )

            if dist is None:
                continue

            # Check if the animal is entering the zone around the water point
            if dist <= WATER_ZONE_DISTANCE:
                result_wzone[f] = True

            # Check if the animal is drinking (in tight zone and stopped)
            if dist <= WATER_STOP_DISTANCE:
                if f in stop_dict:
                    result_wstop[f] = True

        # ================ END OF LOGIC ================

        water_zone_TL.reBuildWithDictionary(result_wzone)
        water_zone_TL.endRebuildEventTimeLine(connection)

        water_stop_TL.reBuildWithDictionary(result_wstop)
        water_stop_TL.removeEventsBelowLength(WATER_STOP_MIN_DURATION)
        water_stop_TL.endRebuildEventTimeLine(connection)

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
