"""
@creation: 26-01-2026
@author: xmousset
"""

import sys
import os
import logging
import traceback
import subprocess
from types import ModuleType
from sqlite3 import Connection
from typing import Callable, Literal

import pandas as pd

from scripts.binner import Binner
from events.events_manager import sort_in_official_order

from lmtanalysis.Animal import AnimalPool
from lmtanalysis.AnimalType import AnimalType
from lmtanalysis.Event import Chronometer
from lmtanalysis.Measure import oneDay
from lmtanalysis import BuildDataBaseIndex, CheckWrongAnimal
from lmtanalysis.TaskLogger import TaskLogger
from lmtanalysis.EventTimeLineCache import (
    flushEventTimeLineCache,
    disableEventTimeLineCache,
)

from psutil import virtual_memory


class EventsRebuilder:
    def __init__(
        self,
        connection: Connection,
        animal_type: AnimalType = AnimalType.MOUSE,
        start: int | pd.Timestamp | None = None,
        end: int | pd.Timestamp | None = None,
        fps: int = 30,
        processing_window: int = oneDay,
        utc_offset: float = 0.0,
    ):
        """Class to handle the rebuilding of events in the database.

        Args:
            connection (Connection): SQLite database connection.
            animal_type (AnimalType): Type of animal for event processing.
            start (int | pd.Timestamp | None): Start limit for analysis.
                Can be in frames (int) or timestamps (pd.Timestamp).
            end (int | pd.Timestamp | None): End limit for analysis.
                Can be in frames (int) or timestamps (pd.Timestamp).
            fps (int): Frame rate of the recording in frames per second.
                Default is 30.
            processing_window (int): Processing window size in frames.
                Default is one day (in frames).
            utc_offset (float, optional): UTC offset in hours for correct
                timezone conversion (e.g. *+9.0* for Tokyo). Defaults to *0.0*.
        """
        self.conn = connection
        self.animal_type = animal_type

        last_framenumber, last_timestamp = Binner.get_last_frame(self.conn)
        self.binner = Binner(
            last_framenumber,
            last_timestamp,
            bin_size=processing_window,
            bin_rounding=False,
            limits=(start, end),
            fps=fps,
            utc_offset=utc_offset,
        )

    def get_events_in_database(self) -> set[str]:
        """Get the list of existing events in the SQLite database."""
        query = "SELECT DISTINCT NAME FROM EVENT ORDER BY NAME"

        cursor = self.conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()

        database_events = set([row[0] for row in results])
        return database_events

    def set_processing_window(self, processing_window: int):
        """Set the processing window (in *frames*) for processing."""
        self.binner.set_parameters(bin_size=processing_window)

    def get_processing_window(self, unit: Literal["FRAME", "TIME"] = "FRAME"):
        """Get the processing window (data chunk size)."""
        if unit == "FRAME":
            return self.binner.bin_size
        elif unit == "TIME":
            return self.binner.frames_to_timedelta(self.binner.bin_size)
        else:
            raise ValueError("Invalid unit. Choose 'FRAME' or 'TIME'.")

    def set_processing_limits(
        self,
        start: int | pd.Timestamp | None = None,
        end: int | pd.Timestamp | None = None,
    ):
        """Set the processing limits for data processing from frames or
        timestamps."""

        self.binner.set_parameters(start_limit=start, end_limit=end)

    def get_processing_limits(
        self, unit: Literal["FRAME", "TIME"] = "FRAME"
    ) -> tuple[int | pd.Timestamp, int | pd.Timestamp]:
        """Get the processing frame limits."""
        if unit == "FRAME":
            return self.binner.limits
        elif unit == "TIME":
            start_time = self.binner.frame_to_time(self.binner.limits[0])
            end_time = self.binner.frame_to_time(self.binner.limits[1])
            return (start_time, end_time)
        else:
            raise ValueError("Invalid unit. Choose 'FRAME' or 'TIME'.")

    def check_memory(self):
        """Check available system memory and disable event caching if
        necessary."""
        mem = virtual_memory()
        availableMemoryGB = mem.total / 1_000_000_000
        logging.info(f"Total memory on computer: (GB) {availableMemoryGB}")

        if availableMemoryGB < 10:
            logging.warning("Not enough memory to use cache load of events.")
            disableEventTimeLineCache()

    def _rebuild_window(
        self,
        modules: set[ModuleType],
        window: tuple[int, int],
        progress_callback: Callable[[int, int], None] | None = None,
        window_progress: tuple[int, int] = (0, 1),
    ):
        """Rebuild events in the specified time window using the specified
        modules.

        If a progress_callback is provided, it will be called with progress
        messages (used for updating the UI in app). Otherwise, progress will be
        printed to the console.
        """

        if not modules:
            logging.info("Empty module list. Flushing not necessary.")
            return

        CheckWrongAnimal.check(self.conn, window[0], window[1])

        animalPool = None
        flushEventTimeLineCache()
        logging.info(
            f"Caching load of animal detection for rebuilding "
            f"between frame {window[0]} and {window[1]}"
        )
        animalPool = AnimalPool()
        animalPool.loadAnimals(self.conn)
        animalPool.loadDetection(start=window[0], end=window[1])

        nb_modules = len(modules)
        progression = [
            nb_modules * window_progress[0],
            nb_modules * window_progress[1],
            progress_callback,
        ]
        self.update_progression(*progression)
        logging.info(
            f"Rebuilding {len(modules)} events in the database "
            f"between frame {window[0]} and {window[1]}"
        )
        for i, build_event_module in enumerate(
            sort_in_official_order(modules)
        ):

            event_chrono = Chronometer(build_event_module.__name__)
            module_name = build_event_module.__name__.split('.')[-1]
            logging.info(f"Processing {module_name}.py")
            build_event_module.reBuildEvent(
                connection=self.conn,
                file=None,
                tmin=window[0],
                tmax=window[1],
                pool=animalPool,
                animalType=self.animal_type,
            )
            logging.info(f"Rebuild time: {event_chrono.getTimeInS():.2f} s")

            progression[0] = i + 1 + nb_modules * window_progress[0]
            self.update_progression(*progression)

    def rebuild(
        self,
        modules: set[ModuleType],
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Rebuild events in the database from 'self.start' to 'self.end' using
        the specified modules.

        If a progress_callback is provided, it will be called with progress
        messages (used for updating the UI in app). Otherwise, progress will be
        printed to the console.
        """
        if not modules:
            logging.info("No modules to rebuild.")
            self.update_progression(1, 1, progress_callback)
            return

        self.check_memory()

        # update missing fields
        try:
            cursor = self.conn.cursor()
            query = "ALTER TABLE EVENT ADD METADATA TEXT"
            cursor.execute(query)
            self.conn.commit()
        except:
            logging.warning("METADATA field already exists")

        BuildDataBaseIndex.buildDataBaseIndex(self.conn, force=False)

        try:
            chrono = Chronometer("Flushing events")
            for module in modules:
                module.flush(self.conn)
            logging.info(f"Flushing time: {chrono.getTimeInS():.2f} s")

            processing_windows = self.binner.get_bin_iterator()
            nb_windows = len(processing_windows)
            for i, window in enumerate(processing_windows):
                self._rebuild_window(
                    modules,
                    window,
                    progress_callback,
                    window_progress=(i, nb_windows),
                )

        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            lines = traceback.format_exception(
                exc_type, exc_value, exc_traceback
            )
            error = "".join("!! " + line for line in lines)

            t = TaskLogger(self.conn)
            t.addLog(error)
            flushEventTimeLineCache()

            print(error, file=sys.stderr)
            raise Exception()

        self.update_progression(1, 1, progress_callback)
        logging.info("*** REBUILD FINISHED ***")

    @staticmethod
    def update_progression(
        current_progression: int,
        max_progression: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Update the progression of the rebuilding process."""
        if progress_callback:
            progress_callback(current_progression, max_progression)
        else:
            print(
                f"Progress: {current_progression}/{max_progression} "
                f"({(current_progression/max_progression)*100:.1f}%)"
            )
