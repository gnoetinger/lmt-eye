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

EVENTS_NAME: list[str] = ["in house corner", "over house"]

EVENTS_DESCRIPTION: str = """
    In house corner: The animal is located in the corner of the house. 
    Detected when the animal is within 200 pixels from the corner position (100, 350).
    
    Over house: The animal is on top of the house.
    Detected when the animal is 25-100 pixels from the corner and its head (massZ) is above 130.
"""


# Rebuild function
# ----------------
def reBuildEvent(
    connection: sqlite3.Connection,
    file=None,
    tmin: int | None = None,
    tmax: int | None = None,
    pool: AnimalPool | None = None,
    animalType=None,
) -> None:

    # Parameters
    # ----------------
    CORNER_POSITION = (100, 350)  # house corner position
    CORNER_DISTANCE_IN = 200  # distance to be in house corner
    CORNER_DISTANCE_ON_MIN = 25  # minimum distance to be on house
    CORNER_DISTANCE_ON_MAX = 100  # maximum distance to be on house
    HEAD_HEIGHT_THRESHOLD = 130  # massZ threshold to be on top of house
    MERGING_GAP = 30  # merge events that are separated by 30 frames or less

    # Events creation
    # ----------------
    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=False)

    for animal in pool.animalDictionary.values():

        result_in_house_corner = {}
        result_over_house = {}

        houseCornerTimeLine = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            loadEvent=False,
        )
        overHouseTimeLine = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[1],
            idA=animal.baseId,
            loadEvent=False,
        )

        # ================ EVENT LOGIC ================

        sorted_detections = sorted(animal.detectionDictionary.items())

        for f, detect in sorted_detections:
            dist = detect.getDistanceToPoint(
                xPoint=CORNER_POSITION[0], yPoint=CORNER_POSITION[1]
            )
            if dist is None:  # if distance cannot be calculated, skip
                continue

            if dist < CORNER_DISTANCE_IN:
                result_in_house_corner[f] = True

            if CORNER_DISTANCE_ON_MIN < dist < CORNER_DISTANCE_ON_MAX:
                if detect.massZ > HEAD_HEIGHT_THRESHOLD:
                    result_over_house[f] = True

        # ================ END OF LOGIC ================

        houseCornerTimeLine.reBuildWithDictionary(result_in_house_corner)
        houseCornerTimeLine.endRebuildEventTimeLine(connection)

        overHouseTimeLine.reBuildWithDictionary(result_over_house)
        overHouseTimeLine.mergeCloseEvents(MERGING_GAP)
        overHouseTimeLine.endRebuildEventTimeLine(connection)

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
