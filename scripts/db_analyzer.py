"""
@author: xmousset
"""

import logging
import sqlite3
from typing import Any, Callable
from pathlib import Path

import pandas as pd

from scripts.settings import AnalysisSettings
from scripts.events_rebuilder import EventsRebuilder
from scripts.reports_manager import HTMLReportManager
from scripts.df_constructor import DataframeConstructor
from scripts.tkinter_tools import (
    select_sqlite_file,
    select_folder,
)

from events.events_manager import get_modules_from_events_name
from reports import activity, event, overview, sensors, trajectory


class DatabaseAnalyzer:
    """Class to analyze LMT database, generate reports and save them to an
    output folder."""

    @staticmethod
    def get_informations(database_path: Path):
        """Get basic information about the experiment stored in the database.
        Returns a dictionary with keys:
            - 'n_animals': number of animals in the experiment.
            - 'start_time': start time of the experiment (pd.Timestamp).
            - 'end_time': end time of the experiment (pd.Timestamp).
            - 'duration': duration of the experiment (pd.Timedelta).
        """
        connection = sqlite3.connect(str(database_path))

        query = """
            SELECT
                COUNT(DISTINCT RFID) AS n_animals,
                (SELECT FRAMENUMBER FROM FRAME ORDER BY FRAMENUMBER ASC LIMIT 1) AS first_frame,
                (SELECT TIMESTAMP FROM FRAME ORDER BY FRAMENUMBER ASC LIMIT 1) AS first_timestamp,
                (SELECT FRAMENUMBER FROM FRAME ORDER BY FRAMENUMBER DESC LIMIT 1) AS last_frame,
                (SELECT TIMESTAMP FROM FRAME ORDER BY FRAMENUMBER DESC LIMIT 1) AS last_timestamp
            FROM ANIMAL;
        """
        cursor = connection.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        n_animals: int = result[0]
        start_frame: int = result[1]
        start_timestamp: int = result[2]
        end_frame: int = result[3]
        end_timestamp: int = result[4]
        start_time: pd.Timestamp = pd.to_datetime(start_timestamp, unit="ms")
        end_time: pd.Timestamp = pd.to_datetime(end_timestamp, unit="ms")
        duration: pd.Timedelta = end_time - start_time
        fps = (end_frame - start_frame) / duration.total_seconds()

        connection.close()

        info: dict[str, Any] = {
            "database_name": database_path.stem,
            "n_animals": n_animals,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "fps": fps,
        }
        return info

    def __init__(
        self,
        database_path: Path | str | None = None,
        settings: AnalysisSettings | None = None,
    ):
        """
        LMT-EYE analysis workflow for LMT database. Can rebuild events,
        generate dataframes and HTML reports.

        Parameters
        ----------
        database_path : Path, optional
            Path to the SQLite data file. If not provided, prompts user to
            select file.
        settings : AnalysisSettings, optional
            Analysis settings. If not provided, defaults to a new instance
            of AnalysisSettings.
        """
        if isinstance(database_path, str):
            database_path = Path(database_path)
        self.database_path = database_path
        if database_path is None:
            self.database_path = self.choose_sqlite_file()

        if settings is None:
            self.settings = AnalysisSettings()
        else:
            self.settings = settings

    def choose_sqlite_file(self):
        """Load the SQLite data file. If no file path is provided, prompts the
        user to select a file."""
        database_path = select_sqlite_file()
        if database_path is None:
            return
        self.database_path = database_path

    def set_output_folder(self, output_folder: Path | str | None = None):
        """Choose the output folder for the analysis reports. If no folder path
        is provided, prompts the user to select a folder."""
        output_folder = select_folder()
        if output_folder is None:
            return
        self.settings.output_folder = output_folder

    def rebuild_database(
        self, progress_callback: Callable[[int, int], None] | None = None
    ):
        """Rebuild events in the database according to the selected rebuild
        option.

        If progress_callback is provided, it should be a function that takes
        two integer arguments: the current progress value and the total value.
        The function will be called periodically during the rebuilding process
        to update the progress. Otherwise, progress will be printed to the
        console.
        """

        if self.database_path is None:
            raise ValueError("No database path provided for analysis.")

        connection = sqlite3.connect(self.database_path)

        rebuilder = EventsRebuilder(
            connection,
            self.settings.animal_type,
            None,  # rebuild from start of experiment
            None,  # rebuild until end of experiment
            self.settings.fps,
            self.settings.processing_window,
            self.settings.utc_offset,
        )

        self.settings.logic_update()
        if self.settings.rebuild_events:
            events_to_rebuild = self.settings.events
        else:
            events_to_rebuild = (
                self.settings.events - rebuilder.get_events_in_database()
            )

        modules = get_modules_from_events_name(events_to_rebuild)
        rebuilder.rebuild(modules, progress_callback)
        connection.close()

    def run_analysis(
        self, progress_callback: Callable[[int, int], None] | None = None
    ):
        """Run the analysis workflow, generating dataframes and HTML reports.
        Save the reports to the selected output folder.

        If progress_callback is provided, it should be a function that takes
        two integer arguments: the current progress value and the total value.
        The function will be called periodically during the rebuilding process
        to update the progress. Otherwise, progress will be printed to the
        console."""

        if self.database_path is None:
            raise ValueError("No database path provided for analysis.")

        self.settings.logic_update()
        self.settings.database_path = self.database_path

        connection = sqlite3.connect(self.database_path)
        repo_manager = HTMLReportManager()

        df_constructor = DataframeConstructor(
            connection=connection,
            bin_rounding=self.settings.bin_rounding,
            bin_window=self.settings.time_window,
            processing_window=self.settings.processing_window,
            processing_limits=self.settings.convert_processing_limits(),
            analysis_area=self.settings.analysis_area,
            fps=self.settings.fps,
            utc_offset=self.settings.utc_offset,
        )

        if not self.settings.events:
            all_event_df = None
            sorted_events = []
        else:
            all_event_df = pd.DataFrame()
            sorted_events = sorted(self.settings.events)

        total_steps = 1 + len(sorted_events)
        if self.settings.display_activity:
            total_steps += 1
        if self.settings.display_trajectory:
            total_steps += 1
        if self.settings.display_sensors:
            total_steps += 1
        progression: list = [0, total_steps, progress_callback]
        self.update_progression(*progression)

        # ACTIVITY
        # ----------------
        if self.settings.display_activity:
            activity_df = df_constructor.get_df_activity(
                self.settings.filter_flickering,
                self.settings.filter_stop,
            )
            activity.generic_reports(
                repo_manager,
                activity_df,
                self.settings,
            )
            progression[0] += 1
            self.update_progression(*progression)
        else:
            activity_df = None

        # TRAJECTORY
        # ----------------
        if self.settings.display_trajectory:
            trajectory_df = df_constructor.get_df_trajectory()
            trajectory.generic_reports(
                repo_manager,
                trajectory_df,
                self.settings,
            )
            trajectory_df = None  # avoid big memory usage
            progression[0] += 1
            self.update_progression(*progression)

        # EVENTS
        # ----------------
        if all_event_df is not None:
            for event_name in sorted_events:
                event_df = df_constructor.get_df_event(
                    event_name,
                    self.settings.event_min_duration,
                )

                hist_df = df_constructor.get_df_event_histogram(
                    event_name,
                    self.settings.event_min_duration,
                )
                event.generic_reports(
                    repo_manager,
                    event_df,
                    hist_df,
                    event_name,
                    self.settings,
                )
                all_event_df = pd.concat([all_event_df, event_df])
                progression[0] += 1
                self.update_progression(*progression)

        # SENSORS
        # ----------------
        if self.settings.display_sensors:
            sensors_df = df_constructor.get_df_sensors()
            sensors.generic_reports(
                repo_manager,
                sensors_df,
                self.settings,
            )
            progression[0] += 1
            self.update_progression(*progression)
        else:
            sensors_df = None

        # OVERVIEW
        # ----------------
        animals_df = df_constructor.get_df_animals()
        overview.generic_reports(
            repo_manager,
            animals_df,
            activity_df,
            all_event_df,
            sensors_df,
            self.settings,
        )
        progression[0] += 1
        self.update_progression(*progression)

        # OUTPUT
        # ----------------
        output_folder = self.get_output_folder()
        repo_manager.generate_local_output(output_folder)
        self.settings.save(output_folder / "settings.json")

        # results_df: list[pd.DataFrame | None] = [
        #     activity_df,
        #     all_event_df,
        #     sensors_df,
        #     animals_df,
        # ]

        # return results_df

    def get_output_folder(self) -> Path:
        """Get the output folder for the analysis reports. If no output folder
        is set, return the default output folder based on the database path."""

        if self.database_path is None:
            raise ValueError(
                "No database path provided, cannot determine output folder."
            )

        if self.settings.output_folder is not None:
            output_folder = self.settings.output_folder
        else:
            output_folder = self.database_path.parent

        output_folder = output_folder / (
            self.database_path.stem + " - analysis"
        )

        return output_folder

    def open_results(self):
        """Open the generated analysis output in the default web browser."""

        output_folder = self.get_output_folder()

        if output_folder.is_dir():
            HTMLReportManager.open_local_output(output_folder)
        else:
            logging.error(f"Output folder not found: {output_folder}")

    def update_progression(
        self,
        current_progression: int,
        max_progression: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Update the progress of the analysis comparison."""
        if progress_callback:
            progress_callback(current_progression, max_progression)
        else:
            print(
                f"Progress: {current_progression}/{max_progression} "
                f"({(current_progression/max_progression)*100:.1f}%)"
            )
