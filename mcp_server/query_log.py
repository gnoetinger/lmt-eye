"""Local log of the user prompts sent to the AI when it uses LMT-EYE.

The MCP server never receives what the user types to the AI: it only
receives the AI's tool calls. So the AI is asked (in the server
instructions) to call the ``record_user_prompt`` tool once per user message,
with the message copied word for word, before using the other tools. This
module writes those prompts, one JSON line each, in
``mcp_server/logs/user_prompts.log``: local time, client, session and prompt.
The file is rotated at 5 MB and the 5 previous files are kept.

Logging must never break the server: every error inside this module is
caught and reported once in the application log.
"""

import json
import logging
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).parent / "logs"
FALLBACK_LOG_DIR = Path.home() / "documents" / "LMT-EYE_settings" / "logs"
"""Used when the application folder is not writable."""
LOG_FILE_NAME = "user_prompts.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
DUPLICATE_WINDOW_S = 600
"""The same prompt from the same client within this delay is logged once."""

_logger = logging.getLogger("lmt_eye.mcp.prompts")
_logger.setLevel(logging.INFO)
_logger.propagate = False  # keep prompts out of the application log
_log_path: Path | None = None
_write_failed = False
_last: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


# ================ SETUP ================


def setup() -> Path | None:
    """Open the log file (only once per process). Return its path, or None
    if no folder is writable."""
    global _log_path
    if _log_path is not None:
        return _log_path

    for folder in (LOG_DIR, FALLBACK_LOG_DIR):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if folder == LOG_DIR:
                ignore = folder / ".gitignore"
                if not ignore.exists():
                    ignore.write_text(
                        "# Local MCP logs: never commit them\n*\n",
                        encoding="utf-8",
                    )
            handler = RotatingFileHandler(
                folder / LOG_FILE_NAME,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
        except OSError as e:
            logging.warning(f"MCP prompt log: cannot write in {folder} ({e})")
            continue
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
        _log_path = folder / LOG_FILE_NAME
        logging.info(f"MCP prompt log: {_log_path}")
        return _log_path

    logging.error("MCP prompt log disabled: no writable folder.")
    return None


def get_log_path() -> Path | None:
    return _log_path


# ================ CLIENT ================


def _get(obj: Any, *names: str) -> Any:
    """First attribute or key found among 'names' (pydantic model or dict)."""
    for name in names:
        if isinstance(obj, dict):
            if name in obj:
                return obj[name]
        elif obj is not None and hasattr(obj, name):
            return getattr(obj, name)
    return None


def client_label(request_context: Any) -> str:
    """'name version' from the MCP handshake, else the HTTP User-Agent."""
    try:
        params = _get(_get(request_context, "session"), "client_params")
        info = _get(params, "clientInfo", "client_info")
        name = _get(info, "name")
        if name:
            version = _get(info, "version")
            return f"{name} {version}" if version else str(name)
    except Exception:
        pass
    try:
        headers = _get(_get(request_context, "request"), "headers")
        if headers is not None and headers.get("user-agent"):
            return str(headers.get("user-agent"))
    except Exception:
        pass
    return "unknown"


def session_id(request_context: Any) -> str | None:
    try:
        headers = _get(_get(request_context, "request"), "headers")
        if headers is not None:
            return headers.get("mcp-session-id")
    except Exception:
        pass
    return None


# ================ WRITING ================


def record_prompt(prompt: str, request_context: Any = None) -> dict[str, Any]:
    """Write one prompt in the log. Return what was done."""
    global _write_failed
    if _log_path is None:
        return {"recorded": False, "reason": "prompt log disabled"}

    client = client_label(request_context)
    session = session_id(request_context)
    key = session or client
    now = time.monotonic()
    with _lock:
        last = _last.get(key)
        if last and last[0] == prompt and now - last[1] < DUPLICATE_WINDOW_S:
            return {"recorded": False, "reason": "already recorded"}
        _last[key] = (prompt, now)

    entry = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "client": client,
        "session": session,
        "prompt": prompt,
    }
    try:
        _logger.info(json.dumps(entry, ensure_ascii=False))
    except Exception as e:  # never break the server because of the log
        if not _write_failed:
            logging.error(f"MCP prompt log: cannot write ({e})")
            _write_failed = True
        return {"recorded": False, "reason": "write error"}
    return {"recorded": True}
