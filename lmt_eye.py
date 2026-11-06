"""
@author: xmousset
"""

print("\n === LMT-EYE === \n")
from pathlib import Path

# ================ APP INFO ================
# command for executable creation (run in terminal at project root):
# pyinstaller --onefile --icon=res/lmt_eye_icon.png --add-data "res/lmt_eye_icon.png;res" --add-data "res/template;res/template" --add-data "res/assets;res/assets" --add-data "res/mouse_run.gif;res" --add-data "events/custom;events/custom" lmt_eye.py

APP_VERSION = "2.4"
APP_RELEASE = "2026-08-26"

APP_PATH = Path(__file__).parent
ICON_PATH = APP_PATH / "res" / "lmt_eye_icon.png"
GIF_PATH = APP_PATH / "res" / "mouse_run.gif"

# ================ IMPORTS ================
import sys
import logging
import traceback
from typing import Literal
from datetime import datetime

import pandas as pd

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QMovie
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from scripts.logger import logger_setup
from scripts.settings import ComparisonSettings
from scripts.db_analyzer import DatabaseAnalyzer
from scripts.analyses_comparator import AnalysesComparator

from widgets.sql_modifications import UpdateDatabaseInfo
from widgets.pyqt6_tools import YesNoQuestion, get_btn_style
from widgets.settings_analysis_window import AnalysisSettingsWindow
from widgets.settings_comparison_window import ComparisonSettingsWindow
from widgets.mcp_indicator import McpStatusIndicator

from mcp_server import McpSettings, app_state, client_setup, get_controller

logger_setup(
    level=logging.INFO,
    display_level=False,
    display_time=False,
    display_file_and_line=False,
    write_to_file=None,
)


class LMTEYEApp(QMainWindow):
    """Main application class for LMT-EYE."""

    def __init__(self):
        """Initialize the LMT-EYE application."""
        super().__init__()
        self.setWindowTitle("LMT-EYE - v" + APP_VERSION)
        self.setFixedSize(550, 400)
        self._init_ui()

    def _init_ui(self):
        self.database_analysis = DatabaseAnalysisWidget()
        self.compare_analysis = AnalysesComparisonWidget()

        self.stacked = QStackedWidget()
        self.stacked.addWidget(self.database_analysis)
        self.stacked.addWidget(self.compare_analysis)
        self.setCentralWidget(self.stacked)

        menu = self.menuBar()
        if menu is None:
            raise RuntimeError("Menu bar error.")

        switch_menu = menu.addMenu("Menu")
        if switch_menu is None:
            raise RuntimeError("Switch menu error.")
        switch_menu.addAction("Analysis creation", lambda: self.change_ui(0))
        switch_menu.addAction("Analysis comparison", lambda: self.change_ui(1))

        # local MCP server on/off (same setting as in Analysis settings)
        switch_menu.addSeparator()
        self.mcp_action = switch_menu.addAction("Local MCP server")
        if self.mcp_action is None:
            raise RuntimeError("MCP action error.")
        self.mcp_action.setCheckable(True)
        self.mcp_action.setChecked(get_controller().settings.enabled)
        self.mcp_action.triggered.connect(self.on_mcp_toggled)
        switch_menu.aboutToShow.connect(
            lambda: self.mcp_action.setChecked(
                get_controller().settings.enabled
            )
        )
        switch_menu.addAction(
            "Register in Claude Code", self.on_register_claude_code
        )

        debug_menu = menu.addMenu("Debug")
        if debug_menu is None:
            raise RuntimeError("Debug menu error.")
        debug_menu.addAction("Reset settings", lambda: self.reset_settings())
        debug_menu.addAction(
            "Logging setup",
            lambda: LoggingConfigDialog(self).exec(),
        )

        help_menu = menu.addMenu("Help")
        if help_menu is None:
            raise RuntimeError("Help menu error.")
        help_menu.addAction("About LMT-EYE", lambda: self.show_help("version"))
        help_menu.addAction("Resources", lambda: self.show_help("resources"))
        help_menu.addAction("Documentation", lambda: self.show_help("doc"))
        help_menu.addAction("MCP server", lambda: self.show_help("mcp"))

        # MCP status light, top right corner
        menu.setCornerWidget(
            McpStatusIndicator(get_controller(), menu),
            Qt.Corner.TopRightCorner,
        )

    def on_register_claude_code(self):
        """Register the local MCP server in Claude Code (runs the 'claude'
        command, so the user does not have to type it)."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, message = get_controller().register_in_claude_code()
        finally:
            QApplication.restoreOverrideCursor()
        if ok:
            QMessageBox.information(self, "Claude Code", message)
        else:
            QMessageBox.warning(self, "Claude Code", message)

    def on_mcp_toggled(self, checked: bool):
        """Enable or disable the local MCP server from the menu."""
        controller = get_controller()
        controller.set_enabled(checked)
        if checked and not controller.is_running:
            QMessageBox.warning(
                self,
                "MCP server",
                "The MCP server could not start:\n"
                f"{controller.last_error}",
            )

    def change_ui(self, idx: int | None = None):
        if idx is not None:
            if idx >= 0 and idx < self.stacked.count():
                new_idx = idx
            else:
                logging.warning(
                    f"Invalid index {idx} for stacked widget. Ignoring."
                )
                return
        else:
            new_idx = (self.stacked.currentIndex() + 1) % self.stacked.count()

        self.stacked.setCurrentIndex(new_idx)

    def reset_settings(self):
        """Clear the default settings."""
        default_path = (
            AnalysisSettingsWindow.SAVING_PATH / "default_settings.json"
        )
        default_path.unlink(missing_ok=True)
        QMessageBox.information(
            self, "Settings reset", "All settings have been reset."
        )

    def show_help(
        self,
        option: Literal["full", "version", "resources", "doc", "mcp"] = "full",
    ):
        help_dialog = HelpDialog(self)
        match option:
            case "full":
                help_dialog.init_ui(help_dialog.full_msg())
            case "version":
                help_dialog.init_ui(help_dialog.version_msg())
            case "resources":
                help_dialog.init_ui(help_dialog.resources_msg())
            case "doc":
                help_dialog.init_ui(help_dialog.doc_msg())
            case "mcp":
                help_dialog.init_ui(help_dialog.mcp_msg())
        help_dialog.exec()


class HelpDialog(QDialog):

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Help")
        self.setFixedWidth(300)

    def init_ui(self, msg: str):
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(msg)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.setOpenExternalLinks(True)
        label.setWordWrap(True)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(btn_box)

    def version_msg(self):
        msg = f"""
            <b>LMT-EYE</b> - <i>Explore Your Experiments !</i><br>
            <br>
            Version: {APP_VERSION}<br>
            Release date: {APP_RELEASE}<br>
        """
        return msg

    def resources_msg(self):
        msg = f"""
            You can find the source code of LMT-EYE on the following link:<br>
            Github: <a href='https://github.com/xmousset/lmt-eye'>
            lmt-eye repository</a><br>
            <br>
            LMT-EYE is based on a report created by Fabrice De Chaumont:<br>
            Github: <a href='https://github.com/fdechaumont/lmt-analysis'>
            lmt-analysis repository</a><br>
            <br>
            To seek for help, visit LMT website:<br>
            <a href='https://micecraft.org/lmt/'>
            https://micecraft.org/lmt/</a><br>
            <br>
            You can also go on the LMT Discord server to ask LMT creators and
            other users about your problems to have a quick answer:<br>
            <a href='https://discord.com/invite/zWDHNf9eHM'>
            Join LMT Discord server</a>
        """
        return msg

    def doc_msg(self):
        msg = f"""
            <b>LMT Documentation</b><br>
            <br>
            Here is the LMT-EYE wiki, where you can find some documentation resources:<br>
            <a href='https://github.com/xmousset/lmt-eye/wiki'>
            LMT-EYE Wiki</a><br>
            <br>
            - <a href='https://docs.google.com/document/d/1Wn0yfELiKF1Vydvoe-_4qiQ44q61_3xg85r0I6be33Y/edit?usp=sharing'>
            RFID Tags informations</a><br>
        """
        return msg

    def mcp_msg(self):
        controller = get_controller()
        _, description = controller.status()
        if client_setup.registered_url() == controller.url:
            claude_code = "registered"
        elif client_setup.find_claude_cli() is None:
            claude_code = "not installed"
        else:
            claude_code = "not registered"
        msg = f"""
            <b>Local MCP server</b><br>
            <br>
            Status: {description.splitlines()[0]}<br>
            Address: {controller.url}<br>
            <br>
            Claude Code: {claude_code}<br>
            <br>
            LMT-EYE registers itself in Claude Code when the server starts
            (or use <i>Menu &gt; Register in Claude Code</i>). Manual
            command, if needed:<br>
            <code>claude mcp add --transport http --scope user lmt-eye
            {controller.url}</code><br>
            <br>
            Enable or disable the server in <i>Menu &gt; Local MCP server</i>
            or in the analysis settings window.
        """
        return msg

    def full_msg(self):
        return (
            self.version_msg()
            + "<br><br>"
            + self.resources_msg()
            + "<br><br>"
            + self.doc_msg()
        )


class LoggingConfigDialog(QDialog):
    """Dialog to configure logging settings at runtime."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Logging setup")
        self.setFixedWidth(400)
        self._init_ui()

    def _init_ui(self):
        form = QFormLayout()

        # Level selector
        self.level_cb = QComboBox()
        levels = [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ]
        for name, _ in levels:
            self.level_cb.addItem(name)
        self.level_cb.setCurrentText("INFO")

        # Checkboxes
        self.chk_display_level = QCheckBox("Display level")
        self.chk_display_time = QCheckBox("Display time")
        self.chk_file_and_line = QCheckBox("Display file and line")

        # File output
        file_row = QHBoxLayout()
        self.file_le = QLineEdit()
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.file_le)
        file_row.addWidget(browse_btn)

        form.addRow("Level:", self.level_cb)
        form.addRow("", self.chk_display_level)
        form.addRow("", self.chk_display_time)
        form.addRow("", self.chk_file_and_line)
        form.addRow("Write to file:", file_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _browse_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select log file",
            "",
            "Log files (*.log);;All files (*)",
        )
        if path:
            self.file_le.setText(path)

    def _apply(self):
        level_name = self.level_cb.currentText()
        level = getattr(logging, level_name, logging.INFO)
        display_level = self.chk_display_level.isChecked()
        display_time = self.chk_display_time.isChecked()
        display_file_and_line = self.chk_file_and_line.isChecked()
        write_to_file = self.file_le.text() or None

        try:
            logger_setup(
                level=level,
                display_level=display_level,
                display_time=display_time,
                display_file_and_line=display_file_and_line,
                write_to_file=write_to_file,
            )
            QMessageBox.information(
                self, "Logging", "Logging configuration updated."
            )
            logging.info("Logging configuration updated.")
            self.accept()
        except Exception as e:
            logging.error(f"Failed to apply logging settings:\n{e}")
            QMessageBox.critical(
                self, "Logging", f"Failed to apply logging settings:\n{e}"
            )


class DatabaseAnalysisWidget(QWidget):
    """Database Analysis Widget for LMT-EYE.
    It allows to load a database, rebuild events and create reports.
    """

    def __init__(self):
        """Initialize the database analysis widget."""
        super().__init__()
        self.database_path: Path | None = None
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI elements of the database analysis window."""
        main_layout = QVBoxLayout()

        # ================ DATABASE INFORMATIONS ================
        self.info_lbl: dict[str, QLabel] = {}
        self.info_lbl["db_name"] = QLabel()
        self.info_lbl["animals"] = QLabel()
        self.info_lbl["start"] = QLabel()
        self.info_lbl["end"] = QLabel()
        self.info_lbl["tz"] = QLabel()
        self.info_lbl["tz"].setStyleSheet("color: gray; font-style: italic;")
        self.info_lbl["duration"] = QLabel()
        self.info_lbl["fps"] = QLabel()

        self.info_form = QFormLayout()
        self.info_form.setFormAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.info_form.addRow("<b>Database:</b>", self.info_lbl["db_name"])
        self.info_form.addRow("<b>Animals:</b>", self.info_lbl["animals"])
        self.info_form.addRow("<b>Start:</b>", self.info_lbl["start"])
        self.info_form.addRow("<b>End:</b>", self.info_lbl["end"])
        self.info_form.addRow("", self.info_lbl["tz"])
        self.info_form.addRow("<b>Duration:</b>", self.info_lbl["duration"])
        self.info_form.addRow("<b>FPS:</b>", self.info_lbl["fps"])

        self.update_database_info()

        main_layout.addLayout(self.info_form)

        # ================ BUTTONS ROW ================
        # database button
        btn_style = get_btn_style(txt_color="white", bg_color="blue")
        self.load_db_btn = QPushButton("Load Database")
        self.load_db_btn.setStyleSheet(btn_style)
        self.load_db_btn.setFixedSize(150, 50)
        self.load_db_btn.clicked.connect(self.on_load_db)

        # update animals information button
        btn_style = get_btn_style(txt_color="white", bg_color="black")
        self.update_info_btn = QPushButton("Animals Infos")
        self.update_info_btn.setStyleSheet(btn_style)
        self.update_info_btn.setFixedSize(150, 50)
        self.update_info_btn.clicked.connect(self.on_update_info)

        # continue button
        btn_style = get_btn_style(txt_color="white", bg_color="red")
        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setStyleSheet(btn_style)
        self.continue_btn.setFixedSize(150, 50)
        self.continue_btn.clicked.connect(self.on_continue)

        # row layout
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self.load_db_btn)
        buttons_row.addWidget(self.update_info_btn)
        buttons_row.addWidget(self.continue_btn)
        buttons_row.addStretch(1)

        main_layout.addLayout(buttons_row)

        self.setLayout(main_layout)

    def update_database_info(self):
        """Update database information displayed in the main window."""
        infos = {}
        if self.database_path is not None:
            t_format = "%Y %B - %A %d - %H:%M"
            infos = DatabaseAnalyzer.get_informations(self.database_path)

            local_time = datetime.now().astimezone()
            utc_offset = local_time.utcoffset()
            utc_offset_name = local_time.tzname()
            if utc_offset is None:
                logging.warning("Warning: UTC offset is None, setting to 0.")
                utc_offset = pd.Timedelta(0)
                utc_offset_str = "?"
            else:
                utc_hours = utc_offset.total_seconds() / 3600
                if utc_hours == int(utc_hours):
                    utc_offset_str = f"{int(utc_hours):+.0f}"
                elif (utc_hours * 10) == int(utc_hours * 10):
                    utc_offset_str = f"{utc_hours:+.1f}"
                else:
                    utc_offset_str = f"{utc_hours:+.2f}"

            start_time = infos["start_time"].strftime(t_format)
            end_time = infos["end_time"].strftime(t_format)
            d = infos["duration"].days
            h = infos["duration"].seconds // 3600
            m = (infos["duration"].seconds // 60) % 60

            self.info_lbl["db_name"].setText(infos["database_name"])
            self.info_lbl["animals"].setText(str(infos["n_animals"]))
            self.info_lbl["start"].setText(f"(UTC+0) {start_time}")
            self.info_lbl["end"].setText(f"(UTC+0) {end_time}")
            self.info_lbl["tz"].setText(
                "<span>&#11169;&nbsp;</span> your current time zone: "
                f"UTC{utc_offset_str} - {utc_offset_name}"
            )
            self.info_lbl["duration"].setText(
                f"{d} days, {h} hours and {m} minutes"
            )
            self.info_lbl["fps"].setText(f"{infos['fps']:.1f}")

            for row_id in range(self.info_form.rowCount()):
                if row_id > 0:
                    self.info_form.setRowVisible(row_id, True)

        else:
            for lbl in self.info_lbl.values():
                lbl.setText("")
            self.info_lbl["db_name"].setText("No loaded database.")

            for row_id in range(self.info_form.rowCount()):
                if row_id > 0:
                    self.info_form.setRowVisible(row_id, False)

    def adjust_continue_btn_color(self):
        """Modify continue button style depending on the database load
        status."""
        if self.database_path:
            btn_style = get_btn_style(txt_color="white", bg_color="green")
        else:
            btn_style = get_btn_style(txt_color="white", bg_color="red")
        self.continue_btn.setStyleSheet(btn_style)

    def on_load_db(self):
        """Launches a file dialog for loading database."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SQLite file",
            "",
            "SQLite files (*.sqlite);;All files (*)",
        )
        if not file_path:
            return
        self.database_path = Path(file_path)
        app_state.database_path = self.database_path  # shared with MCP tools
        self.update_database_info()

        self.adjust_continue_btn_color()

    def warning_message_load_database(self):
        """Check if a database is loaded, and show a warning if not."""
        QMessageBox.warning(
            self,
            "No Database",
            "You must load a database before.",
        )

    def on_update_info(self):
        """Update animals information in database."""
        if self.database_path is None:
            self.warning_message_load_database()
            return

        UpdateDatabaseInfo(self, self.database_path).exec()

    def on_continue(self):
        """Rebuild database then analyse it."""
        if self.database_path is None:
            self.warning_message_load_database()
            return

        dlg = AnalysisSettingsWindow(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            settings = dlg.settings
            rebuild_only = dlg.rebuild_only
        else:
            logging.warning("Process cancelled.")
            return

        analyzer = DatabaseAnalyzer(self.database_path, settings)

        progress_bar = DbAnalysisProgressBar(
            self, database_name=self.database_path.stem
        )

        worker = AnalysisWorker(analyzer, rebuild_only=rebuild_only)
        worker.signals.rebuild_progress.connect(
            progress_bar.set_rebuild_progress
        )
        worker.signals.analyse_progress.connect(
            progress_bar.set_analyse_progress
        )
        if rebuild_only:
            worker.signals.analyzer.connect(self.rebuild_only_finished)
        else:
            worker.signals.analyzer.connect(self.handle_open_analysis)
        worker.signals.finished.connect(progress_bar.progression_finished)

        progress_bar.show()
        self.threadpool.start(worker)

        logging.info(f"Process for {self.database_path.stem} started.")

    def handle_open_analysis(self, analyzer: DatabaseAnalyzer | None):
        """Ask user if they want to open the processed results when the
        analysis is finished.
        Automatically close the window after 5 minutes if the user does not
        answer."""
        if analyzer is not None:
            logging.info("*** PROCESS FINISHED ***")

            if analyzer.database_path is None:
                logging.error("Analyzer has no database path.")
                return

            name = analyzer.database_path.stem
            output = analyzer.get_output_folder()
            text = f"""
            LMT-EYE has finished to analyse the following database:
            {name}\n
            Results are saved in:
            {output}\n
            Do you want to open the results ?
            """
            dlg = YesNoQuestion(
                parent=self,
                question=text,
                timeout_s=300,  # 5 minutes
            )
            if dlg.exec():
                analyzer.open_results()
        else:
            logging.critical("Analysis failed.")
            QMessageBox.critical(self, "Processing", "Analysis failed.")

    def rebuild_only_finished(self, analyzer: DatabaseAnalyzer | None):
        """Inform the user that the database has been rebuilt.
        Automatically close the window after 5 minutes if the user does not
        answer."""
        if analyzer is not None:

            if analyzer.database_path is None:
                logging.error("Analyzer has no database path.")
                return

            text = (
                "LMT-EYE has finished to rebuild the following database:\n"
                f"{analyzer.database_path.stem}"
            )

            QMessageBox.information(
                self,
                "Rebuild only",
                text,
            )
            logging.info("Rebuild only process finished.")
        else:
            logging.critical("Rebuild failed.")
            QMessageBox.critical(self, "Rebuild only", "Rebuild failed.")


class AnalysisWorkerSignals(QObject):
    """Manage signals from a running worker thread."""

    finished = pyqtSignal(bool)
    analyzer = pyqtSignal(DatabaseAnalyzer)
    rebuild_progress = pyqtSignal(int, int)
    """Progression as (int, int) signal meaning (current, max)."""
    analyse_progress = pyqtSignal(int, int)
    """Progression as (int, int) signal meaning (current, max)."""


class AnalysisWorker(QRunnable):
    def __init__(
        self,
        data_analyzer: DatabaseAnalyzer,
        rebuild_only: bool = False,
    ):
        super().__init__()
        self.data_analyzer = data_analyzer
        self.rebuild_only = rebuild_only
        self.signals = AnalysisWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            self.data_analyzer.rebuild_database(
                progress_callback=self.signals.rebuild_progress.emit
            )
            if not self.rebuild_only:
                self.data_analyzer.run_analysis(
                    progress_callback=self.signals.analyse_progress.emit
                )

            self.signals.finished.emit(True)
            self.signals.analyzer.emit(self.data_analyzer)

        except Exception as e:
            logging.critical(f"AnalysisWorker failed to run.\nException: {e}")
            traceback.print_exc()
            self.signals.finished.emit(False)


class DbAnalysisProgressBar(QDialog):
    """Dialog to show progress during database analysis."""

    def __init__(
        self,
        parent: QWidget | None = None,
        title="Analysis progression",
        database_name: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.setFixedSize(350, 220)
        self._init_ui(database_name)

    def _init_ui(self, database_name: str | None):
        form = QFormLayout()

        if database_name is None:
            label_text = "Processing. Please wait."
        else:
            label_text = f"{database_name}\nis being processed. Please wait."

        process_label = QLabel(label_text)
        process_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        process_label.setStyleSheet("font-size: 15px;")

        movie_label = QLabel()
        movie_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movie = QMovie(str(GIF_PATH))
        if self.movie.isValid():
            movie_label.setMovie(self.movie)
            self.movie.start()

        self.rebuild_progress = QProgressBar()
        self.rebuild_progress.setMinimum(0)
        self.analyse_progress = QProgressBar()
        self.analyse_progress.setMinimum(0)

        form.addRow(process_label)
        form.addRow(movie_label)
        form.addRow("Rebuild Progress", self.rebuild_progress)
        form.addRow("Analyse Progress", self.analyse_progress)

        self.setLayout(form)

    def set_rebuild_progress(self, value, maximum):
        self.rebuild_progress.setMaximum(maximum)
        self.rebuild_progress.setValue(value)

    def set_analyse_progress(self, value, maximum):
        self.analyse_progress.setMaximum(maximum)
        self.analyse_progress.setValue(value)

    def progression_finished(self, is_finished: bool):
        if is_finished:
            self.accept()
        else:
            self.reject()


class AnalysesComparisonWidget(QWidget):
    """Analysis Comparison Widget for LMT-EYE.
    It allows to select one or multiple database analyses, compare them
    according to set animal information and create comparison reports.
    """

    def __init__(self):
        """Initialize the analysis comparison widget."""
        super().__init__()
        self.analyses_path: list[Path] = []
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self._init_ui()

    def _init_ui(self):
        """Initialize the UI elements of the analysis comparison window."""
        main_layout = QVBoxLayout()

        # ================ ANALYSES INFORMATIONS ================

        self.info_label = QLabel()
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        self.info_label.setText("<b>No loaded analyses.</b>")

        analyses_info_row = QHBoxLayout()
        analyses_info_row.addWidget(self.info_label)
        main_layout.addLayout(analyses_info_row)

        # ================ BUTTONS ROW ================

        btn_style = get_btn_style(txt_color="white", bg_color="blue")

        # add one analysis button
        self.add_one_btn = QPushButton("Add one")
        self.add_one_btn.setToolTip(
            "<b>Add a single analysis.</b><br>"
            "The selected folder must have the following file:<br>"
            f"<i>{ComparisonSettings.MAIN_TABLE}</i>"
        )
        self.add_one_btn.setStyleSheet(btn_style)
        self.add_one_btn.setFixedSize(120, 50)
        self.add_one_btn.clicked.connect(self.on_load_one)

        # add multiple analysis button
        self.add_multiple_btn = QPushButton("Add multiple")
        self.add_multiple_btn.setToolTip(
            "<b>Add all analyses found in folder.</b><br>"
            "The selected folder must contain at least one valid analysis."
            "A valid analysis must have the following file:<br>"
            f"<i>{ComparisonSettings.MAIN_TABLE}</i>"
        )
        self.add_multiple_btn.setStyleSheet(btn_style)
        self.add_multiple_btn.setFixedSize(120, 50)
        self.add_multiple_btn.clicked.connect(self.on_load_multiple)

        # remove analysis button
        btn_style = get_btn_style(txt_color="white", bg_color="black")
        self.remove_analyses_btn = QPushButton("Remove")
        self.remove_analyses_btn.setStyleSheet(btn_style)
        self.remove_analyses_btn.setFixedSize(120, 50)
        self.remove_analyses_btn.clicked.connect(self.on_remove_analysis)

        # continue button
        btn_style = get_btn_style(txt_color="white", bg_color="red")
        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setStyleSheet(btn_style)
        self.continue_btn.setFixedSize(120, 50)
        self.continue_btn.clicked.connect(self.on_continue)

        # row layout
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self.add_one_btn)
        buttons_row.addWidget(self.add_multiple_btn)
        buttons_row.addWidget(self.remove_analyses_btn)
        buttons_row.addWidget(self.continue_btn)
        buttons_row.addStretch(1)

        main_layout.addLayout(buttons_row)

        self.setLayout(main_layout)

    def update_analyses_info(self):
        """Update analyses information displayed in the main window."""

        common_columns = ComparisonSettings.get_common_columns_from_list(
            self.analyses_path
        )

        info_html = f"""
            <table style='font-size:13px;'>
            <tr>
                <td><b>Number of loaded analyses:</b></td>
                <td>{len(self.analyses_path)}</td>
            </tr>
            <br>
            <tr>
                <td><b>Available Comparators:</b></td>
                <td>{", ".join(sorted(common_columns))}</td>
            </tr>
            </table>
        """
        self.info_label.setText(info_html)

    def show_invalid_folder(
        self,
        path: Path,
        multiple_analyses: bool = False,
    ):
        """Show a warning message for an invalid analysis."""
        if multiple_analyses:
            msg = (
                "The selected folder <b>DOES NOT</b> contain at least one "
                "valid analysis."
            )
        else:
            msg = (
                f"The selected folder ({path.name}) <b>IS NOT</b> a valid "
                "analysis."
            )
        QMessageBox.warning(
            self,
            "Invalid Analysis",
            msg,
        )

    def adjust_continue_btn_color(self):
        """Modify continue button style depending on the analyses path load
        status."""
        if self.analyses_path:
            btn_style = get_btn_style(txt_color="white", bg_color="green")
        else:
            btn_style = get_btn_style(txt_color="white", bg_color="red")
        self.continue_btn.setStyleSheet(btn_style)

    def on_load_one(self):
        """Launches a file dialog for loading a single analysis."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "LMT-EYE - Select One Analysis Directory",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not dir_path:
            return

        dir_path = Path(dir_path)
        if not (dir_path / ComparisonSettings.MAIN_TABLE).exists():
            self.show_invalid_folder(dir_path)
            return

        self.analyses_path.append(dir_path)
        self.update_analyses_info()

        self.adjust_continue_btn_color()

    def on_load_multiple(self):
        """Launches a file dialog for loading multiple analyses."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "LMT-EYE - Select One Directory That Contains Multiple Analyses",
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not dir_path:
            return

        dir_path = Path(dir_path)
        analyses_path = [
            dir
            for dir in dir_path.iterdir()
            if dir.is_dir() and (dir / ComparisonSettings.MAIN_TABLE).exists()
        ]
        if not analyses_path:
            self.show_invalid_folder(dir_path, multiple_analyses=True)
            return

        self.analyses_path.extend(analyses_path)
        self.update_analyses_info()

        self.adjust_continue_btn_color()

    def on_remove_analysis(self):
        """Remove the last loaded analysis."""
        if not self.analyses_path:
            QMessageBox.information(
                self,
                "No Analysis to Remove",
                "No analysis available for removal.",
            )
            return
        analysis_dict = {path.name: path for path in self.analyses_path}
        analysis_name, ok = QInputDialog.getItem(
            self,
            "Remove Analysis",
            "Select analysis to remove:",
            sorted(analysis_dict.keys()),
            0,
            False,
        )
        if not ok or not analysis_name:
            return
        self.analyses_path.remove(analysis_dict[analysis_name])
        logging.info(f"Removed analysis: {analysis_name}")
        self.update_analyses_info()

        self.adjust_continue_btn_color()

    def warning_message_load_analyses(self):
        """Check if analyses are loaded, and show a warning if not."""
        QMessageBox.warning(
            self,
            "No Analyses",
            "You must load analyses before.",
        )

    def on_continue(self):
        """Rebuild analyses then analyse it."""
        if not self.analyses_path:
            self.warning_message_load_analyses()
            return

        settings_window = ComparisonSettingsWindow(self, self.analyses_path)
        if settings_window.exec() == QDialog.DialogCode.Accepted:
            settings = settings_window.settings
        else:
            logging.warning("Process cancelled.")
            return

        progress_bar = AnalysesComparisonProgressBar(
            self,
            report_color=settings.report_color,
            analyses_path=settings.analyses_path,
        )

        data_comparator = AnalysesComparator(settings)

        worker = ComparisonWorker(data_comparator)
        worker.signals.comparison_progress.connect(
            progress_bar.set_comparison_progress
        )
        worker.signals.comparator.connect(self.handle_open_analysis)
        worker.signals.finished.connect(progress_bar.progression_finished)

        progress_bar.show()
        self.threadpool.start(worker)

        logging.info(
            f"Comparison process for {len(self.analyses_path)} "
            "analyses started."
        )

    def handle_open_analysis(self, comparator: AnalysesComparator | None):
        """Ask user if they want to open the processed results when the
        analysis is finished.
        Automatically close the window after 5 minutes if the user does not
        answer."""
        if comparator is not None:
            logging.info("*** PROCESS FINISHED ***")

            output = comparator.get_output_folder()
            text = f"""
            LMT-EYE has finished to compare the {len(self.analyses_path)}
            analyses. Results are saved in:\n
            {output}\n
            Do you want to open the results ?
            """
            dlg = YesNoQuestion(
                parent=self,
                question=text,
                timeout_s=300,  # 5 minutes
            )
            if dlg.exec():
                comparator.open_results()
        else:
            QMessageBox.critical(self, "Error", "Analysis failed.")


class ComparisonWorkerSignals(QObject):
    """Manage signals from a running worker thread."""

    finished = pyqtSignal(bool)
    comparator = pyqtSignal(AnalysesComparator)
    comparison_progress = pyqtSignal(int, int)  # current, max


class ComparisonWorker(QRunnable):
    def __init__(self, data_comparator: AnalysesComparator):
        super().__init__()
        self.data_comparator = data_comparator
        self.signals = ComparisonWorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            self.data_comparator.compare_analyses(
                progress_callback=self.signals.comparison_progress.emit
            )
            self.signals.finished.emit(True)
            self.signals.comparator.emit(self.data_comparator)

        except Exception as e:
            logging.critical(f"ComparisonWorker failed to run. Exception: {e}")
            traceback.print_exc()
            self.signals.finished.emit(False)


class AnalysesComparisonProgressBar(QDialog):
    """Dialog to show progress during analyses comparison."""

    def __init__(
        self,
        parent: QWidget | None = None,
        title="Comparison progression",
        report_color: str = "RFID",
        analyses_path: list[Path] = [],
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(False)
        self.setFixedSize(350, 220)
        self._init_ui(report_color, analyses_path)

    def _init_ui(self, report_color: str, analyses_path: list[Path]):
        form = QFormLayout()

        if not analyses_path:
            label_text = f"Processing using {report_color}. Please wait."
        else:
            label_text = (
                f"{len(analyses_path)} analyses are being processed.\n"
                f"{report_color} is the comparator.\nPlease wait."
            )

        process_label = QLabel(label_text)
        process_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        process_label.setStyleSheet("font-size: 15px;")

        movie_label = QLabel()
        movie_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movie = QMovie(str(GIF_PATH))
        if self.movie.isValid():
            movie_label.setMovie(self.movie)
            self.movie.start()

        self.comparison_progress = QProgressBar()
        self.comparison_progress.setMinimum(0)

        form.addRow(process_label)
        form.addRow(movie_label)
        form.addRow("<b>Comparison Progress</b>", self.comparison_progress)

        self.setLayout(form)

    def set_comparison_progress(self, value, maximum):
        self.comparison_progress.setMaximum(maximum)
        self.comparison_progress.setValue(value)

    def progression_finished(self, is_finished: bool):
        if is_finished:
            self.accept()
        else:
            self.reject()


def exception_hook(type_, value, tb):
    """Global exception hook to catch unhandled exceptions and display them in
    a message box."""
    traceback.print_exception(type_, value, tb)
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("Application Error")
    msg.setText("An unexpected error occurred.")
    msg.setDetailedText("".join(traceback.format_exception(type_, value, tb)))
    msg.exec()


if __name__ == "__main__":

    try:
        # set windows taskbar icon (must be before QApplication)
        from ctypes import windll

        windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "lmt.lmt-eye.app"
        )
    except ImportError:
        # not on windows, do nothing
        pass

    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setApplicationName("LMT-EYE")

    # local MCP server: ask once on first launch, then follow the preference
    mcp_controller = get_controller(APP_VERSION)
    if not McpSettings.exists():
        answer = QMessageBox.question(
            None,
            "LMT-EYE - MCP server",
            "Enable the local MCP server?\n\n"
            "It lets MCP clients (Claude, ...) running on this computer read "
            "LMT-EYE data. You can change this later in the analysis "
            "settings or in Menu > Local MCP server.",
        )
        mcp_controller.set_enabled(
            answer == QMessageBox.StandardButton.Yes
        )
    elif mcp_controller.settings.enabled:
        mcp_controller.start()
    app.aboutToQuit.connect(mcp_controller.stop)

    main_window = LMTEYEApp()

    main_window.show()
    sys.exit(app.exec())
