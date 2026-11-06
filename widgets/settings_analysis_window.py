import logging
from pathlib import Path

import pandas as pd

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QWidget,
)

from events.events_manager import OFFICIAL_EVENTS, CUSTOM_EVENTS
from scripts.settings import AnalysisSettings
from mcp_server import get_controller

from widgets.pyqt6_tools import get_btn_style
from widgets.area_selection import AreaSelectionWindow
from widgets.event_selection import EventSelectionWindow

from lmtanalysis.Animal import AnimalType


class AnalysisSettingsWindow(QDialog):
    """Dialog to edit LMT database analyzer settings."""

    SAVING_PATH = Path.home() / "documents" / "LMT-EYE_settings"
    SAVING_PATH.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_default_settings():
        """Load default settings if available."""

        settings = AnalysisSettings()

        default_path = (
            AnalysisSettingsWindow.SAVING_PATH / "default_settings.json"
        )

        if default_path.is_file():
            settings.load(default_path)
        else:
            logging.info("No default settings set by user.")

        return settings

    def __init__(self, parent: QWidget | None):
        """Initialize the settings window by loading default settings."""
        super().__init__(parent)
        self.setWindowTitle("LMT-EYE - Analysis Settings")

        self.settings = self.load_default_settings()
        self.rebuild_only = False
        self._init_ui()

    def _init_ui(self):
        form = QFormLayout()

        # ================ OUTPUT FOLDER ================

        # output_folder
        if self.settings.output_folder is None:
            output_text = ""
        else:
            output_text = str(self.settings.output_folder)

        self.output_folder_edit = QLineEdit(output_text)
        self.output_folder_edit.setReadOnly(True)
        self.output_folder_edit.setPlaceholderText("same folder as database")
        self.output_folder_edit.setToolTip(
            "Folder where analysis results will be saved."
        )
        out_btn = QPushButton("Browse")
        btn_style = get_btn_style(txt_color="white", bg_color="black")
        out_btn.setStyleSheet(btn_style)
        out_btn.setFixedWidth(80)
        out_btn.clicked.connect(self.select_output_folder)

        out_row = QHBoxLayout()
        out_row.addWidget(self.output_folder_edit)
        out_row.addWidget(out_btn)

        form.addRow("<b>Output Folder</b>", out_row)

        # ================ ANIMAL TYPE ================

        # animal_type
        self.animal_type_box = QComboBox()
        self.animal_type_box.setToolTip(
            "Type of animals used in the experiment."
        )
        options = [animal_type.name for animal_type in AnimalType]
        self.animal_type_box.addItems(options)
        current_type = self.settings.animal_type.name
        if current_type in options:
            self.animal_type_box.setCurrentText(current_type)
        else:
            logging.warning(f"Animal type '{current_type}' is not available.")
            self.animal_type_box.setCurrentText("ERROR")

        # row layout
        animal_type_row = QHBoxLayout()
        animal_type_row.addWidget(self.animal_type_box)
        animal_type_row.addStretch(1)

        form.addRow("<b>Animal type</b>", animal_type_row)
        form.addRow(self.Qhline())

        # ================ REPORTS OPTIONS ================

        # display_activity
        self.activity_cb = QCheckBox()
        self.activity_cb.setToolTip(
            "Whether to display the activity reports in the results."
        )
        self.activity_cb.setChecked(self.settings.display_activity)

        # display_heatmap
        self.heatmap_cb = QCheckBox()
        self.heatmap_cb.setToolTip(
            "Whether to display the heatmap reports in the results.\n"
            "Could drastically increase memory usage and processing time."
        )
        self.heatmap_cb.setChecked(self.settings.display_heatmap)

        # display_trackplot
        self.trackplot_cb = QCheckBox()
        self.trackplot_cb.setToolTip(
            "Whether to display the trackplot reports in the results.\n"
            "Could drastically increase memory usage and processing time."
        )
        self.trackplot_cb.setChecked(self.settings.display_trackplot)

        # display_sensors
        self.sensors_cb = QCheckBox()
        self.sensors_cb.setToolTip(
            "Whether to display the sensors reports in the results."
        )
        self.sensors_cb.setChecked(self.settings.display_sensors)

        # row layout
        reports_options_row = QHBoxLayout()
        reports_options_row.addWidget(QLabel("Activity:"))
        reports_options_row.addWidget(self.activity_cb)
        reports_options_row.addStretch(1)
        reports_options_row.addWidget(QLabel("Heatmap:"))
        reports_options_row.addWidget(self.heatmap_cb)
        reports_options_row.addStretch(1)
        reports_options_row.addWidget(QLabel("Trackplot:"))
        reports_options_row.addWidget(self.trackplot_cb)
        reports_options_row.addStretch(1)
        reports_options_row.addWidget(QLabel("Sensors:"))
        reports_options_row.addWidget(self.sensors_cb)
        reports_options_row.addStretch(1)

        form.addRow("<b>Reports</b>", reports_options_row)
        form.addRow(self.Qhline())

        # ================ EVENTS ================
        official, custom, _ = self.get_events_from_settings()
        self.selected_events: dict[str, set[str]] = {
            "official": official,
            "custom": custom,
        }

        # events (official)
        btn_style = get_btn_style(txt_color="white", bg_color="blue")
        self.select_official_events_btn = QPushButton("Official Events")
        self.select_official_events_btn.setToolTip(
            "Select events to rebuild and analyse in the analysis process."
        )
        self.select_official_events_btn.setStyleSheet(btn_style)
        self.select_official_events_btn.setFixedWidth(150)
        self.select_official_events_btn.clicked.connect(
            self.on_select_official_events
        )

        # events (custom)
        btn_style = get_btn_style(txt_color="white", bg_color="blue")
        self.select_custom_events_btn = QPushButton("Custom Events")
        self.select_custom_events_btn.setToolTip(
            "Select events to rebuild and analyse in the analysis process "
            "among custom events\n (not official, but already existing in the "
            "events/custom folder in the form of 'BuildEvent___.py')."
        )
        self.select_custom_events_btn.setStyleSheet(btn_style)
        self.select_custom_events_btn.setFixedWidth(150)
        self.select_custom_events_btn.clicked.connect(
            self.on_select_custom_events
        )

        # events (written)
        self.written_event_edit = QLineEdit()
        self.written_event_edit.setPlaceholderText("no annotated events")
        self.written_event_edit.setToolTip(
            "Enter annotated event names to be included in the analysis.\n"
            "Separate multiple events with commas. (e.g.: Event1, Event2, "
            "Event3)\n"
            "These events came from LMT software manual annotations and, "
            "therefore, cannot be rebuilt.\n"
            "If they exist in the database, they will be included in the "
            "analysis.\n"
            "If they do not exist in the database, they will be ignored."
        )

        # rebuild_events
        self.rebuild_box = QCheckBox()
        self.rebuild_box.setToolTip(
            "Whether to rebuild all selected events in the database before "
            "analysis (Checked)\n or to rebuild only the events that do not "
            "exist in the database (Unchecked).\n Unchecked is faster."
        )
        self.rebuild_box.setChecked(self.settings.rebuild_events)

        # rows layout
        events_row = QHBoxLayout()
        events_row.addStretch(1)
        events_row.addWidget(self.select_official_events_btn)
        events_row.addStretch(1)
        events_row.addWidget(self.select_custom_events_btn)
        events_row.addStretch(1)
        events_row.addWidget(QLabel("Rebuild:"))
        events_row.addWidget(self.rebuild_box)

        written_row = QHBoxLayout()
        written_row.addWidget(self.written_event_edit)

        form.addRow("<b>Events</b>", events_row)
        form.addRow("<b>Annotated events</b>", written_row)
        form.addRow(self.Qhline())

        # ================ ACTIVITY FILTERS ================

        # filter_flickering
        self.flickering_cb = QCheckBox()
        self.flickering_cb.setToolTip(
            "Whether to filter the 'Flickering' event for animal activity.\n"
            "If enabled, all frames containing a 'Flickering' event will be "
            "excluded from the activity analysis."
        )
        self.flickering_cb.setChecked(self.settings.filter_flickering)

        # filter_stop
        self.stop_cb = QCheckBox()
        self.stop_cb.setToolTip(
            "Whether to filter the 'Stop' event for animal activity.\n"
            "If enabled, all frames containing a 'Stop' event will be "
            "excluded from the activity analysis."
        )
        self.stop_cb.setChecked(self.settings.filter_stop)

        # row layout
        activity_filters_row = QHBoxLayout()
        activity_filters_row.addStretch(1)
        activity_filters_row.addWidget(QLabel("Flickering:"))
        activity_filters_row.addWidget(self.flickering_cb)
        activity_filters_row.addStretch(1)
        activity_filters_row.addWidget(QLabel("Stop:"))
        activity_filters_row.addWidget(self.stop_cb)
        activity_filters_row.addStretch(1)

        form.addRow("<b>Activity filters</b>", activity_filters_row)

        # ================ EVENT FILTERS ================

        # event_minimal_duration
        self.event_duration_filter_spin = QSpinBox()
        self.event_duration_filter_spin.setToolTip(
            "Whether to filter out all the events that are not long enough.\n"
            "All events that are shorter or equal to this duration (in "
            "frames) will be filtered out from the analysis (this does not "
            "affect the database).\nThis is only applied for event analysis. "
            "Filters like stop or flickering and events display in "
            "<i>Activity</i> reports are not affected.\nDefault value is 0, "
            "which means that no events will be filtered out."
        )
        self.event_duration_filter_spin.setRange(0, 180)
        self.event_duration_filter_spin.setMinimumWidth(75)

        event_filters_row = QHBoxLayout()
        event_filters_row.addStretch(1)
        event_filters_row.addWidget(QLabel("Remove event <span>&le;</span>"))
        event_filters_row.addWidget(self.event_duration_filter_spin)
        event_filters_row.addWidget(QLabel("<i>frames</i>"))

        event_filters_row.addStretch(1)
        form.addRow("<b>Event filter</b>", event_filters_row)

        # ================ AREA FILTERING ================

        btn_style = get_btn_style(txt_color="white", bg_color="blue")
        self.select_area_btn = QPushButton("Select Area")
        self.select_area_btn.setToolTip(
            "Select the area to be analyzed in the analysis process."
        )
        self.select_area_btn.setStyleSheet(btn_style)
        self.select_area_btn.setFixedWidth(130)
        self.select_area_btn.clicked.connect(self.on_select_area)

        self.selected_area_label = QLabel()
        self._update_area_label()

        area_row = QHBoxLayout()
        area_row.addWidget(
            self.select_area_btn, alignment=Qt.AlignmentFlag.AlignCenter
        )
        area_row.addStretch(1)
        area_row.addWidget(
            self.selected_area_label, alignment=Qt.AlignmentFlag.AlignCenter
        )
        area_row.addStretch(1)

        form.addRow("<b>Area filter</b>", area_row)
        form.addRow(self.Qhline())

        # ================ TIME, PROCESSING and FPS ================

        # time_window (frames and minutes)
        self.time_window_frames = QSpinBox()
        self.time_window_frames.setToolTip(
            "Defines the binning of datas for the analysis (in frames).\n"
            "TIP: for a bin size smaller than 1 minute, change this value "
            "without modifying the minutes value (it will stay as 1 minute, "
            "but it is the frames value that will be used).\nWARNING: app may "
            "crash if there is only 1 bin for the whole experiment, so choose "
            "a bin size smaller than the experiment duration."
        )
        self.time_window_frames.setRange(1, 100_000_000)

        self.time_window_minutes = QDoubleSpinBox()
        self.time_window_minutes.setToolTip(
            "Defines the binning of datas for the analysis (in minutes).\n"
            "TIP: for a bin size smaller than 1 minute, change the frames "
            "value.\nWARNING: app may crash if there is only 1 bin for the "
            "whole experiment, so choose a bin size smaller than the "
            "experiment duration."
        )
        self.time_window_minutes.setDecimals(0)
        self.time_window_minutes.setRange(0, 100_000)

        # processing_window (frames and minutes)
        self.process_window_frames = QSpinBox()
        self.process_window_frames.setToolTip(
            "Defines the time window to consider for each processing step "
            "(in frames).\nUseful if the analysis is very long and needs to "
            "be processed in chunks.\n"
            "DO NOT IMPACT ANALYSIS RESULTS."
        )
        self.process_window_frames.setRange(1, 100_000_000)
        self.process_window_frames.setStyleSheet("color: grey;")

        self.process_window_hours = QDoubleSpinBox()
        self.process_window_hours.setToolTip(
            "Defines the time window to consider for each processing step "
            "(in hours).\nUseful if the analysis is very long and needs to "
            "be processed in chunks.\n"
            "DO NOT IMPACT ANALYSIS RESULTS."
        )
        self.process_window_hours.setDecimals(0)
        self.process_window_hours.setRange(0, 10_000)
        self.process_window_hours.setStyleSheet("color: grey;")

        # bin_rounding
        self.bin_rounding_cb = QCheckBox()
        self.bin_rounding_cb.setToolTip(
            "Whether to round bins in order to match round hours for the "
            "analysis.\n"
            "Example with 15 minutes bins and an experiment start at 12h07: \n"
            "- ENABLED: bins will be 12h00, 12h15, 12h30, 12h45, etc\n"
            "- DISABLED: bins will be 12h07, 12h22, 12h37, 12h52, etc.\n"
            "Rounding bins can make analysis results easier to read and "
            "compare between experiments.\n"
            "Note: if enabled, the first bin will start before the start of "
            "the experiment\n (e.g. 12h00 in the previous example), and not "
            "at the experiment start (e.g. 12h07 in the previous example).\n"
            "This leads to a first bin with less data than the others."
        )
        self.bin_rounding_cb.setChecked(self.settings.bin_rounding)

        # fps
        self.fps_spin = QSpinBox()
        self.fps_spin.setToolTip(
            "Frames per second of the recording.\n"
            "DO NOT MODIFY UNLESS YOU KNOW WHAT YOU ARE DOING."
        )
        self.fps_spin.setRange(1, 60)
        self.fps_spin.setMinimumWidth(75)
        self.fps_spin.setStyleSheet("color: grey;")

        # updates frames when times are changed, and vice versa
        self.time_window_frames.valueChanged.connect(
            self._on_time_frames_changed
        )
        self.time_window_minutes.valueChanged.connect(
            self._on_time_minutes_changed
        )
        self.process_window_frames.valueChanged.connect(
            self._on_process_frames_changed
        )
        self.process_window_hours.valueChanged.connect(
            self._on_process_hours_changed
        )
        self.fps_spin.valueChanged.connect(self._on_fps_changed)

        # layout for time, processing and fps
        time_row = QHBoxLayout()
        time_row.addStretch(1)
        time_row.addWidget(QLabel("Frames:"))
        time_row.addWidget(self.time_window_frames)
        time_row.addStretch(1)
        time_row.addWidget(QLabel("Minutes:"))
        time_row.addWidget(self.time_window_minutes)
        time_row.addStretch(1)
        time_row.addWidget(QLabel("Round bins:"))
        time_row.addWidget(self.bin_rounding_cb)
        time_row.addStretch(1)
        form.addRow("<b>Binning</b>", time_row)

        proc_row = QHBoxLayout()
        proc_row.addStretch(1)
        proc_frames_label = QLabel("Frames:")
        proc_frames_label.setStyleSheet("color: grey;")
        proc_row.addWidget(proc_frames_label)
        proc_row.addWidget(self.process_window_frames)
        proc_row.addStretch(1)
        proc_hours_label = QLabel("Hours:")
        proc_hours_label.setStyleSheet("color: grey;")
        proc_row.addWidget(proc_hours_label)
        proc_row.addWidget(self.process_window_hours)
        proc_row.addStretch(1)
        form.addRow(
            "<span style='color: grey;'><b>Processing</b></span>", proc_row
        )

        fps_row = QHBoxLayout()
        fps_row.addStretch(1)
        fps_label = QLabel("FPS:")
        fps_label.setStyleSheet("color: grey;")
        fps_row.addWidget(fps_label)
        fps_row.addWidget(self.fps_spin)
        fps_row.addStretch(1)
        form.addRow("<span style='color: grey;'><b>FPS</b></span>", fps_row)

        form.addRow(self.Qhline())

        # ================ NIGHT TIME ================

        # night_begin
        h, m = self.settings.night_begin
        self.night_begin_edit = QLineEdit(f"{h:02d}:{m:02d}")
        self.night_begin_edit.setToolTip(
            "Define when the night cycle begins (HH:MM, e.g. 20:00).\n"
            "Only used to display a shadow on graphs during night hours."
        )
        self.night_begin_edit.setFixedWidth(45)

        # night_duration
        h, m = self.settings.night_duration
        self.night_duration_edit = QLineEdit(f"{h:02d}:{m:02d}")
        self.night_duration_edit.setToolTip(
            "Define the night cycle duration (HH:MM, e.g. 12:00).\n"
            "Only used to display a shadow on graphs during night hours."
        )
        self.night_duration_edit.setFixedWidth(45)

        # night_end
        end_total_min = (
            self.settings.night_begin[0] * 60
            + self.settings.night_begin[1]
            + self.settings.night_duration[0] * 60
            + self.settings.night_duration[1]
        ) % (24 * 60)
        h, m = end_total_min // 60, end_total_min % 60
        self.night_end_edit = QLineEdit(f"{h:02d}:{m:02d}")
        self.night_end_edit.setToolTip(
            "Define when the night cycle ends (HH:MM, e.g. 08:00).\n"
            "Only used to display a shadow on graphs during night hours."
        )
        self.night_end_edit.setFixedWidth(45)

        # connect signals to update night end
        self.night_begin_edit.textChanged.connect(self._on_night_begin_changed)
        self.night_duration_edit.textChanged.connect(
            self._on_night_duration_changed
        )
        self.night_end_edit.textChanged.connect(self._on_night_end_changed)

        # row layout
        night_row = QHBoxLayout()
        night_row.addStretch(1)
        night_row.addWidget(QLabel("Begin:"))
        night_row.addWidget(self.night_begin_edit)
        night_row.addStretch(1)
        night_row.addWidget(QLabel("End:"))
        night_row.addWidget(self.night_end_edit)
        night_row.addStretch(1)
        night_row.addWidget(QLabel("Duration:"))
        night_row.addWidget(self.night_duration_edit)
        night_row.addStretch(1)

        form.addRow("<b>Night time</b>", night_row)

        # ================ UTC TIME ZONE ================

        # utc_offset
        self.utc_offset_spin = QDoubleSpinBox()
        self.utc_offset_spin.setToolTip(
            "Define the UTC offset in hours for correct timezone conversion.\n"
            "For example, +1 for Paris, +9 for Tokyo or +5.75 for Kathmandu."
        )
        self.utc_offset_spin.setRange(-12.0, 14.0)
        self.utc_offset_spin.setMinimumWidth(75)

        utc_row = QHBoxLayout()
        utc_row.addStretch(1)
        utc_row.addWidget(QLabel("UTC offset (h):"))
        utc_row.addWidget(self.utc_offset_spin)
        utc_row.addStretch(1)

        form.addRow("<b>Time Zone</b>", utc_row)
        form.addRow(self.Qhline())

        # ================ PROCESSING LIMITS (start, end) ================

        # processing_limits (start)
        self.start_edit = QLineEdit()
        self.start_edit.setToolTip(
            "Can be either a FRAMENUMBER (integer) "
            "or a TIMESTAMP (YYYY-MM-DD HH:MM:SS)"
        )
        self.start_edit.setPlaceholderText("first frame")
        self.start_edit.setMinimumHeight(30)

        # processing_limits (end)
        self.end_edit = QLineEdit()
        self.end_edit.setToolTip(
            "Can be either a FRAMENUMBER (integer) "
            "or a TIMESTAMP (YYYY-MM-DD HH:MM:SS)"
        )
        self.end_edit.setPlaceholderText("last frame")
        self.end_edit.setMinimumHeight(30)

        # connect signals to verify processing limits
        self.start_edit.textChanged.connect(self._on_processing_limits_changed)
        self.end_edit.textChanged.connect(self._on_processing_limits_changed)

        # row layout
        limits_row = QHBoxLayout()
        limits_row.addWidget(QLabel("Start:"))
        limits_row.addWidget(self.start_edit)
        limits_row.addWidget(QLabel("End:"))
        limits_row.addWidget(self.end_edit)

        # timestamp format example
        example_label = QLabel(
            "either a FRAMENUMBER or a TIMESTAMP (e.g. YYYY-MM-DD HH:MM:SS)"
        )
        example_label.setStyleSheet(
            "font-size: 12px; color: #666; font-style: italic;"
        )

        limits_infos_row = QHBoxLayout()
        limits_infos_row.addWidget(
            example_label, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        # row layout
        form.addRow("<b>Processing limits</b>", limits_row)
        form.addRow(limits_infos_row)
        form.addRow(self.Qhline())

        # ================ LOCAL MCP SERVER ================

        # not an analysis parameter: applied immediately and saved in
        # mcp_settings.json, whatever button is used to close this window
        self.mcp_cb = QCheckBox("Enable local MCP server")
        self.mcp_cb.setToolTip(
            "Let MCP clients (Claude, ...) read LMT-EYE data through a\n"
            "local server (http://127.0.0.1 only). Applied immediately."
        )
        self.mcp_cb.setChecked(get_controller().settings.enabled)
        self.mcp_cb.toggled.connect(self.on_mcp_toggled)

        mcp_row = QHBoxLayout()
        mcp_row.addWidget(self.mcp_cb)
        mcp_row.addStretch(1)

        form.addRow("<b>MCP server</b>", mcp_row)
        form.addRow(self.Qhline())

        # ================ SETTINGS BUTTONS ================

        btn_style = get_btn_style(size=13, txt_color="white", bg_color="black")

        # load settings
        self.load_settings_btn = QPushButton("Load settings")
        self.load_settings_btn.setToolTip("Load settings from a JSON file.")
        self.load_settings_btn.setStyleSheet(btn_style)
        self.load_settings_btn.setFixedWidth(130)
        self.load_settings_btn.clicked.connect(self.on_load_settings)

        # save settings
        self.save_settings_btn = QPushButton("Save settings")
        self.save_settings_btn.setToolTip(
            "Save current settings to a JSON file."
        )
        self.save_settings_btn.setStyleSheet(btn_style)
        self.save_settings_btn.setFixedWidth(130)
        self.save_settings_btn.clicked.connect(self.on_save_settings)

        # set default settings
        self.default_settings_btn = QPushButton("Define as default")
        self.default_settings_btn.setToolTip(
            "Save current settings as default."
        )
        self.default_settings_btn.setStyleSheet(btn_style)
        self.default_settings_btn.setFixedWidth(130)
        self.default_settings_btn.clicked.connect(self.on_default_settings)

        # row layout
        settings_row = QHBoxLayout()
        settings_row.addStretch(1)
        settings_row.addWidget(self.load_settings_btn)
        settings_row.addWidget(self.save_settings_btn)
        settings_row.addWidget(self.default_settings_btn)
        settings_row.addStretch(1)

        form.addRow(settings_row)
        form.addRow(self.Qhline())

        # ================ VALIDATION BUTTONS ================

        # process
        btn_style = get_btn_style(txt_color="white", bg_color="green")
        ok_btn = QPushButton("Process")
        ok_btn.setFixedWidth(100)
        ok_btn.setStyleSheet(btn_style)
        ok_btn.clicked.connect(self.on_accept)

        # cancel
        btn_style = get_btn_style(txt_color="white", bg_color="red")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setStyleSheet(btn_style)
        cancel_btn.clicked.connect(self.on_reject)

        # rebuild only
        btn_style = get_btn_style(size=13, bold=False)
        rebuild_btn = QPushButton("Rebuild only")
        rebuild_btn.setToolTip(
            "Force the rebuild of all events without launching the analysis.\n"
            "Always consider the 'Rebuild' tick box as ticked."
        )
        rebuild_btn.setFixedWidth(100)
        rebuild_btn.setStyleSheet(btn_style)
        rebuild_btn.clicked.connect(self.on_rebuild_only)

        # row layout
        validation_row = QHBoxLayout()
        validation_row.addStretch(2)
        validation_row.addWidget(ok_btn)
        validation_row.addWidget(cancel_btn)
        validation_row.addStretch(1)
        validation_row.addWidget(rebuild_btn)

        form.addRow(validation_row)

        self.setLayout(form)
        ok_btn.setFocus()
        self._update_ui_from_settings()

    # ================ UI x Settings ================

    def _update_ui_from_settings(self):
        """Update UI elements based on LMT-EYE settings."""
        settings = self.settings.as_str_dict()

        self.start_edit.setText(settings["processing_limits"][0])
        self.end_edit.setText(settings["processing_limits"][1])
        self._on_processing_limits_changed()
        self.output_folder_edit.setText(settings["output_folder"])

        official, custom, written = self.get_events_from_settings()
        self.selected_events["official"] = official
        self.selected_events["custom"] = custom
        self.selected_events["written"] = written
        self.written_event_edit.setText(", ".join(written))

        self.animal_type_box.setCurrentText(self.settings.animal_type.name)
        self.sensors_cb.setChecked(self.settings.display_sensors)
        self.activity_cb.setChecked(self.settings.display_activity)
        self.heatmap_cb.setChecked(self.settings.display_heatmap)
        self.trackplot_cb.setChecked(self.settings.display_trackplot)
        self.flickering_cb.setChecked(self.settings.filter_flickering)
        self.stop_cb.setChecked(self.settings.filter_stop)
        self.event_duration_filter_spin.setValue(
            self.settings.event_min_duration - 1
        )
        self.time_window_frames.setValue(self.settings.time_window)
        self._on_time_frames_changed()  # to update minutes accordingly
        self.process_window_frames.setValue(self.settings.processing_window)
        self._on_process_frames_changed()  # to update hours accordingly
        self.bin_rounding_cb.setChecked(self.settings.bin_rounding)
        self.fps_spin.setValue(self.settings.fps)
        h, m = self.settings.night_begin
        self.night_begin_edit.setText(f"{h:02d}:{m:02d}")
        h, m = self.settings.night_duration
        self.night_duration_edit.setText(f"{h:02d}:{m:02d}")
        self.rebuild_box.setChecked(self.settings.rebuild_events)
        self.utc_offset_spin.setValue(self.settings.utc_offset)

    def _update_settings_from_ui(self):
        """Update LMT-EYE settings based on current UI values."""
        self.settings.output_folder = (
            Path(self.output_folder_edit.text())
            if self.output_folder_edit.text()
            else None
        )

        official, custom, written = self.get_events_from_ui()
        official = self.selected_events["official"]
        custom = self.selected_events["custom"]
        written = self.get_written_events_from_ui()
        self.settings.events = official | custom | written

        self.settings.animal_type = AnimalType[
            self.animal_type_box.currentText()
        ]
        self.settings.display_sensors = self.sensors_cb.isChecked()
        self.settings.display_activity = self.activity_cb.isChecked()
        self.settings.display_heatmap = self.heatmap_cb.isChecked()
        self.settings.display_trackplot = self.trackplot_cb.isChecked()
        self.settings.filter_flickering = self.flickering_cb.isChecked()
        self.settings.filter_stop = self.stop_cb.isChecked()
        self.settings.event_min_duration = (
            self.event_duration_filter_spin.value() + 1
        )
        self.settings.time_window = self.time_window_frames.value()
        self.settings.processing_window = self.process_window_frames.value()
        self.settings.fps = self.fps_spin.value()
        begin, duration, _ = self._get_night_times()
        if begin is not None:
            self.settings.night_begin = begin
        if duration is not None:
            self.settings.night_duration = duration
        self.settings.rebuild_events = self.rebuild_box.isChecked()
        self.settings.bin_rounding = self.bin_rounding_cb.isChecked()
        self.settings.utc_offset = self.utc_offset_spin.value()

        start_limit = self.start_edit.text().strip()
        if not start_limit or not self._check_limits_is_valid(start_limit):
            start_limit = None
        end_limit = self.end_edit.text().strip()
        if not end_limit or not self._check_limits_is_valid(end_limit):
            end_limit = None
        self.settings.processing_limits = (start_limit, end_limit)

    # ================ UPDATE FUNCTIONS ================

    def _clamp_time_window_values(self, frames: int):
        """Clamp time window frames and update minutes accordingly."""
        fpm = self.fps_spin.value() * 60  # frames per minute
        minutes = frames / fpm

        min_frames = 1  # 1 frame
        max_frames = 7 * 24 * 60 * fpm  # 7 days

        if frames < min_frames:
            frames = min_frames
            minutes = frames / fpm

        if frames > max_frames:
            frames = max_frames
            minutes = frames / fpm

        self.time_window_frames.setValue(frames)
        self.time_window_minutes.setValue(minutes)

    def _on_time_frames_changed(self):
        """Handle changes in time window frames spinbox."""
        self.time_window_frames.blockSignals(True)
        self.time_window_minutes.blockSignals(True)

        frames = self.time_window_frames.value()
        self._clamp_time_window_values(frames)

        self.time_window_frames.blockSignals(False)
        self.time_window_minutes.blockSignals(False)

    def _on_time_minutes_changed(self):
        """Handle changes in time window minutes spinbox."""
        self.time_window_frames.blockSignals(True)
        self.time_window_minutes.blockSignals(True)

        fpm = self.fps_spin.value() * 60  # frames per minute
        minutes = self.time_window_minutes.value()
        frames = int(minutes * fpm)
        self._clamp_time_window_values(frames)

        self.time_window_frames.blockSignals(False)
        self.time_window_minutes.blockSignals(False)

    def _clamp_process_window_values(self, frames: int):
        """Clamp processing window frames and update minutes accordingly."""
        fph = self.fps_spin.value() * 60 * 60  # frames per hour
        hours = frames / fph

        min_frames = fph  # 1 hour
        max_frames = 7 * 24 * fph  # 7 days

        if frames < min_frames:
            frames = min_frames
            hours = frames / fph

        if frames > max_frames:
            frames = max_frames
            hours = frames / fph

        self.process_window_frames.setValue(frames)
        self.process_window_hours.setValue(hours)

    def _on_process_frames_changed(self):
        self.process_window_frames.blockSignals(True)
        self.process_window_hours.blockSignals(True)

        frames = self.process_window_frames.value()
        self._clamp_process_window_values(frames)

        self.process_window_frames.blockSignals(False)
        self.process_window_hours.blockSignals(False)

    def _on_process_hours_changed(self):
        self.process_window_frames.blockSignals(True)
        self.process_window_hours.blockSignals(True)

        fph = self.fps_spin.value() * 60 * 60  # frames per hour
        hours = self.process_window_hours.value()
        frames = int(round(hours * fph))
        self._clamp_process_window_values(frames)

        self.process_window_frames.setValue(frames)
        self.process_window_frames.blockSignals(False)
        self.process_window_hours.blockSignals(False)

    def _on_fps_changed(self):
        # When FPS changes, update both minutes <-> frames for both windows
        self._on_time_frames_changed()
        self._on_process_frames_changed()

    def _check_limits_is_valid(self, text: str) -> bool:
        """Check if a processing limit input is valid (either empty, an integer
        or a timestamp)."""
        text = text.strip()
        if not text:
            return True
        elif text.isdigit():
            return True
        else:
            try:
                pd.Timestamp(text)
                return True
            except:
                return False

    def _check_processing_limits_valid(self) -> bool:
        """Check if processing limits inputs are valid."""
        start_is_valid = self._check_limits_is_valid(self.start_edit.text())
        end_is_valid = self._check_limits_is_valid(self.end_edit.text())
        result = start_is_valid and end_is_valid
        if not result:
            QMessageBox.warning(
                self,
                "Invalid processing limits",
                (
                    "Invalid processing limits. Please correct the processing "
                    "limits inputs."
                ),
            )
        return result

    def _on_processing_limits_changed(self):
        """Validate start processing limit input and set red border if invalid."""
        start_is_valid = self._check_limits_is_valid(self.start_edit.text())
        end_is_valid = self._check_limits_is_valid(self.end_edit.text())
        self.start_edit.setStyleSheet(
            "border: 1px solid red;" if not start_is_valid else None
        )
        self.end_edit.setStyleSheet(
            "border: 1px solid red;" if not end_is_valid else None
        )

    @staticmethod
    def _parse_time_text(text: str) -> tuple[int, int] | None:
        """Parse a time string like '18:00' or '18h00' into (int, int) for
        (hours, minutes)."""
        text = text.strip()
        if len(text) < 4:
            return None
        hours_str = text[:2]
        minutes_str = text[-2:]
        if not hours_str.isdigit() or not minutes_str.isdigit():
            return None
        h, m = int(hours_str), int(minutes_str)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return (h, m)

    def _get_night_times(self):
        """Validate night time inputs and return True if valid, False otherwise."""
        begin = self._parse_time_text(self.night_begin_edit.text())
        duration = self._parse_time_text(self.night_duration_edit.text())
        end = self._parse_time_text(self.night_end_edit.text())

        return begin, duration, end

    def _check_night_times_valid(self) -> bool:
        """Check if night time inputs are valid."""
        begin, duration, end = self._get_night_times()
        result = begin is not None and duration is not None and end is not None
        if not result:
            QMessageBox.warning(
                self,
                "Invalid Night hours",
                "Invalid night hours. Please correct the night hours inputs.",
            )
        return result

    def _update_night_times(self):
        begin, duration, end = self._get_night_times()

        if begin is None:
            self.night_begin_edit.setStyleSheet("border: 1px solid red;")
        else:
            self.night_begin_edit.setStyleSheet(None)

        if duration is None:
            self.night_duration_edit.setStyleSheet("border: 1px solid red;")
        else:
            self.night_duration_edit.setStyleSheet(None)

        if end is None:
            self.night_end_edit.setStyleSheet("border: 1px solid red;")
        else:
            self.night_end_edit.setStyleSheet(None)

        return begin, duration, end

    def _on_night_begin_changed(self):
        begin, _, end = self._update_night_times()
        if begin is None or end is None:
            return

        begin_total_min = begin[0] * 60 + begin[1]
        end_total_min = end[0] * 60 + end[1]
        duration_total_min = (end_total_min - begin_total_min) % (24 * 60)
        duration = (duration_total_min // 60, duration_total_min % 60)
        self.night_duration_edit.blockSignals(True)
        self.night_duration_edit.setText(
            f"{duration[0]:02d}:{duration[1]:02d}"
        )
        self.night_duration_edit.blockSignals(False)

    def _on_night_duration_changed(self):
        begin, duration, _ = self._update_night_times()
        if begin is None or duration is None:
            return

        duration_total_min = duration[0] * 60 + duration[1]
        end_total_min = (begin[0] * 60 + begin[1] + duration_total_min) % (
            24 * 60
        )
        end = (end_total_min // 60, end_total_min % 60)
        self.night_end_edit.blockSignals(True)
        self.night_end_edit.setText(f"{end[0]:02d}:{end[1]:02d}")
        self.night_end_edit.blockSignals(False)

    def _on_night_end_changed(self):
        begin, _, end = self._update_night_times()
        if begin is None or end is None:
            return

        begin_total_min = begin[0] * 60 + begin[1]
        end_total_min = end[0] * 60 + end[1]
        duration_total_min = (end_total_min - begin_total_min) % (24 * 60)
        duration = (duration_total_min // 60, duration_total_min % 60)
        self.night_duration_edit.blockSignals(True)
        self.night_duration_edit.setText(
            f"{duration[0]:02d}:{duration[1]:02d}"
        )
        self.night_duration_edit.blockSignals(False)

    # ================ UTILS FUNCTIONS ================

    def get_events_from_ui(self):
        """Get the selected events from UI as a set by combining official,
        custom and written events."""
        official = self.selected_events["official"]
        custom = self.selected_events["custom"]
        written = self.get_written_events_from_ui()
        return official, custom, written

    def get_events_from_settings(self):
        """Get all events present in both settings.events and ALL_EVENTS.
        It corresponds to the events that are selected in the UI (through
        EventSelectionWindow) and are known by the app (i.e. for which the
        app has a specific analysis implemented).
        """
        official = self.settings.events & set(OFFICIAL_EVENTS.keys())
        custom = self.settings.events & set(CUSTOM_EVENTS.keys())
        written = self.settings.events - official - custom
        return official, custom, written

    def on_select_official_events(self):
        dlg = EventSelectionWindow(
            self,
            "official",
            self.selected_events["official"],
        )
        if dlg.exec():
            self.selected_events["official"] = dlg.selected_events

    def on_select_custom_events(self):
        dlg = EventSelectionWindow(
            self,
            "custom",
            self.selected_events["custom"],
        )
        if dlg.exec():
            self.selected_events["custom"] = dlg.selected_events

    def get_written_events_from_ui(self):
        """Get the written events from UI as a set."""
        w_e_list = self.written_event_edit.text().split(",")
        w_e_set = {event.strip() for event in w_e_list if event.strip()}
        return w_e_set

    def on_select_area(self):
        animal_type = AnimalType[self.animal_type_box.currentText()]
        dlg = AreaSelectionWindow(
            self,
            self.settings.analysis_area,
            animal_type,
        )
        if dlg.exec():
            self.settings.analysis_area = dlg.selected_area
            self._update_area_label()

    def _update_area_label(self):
        area = self.settings.analysis_area
        if area is None:
            text = "No area filtering."
        else:
            x_min, y_min, x_max, y_max = area
            text = (
                f"Area from ({x_min}, {y_min}) "
                f"to ({x_max}, {y_max}) in <i>cm</i>."
            )
        self.selected_area_label.setText(text)

    def select_output_folder(self):
        """Open a dialog to choose output folder."""
        folder_str = QFileDialog.getExistingDirectory(
            self, "Select Output Folder"
        )
        if folder_str:
            self.output_folder_edit.setText(folder_str)
        else:
            self.output_folder_edit.setText(None)

    def on_save_settings(self):
        """Save current settings from UI to a JSON file."""
        save_str, _ = QFileDialog.getSaveFileName(
            self,
            "Select Settings File",
            str(AnalysisSettingsWindow.SAVING_PATH),
            "JSON Files (*.json)",
        )
        save_path = Path(save_str) if save_str else None
        if save_path is None:
            logging.warning("No file selected.")
            return
        self._update_settings_from_ui()
        self.settings.save(save_path)

    def on_load_settings(self):
        """Load settings from a JSON file and update UI."""
        load_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Settings File",
            str(AnalysisSettingsWindow.SAVING_PATH),
            "JSON Files (*.json)",
        )
        load_path = Path(load_str) if load_str else None
        if load_path is None:
            logging.warning("No file selected.")
            return
        self.settings.load(load_path)
        self._update_ui_from_settings()

    def on_default_settings(self):
        """Save current settings as the default settings
        (default_settings.json in the same directory)."""
        save_path = (
            AnalysisSettingsWindow.SAVING_PATH / "default_settings.json"
        )
        self._update_settings_from_ui()
        self.settings.save(save_path)

    def on_mcp_toggled(self, checked: bool):
        """Enable or disable the local MCP server."""
        controller = get_controller()
        controller.set_enabled(checked)
        if checked and not controller.is_running:
            QMessageBox.warning(
                self,
                "MCP server",
                "The MCP server could not start:\n"
                f"{controller.last_error}",
            )

    def on_accept(self):
        """Update settings and accept dialog."""
        self._update_settings_from_ui()
        if not self._check_processing_limits_valid():
            return
        if not self._check_night_times_valid():
            return
        self.accept()

    def on_reject(self):
        """Reject dialog."""
        self.reject()

    def on_rebuild_only(self):
        """Update settings and accept dialog with a specific code for rebuild
        only."""
        self._update_settings_from_ui()
        if not self._check_processing_limits_valid():
            return
        if not self._check_night_times_valid():
            return
        self.settings.rebuild_events = True
        self.rebuild_only = True
        self.accept()

    def Qhline(self):
        """Utility function to create a horizontal line separator."""
        hline = QFrame()
        hline.setFrameShape(QFrame.Shape.HLine)
        hline.setFrameShadow(QFrame.Shadow.Sunken)
        hline.setFixedHeight(1)
        return hline


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    dlg = AnalysisSettingsWindow(parent=None)

    if dlg.exec():
        settings = dlg.settings
        print("=== Analysis Settings ===")
        for key, value in settings.as_dict().items():
            print(f"  {key}: {value}")
    else:
        print("Dialog cancelled.")
