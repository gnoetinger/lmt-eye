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

EVENTS_NAME: list[str] = ["Example event"]
# MUST be a list of event names (even if there is only one event in the file)
# to allow the possibility of creating multiple events in one rebuild function

EVENTS_DESCRIPTION: str = """
    This is an example of a custom event. It is not an official event, but it can be built and analysed like any other event.
    You can use this file as a template to create your own custom events.
    To do so, copy and paste this file, rename it (e.g. BuildEventMyEvent.py), and modify the code in the reBuildEvent function.
    Make sure to change the EVENTS_NAME variable and the docstring of the reBuildEvent function to describe your event and its parameters.
    If multiple events are created in one rebuild function, all will have this description.
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
    # your variables here
) -> None:
    """
    Rebuilds the appropriate event for all animals in the database.

    Parameters
    ----------
    connection : sqlite3.Connection
        The SQLite database connection.
    file : Any or None, optional
        The file path or object.
        Can be used by EventTimeLineCached to cache event loading.
        Default is None.
    tmin : int or None, optional
        Start time for detections (in frame). If None, it will load all
        detections from the start.
    tmax : int or None, optional
        End time for detections (in frame). If None, it will load all
        detections until the end.
    pool : AnimalPool or None, optional
        AnimalPool instance (create new one if None, using tmin and tmax).
    animalType : AnimalType, optional
        The appropriate animal type. Default is MOUSE.
    YOUR_VARIABLES : type
        Description of your variables.
        IMPORTANT: LMT-EYE always use the default values of your variables.

    Returns
    -------
    None
    """

    # Parameters
    # ----------------
    CM_OVER_PX = get_scale_cm_over_px(animalType)  # px <-> cm conversion

    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax, lightLoad=True)
    # lightLoad=True allows to load only massX and massY of detections
    # it is faster and uses less memory. Set it to False if you need any of:
    # massZ, frontX, frontY, frontZ, backX, backY, backZ
    # or rearing, lookUp, lookDown variables

    # Events creation
    # ----------------
    for animal in pool.animalDictionary.values():

        # create a new event timeline for each animal
        # it will be filled with the result of your event detection
        # then saved in database at the end of the process
        example_TL = EventTimeLine(
            conn=None,
            eventName=EVENTS_NAME[0],
            idA=animal.baseId,
            idB=None,
            idC=None,
            idD=None,
            loadEvent=False,
        )
        # prepare a dictionary to store the result of your event detection
        # keys of this dictionary should be frame numbers
        # values should be True (do not add False values to the dictionary)
        # this result initialisation must follow the EventTimeLine creation
        result = {}

        # USAGE EXAMPLE:
        # > result[f] = True
        # this means your event occur at frame "f"
        # NEVER add a "False" value to the dictionary

        # ================ EVENT LOGIC ================

        # Useful examples
        # ----------------
        # example of how to get all frames and detections of the animal
        sorted_detections = sorted(animal.detectionDictionary.items())

        # example of how to get all frames where the animal was detected
        animal_frames = [frame for frame, _ in sorted_detections]

        # examples of how to skip animals without detections
        if len(animal_frames) == 0:
            continue

        # example of how to get massX position of the animal detections
        # in a numpy array and with the same order as animal_frames
        massX = np.array(
            [detection.massX for _, detection in sorted_detections]
        )
        # NOTE: if you want to access to head or tail points, you need to set
        # lightLoad=False when loading detections in the pool (see above)

        # example of how to compute speed along X axis
        frame_gaps = np.diff(np.array(animal_frames))
        vx = np.zeros_like(massX)
        vx[1:] = np.diff(massX) / frame_gaps

        # example of how to get the frames corresponding to an existing event
        # in the form of a dictionary (keys are frames, values are True)
        # {frame: True, ...}
        stop_frames = EventTimeLine(
            conn=connection,
            eventName="Stop",
            idA=animal.baseId,
        ).getDictionary()

        result[42] = True  # example of result dictionary

        # ================ END OF LOGIC ================

        # store your result in the event timeline and save it in database
        example_TL.reBuildWithDictionary(result)
        example_TL.endRebuildEventTimeLine(connection)

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
