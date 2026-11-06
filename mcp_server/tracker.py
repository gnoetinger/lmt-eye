"""Detection of connected MCP clients.

With the HTTP transport there is no permanent connection, so "connected"
is deduced from traffic on the MCP endpoint. A client is considered
connected when:
    - one of its requests is still open (e.g. a long-lived event stream
      that clients keep open while connected), or
    - its last request is more recent than ``idle_timeout_s``.
A ``DELETE`` request (clean session close) forgets the client at once.

Clients are identified by their ``Mcp-Session-Id`` header when present,
otherwise by their User-Agent and address.
"""

import threading
import time
from dataclasses import dataclass

IDLE_TIMEOUT_S = 60.0


@dataclass
class _Client:
    label: str
    last_seen: float
    open_requests: int = 0


class ClientTracker:
    def __init__(self, idle_timeout_s: float = IDLE_TIMEOUT_S) -> None:
        self.idle_timeout_s = idle_timeout_s
        self._lock = threading.Lock()
        self._clients: dict[str, _Client] = {}

    # ---- called from the server thread ----

    def request_started(self, key: str, label: str) -> None:
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                client = _Client(label=label, last_seen=time.monotonic())
                self._clients[key] = client
            client.open_requests += 1
            client.last_seen = time.monotonic()

    def request_finished(self, key: str) -> None:
        with self._lock:
            client = self._clients.get(key)
            if client is not None:
                client.open_requests = max(0, client.open_requests - 1)
                client.last_seen = time.monotonic()

    def forget(self, key: str) -> None:
        with self._lock:
            self._clients.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._clients.clear()

    # ---- called from the Qt thread ----

    def connected_clients(self) -> list[str]:
        """Labels of the clients currently considered connected."""
        now = time.monotonic()
        with self._lock:
            # drop clients idle for a long time
            for key in [
                k
                for k, c in self._clients.items()
                if c.open_requests == 0
                and now - c.last_seen > 10 * self.idle_timeout_s
            ]:
                del self._clients[key]
            return sorted(
                {
                    c.label
                    for c in self._clients.values()
                    if c.open_requests > 0
                    or now - c.last_seen < self.idle_timeout_s
                }
            )

    def is_connected(self) -> bool:
        return bool(self.connected_clients())


class TrackingMiddleware:
    """ASGI middleware that reports MCP traffic to a ClientTracker without
    modifying requests or responses."""

    def __init__(self, app, tracker: ClientTracker, path: str = "/mcp"):
        self.app = app
        self.tracker = tracker
        self.path = path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(
            self.path
        ):
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        user_agent = headers.get("user-agent", "unknown client")
        host = (scope.get("client") or ("?", 0))[0]
        session_id = headers.get("mcp-session-id")
        key = session_id or f"{host}|{user_agent}"
        label = user_agent.split(" ")[0] or "unknown client"

        if scope["method"] == "DELETE":
            self.tracker.forget(key)
            self.tracker.forget(f"{host}|{user_agent}")
            await self.app(scope, receive, send)
            return

        if session_id is not None:
            # the first request of a session (initialize) has no session id
            # yet and was recorded under a provisional key: drop it
            self.tracker.forget(f"{host}|{user_agent}")

        self.tracker.request_started(key, label)
        try:
            await self.app(scope, receive, send)
        finally:
            self.tracker.request_finished(key)
