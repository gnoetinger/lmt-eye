# ================ WRITING ================


def _key(request_context: Any) -> tuple[str, str | None, str]:
    """(client, session, key): the key identifies one conversation."""
    client = client_label(request_context)
    session = session_id(request_context)
    return client, session, session or client


def _write(prompt: str, client: str, session: str | None) -> bool:
    global _write_failed
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
        return False
    return True


def record_prompt(prompt: str, request_context: Any = None) -> dict[str, Any]:
    """Receive a user prompt from the AI.

    The prompt is only written once the AI really uses an LMT-EYE tool to
    answer it (see ``tool_used``): a prompt sent to record_user_prompt and
    followed by no other LMT-EYE tool call is never written. If a tool was
    already used just before (the AI called the tool first), the prompt is
    written at once."""
    if _log_path is None:
        return {"recorded": False, "reason": "prompt log disabled"}

    client, session, key = _key(request_context)
    now = time.monotonic()
    with _lock:
        last = _last.get(key)
        if last and last[0] == prompt and now - last[1] < DUPLICATE_WINDOW_S:
            return {"recorded": False, "reason": "already recorded"}
        used = _last_tool_use.get(key)
        if used is None or now - used > RECENT_TOOL_USE_S:
            _pending[key] = (prompt, now, client, session)
            return {
                "recorded": False,
                "pending": True,
                "reason": "will be recorded when another LMT-EYE tool is "
                "used to answer this message",
            }
        _pending.pop(key, None)
        _last[key] = (prompt, now)
    return {"recorded": _write(prompt, client, session)}


def tool_used(request_context: Any = None) -> None:
    """Called by every LMT-EYE data tool: write the pending prompt of this
    conversation, if any. Never raises."""
    try:
        if _log_path is None:
            return
        _, _, key = _key(request_context)
        now = time.monotonic()
        with _lock:
            _last_tool_use[key] = now
            pending = _pending.pop(key, None)
            if pending is None or now - pending[1] > PENDING_WINDOW_S:
                return
            prompt, _, client, session = pending
            _last[key] = (prompt, now)
        _write(prompt, client, session)
    except Exception as e:
        logging.error(f"MCP prompt log: {e}")
