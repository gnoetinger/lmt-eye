import logging
from pathlib import Path
from typing import Callable

import pandas as pd

from scripts.reports_manager import HTMLReportManager
from scripts.settings import ComparisonSettings
from reports import activity, event, overview


class AnalysesComparator:
    def __init__(
        self,
        settings: ComparisonSettings,
    ):
        self.settings = settings

    def get_common_events(self) -> list[str]:
        """Get the list of common events across all analyses.

        **WARNING**: the name has "_" (underscore) instead of " " (space).
        It is useful for getting table files but not the correct event name.
        """
        event_pattern = "_Event_overview_Download_data.xlsx"
        set_list: list[set[str]] = []
        for path in self.settings.analyses_path:
            event_set = set()
            for event_table in path.glob(f"*{event_pattern}"):
                event_set.add(event_table.name.removesuffix(event_pattern))
            set_list.append(event_set)

        common_events = set.intersection(*set_list)
        return sorted(common_events)

    def concatenate_dfs(
        self,
        table_name: str,
        suffix: str = "_complete_table_Download_data.xlsx",
    ) -> pd.DataFrame:
        """Concatenate a list of DataFrames into a single DataFrame."""
        dfs: list[pd.DataFrame] = []
        for path in self.settings.analyses_path:
            dfs.append(
                pd.read_excel(
                    path / (table_name + suffix), dtype={"RFID": str}
                )
            )
        return pd.concat(dfs, ignore_index=True)

    def compare_analyses(
        self,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Compare analyses based on the selected comparator and generate a
        report.

        If progress_callback is provided, it should be a function that takes
        two integer arguments: the current progress value and the total value.
        The function will be called periodically during the comparison process
        to update the progress. Otherwise, progress will be printed to the
        console.
        """
        if len(self.settings.analyses_path) == 0:
            raise ValueError("No database path provided for analysis.")

        repo_manager = HTMLReportManager()
        events = self.get_common_events()

        # progression: list = [0, 3 + len(events), progress_callback]
        progression: list = [0, 2, progress_callback]

        # ANIMAL INFO
        # ----------------

        animal_df = self.concatenate_dfs("main")
        self.update_progression(*progression)

        # ACTIVITY
        # ----------------

        activity_df = pd.merge(
            animal_df,
            self.concatenate_dfs("Activity"),
            on="RFID",
        )
        progression[0] += 1
        self.update_progression(*progression)

        activity.generic_reports(
            repo_manager,
            activity_df,
            self.settings,
        )
        progression[0] += 1
        self.update_progression(*progression)

        # EVENTS
        # ----------------
        all_event_df = None
        for event_table_name in self.get_common_events():

            event_df = pd.merge(
                animal_df,
                self.concatenate_dfs(event_table_name),
                on="RFID",
            )
            hist_df = pd.merge(
                animal_df,
                self.concatenate_dfs(
                    event_table_name,
                    suffix=(
                        "_Histogram_of_event_count_over_their_duration"
                        "_Download_data.xlsx"
                    ),
                ),
                on="RFID",
            )
            event.generic_reports(
                repo_manager,
                event_df,
                hist_df,
                event_table_name.replace("_", " "),
                self.settings,
            )

            progression[0] += 1
            self.update_progression(*progression)

            if event_df.empty:
                continue

            if all_event_df is None:
                all_event_df = event_df
            else:
                all_event_df = pd.concat([all_event_df, event_df])

        # OVERVIEW
        # ----------------
        overview.generic_reports(
            repo_manager,
            animal_df,
            activity_df,
            all_event_df,
            None,
            self.settings,
        )
        progression[0] += 1
        self.update_progression(*progression)

        output_folder = self.get_output_folder()
        repo_manager.generate_local_output(output_folder)
        self.settings.save(output_folder / "settings.json")

        # results_df: list[pd.DataFrame | None] = [
        #     activity_df,
        #     # heatmap_df,
        #     # trackplot_df,
        #     events_df,
        #     sensors_df,
        #     animal_df,
        # ]

        # return results_df

    def get_output_folder(self) -> Path:
        """Get the output folder of the generated reports."""

        if self.settings.output_folder is not None:
            output_folder = self.settings.output_folder.with_name(
                self.settings.output_folder.name
                + f" - {self.settings.report_color} comparison"
            )
        else:
            output_folder = (
                self.settings.analyses_path[0].parent
                / f"{self.settings.report_color} comparison"
            )

        return output_folder

    def open_results(self):
        """Open the generated analysis output in the default web browser."""

        output_folder = self.get_output_folder()

        if output_folder.is_dir():
            HTMLReportManager.open_local_output(output_folder)
        else:
            logging.error(f"Output folder not found: {output_folder}")

    @staticmethod
    def update_progression(
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
