"""Status light of the local MCP server, shown at the top right of the main
window (corner of the menu bar).

    green  : server enabled and at least one client connected
    yellow : server enabled, waiting for a client
    red    : server disabled, or stopped on an error
"""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QWidget

from mcp_server import McpServerController, McpStatus

COLORS = {
    McpStatus.CONNECTED: "#2e9e44",
    McpStatus.WAITING: "#e0b000",
    McpStatus.DISABLED: "#d03030",
    McpStatus.ERROR: "#d03030",
}


class McpStatusIndicator(QLabel):
    """Colored dot + "MCP" label, refreshed every second."""

    REFRESH_MS = 1000

    def __init__(
        self, controller: McpServerController, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.controller = controller
        self._last: tuple[McpStatus, str] | None = None
        self.setContentsMargins(0, 0, 8, 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.REFRESH_MS)
        self.refresh()

    def refresh(self) -> None:
        status = self.controller.status()
        if status == self._last:
            return
        self._last = status
        state, description = status
        self.setText(
            f"<span style='color:{COLORS[state]}; font-size:16px;'>&#9679;</span>"
            "&nbsp;<span style='font-size:11px;'>MCP</span>"
        )
        self.setToolTip(description)
