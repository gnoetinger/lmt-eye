"""Start, stop and status of the local MCP server.

The server (uvicorn + Streamable HTTP app of the MCP SDK) runs in a daemon
thread with its own event loop, so the Qt interface is never blocked. The
interface only calls ``start``, ``stop``, ``set_enabled`` and ``status``.
"""

import enum
import logging
import socket
import threading
import time

from mcp_server import client_setup
from mcp_server.settings import McpSettings
from mcp_server.tracker import ClientTracker, TrackingMiddleware

HOST = "127.0.0.1"
MCP_PATH = "/mcp"


class McpStatus(enum.Enum):
    DISABLED = "disabled"  # red
    ERROR = "error"  # red, with an error message
    WAITING = "waiting"  # yellow: running, no client
    CONNECTED = "connected"  # green: running, at least one client


class McpServerController:
    def __init__(
        self,
        settings: McpSettings | None = None,
        app_version: str = "",
    ) -> None:
        self.settings = settings if settings is not None else McpSettings.load()
        self.app_version = app_version
        self.tracker = ClientTracker()
        self.last_error: str | None = None
        self.claude_code_message: str = ""
        """Result of the last registration in Claude Code."""
        self._server = None  # uvicorn.Server
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    # ================ PROPERTIES ================

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.settings.port}{MCP_PATH}"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ================ CONTROL ================

    def set_enabled(self, enabled: bool) -> None:
        """Save the preference, then start or stop the server."""
        self.settings.enabled = enabled
        self.settings.save()
        if enabled:
            self.start()
        else:
            self.stop()

    def start(self) -> bool:
        """Start the server in a background thread. Return True if the
        server is running."""
        with self._lock:
            if self.is_running:
                return True
            self.last_error = None
            self.tracker.reset()

            # bind the port here so that "port already in use" is reported
            # immediately instead of killing the server thread
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
                    sock.setsockopt(
                        socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                    )
                sock.bind((HOST, self.settings.port))
            except OSError as e:
                sock.close()
                self.last_error = (
                    f"Port {self.settings.port} unavailable ({e.strerror})"
                )
                logging.error(f"MCP server: {self.last_error}")
                return False

            try:
                # imported here so that LMT-EYE still starts if the MCP SDK
                # is not installed
                import uvicorn

                from mcp_server.tools import build_server

                mcp_app = build_server(self.app_version).streamable_http_app(
                    streamable_http_path=MCP_PATH, host=HOST
                )
                app = TrackingMiddleware(mcp_app, self.tracker, MCP_PATH)
                config = uvicorn.Config(
                    app,
                    log_level="warning",
                    timeout_graceful_shutdown=2,
                    lifespan="on",
                )
                self._server = uvicorn.Server(config)
            except Exception as e:
                sock.close()
                self.last_error = f"Cannot create MCP server: {e}"
                logging.error(self.last_error)
                return False

            self._thread = threading.Thread(
                target=self._run,
                args=(self._server, sock),
                name="lmt-eye-mcp-server",
                daemon=True,
            )
            self._thread.start()

        logging.info(f"MCP server started on {self.url}")
        if self.settings.register_claude_code:
            threading.Thread(
                target=self.register_in_claude_code,
                name="lmt-eye-mcp-register",
                daemon=True,
            ).start()
        return True

    def register_in_claude_code(self) -> tuple[bool, str]:
        """Register this server in Claude Code (runs the 'claude' command,
        may take a few seconds: call it outside the Qt thread when
        possible)."""
        ok, message = client_setup.register_in_claude_code(self.url)
        self.claude_code_message = message
        if not ok:
            logging.warning(message)
        return ok, message

    def _run(self, server, sock: socket.socket) -> None:
        try:
            server.run(sockets=[sock])
        except BaseException as e:  # uvicorn may raise SystemExit
            self.last_error = f"MCP server stopped: {e!r}"
            logging.error(self.last_error)
        finally:
            sock.close()

    def stop(self, timeout_s: float = 5.0) -> None:
        """Ask the server to stop and wait for its thread."""
        with self._lock:
            server, thread = self._server, self._thread
            if server is None or thread is None:
                return
            server.should_exit = True
            thread.join(timeout_s)
            if thread.is_alive():
                server.force_exit = True
                thread.join(1.0)
            self._server = None
            self._thread = None
            self.tracker.reset()
        logging.info("MCP server stopped.")

    def wait_until_started(self, timeout_s: float = 5.0) -> bool:
        """Block until the server accepts connections (for tests)."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            server = self._server
            if server is not None and server.started:
                return True
            if not self.is_running:
                return False
            time.sleep(0.05)
        return False

    # ================ STATUS ================

    def status(self) -> tuple[McpStatus, str]:
        """Return the current status and a human-readable description."""
        if not self.settings.enabled and not self.is_running:
            return McpStatus.DISABLED, "MCP server disabled"
        if not self.is_running:
            error = self.last_error or "MCP server not running"
            return McpStatus.ERROR, error
        clients = self.tracker.connected_clients()
        if clients:
            return (
                McpStatus.CONNECTED,
                f"MCP server connected ({', '.join(clients)})\n{self.url}",
            )
        return McpStatus.WAITING, f"MCP server waiting for a client\n{self.url}"


_controller: McpServerController | None = None


def get_controller(app_version: str = "") -> McpServerController:
    """Return the application-wide controller (created on first call)."""
    global _controller
    if _controller is None:
        _controller = McpServerController(app_version=app_version)
    return _controller
