"""
@author: Fab

Huddling Event Detection
Created on 6 sept. 2017
"""

import logging
import sqlite3
import numpy as np
from typing import Any

from lmtanalysis.TaskLogger import TaskLogger
from lmtanalysis.Event import deleteEventTimeLineInBase
from lmtanalysis.Animal import Animal, AnimalPool, AnimalType, EventTimeLine
from lmtanalysis.Measure import oneSecond, oneMinute, oneHour, oneDay, oneWeek

# Event info
# ----------------

EVENTS_NAME: list[str] = ["Huddling"]

EVENTS_DESCRIPTION: str = """
    Detects huddling behavior in animals based on body shape roundness.
    An animal is considered huddling when its body roundness is below a certain threshold,
    indicating a curved or huddled posture rather than an extended position.
    WARNING: This event is very long to process.
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
    ROUNDNESS_THRESHOLD = 1.85  # threshold for detecting huddled posture

    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)

    if tmin is None:
        tmin = 1
    if tmax is None:
        tmax = pool.getMaxDetectionT()

    # Events creation
    # ----------------
    for animal in pool.animalDictionary.values():
        result = {}
        huddling_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            loadEvent=False,
        )

        # ================ EVENT LOGIC ================

        n_hour = 0
        # Exceptional print here, because Huddling can be very long to process
        logging.info(f"Processing Huddling for animal {animal.baseId}...")
        for frame_num in range(tmin, tmax + 1):
            if frame_num % oneHour == 0:
                n_hour += 1
                logging.info(f"Processing Huddling, {n_hour} hours processed")

            # Get the binary detection mask for this frame
            mask = animal.getBinaryDetectionMask(frame_num)
            if mask is None:
                continue

            # Get the roundness of the mask (indicator of huddled posture)
            roundness = mask.getRoundness()
            if roundness is None:
                continue

            # If roundness is below threshold, animal is huddling
            if roundness < ROUNDNESS_THRESHOLD:
                result[frame_num] = True

        # ================ END OF LOGIC ================

        # store your result in the event timeline and save it in database
        huddling_TL.reBuildWithDictionary(result)
        huddling_TL.endRebuildEventTimeLine(connection)

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
