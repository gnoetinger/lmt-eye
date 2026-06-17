import logging
from types import ModuleType
from typing import Any, Literal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from events.events_manager import OFFICIAL_EVENTS, CUSTOM_EVENTS
from widgets.pyqt6_tools import get_btn_style


class EventSelectionWindow(QDialog):
    """PyQt6 Dialog to select which analysis to perform"""

    def __init__(
        self,
        parent: QWidget | None,
        events_package: Literal["official", "custom"] = "official",
        preselected_events: set[str] | None = None,
    ):
        super().__init__(parent)
        if preselected_events is None:
            preselected_events = set()
        self.selected_events: set[str] = preselected_events
        match events_package:
            case "official":
                self._init_ui(OFFICIAL_EVENTS)
            case "custom":
                self._init_ui(CUSTOM_EVENTS)
            case _:
                raise ValueError(
                    f"Invalid events_package: {events_package}. "
                    "Expected 'official' or 'custom'."
                )

    def _init_ui(self, events_dict: dict[str, Any]):
        self.setWindowTitle("LMT-EYE - Analysis Settings - Event Selection")
        self.setFixedSize(1000, 400)
        layout = QVBoxLayout()

        label = QLabel("Available events:")
        label.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(
            label,
            alignment=Qt.AlignmentFlag.AlignHCenter
            | Qt.AlignmentFlag.AlignTop,
        )

        grid_layout = QGridLayout()
        self.analysis_options = []
        max_col = 5
        row = 0
        col = 0
        for name in sorted(events_dict.keys()):
            cb = QCheckBox(name)
            module = events_dict[name]
            if isinstance(module, ModuleType):
                if getattr(module, "EVENTS_DESCRIPTION", None) is not None:
                    cb.setToolTip(module.EVENTS_DESCRIPTION)
            grid_layout.addWidget(cb, row, col)
            self.analysis_options.append(cb)
            if name in self.selected_events:
                cb.setChecked(True)
            col += 1
            if col >= max_col:
                col = 0
                row += 1

        grid_layout.setRowStretch(row + 1, 1)
        grid_widget = QWidget()
        grid_widget.setLayout(grid_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_widget)
        layout.addWidget(scroll_area)

        btn_style = get_btn_style(txt_color="white", bg_color="blue")
        self.proceed_btn = QPushButton("Validate Selection")
        self.proceed_btn.setStyleSheet(btn_style)
        self.proceed_btn.clicked.connect(self.on_validation)
        layout.addWidget(
            self.proceed_btn, alignment=Qt.AlignmentFlag.AlignHCenter
        )

        self.setLayout(layout)

    def on_validation(self):
        """Get all selected events."""
        self.selected_events = self.get_selected_events()
        if self.selected_events:
            list_events = ", ".join(self.selected_events)
        else:
            list_events = "No event selected"
        logging.info(f"Selected events: {list_events}.")
        self.accept()

    def get_selected_events(self) -> set[str]:
        """Return a set of event names for checked checkboxes."""
        return {cb.text() for cb in self.analysis_options if cb.isChecked()}


if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication

    app = QApplication([])
    preselected = {"Flickering", "Stop", "Corner"}
    dialog = EventSelectionWindow(
        None,
        events_package="official",
        # events_package="custom",
        preselected_events=preselected,
    )
    if dialog.exec():
        print("Selected events:", dialog.selected_events)
