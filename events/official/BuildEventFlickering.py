"""
Created on 25-11-2025
@author: Xavier Mousset
"""

import logging
import sqlite3
import numpy as np
from typing import Any

from lmtanalysis.TaskLogger import TaskLogger
from lmtanalysis.Parameters import get_scale_cm_over_px
from lmtanalysis.Event import deleteEventTimeLineInBase
from lmtanalysis.Animal import AnimalPool, AnimalType, EventTimeLine

# Event info
# ----------------

EVENTS_NAME = ["Flickering"]

EVENTS_DESCRIPTION = """
    Detects when the animal is flickering, i.e., when it is moving very fast
    but without much displacement (e.g., during a tremor or a seizure).
    Flickering is calculated on 19 frames (centered window, equal to 0.6 second)
    and with at least 7 frames (0.2 second).
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
    window: int = 19,
    event_min_frames: int = 6,
    flick_when_few_frames: bool = False,
):
    """
    Rebuilds the 'Flickering' events for all animals in the database within a
    specified time window.

    Flickering is calculated on 19 frames (centered window, equal to 0.6
    second) and with at least 7 frames (0.2 second).

    Parameters
    ----------
    window : int, optional
        The size of the rolling window (in frames) used to compute flickering
        events. Must be at least 7. Default is 19 (0.6 second).
    event_min_frames : int, optional
        The minimum number of frames required to consider a flickering event.
        Default is 6.
    flick_when_few_frames : bool, optional
        When the minimum number of frames is not reached (< event_min_frames),
        define if it must be considered as a flickering or not. Default is
        False (i.e., small numbers of frames are not considered a flickering
        event).
    """

    # Inputs errors
    # ----------------
    if window < 7:
        raise ValueError("Minimum window size for flickering is 7 frames.")

    # Parameters
    # ----------------
    CM_OVER_PX = get_scale_cm_over_px(animalType)

    min_speed_2 = (1.6 / CM_OVER_PX) ** 2
    # minimum value for the max_speed of the 'window' interval in cm/frame
    speed_displacement_diff_2 = (0.7 / CM_OVER_PX) ** 2
    # minimum value for the difference between mean_speed and displacement
    # of the 'window' interval in cm/frame

    half_w = window // 2
    left_w = half_w
    right_w = half_w
    if window % 2 == 0:
        right_w = right_w - 1

    if pool is None:
        pool = AnimalPool()
        pool.loadAnimals(connection)
        pool.loadDetection(start=tmin, end=tmax)

    # Events creation for each animal
    # ----------------
    for animal_key in pool.animalDictionary.keys():

        flickeringTimeLine = EventTimeLine(
            conn=connection,
            eventName=EVENTS_NAME[0],
            idA=animal_key,
            idB=None,
            idC=None,
            idD=None,
            loadEvent=False,
            minFrame=tmin,
            maxFrame=tmax,
        )

        result = {}

        animal = pool.animalDictionary[animal_key]

        # ================ Flickering logic ================

        animal_frames = np.array(sorted(animal.detectionDictionary.keys()))
        if animal_frames.size == 0:
            continue

        # compute speed and acceleration
        frame_gaps = np.diff(animal_frames)
        massX = np.array(
            [animal.detectionDictionary.get(f).massX for f in animal_frames]
        )
        massY = np.array(
            [animal.detectionDictionary.get(f).massY for f in animal_frames]
        )

        vx = np.zeros_like(massX)
        vy = np.zeros_like(massY)
        vx[1:] = np.diff(massX) / frame_gaps
        vy[1:] = np.diff(massY) / frame_gaps

        # detect flickering
        for idx, f in enumerate(animal_frames[left_w:-right_w], start=left_w):
            f_key = int(f)

            # ensure to not take big frame gaps
            local_lw = left_w
            local_rw = right_w
            frame_ref = animal_frames[idx]
            while (
                local_lw > 0
                and animal_frames[idx - local_lw] < frame_ref - left_w
            ):
                local_lw -= 1
            while (
                local_rw > 0
                and animal_frames[idx + local_rw] > frame_ref + right_w
            ):
                local_rw -= 1

            # minimum number of frames required
            if local_lw + local_rw < event_min_frames:
                if flick_when_few_frames:
                    result[f_key] = True
                continue

            start = idx - local_lw
            end = idx + local_rw
            local_vx = vx[start : end + 1]
            local_vy = vy[start : end + 1]

            speed_2 = local_vx**2 + local_vy**2
            max_speed_2 = np.max(speed_2)
            mean_speed_2 = np.mean(speed_2)
            displacement_2 = np.mean(local_vx) ** 2 + np.mean(local_vy) ** 2

            # criteria for flickering
            if (
                max_speed_2 > min_speed_2
                and mean_speed_2 - displacement_2 > speed_displacement_diff_2
            ):
                result[f_key] = True

        # ================ End of Flickering logic ================

        # DO NOT MODIFY
        # ----------------
        flickeringTimeLine.reBuildWithDictionary(result)
        flickeringTimeLine.endRebuildEventTimeLine(connection)

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
