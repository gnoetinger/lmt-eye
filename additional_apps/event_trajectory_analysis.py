"""
@author: xmousset

This app extracts trajectory data from a SQLite database based on specified
events and time windows, and allows for visualization and export of the
results. It uses PyQt6 for the GUI, pandas for data manipulation, and Plotly
for graphing.

It is a standalone tool for analyzing animal trajectory data in relation to
events recorded in the database. It is designed to be user-friendly, allowing
users to load a database or a pre-processed CSV, specify parameters, process
the data, and visualize the results.
"""

import sys
import sqlite3
import traceback
import base64
from pathlib import Path

# pyinstaller --onefile --icon=res/lmt_eye_icon.png --add-data "res/lmt_eye_icon.png;res" --add-data "app_fabio/bg.png;app_fabio" app_fabio/app.py

# ================ APP INFO ================
APP_VERSION = "1.2"

# ================ IMPORTS ================

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from PyQt6.QtCore import (
    Qt,
    QObject,
    QRunnable,
    QThreadPool,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from lmtanalysis.Animal import AnimalPool
from lmtanalysis.Event import EventTimeLine
from lmtanalysis.Measure import oneSecond

# Handle PyInstaller bundled executable
if getattr(sys, "frozen", False):
    # Running as executable
    APP_PATH = Path(sys._MEIPASS) / "additional_apps"  # type: ignore
else:
    # Running as script
    APP_PATH = Path(__file__).parent

ICON_PATH = APP_PATH.parent / "res" / "lmt_eye_icon.png"

GRAPH_TYPES = [
    "Density contour",
    "Density heatmap",
    "Density heatmap log scale",
    "Scatter (WHEN color)",
    "Density contour + marginals",
]

WHEN_OPTIONS = ["All", "before", "during", "after"]

IMG_SIZE_PX = (512, 424)

# Background image settings (no default bundled image)
BG_IMAGE_PATH: Path | None = None


def _image_to_data_uri(image_path: str | Path) -> str | None:
    """Convert an image file to a data URI string for use in Plotly."""
    path = Path(image_path)
    if not path.exists():
        return None

    try:
        # Determine MIME type from file extension
        ext = path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(ext, "image/png")

        # Read file and encode to base64
        with open(path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        return f"data:{mime_type};base64,{image_data}"
    except Exception:
        return None


def _btn_style(txt_color: str = "white", bg_color: str = "#1976D2") -> str:
    return f"""
    QPushButton {{
        color: {txt_color};
        background-color: {bg_color};
        border-radius: 5px;
        font-size: 13px;
        font-weight: bold;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background-color: #42a5f5;
    }}
    QPushButton:disabled {{
        background-color: #cccccc;
        color: #888888;
    }}
    """


# ================ Worker / thread ================


class ProcessingSignals(QObject):
    finished = pyqtSignal(object, list)
    error = pyqtSignal(str)


class ProcessingWorker(QRunnable):
    """Run trajectory data extraction in a background thread."""

    def __init__(
        self,
        db_path: str,
        animal_id: int | None,
        event_name: str,
        before_window: int,
        during_window: int,
        after_window: int,
        min_detection_pct: float = 0.6,
        processing_frames_window: tuple[int, int | None] = (0, None),
    ):
        super().__init__()
        self.db_path = db_path
        self.animal_id = animal_id
        self.event_name = event_name
        self.before_window = before_window
        self.during_window = during_window
        self.after_window = after_window
        self.min_detection_pct = min_detection_pct
        self.processing_frames_window = processing_frames_window
        self.signals = ProcessingSignals()

    @pyqtSlot()
    def run(self):
        conn = sqlite3.connect(self.db_path)
        try:
            event_timeline = EventTimeLine(
                conn,
                self.event_name,
                minFrame=self.processing_frames_window[0],
                maxFrame=self.processing_frames_window[1],
            )

            if not event_timeline.eventList:
                self.signals.error.emit(
                    f"No occurrences of event '{self.event_name}' found in the database."
                )
                return

            animal_pool = AnimalPool()
            animal_pool.loadAnimals(conn)

            status_lines: list[str] = []
            results: list[dict] = []

            status_lines.append("Event ID: Before | During | After (%)")
            for event_id, event in enumerate(event_timeline.eventList):
                f0 = event.startFrame

                before_d = EventTimeLine(
                    conn,
                    "Detection",
                    idA=self.animal_id,
                    minFrame=f0 - self.before_window - 1,
                    maxFrame=f0 - 1,
                ).getTotalLength()

                during_d = EventTimeLine(
                    conn,
                    "Detection",
                    idA=self.animal_id,
                    minFrame=f0,
                    maxFrame=f0 + self.during_window,
                ).getTotalLength()

                after_d = EventTimeLine(
                    conn,
                    "Detection",
                    idA=self.animal_id,
                    minFrame=f0 + self.during_window + 1,
                    maxFrame=f0 + self.during_window + 1 + self.after_window,
                ).getTotalLength()

                if self.before_window > 0:
                    before_pct = before_d / self.before_window
                else:
                    before_pct = 0.0

                if self.during_window > 0:
                    during_pct = during_d / self.during_window
                else:
                    during_pct = 0.0

                if self.after_window > 0:
                    after_pct = after_d / self.after_window
                else:
                    after_pct = 0.0

                # Each window is checked independently against the minimum
                # detection percentage (windows with 0 length always pass).
                before_ok = (
                    self.before_window == 0
                    or before_pct >= self.min_detection_pct
                )
                during_ok = (
                    self.during_window == 0
                    or during_pct >= self.min_detection_pct
                )
                after_ok = (
                    self.after_window == 0
                    or after_pct >= self.min_detection_pct
                )
                ok = before_ok and during_ok and after_ok
                status_lines.append(
                    f"{event_id}: {before_pct * 100:.1f}% | "
                    f"{during_pct * 100:.1f}% | "
                    f"{after_pct * 100:.1f}% " + ("✓" if ok else "✗")
                )

                if not ok:
                    continue

                animal_pool.loadDetection(
                    start=f0 - self.before_window - 1,
                    end=f0 + self.during_window + self.after_window + 1,
                    lightLoad=True,
                )

                for animal in animal_pool.getAnimalList():
                    if (
                        self.animal_id is not None
                        and animal.baseId != self.animal_id
                    ):
                        continue

                    xList, yList, fList = animal.get_trajectory()

                    for i in range(len(xList)):
                        if (
                            np.isnan(xList[i]).any()
                            or np.isnan(yList[i]).any()
                        ):
                            continue
                        frame = fList[i]
                        results.append(
                            {
                                "ANIMALID": animal.baseId,
                                "RFID": str(animal.RFID),
                                "EVENTID": event_id,
                                "EVENTNAME": self.event_name,
                                "BEFORE_PCT": before_pct,
                                "DURING_PCT": during_pct,
                                "AFTER_PCT": after_pct,
                                "FRAME": frame,
                                "TIME": animal.getTimestampAt(frame),
                                "X": np.mean(xList[i]),
                                "Y": np.mean(yList[i]),
                                "WHEN": (
                                    "before"
                                    if frame < f0
                                    else (
                                        "during"
                                        if frame <= f0 + self.during_window
                                        else "after"
                                    )
                                ),
                            }
                        )

            if not results:
                self.signals.finished.emit(None, status_lines)
            else:
                df = pd.DataFrame(results)
                self.signals.finished.emit(df, status_lines)

        except Exception:
            self.signals.error.emit(traceback.format_exc())
        finally:
            conn.close()


# ================ Main Window ================
class FabioApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Event Trajectory Analysis — v{APP_VERSION}")
        self.setMinimumWidth(666)
        self.setMinimumHeight(666)
        self._init_ui()

    def _init_ui(self):
        central = ParameterWidget()
        scroll = QScrollArea()
        scroll.setWidget(central)
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)


# ================ Central widget ================


class ParameterWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.connection: sqlite3.Connection | None = None
        self.db_path: str | None = None
        self.animal_pool: AnimalPool | None = None
        self.df: pd.DataFrame | None = None
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self.current_figure: go.Figure | None = None
        self.current_graph_type: str | None = None
        self._init_ui()

    # ------------------------------------------------------------------
    #  UI setup
    # ------------------------------------------------------------------

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        main_layout.addWidget(self._build_ui_db())
        main_layout.addWidget(self._build_ui_params())

        # Create horizontal layout for process and export sections side-by-side
        process_export_layout = QHBoxLayout()
        process_export_layout.setSpacing(14)
        process_export_layout.addWidget(self._build_ui_process())
        process_export_layout.addWidget(self._build_ui_export())
        main_layout.addLayout(process_export_layout)

        main_layout.addWidget(self._build_ui_results())
        main_layout.addStretch(1)

    def _build_ui_db(self) -> QGroupBox:
        group = QGroupBox("1 — Database")
        layout = QHBoxLayout(group)

        self.db_label = QLabel("<i>No database loaded.</i>")
        self.db_label.setWordWrap(True)

        load_btn = QPushButton("Load Database…")
        load_btn.setStyleSheet(_btn_style())
        load_btn.setFixedWidth(160)
        load_btn.clicked.connect(self._on_load_db)

        load_df_btn = QPushButton("Load CSV…")
        load_df_btn.setStyleSheet(_btn_style(bg_color="#2e7d32"))
        load_df_btn.setFixedWidth(160)
        load_df_btn.clicked.connect(self._on_load_df_csv)

        layout.addWidget(self.db_label, 1)
        layout.addWidget(load_btn)
        layout.addWidget(load_df_btn)
        return group

    def _build_ui_params(self) -> QGroupBox:
        self.params_group = QGroupBox("2 — Parameters")
        self.params_group.setEnabled(False)
        form = QFormLayout(self.params_group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        # animal
        self.animal_combo = QComboBox()
        self.animal_combo.setMinimumWidth(260)
        form.addRow("Animal:", self.animal_combo)

        # event name
        self.event_line = QLineEdit()
        self.event_line.setMinimumWidth(260)
        self.event_line.setPlaceholderText("Type event name")
        form.addRow("Event:", self.event_line)

        # time windows
        self.before_label = QLabel("Before event:")
        self.before_spin = QSpinBox()
        self.before_spin.setRange(0, 3600)
        self.before_spin.setValue(300)
        self.before_spin.setSuffix(" s")
        form.addRow(self.before_label, self.before_spin)

        self.during_label = QLabel("During event:")
        self.during_spin = QSpinBox()
        self.during_spin.setRange(0, 3600)
        self.during_spin.setValue(60)
        self.during_spin.setSuffix(" s")
        form.addRow(self.during_label, self.during_spin)

        self.after_label = QLabel("After event:")
        self.after_spin = QSpinBox()
        self.after_spin.setRange(0, 3600)
        self.after_spin.setValue(300)
        self.after_spin.setSuffix(" s")
        form.addRow(self.after_label, self.after_spin)

        # Store time window widgets for hiding when CSV is loaded
        self.time_window_widgets = [
            self.before_label,
            self.before_spin,
            self.during_label,
            self.during_spin,
            self.after_label,
            self.after_spin,
        ]

        # Optional processing frame window (min/max)
        frame_row = QHBoxLayout()
        self.use_frame_window_check = QCheckBox("Limit frames (min/max)")
        self.use_frame_window_check.setChecked(False)
        self.use_frame_window_check.toggled.connect(
            self._on_toggle_frame_window
        )

        self.min_frame_spin = QSpinBox()
        self.min_frame_spin.setRange(0, 10_000_000)
        self.min_frame_spin.setValue(0)
        self.min_frame_spin.setPrefix("Min: ")
        self.min_frame_spin.setEnabled(False)

        self.max_frame_spin = QSpinBox()
        self.max_frame_spin.setRange(0, 10_000_000)
        self.max_frame_spin.setValue(0)
        self.max_frame_spin.setPrefix("Max: ")
        self.max_frame_spin.setEnabled(False)

        frame_row.addWidget(self.use_frame_window_check)
        frame_row.addWidget(self.min_frame_spin)
        frame_row.addWidget(self.max_frame_spin)
        form.addRow(frame_row)

        # Minimum detection percentage required for each window to be valid
        self.min_detection_pct_spin = QSpinBox()
        self.min_detection_pct_spin.setRange(0, 100)
        self.min_detection_pct_spin.setValue(60)
        self.min_detection_pct_spin.setSuffix(" %")
        form.addRow("Min. detection:", self.min_detection_pct_spin)

        return self.params_group

    def _build_ui_process(self) -> QGroupBox:
        self.process_group = QGroupBox("3 — Process")
        self.process_group.setEnabled(False)
        layout = QVBoxLayout(self.process_group)

        update_btn = QPushButton("Process")
        update_btn.setStyleSheet(_btn_style(bg_color="#c0392b"))
        update_btn.setFixedWidth(160)
        update_btn.clicked.connect(self._on_process)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        layout.addWidget(update_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.status_label)
        return self.process_group

    def _build_ui_export(self) -> QGroupBox:
        self.export_group = QGroupBox("3.5 — Save Processing")
        self.export_group.setEnabled(False)
        layout = QVBoxLayout(self.export_group)

        export_label = QLabel(
            "After processing, export the full DataFrame to file "
            "for later analysis without reprocessing."
        )
        export_label.setWordWrap(True)
        export_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(export_label)

        export_btn = QPushButton("Export Full DataFrame…")
        export_btn.setStyleSheet(_btn_style(bg_color="#6a1b9a"))
        export_btn.setFixedWidth(180)
        export_btn.clicked.connect(self._on_export_df)
        layout.addWidget(export_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        return self.export_group

    def _build_ui_results(self) -> QGroupBox:
        self.results_group = QGroupBox("4 — Results")
        self.results_group.setEnabled(False)
        layout = QVBoxLayout(self.results_group)

        # Event ID row
        event_id_row = QHBoxLayout()
        event_id_row.addWidget(QLabel("Event ID:"))
        self.event_id_combo = QComboBox()
        self.event_id_combo.setMinimumWidth(200)
        self.event_id_combo.currentIndexChanged.connect(
            self._on_event_id_changed
        )
        event_id_row.addWidget(self.event_id_combo)
        self.detection_pct_label = QLabel("")
        self.detection_pct_label.setTextFormat(Qt.TextFormat.RichText)
        event_id_row.addWidget(self.detection_pct_label)
        event_id_row.addStretch(1)
        layout.addLayout(event_id_row)

        # WHEN filter row
        when_row = QHBoxLayout()
        when_row.addWidget(QLabel("WHEN filter:"))
        self.when_combo = QComboBox()
        self.when_combo.addItems(WHEN_OPTIONS)
        self.when_combo.setFixedWidth(120)
        when_row.addWidget(self.when_combo)
        when_row.addStretch(1)
        layout.addLayout(when_row)

        # Graph type row
        graph_row = QHBoxLayout()
        graph_row.addWidget(QLabel("Graph type:"))
        self.graph_combo = QComboBox()
        self.graph_combo.addItems(GRAPH_TYPES)
        self.graph_combo.setMinimumWidth(320)
        graph_row.addWidget(self.graph_combo)
        graph_row.addStretch(1)
        layout.addLayout(graph_row)

        # Background image checkbox row
        bg_row = QHBoxLayout()
        self.bg_image_check = QCheckBox("Show background image")
        self.bg_image_check.setChecked(True)
        bg_row.addWidget(self.bg_image_check)
        bg_row.addStretch(1)
        layout.addLayout(bg_row)

        # Background image selector row
        bg_select_row = QHBoxLayout()
        self.bg_path_label = QLabel(
            str(BG_IMAGE_PATH)
            if BG_IMAGE_PATH and BG_IMAGE_PATH.exists()
            else "<i>No background</i>"
        )
        self.bg_path_label.setWordWrap(True)
        self.bg_path_label.setStyleSheet("color:#666;font-size:11px;")

        choose_bg_btn = QPushButton("Choose background image…")
        choose_bg_btn.setStyleSheet(_btn_style())
        choose_bg_btn.setFixedWidth(200)
        choose_bg_btn.clicked.connect(self._on_choose_bg_image)

        reset_bg_btn = QPushButton("Reset background")
        reset_bg_btn.setStyleSheet(_btn_style(bg_color="#888888"))
        reset_bg_btn.setFixedWidth(140)
        reset_bg_btn.clicked.connect(self._on_reset_bg_image)

        bg_select_row.addWidget(self.bg_path_label, 1)
        bg_select_row.addWidget(choose_bg_btn)
        bg_select_row.addWidget(reset_bg_btn)
        layout.addLayout(bg_select_row)

        # Manual color scale (enable to force same colorbar max across images)
        scale_row = QHBoxLayout()
        self.manual_vmax_check = QCheckBox("Manual color scale max")
        self.manual_vmax_check.setChecked(False)
        self.manual_vmax_spin = QSpinBox()
        self.manual_vmax_spin.setRange(1, 10_000_000)
        self.manual_vmax_spin.setValue(100)
        self.manual_vmax_spin.setPrefix("Max: ")
        self.manual_vmax_spin.setEnabled(False)
        self.manual_vmax_check.toggled.connect(
            lambda checked: self.manual_vmax_spin.setEnabled(checked)
        )
        scale_row.addWidget(self.manual_vmax_check)
        scale_row.addWidget(self.manual_vmax_spin)
        scale_row.addStretch(1)
        layout.addLayout(scale_row)

        # Buttons row
        btn_row = QHBoxLayout()

        show_btn = QPushButton("Show Graph")
        show_btn.setStyleSheet(_btn_style())
        show_btn.setFixedWidth(140)
        show_btn.clicked.connect(self._on_show_graph)

        csv_btn = QPushButton("Save Graph as CSV")
        csv_btn.setStyleSheet(_btn_style(bg_color="#2e7d32"))
        csv_btn.setFixedWidth(140)
        csv_btn.setToolTip(
            "Save the current view (filtered by Event ID and WHEN) as CSV."
        )
        csv_btn.clicked.connect(self._on_save_csv)

        btn_row.addStretch(1)
        btn_row.addWidget(show_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(csv_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        return self.results_group

    # Helpers
    # ----------------

    def _get_display_df(self) -> pd.DataFrame | None:
        if self.df is None:
            return None
        df = self.df.copy()
        event_id = self.event_id_combo.currentData()
        if event_id is not None:  # If not "All events"
            df = df[df["EVENTID"] == event_id]
        when = self.when_combo.currentText()
        if when != "All":
            df = df[df["WHEN"] == when]
        return df

    def _graph_title(self) -> str:
        if self.df is None or self.df.empty:
            return "No data"

        # Extract data from DataFrame instead of combo boxes
        unique_rfids = sorted(self.df["RFID"].unique())
        rfid_text = ", ".join(str(rfid) for rfid in unique_rfids)

        event_names = self.df["EVENTNAME"].unique()
        if len(event_names) == 1:
            event_text = str(event_names[0])
        else:
            event_text = f"Multiple events ({len(event_names)})"

        return f"RFID {rfid_text} — {event_text}"

    def _get_filename_from_data(self, suffix: str = "") -> str:
        """Generate a filename from the DataFrame data."""
        if self.df is None or self.df.empty:
            return f"trajectory{suffix}.csv"

        # Get event name(s)
        event_names = self.df["EVENTNAME"].unique()
        if len(event_names) == 1:
            event_text = event_names[0][:30]  # Truncate long event names
            event_text = event_text.replace(" ", "_")
        else:
            event_text = f"multi_event"

        return f"trajectory_{event_text}{suffix}.csv"

    def _update_detection_pct_label(self) -> None:
        """Update the detection percentage label based on selected event ID."""
        if self.df is None or self.df.empty:
            self.detection_pct_label.setText("")
            return

        event_id = self.event_id_combo.currentData()
        if event_id is None:  # "All events" selected
            self.detection_pct_label.setText("")
            return

        # Filter to selected event ID
        event_data = self.df[self.df["EVENTID"] == event_id]
        if event_data.empty:
            self.detection_pct_label.setText("")
            return

        # Get detection percentages (take first row's values, they should be same for event)
        before_pct = event_data["BEFORE_PCT"].iloc[0] * 100
        during_pct = event_data["DURING_PCT"].iloc[0] * 100
        after_pct = event_data["AFTER_PCT"].iloc[0] * 100

        # Format with colors
        label_text = (
            f"<span style='color:#666;font-size:11px;'>"
            f"Before: {before_pct:.0f}% | "
            f"During: {during_pct:.0f}% | "
            f"After: {after_pct:.0f}%"
            f"</span>"
        )
        self.detection_pct_label.setText(label_text)

    def _show_time_windows(self, show: bool) -> None:
        """Show or hide time window widgets."""
        for widget in self.time_window_widgets:
            widget.setVisible(show)
        # keep frame window visible regardless (user requested)
        # (no-op here because frame widgets are part of the form)

    def _on_toggle_frame_window(self, checked: bool) -> None:
        """Enable or disable min/max frame inputs."""
        self.min_frame_spin.setEnabled(checked)
        self.max_frame_spin.setEnabled(checked)

    def _extract_graph_data(self) -> pd.DataFrame | None:
        """Extract the actual graph data (e.g., density values) based on graph type."""
        if self.current_figure is None or self.current_graph_type is None:
            return None

        graph_type = self.current_graph_type.lower()

        # For density heatmaps and contours, extract the 2D grid data
        if "heatmap" in graph_type or "contour" in graph_type:
            try:
                trace = self.current_figure.data[0]
                x_vals = trace.x  # type: ignore
                y_vals = trace.y  # type: ignore
                z_vals = trace.z  # type: ignore

                if x_vals is None or y_vals is None or z_vals is None:
                    return None

                # Create a DataFrame from the grid data
                rows = []
                for i, y in enumerate(y_vals):
                    for j, x in enumerate(x_vals):
                        rows.append(
                            {
                                "X": x,
                                "Y": y,
                                "Density": (
                                    z_vals[i][j]
                                    if isinstance(
                                        z_vals[i], (list, np.ndarray)
                                    )
                                    else z_vals[i]
                                ),
                            }
                        )
                return pd.DataFrame(rows)
            except Exception:
                return None

        # For scatter plots, use the display DataFrame
        elif "scatter" in graph_type:
            return self._get_display_df()

        # Fallback: return filtered data
        return self._get_display_df()

    # Slots
    # ----------------

    def _on_load_db(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SQLite file",
            "",
            "SQLite files (*.sqlite);;All files (*)",
        )
        if not file_path:
            return

        if self.connection is not None:
            self.connection.close()
            self.connection = None

        try:
            self.connection = sqlite3.connect(file_path)
            self.db_path = file_path
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Cannot open database:\n{exc}"
            )
            return

        # Load animals
        self.animal_pool = AnimalPool()
        try:
            self.animal_pool.loadAnimals(self.connection)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Cannot load animals:\n{exc}")
            self.connection.close()
            self.connection = None
            return

        # Populate animal combo
        self.animal_combo.clear()
        for animal in self.animal_pool.getAnimalList():
            label = f"Animal {animal.baseId}  (RFID: {animal.RFID})"
            self.animal_combo.addItem(label, userData=animal.baseId)

        self.db_label.setText(f"<b>{Path(file_path).name}</b>")
        self.params_group.setEnabled(True)
        self.process_group.setEnabled(True)
        self._show_time_windows(
            True
        )  # Show time windows for database workflow
        self.export_group.setEnabled(False)
        self.results_group.setEnabled(False)
        self.df = None
        self.status_label.setText("")

    def _on_load_df_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load DataFrame CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return

        try:
            df = pd.read_csv(file_path)
        except Exception as exc:
            QMessageBox.critical(
                self, "Error", f"Cannot read CSV file:\n{exc}"
            )
            return

        # Validate required columns
        required_columns = {
            "ANIMALID",
            "RFID",
            "EVENTID",
            "EVENTNAME",
            "FRAME",
            "TIME",
            "X",
            "Y",
            "WHEN",
        }
        if not required_columns.issubset(set(df.columns)):
            missing = required_columns - set(df.columns)
            QMessageBox.critical(
                self,
                "Invalid CSV",
                f"DataFrame is missing required columns: {', '.join(missing)}",
            )
            return

        # Load successful
        self.df = df
        self.connection = None
        self.db_path = None
        self.animal_pool = None

        # Update UI
        self.db_label.setText(
            f"<b>{Path(file_path).name}</b> <i>(DataFrame loaded)</i>"
        )
        self.params_group.setEnabled(False)
        self.process_group.setEnabled(False)
        self.status_label.setText("")

        # Clear parameter inputs (not relevant for loaded CSV)
        self.animal_combo.clear()
        self.event_line.setText("")
        self._show_time_windows(False)  # Hide time windows for CSV workflow

        # Populate event ID combo
        self.event_id_combo.clear()
        self.event_id_combo.addItem("All events", userData=None)
        for eid in sorted(df["EVENTID"].unique()):
            self.event_id_combo.addItem(f"ID {eid}", userData=int(eid))

        self._update_detection_pct_label()

        # Update status with loaded data information
        num_rows = len(df)
        num_events = len(df["EVENTID"].unique())
        self.status_label.setText(
            f"<span style='color:#2e7d32;'>DataFrame loaded: {num_rows} rows, "
            f"{num_events} event(s)</span>"
        )

        self.export_group.setEnabled(False)
        self.results_group.setEnabled(True)

        QMessageBox.information(
            self,
            "Loaded",
            f"DataFrame loaded successfully.\n{num_rows} rows, {num_events} event(s)",
        )

    def _on_process(self):
        if self.connection is None or self.db_path is None:
            QMessageBox.warning(
                self, "No Database", "Please load a database first."
            )
            return

        event_name = self.event_line.text()

        animal_id: int | None = self.animal_combo.currentData()
        before_window = self.before_spin.value() * oneSecond
        during_window = self.during_spin.value() * oneSecond
        after_window = self.after_spin.value() * oneSecond

        self.status_label.setText("<i>Processing…</i>")
        self.process_group.setEnabled(False)
        self.export_group.setEnabled(False)
        self.results_group.setEnabled(False)
        self.df = None

        # Compute optional processing frame window and validate
        processing_frames_window: tuple[int, int | None] = (0, None)
        if (
            getattr(self, "use_frame_window_check", None)
            and self.use_frame_window_check.isChecked()
        ):
            min_frame = int(self.min_frame_spin.value())
            max_frame_val = int(self.max_frame_spin.value())
            max_frame = None if max_frame_val == 0 else max_frame_val
            if max_frame is not None and max_frame < min_frame:
                QMessageBox.warning(
                    self,
                    "Invalid frames",
                    "Maximum frame must be greater than or equal to minimum frame.",
                )
                self.process_group.setEnabled(True)
                return
            processing_frames_window = (min_frame, max_frame)

        min_detection_pct = self.min_detection_pct_spin.value() / 100

        worker = ProcessingWorker(
            db_path=self.db_path,
            animal_id=animal_id,
            event_name=event_name,
            before_window=before_window,
            during_window=during_window,
            after_window=after_window,
            min_detection_pct=min_detection_pct,
            processing_frames_window=processing_frames_window,
        )

        worker.signals.finished.connect(self._on_processing_done)
        worker.signals.error.connect(self._on_processing_error)
        self.threadpool.start(worker)

    def _on_processing_done(
        self, df: pd.DataFrame | None, status_lines: list[str]
    ):
        self.process_group.setEnabled(True)

        html_lines = []
        color = "#cacaca"
        html_lines.append(
            f"<span style='color:{color};'>{status_lines[0]}</span>"
        )
        for line in status_lines[1:]:
            color = "#2e7d32" if "✓" in line else "#c0392b"
            html_lines.append(f"<span style='color:{color};'>{line}</span>")
        self.status_label.setText("<br>".join(html_lines))

        if df is None or df.empty:
            QMessageBox.warning(
                self,
                "No Data",
                "No trajectory data could be built.\n"
                "All events failed the minimum detection threshold.",
            )
            return

        self.df = df

        self.event_id_combo.clear()
        self.event_id_combo.addItem("All events", userData=None)
        for eid in sorted(df["EVENTID"].unique()):
            self.event_id_combo.addItem(f"ID {eid}", userData=int(eid))

        self._update_detection_pct_label()
        self.export_group.setEnabled(True)
        self.results_group.setEnabled(True)

    def _on_event_id_changed(self) -> None:
        """Handle event ID combo change."""
        self._update_detection_pct_label()

    def _on_processing_error(self, error_text: str):
        self.process_group.setEnabled(True)
        self.status_label.setText(
            "<span style='color:#c0392b;'>Processing failed.</span>"
        )
        ErrorDialog(self, error_text).exec()

    def _on_show_graph(self):
        display_df = self._get_display_df()
        if display_df is None or display_df.empty:
            QMessageBox.information(
                self, "No Data", "No data to display for this filter."
            )
            return

        title = self._graph_title()
        graph_type = self.graph_combo.currentText()
        bg_img = self.bg_image_check.isChecked()
        # Determine manual vmax if enabled
        manual_vmax = None
        if (
            getattr(self, "manual_vmax_check", None)
            and self.manual_vmax_check.isChecked()
        ):
            manual_vmax = int(self.manual_vmax_spin.value())

        fig = _build_figure(
            display_df, graph_type, title, bg_img, manual_vmax=manual_vmax
        )
        self.current_figure = fig
        self.current_graph_type = graph_type
        fig.show()

    def _on_export_df(self):
        if self.df is None:
            return

        default_filename = self._get_filename_from_data(suffix="_full")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Full DataFrame",
            default_filename,
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return

        try:
            self.df.to_csv(file_path, index=False)
            QMessageBox.information(
                self, "Exported", f"Full DataFrame saved to:\n{file_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not export:\n{exc}")

    def _on_save_csv(self):
        if self.df is None:
            return

        default_filename = Path(self._get_filename_from_data())
        filename = (
            default_filename.stem
            + "_"
            + self.graph_combo.currentText()
            .lower()
            .replace(" ", "_")
            .replace("—", "")
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Graph as CSV",
            filename,
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return

        # Extract the actual graph data (density values, scatter points, etc.)
        save_df = self._extract_graph_data()
        if save_df is None or save_df.empty:
            QMessageBox.information(
                self, "No Data", "No data to save for this graph."
            )
            return

        try:
            save_df.to_csv(file_path, index=False)
            QMessageBox.information(
                self, "Saved", f"Graph data saved to:\n{file_path}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not save CSV:\n{exc}")

    def _on_choose_bg_image(self):
        """Open a file dialog to select a background image."""
        global BG_IMAGE_PATH
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select background image",
            str(APP_PATH),
            "Image files (*.png *.jpg *.jpeg *.gif *.webp);;All files (*)",
        )
        if not file_path:
            return
        p = Path(file_path)
        if not p.exists():
            QMessageBox.warning(
                self, "File not found", "Selected file does not exist."
            )
            return
        BG_IMAGE_PATH = p
        self._update_bg_label()

    def _on_reset_bg_image(self):
        """Clear the selected background image."""
        global BG_IMAGE_PATH
        BG_IMAGE_PATH = None
        self._update_bg_label()

    def _update_bg_label(self) -> None:
        if BG_IMAGE_PATH and Path(BG_IMAGE_PATH).exists():
            self.bg_path_label.setText(str(BG_IMAGE_PATH))
            self.bg_path_label.setToolTip(str(BG_IMAGE_PATH))
        else:
            self.bg_path_label.setText("<i>No background</i>")
            self.bg_path_label.setToolTip("")


# ================ Graph Builder ================


def _apply_base_layout(fig: go.Figure, title: str):
    # Expand Y range to match X range span for correct aspect ratio

    fig.update_layout(
        xaxis=dict(
            title="X position (<i>px</i>)",
        ),
        yaxis=dict(
            title="Y position (<i>px</i>)",
        ),
        title=title,
        plot_bgcolor="rgba(0,0,0,0)",
    )


def _apply_bg_image(fig: go.Figure, layer: str = "below"):
    if layer not in {"below", "above"}:
        raise ValueError("Layer must be 'below' or 'above'")

    # Add background image if it exists
    if not BG_IMAGE_PATH:
        return

    bg_data_uri = _image_to_data_uri(BG_IMAGE_PATH)
    if bg_data_uri:
        # Image positioned at (0,0) with cage dimensions
        x_center = IMG_SIZE_PX[0] / 2
        y_center = -(IMG_SIZE_PX[1] / 2)
        fig.add_layout_image(
            source=bg_data_uri,
            xref="x",
            yref="y",
            x=x_center,
            y=y_center,
            sizex=IMG_SIZE_PX[0],
            sizey=IMG_SIZE_PX[1],
            xanchor="center",
            yanchor="middle",
            opacity=1.0 if layer == "below" else 0.25,
            layer=layer,
        )


def _build_figure(
    df: pd.DataFrame,
    graph_type: str,
    title: str,
    show_bg_img: bool,
    manual_vmax: int | None = None,
) -> go.Figure:
    axis_labels = {
        "X": "X position (<i>px</i>)",
        "Y": "Y position (<i>px</i>)",
    }

    img_bg_layer = None
    match graph_type:
        case "Density contour":
            fig = px.density_contour(
                df,
                x="X",
                y="Y",
                color_discrete_sequence=px.colors.qualitative.Plotly,
                labels=axis_labels,
            )
            fig.update_traces(
                contours_coloring="fill",
                contours_showlines=False,
                selector=dict(type="histogram2dcontour"),
                colorscale="Blues",
            )
            _apply_base_layout(fig, title)
            img_bg_layer = "above"

        case "Density heatmap":
            fig = px.density_heatmap(
                df,
                x="X",
                y="Y",
                labels=axis_labels,
                nbinsx=50,
                nbinsy=50,
            )
            _apply_base_layout(fig, title)
            img_bg_layer = "above"

        case "Density heatmap log scale":
            counts, x_edges, y_edges = np.histogram2d(
                df["X"], df["Y"], bins=50
            )
            log_counts = np.log1p(counts.T)
            raw_ticks = [0, 1, 5, 10, 50, 100, 500, 1000, int(counts.max())]
            raw_ticks = sorted({v for v in raw_ticks if v <= counts.max()})
            fig = go.Figure(
                go.Heatmap(
                    x=(x_edges[:-1] + x_edges[1:]) / 2,
                    y=(y_edges[:-1] + y_edges[1:]) / 2,
                    z=log_counts,
                    colorbar=dict(
                        title="Count",
                        tickvals=np.log1p(raw_ticks),
                        ticktext=[str(v) for v in raw_ticks],
                    ),
                )
            )
            fig.update_layout(
                xaxis=dict(
                    title="X position (<i>px</i>)",
                ),
                yaxis=dict(
                    title="Y position (<i>px</i>)",
                ),
                title=title,
                plot_bgcolor="rgba(0,0,0,0)",
            )
            img_bg_layer = "above"

        case "Scatter (WHEN color)":
            fig = px.scatter(
                df,
                x="X",
                y="Y",
                color="WHEN",
                labels={**axis_labels, "TIME": "Time (relative to sound)"},
            )
            fig.update_traces(marker=dict(opacity=0.3, size=5))
            _apply_base_layout(fig, title)
            img_bg_layer = "below"

        case "Density contour + marginals":
            fig = px.density_contour(
                df,
                x="X",
                y="Y",
                marginal_x="histogram",
                marginal_y="histogram",
                labels=axis_labels,
                color="WHEN",
            )
            fig.update_layout(
                xaxis=dict(
                    title="X position (<i>px</i>)",
                ),
                yaxis=dict(
                    title="Y position (<i>px</i>)",
                ),
                title=title,
                plot_bgcolor="rgba(0,0,0,0)",
            )
            img_bg_layer = "below"

        case _:
            fig = go.Figure()
            fig.update_layout(title=f"Unknown graph type: {graph_type}")

    # Apply manual color scale maximum to density traces.
    # Note: histogram2d/histogram2dcontour compute their z-bins client-side
    # (Plotly.js), so the Python trace's `z` is None — must target by type,
    # not by checking for a populated z array. zauto must be disabled too,
    # otherwise Plotly.js ignores the manual zmax and autoscales anyway.
    if manual_vmax is not None:
        if "log" in graph_type.lower():
            zmax_val = np.log1p(manual_vmax)
        else:
            zmax_val = manual_vmax

        zscale_trace_types = {
            "heatmap",
            "histogram2d",
            "histogram2dcontour",
            "contour",
        }
        for tr in fig.data:
            if tr.type in zscale_trace_types:  # type: ignore
                tr.update(zauto=False, zmin=0, zmax=zmax_val)  # type: ignore

        # px.density_heatmap uses a shared coloraxis instead of per-trace
        # zmin/zmax, so the trace-level update above is ignored for it.
        if fig.layout.coloraxis is not None:
            fig.update_layout(
                coloraxis=dict(cauto=False, cmin=0, cmax=zmax_val)
            )

    if img_bg_layer is not None and show_bg_img:
        _apply_bg_image(fig, layer=img_bg_layer)

    return fig


# ================ Error dialog ================


class ErrorDialog(QDialog):
    def __init__(self, parent: QWidget, error_text: str):
        super().__init__(parent)
        self.setWindowTitle("Processing Error")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        label = QLabel("An error occurred during processing:")
        layout.addWidget(label)

        detail = QLabel(f"<pre>{error_text}</pre>")
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(detail)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)


# ================ Exception hook ================


def exception_hook(type_, value, tb):
    traceback.print_exception(type_, value, tb)
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("Application Error")
    msg.setText("An unexpected error occurred.")
    msg.setDetailedText("".join(traceback.format_exception(type_, value, tb)))
    msg.exec()


# ================ Entry point ================

if __name__ == "__main__":
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationVersion(APP_VERSION)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setApplicationName("App for Fabio")

    window = FabioApp()
    window.show()
    sys.exit(app.exec())
