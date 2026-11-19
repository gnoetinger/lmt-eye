import sys
from pathlib import Path
d = Path(sys.argv[1])
def rd(p): return p.read_text(encoding="utf-8").replace("\r\n", "\n")
def wr(p, s): p.write_bytes(s.replace("\n", "\r\n").encode("utf-8"))
def rep(s, a, b):
    assert s.count(a) == 1, a
    return s.replace(a, b)

q = d / "query_log.py"; s = rd(q)
s = rep(s, "_pending: dict[str, tuple[str, float, str, str | None]] = {}",
        "_pending: dict[str, tuple[str, float, str, str | None, dict[str, Any]]] = {}")
s = rep(s, "receives the AI's tool calls. So the AI is asked",
        "receives the AI's tool calls (and the client name, but never the model\n"
        "or the effort). So the AI is asked")
s = rep(s, "``mcp_server/logs/user_prompts.log``: local time, client, session and prompt.",
        "``mcp_server/logs/user_prompts.log``: local time, client, session,\n"
        "AI provider, model and effort (declared by the AI itself, not verified;\n"
        "null when it did not give them) and prompt.")
s = rep(s, "def _write(prompt: str, client: str, session: str | None) -> bool:",
        "AI_FIELDS = (\"provider\", \"model\", \"effort\")\n\n\n"
        "def _clean_ai(ai: dict[str, Any] | None) -> dict[str, Any]:\n"
        "    \"\"\"ai_provider / ai_model / ai_effort entries (None if not given).\"\"\"\n"
        "    ai = ai or {}\n"
        "    out = {}\n"
        "    for name in AI_FIELDS:\n"
        "        value = ai.get(name)\n"
        "        value = str(value).strip()[:200] if value is not None else \"\"\n"
        "        out[f\"ai_{name}\"] = value or None\n"
        "    return out\n\n\n"
        "def _write(\n    prompt: str,\n    client: str,\n    session: str | None,\n"
        "    ai: dict[str, Any] | None = None,\n) -> bool:")
s = rep(s, '        "session": session,\n        "prompt": prompt,',
        '        "session": session,\n        **_clean_ai(ai),\n        "prompt": prompt,')
s = rep(s, "def record_prompt(prompt: str, request_context: Any = None) -> dict[str, Any]:",
        "def record_prompt(\n    prompt: str,\n    request_context: Any = None,\n"
        "    ai: dict[str, Any] | None = None,\n) -> dict[str, Any]:")
s = rep(s, "    written at once.\"\"\"",
        "    written at once. 'ai' holds the provider, model and effort declared\n"
        "    by the AI (not verified).\"\"\"")
s = rep(s, "            _pending[key] = (prompt, now, client, session)",
        "            _pending[key] = (prompt, now, client, session, ai or {})")
s = rep(s, "    return {\"recorded\": _write(prompt, client, session)}",
        "    return {\"recorded\": _write(prompt, client, session, ai)}")
s = rep(s, "            prompt, _, client, session = pending",
        "            prompt, _, client, session, ai = pending")
s = rep(s, "        _write(prompt, client, session)\n",
        "        _write(prompt, client, session, ai)\n")
wr(q, s)

t = d / "tools.py"; s = rd(t)
s = rep(s, '''    "answering the same message.\\n"
    "LMT database conventions:\\n"''',
'''    "answering the same message. Also fill its provider, model and effort "
    "arguments when you know them (e.g. 'Anthropic', your exact model id, "
    "your reasoning effort); leave out what you do not know, never guess.\\n"
    "LMT database conventions:\\n"''')
s = rep(s, "    def record_user_prompt(prompt: str, ctx: Context) -> dict[str, Any]:",
'''    def record_user_prompt(
        prompt: str,
        ctx: Context,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> dict[str, Any]:''')
s = rep(s, '''        called. It returns {"recorded": ...} or {"pending": true} with a
        reason; either way, go on answering the user."""''',
'''        called. It returns {"recorded": ...} or {"pending": true} with a
        reason; either way, go on answering the user.

        Optional, self-declared (written as given, not verified by
        LMT-EYE): provider (e.g. 'Anthropic', 'OpenAI'), model (your exact
        model id) and effort (your reasoning effort level, e.g. 'low',
        'medium', 'high'). Give only what you know; omit the rest rather
        than guess."""''')
s = rep(s, "        return query_log.record_prompt(prompt, request_context)",
        "        ai = {\"provider\": provider, \"model\": model, \"effort\": effort}\n"
        "        return query_log.record_prompt(prompt, request_context, ai)")
wr(t, s)
print("patched")
