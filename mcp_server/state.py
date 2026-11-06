"""State shared between the Qt interface and the MCP server thread.

MCP tools run outside the Qt main thread and must never touch widgets.
The interface writes here (e.g. when a database is loaded) and tools read
from here. Access is protected by a lock.
"""

import threading
from pathlib import Path


class AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._database_path: Path | None = None

    @property
    def database_path(self) -> Path | None:
        with self._lock:
            return self._database_path

    @database_path.setter
    def database_path(self, path: Path | None) -> None:
        with self._lock:
            self._database_path = Path(path) if path is not None else None


app_state = AppState()
"""Single instance used by the whole application."""
