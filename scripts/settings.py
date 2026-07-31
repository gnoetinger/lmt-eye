"""
@author: xmousset
"""

import logging
from typing import Any
from pathlib import Path
from abc import ABC, abstractmethod

import pandas as pd

from scripts.parameter_saver import ParameterSaver
from lmtanalysis.Animal import AnimalType
from lmtanalysis.Measure import oneMinute, oneDay


class GenericSettings(ABC):
    """Abstract base class for LMT-EYE settings.

    Subclasses must implement `get_default_settings`, `reset()`,
    `convert_in_str()` and `convert_from_str()`.

    Shared attributes
    -----------------
    night_begin : tuple[int, int]
        Hour and minute when the night begins (0-23, 0-59).
        Defaults to (20, 0).
    night_duration : tuple[int, int]
        Duration of the night in hours and minutes.
        Defaults to (12, 0).
    output_folder : Path or None
        Folder to save output reports. Defaults to None.
    report_color : str
        Column name used for color differentiation in graphs. Defaults to "RFID".
    report_x_axis : str
        Column name used for x-axis in graphs. Defaults to "START_TIME".
    """

    # Abstract methods
    # ----------------

    @staticmethod
    @abstractmethod
    def get_default_settings() -> dict[str, Any]:
        """Return the default settings as a dictionary.

        Must include at minimum the five shared keys:
        `night_begin`, `night_duration`, `output_folder`,
        `report_color`, `report_x_axis`.
        """
        pass

    @staticmethod
    @abstractmethod
    def convert_in_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert settings values to strings (JSON-serialisable).

        Must include at minimum the conversion of `output_folder`. Example of
        the expected minimum method:
        ```
        @staticmethod
        def convert_in_str(initial_dict):
            new_dict = initial_dict.copy()
            if new_dict["output_folder"] is not None:
                new_dict["output_folder"] = str(new_dict["output_folder"])
            return new_dict
        """
        pass

    @staticmethod
    @abstractmethod
    def convert_from_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert settings values from strings back to their types.

        Must include at minimum the conversion of `output_folder`. Example of
        the expected minimum method:
        ```
        @staticmethod
        def convert_from_str(initial_dict):
            new_dict = initial_dict.copy()
            if new_dict["output_folder"] is not None:
                new_dict["output_folder"] = Path(new_dict["output_folder"])
            return new_dict
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset shared attributes to their default values."""
        pass

    # Class methods
    # ----------------

    @classmethod
    def get_all_keys(cls) -> list[str]:
        """Return all settings names derived from `get_default_settings`."""
        return list(cls.get_default_settings().keys())

    # Instance methods
    # ----------------

    def __init__(self) -> None:
        """Initialise with default values and a ParameterSaver."""
        self.reset()
        logging.debug("LMT-EYE settings initialized.")
        self._saver = ParameterSaver()

    def as_dict(self) -> dict[str, Any]:
        """Return the current settings as a dictionary."""
        settings: dict[str, Any] = {}
        for key in self.__class__.get_all_keys():
            settings[key] = getattr(self, key)
        return settings

    def as_str_dict(self) -> dict[str, Any]:
        """Return the settings as a JSON-serialisable dictionary."""
        return self.__class__.convert_in_str(self.as_dict())

    def update_from_dict(self, settings_dict: dict[str, Any]) -> None:
        """Update settings from a (possibly partial) dictionary."""
        update_dict = self.as_dict()
        update_dict.update(settings_dict)
        for key in self.__class__.get_all_keys():
            setattr(self, key, update_dict[key])

    def save(self, file_path: Path) -> None:
        """Save the settings to a JSON file."""
        if self._saver is None:
            raise ValueError("No saver defined. Cannot save settings.")
        self._saver.reset()
        self._saver.set_values(self.as_str_dict())
        self._saver.save(file_path)
        logging.info(f"LMT-EYE settings saved to file: {file_path}")

    def load(self, file_path: Path) -> None:
        """Load the settings from a JSON file."""
        if self._saver is None:
            raise ValueError("No saver defined. Cannot load settings.")
        self.reset()
        self._saver.load(file_path)
        settings = self.__class__.convert_from_str(
            self._saver.get_parameters()
        )
        self.update_from_dict(settings)
        logging.info(f"LMT-EYE settings loaded from file: {file_path}")

    def as_html(self) -> str:
        """Return the current settings as an HTML table."""
        settings_str = self.as_str_dict()
        settings = self.as_dict()
        html = "<table border='1' cellpadding='4' cellspacing='0'>"
        html += (
            "<tr>"
            "<th>Name</th>"
            "<th>Type</th>"
            "<th>JSON value</th>"
            "</tr>"
        )
        for key in settings_str:
            html += (
                "<tr>"
                f"<td>{key}</td>"
                f"<td>{type(settings[key]).__name__}</td>"
                f"<td>{settings_str[key]}</td>"
                "</tr>"
            )
        html += "</table>"
        return html

    def get_plot_parameters(self, df: pd.DataFrame) -> dict[str, Any]:
        """Return Plotly color parameters for report graphs.

        **Generic example**: *{"color": "RFID", "category_orders": {"RFID":
        ["001", "002", "003"]}}*
        """
        if not hasattr(self, "report_color"):
            raise ValueError("Settings missing required attributes.")

        comparator = getattr(self, "report_color")

        if comparator not in df.columns:
            raise ValueError(
                f"report_color '{comparator}' not found in dataframe."
            )
        return {
            "color": comparator,
            "category_orders": {comparator: sorted(df[comparator].unique())},
        }

    def get_xlsx_parameters(self, df: pd.DataFrame) -> list[str]:
        """Return the column names used for the xlsx export.

        **Generic example**: *["RFID", "START_TIME"]*
        """
        if not hasattr(self, "report_color") or not hasattr(
            self, "report_x_axis"
        ):
            raise ValueError("Settings missing required attributes.")

        comparator = getattr(self, "report_color")
        x_axis = getattr(self, "report_x_axis")

        if comparator not in df.columns:
            raise ValueError(
                f"report_color '{comparator}' not found in dataframe."
            )
        xlsx_param = ["RFID", x_axis]
        if comparator != "RFID":
            xlsx_param.append(comparator)
        return xlsx_param


class AnalysisSettings(GenericSettings):
    """Manage settings for LMT database analyzer.

    Parameters
    ----------
    analysis_area : tuple of int or None, optional
        Area to be analyzed in the format (x_min, y_min, x_max, y_max) in
        centimeters (*cm*).
        Defaults to None (analyze the entire area).
    animal_type : AnimalType, optional
        Type of animal for event processing. Defaults to AnimalType.MOUSE.
    bin_rounding : bool, optional
        Whether to round the time bins to the nearest hour. If False, the time
        bins will be based on the first timestamp of the recording. Defaults to
        True.
    database_path : Path or None, optional
        Path to the database to analyze. If None, no analysis can be done.
        Defaults to None.
    display_activity : bool, optional
        Whether to display the activity reports in the results.
        Defaults to True.
    display_heatmap : bool, optional
        Whether to display the heatmap of the animals in the reports.
        Defaults to False.
    display_sensors : bool, optional
        Whether to display the sensors reports in the results.
        Defaults to False.
    display_trackplot : bool, optional
        Whether to display the trackplot of the animals in the reports.
        Defaults to False.
    events : set of str, optional
        Set of event names to analyze. By default, no event analysis is
        performed (empty set).
    filter_flickering : bool, optional
        Whether to filter the 'Flickering' event for animal activity.
        Defaults to False.
    filter_stop : bool, optional
        Whether to filter the 'Stop' event for animal activity.
        Defaults to False.
    event_min_duration : int, optional
        Whether to filter out all the events that are not long enough. All
        events that are at least this duration (in frames) will be kept, the
        others will be filtered out. This is only applied for event analysis.
        Filters like stop or flickering and events display in 'Activity'
        reports are not affected. Default value is 1, which means that no
        events will be filtered out based on duration.
    fps : int, optional
        Frame rate of the recording in *frames per second*. Defaults to 30.
    night_begin : tuple of int, optional
        Hour and minute when the night begins (0-23, 0-59).
        Defaults to (20, 0) (8 *p.m.*).
    night_duration : tuple of int, optional
        Duration of the night in hours and minutes.
        Defaults to (12, 0) (12 hours so from 8 *p.m.* to 8 *a.m.*).
    output_folder : Path or str or None, optional
        Folder to save the output reports. By default, prompts user to
        select folder ('manual selection').
    processing_limits : tuple of str, or None, optional
        Start and end of the processing period. Defaults to (None, None).
    processing_window : int, optional
        Load a maximum of 'processing_window' *frames* simultaneously. If the
        data is bigger than this window, the computation will be splitted into
        chunks of 'processing_window' size. Defaults to *2 592 000 frames (=1
        day)*.
    rebuild_events : bool, optional
        Whether to rebuild all the events to analyse in the database before
        analysis. If False, only missing events will be rebuilt. Defaults to
        False.
    time_window : int, optional
        Time window for data binning in *frames*. Defaults to *27 000 (= 15
        min)*.
    utc_offset : float, optional
        UTC offset in hours for correct timezone conversion (e.g. +9.0 for
        Tokyo time, +2.0 for Paris Summer time). Defaults to 0.0.
    report_x_axis : str, optional
        Column name to use for x-axis in graphs reports. Defaults to
        "START_TIME".
    report_color : str, optional
        Column name to use for color differentiation (legend) in graphs
        reports. Defaults to "RFID".

    To add another parameter, simply add it in both the `get_default_settings`
    and the `reset` methods of the class, all other methods will automatically
    handle it.
    If the parameter is not of type int, float, bool, None or str, (or list
    with these sub-types) you will need to add the conversion of the parameter
    in the `convert_in_str` and `convert_from_str` methods for saving and
    loading the settings in a JSON file.
    """

    @staticmethod
    def get_default_settings() -> dict[str, Any]:
        """Get the default settings values as a dictionary."""
        return {
            "analysis_area": None,
            "animal_type": AnimalType.MOUSE,
            "bin_rounding": True,
            "database_path": None,
            "display_activity": True,
            "display_heatmap": False,
            "display_sensors": False,
            "display_trackplot": False,
            "events": set(),
            "event_min_duration": 1,
            "filter_flickering": True,
            "filter_stop": True,
            "fps": 30,
            "processing_limits": (None, None),
            "processing_window": oneDay,
            "rebuild_events": False,
            "time_window": 15 * oneMinute,
            "utc_offset": 0.0,
            "night_begin": (20, 0),
            "night_duration": (12, 0),
            "output_folder": None,
            "report_color": "RFID",
            "report_x_axis": "START_TIME",
        }

    @staticmethod
    def convert_in_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert the dict settings values in string."""
        new_dict = initial_dict.copy()

        new_dict["animal_type"] = new_dict["animal_type"].name

        if isinstance(new_dict["events"], set):
            new_dict["events"] = list(new_dict["events"])

        if new_dict["database_path"] is not None:
            new_dict["database_path"] = str(new_dict["database_path"])

        if new_dict["output_folder"] is not None:
            new_dict["output_folder"] = str(new_dict["output_folder"])

        return new_dict

    @staticmethod
    def convert_from_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert the dict settings values from string to the correct type."""
        new_dict = new_dict = initial_dict.copy()

        new_dict["animal_type"] = AnimalType[new_dict["animal_type"]]

        if new_dict["events"] == [None]:
            new_dict["events"] = set()
        elif isinstance(new_dict["events"], list):
            new_dict["events"] = set(new_dict["events"])

        if new_dict["database_path"] is not None:
            new_dict["database_path"] = Path(new_dict["database_path"])

        if new_dict["output_folder"] is not None:
            new_dict["output_folder"] = Path(new_dict["output_folder"])

        return new_dict

    def reset(self):
        """Reset the settings to their initial values."""
        defaults = AnalysisSettings.get_default_settings()

        self.analysis_area: tuple[int, int, int, int] | None = defaults[
            "analysis_area"
        ]
        self.animal_type: AnimalType = defaults["animal_type"]
        self.bin_rounding: bool = defaults["bin_rounding"]
        self.database_path: Path | None = defaults["database_path"]
        self.display_activity: bool = defaults["display_activity"]
        self.display_heatmap: bool = defaults["display_heatmap"]
        self.display_sensors: bool = defaults["display_sensors"]
        self.display_trackplot: bool = defaults["display_trackplot"]
        self.events: set[str] = defaults["events"]
        self.event_min_duration: int = defaults["event_min_duration"]
        self.filter_flickering: bool = defaults["filter_flickering"]
        self.filter_stop: bool = defaults["filter_stop"]
        self.fps: int = defaults["fps"]
        self.processing_window: int = defaults["processing_window"]
        self.processing_limits: tuple[str | None, str | None] = defaults[
            "processing_limits"
        ]
        self.rebuild_events: bool = defaults["rebuild_events"]
        self.time_window: int = defaults["time_window"]
        self.utc_offset: float = defaults["utc_offset"]

        self.night_begin: tuple[int, int] = defaults["night_begin"]
        self.night_duration: tuple[int, int] = defaults["night_duration"]
        self.output_folder: Path | None = defaults["output_folder"]
        self.report_color: str = defaults["report_color"]
        self.report_x_axis: str = defaults["report_x_axis"]

    def logic_update(self):
        """Update the settings values based on the current settings. Useful,
        for example, to add events if filters are activated."""

        if self.display_activity:
            # need to filter flickering
            if self.filter_flickering:
                self.events.add("Flickering")

            # always needed for activity analysis
            self.events.add("Stop")
            self.events.add("Stop in contact")
            self.events.add("Stop isolated")
            self.events.add("Move isolated")
            self.events.add("Move in contact")

    def convert_processing_limits(
        self,
    ) -> tuple[int | pd.Timestamp | None, int | pd.Timestamp | None]:
        """Convert the processing limits from string to int or pd.Timestamp or
        None."""
        start, end = self.processing_limits

        if isinstance(start, str):
            try:
                start = int(start)
            except:
                start = pd.Timestamp(start)

        if isinstance(end, str):
            try:
                end = int(end)
            except:
                end = pd.Timestamp(end)

        return (start, end)


class ComparisonSettings(GenericSettings):
    """Manage settings for LMT analyses comparator.

    Parameters
    ----------
    analyses_path : list of Path
        List of paths to the analyses to compare.
    night_begin: tuple of int
        Hour and minute when the night begins (0-23, 0-59).
        Defaults to (20, 0) (8 *p.m.*).
    night_duration: tuple of int
        Duration of the night in hours and minutes.
        Defaults to (12, 0) (12 hours so from 8 *p.m.* to 8 *a.m.*).
    output_folder: Path | None
        The folder where the comparison results will be saved. If None, it will
        be saved next to the first listed analysis, with a name based on the
        comparator type. Default is None.

    To add another parameter, simply add it in both the `get_default_settings`
    and the `reset` methods of the class, all other methods will automatically
    handle it.
    """

    MAIN_TABLE = "main_complete_table_Download_data.xlsx"

    @staticmethod
    def get_default_settings() -> dict[str, Any]:
        """Get the default settings values as a dictionary."""
        return {
            "night_begin": (20, 0),
            "night_duration": (12, 0),
            "output_folder": None,
            "report_color": "RFID",
            "report_x_axis": "START_TIME",
        }

    @staticmethod
    def convert_in_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert the dict settings values in string."""
        new_dict = initial_dict.copy()

        if new_dict["output_folder"] is not None:
            new_dict["output_folder"] = str(new_dict["output_folder"])

        return new_dict

    @staticmethod
    def convert_from_str(initial_dict: dict[str, Any]) -> dict[str, Any]:
        """Convert the dict settings values from string to the correct type."""
        new_dict = initial_dict.copy()

        if new_dict["output_folder"] is not None:
            new_dict["output_folder"] = Path(new_dict["output_folder"])

        return new_dict

    def reset(self):
        """Reset the settings to their initial values."""
        defaults = ComparisonSettings.get_default_settings()

        self.night_begin: tuple[int, int] = defaults["night_begin"]
        self.night_duration: tuple[int, int] = defaults["night_duration"]
        self.output_folder: Path | None = defaults["output_folder"]
        self.report_color: str = defaults["report_color"]
        self.report_x_axis: str = defaults["report_x_axis"]

    @classmethod
    def get_common_columns_from_list(cls, path_list: list[Path]) -> list[str]:
        """Get common columns in all analyses."""
        common_columns: set[str] = set()
        for path in path_list:
            df = pd.read_excel(path / cls.MAIN_TABLE)
            if not common_columns:
                common_columns = set(df.columns)
            else:
                common_columns = common_columns.intersection(set(df.columns))
        if "Unnamed: 0" in common_columns:
            common_columns.remove("Unnamed: 0")
        if "ID" in common_columns:
            common_columns.remove("ID")
        return sorted(common_columns)

    def __init__(self, analyses_path: list[Path]):
        """Initialize the settings with default values."""
        self.analyses_path = analyses_path
        super().__init__()

    def get_common_columns(self) -> list[str]:
        """Get common columns in all analyses."""
        return self.get_common_columns_from_list(self.analyses_path)
