import os, re, sys
from pathlib import Path
d = Path(sys.argv[1])
new_writing = Path(sys.argv[2]).read_text(encoding="utf-8")
ql = d / "query_log.py"; tl = d / "tools.py"
# refuse if files changed since backup
b = d.parent / "backups_mcp_prompt_log_20261117"
for f in (ql, tl):
    assert f.read_bytes() == (b / f.name).read_bytes(), f"{f.name} changed since backup"

s = ql.read_text(encoding="utf-8")
old_doc = s[: s.index('"""', 3) + 3]
new_doc = '''"""Local log of the user prompts sent to the AI when it uses LMT-EYE.

The MCP server never receives what the user types to the AI: it only
receives the AI's tool calls. So the AI is asked (in the server
instructions) to call the ``record_user_prompt`` tool with the user's
message, copied word for word, only when it uses LMT-EYE tools to answer
that message. As a safeguard, a prompt is only written once another
LMT-EYE tool is actually called in the same conversation (``tool_used``):
messages answered without LMT-EYE are never written.

Prompts are written one JSON line each in
``mcp_server/logs/user_prompts.log``: local time, client, session and prompt.
The file is rotated at 5 MB and the 5 previous files are kept.

Logging must never break the server: every error inside this module is
caught and reported once in the application log.
"""'''
s = s.replace(old_doc, new_doc, 1)
anchor = '"""The same prompt from the same client within this delay is logged once."""\n'
assert anchor in s
s = s.replace(anchor, anchor + '''PENDING_WINDOW_S = 600
"""A received prompt is dropped if no LMT-EYE tool is used within this delay."""
RECENT_TOOL_USE_S = 60
"""A prompt received this soon after a tool call is written at once."""
''', 1)
anchor2 = "_last: dict[str, tuple[str, float]] = {}\n"
assert anchor2 in s
s = s.replace(anchor2, anchor2 + "_pending: dict[str, tuple[str, float, str, str | None]] = {}\n_last_tool_use: dict[str, float] = {}\n", 1)
i = s.index("# ================ WRITING ================")
s = s[:i] + new_writing
ql.write_text(s, encoding="utf-8")

t = tl.read_text(encoding="utf-8")
old_instr = ('''    "Prompt log: before using LMT-EYE tools to answer a user message, call "
    "record_user_prompt once with that message copied word for word (no "
    "summary, no translation). Do not call it again for the other tool calls "
    "answering the same message.\\n"''')
assert old_instr in t
t = t.replace(old_instr, '''    "Prompt log: only when you use LMT-EYE tools to answer a user message, "
    "call record_user_prompt once with that message copied word for word (no "
    "summary, no translation), together with or just before your first "
    "other LMT-EYE tool call. Never call it for a message you answer without "
    "LMT-EYE tools, and do not call it again for the other tool calls "
    "answering the same message.\\n"''', 1)
old_tdoc = '''        """Record the user's message in LMT-EYE's local prompt log.

        Call it once per user message, before the other LMT-EYE tools, with
        the user's message copied word for word: no summary, no
        translation, no added context. Do not call it again for the other
        tool calls that answer the same message. It returns
        {"recorded": true} or the reason it was not recorded; either way,
        go on answering the user."""'''
assert old_tdoc in t
t = t.replace(old_tdoc, '''        """Record the user's message in LMT-EYE's local prompt log.

        Call it only when you use other LMT-EYE tools to answer the
        message, once, with or just before the first of them. Never call it
        for a message answered without LMT-EYE tools. Copy the user's
        message word for word: no summary, no translation, no added context.
        The message is written to the log when another LMT-EYE tool is
        called. It returns {"recorded": ...} or {"pending": true} with a
        reason; either way, go on answering the user."""''', 1)
anchor3 = "    query_log.setup()\n"
assert anchor3 in t
t = t.replace(anchor3, anchor3 + '''
    def _mark_used(ctx: Context) -> None:
        """Tell the prompt log that LMT-EYE is used to answer: the pending
        user prompt of this conversation is written now."""
        try:
            request_context = ctx.request_context
        except Exception:
            request_context = None
        query_log.tool_used(request_context)
''', 1)
sigs = {
    "def get_loaded_database() -> dict[str, Any]:": "def get_loaded_database(ctx: Context) -> dict[str, Any]:",
    "def get_database_info(database_path: str | None = None)": "def get_database_info(\n        ctx: Context, database_path: str | None = None\n    )",
    "def list_animals(database_path: str | None = None)": "def list_animals(\n        ctx: Context, database_path: str | None = None\n    )",
    "    def list_event_types(\n        database_path": "    def list_event_types(\n        ctx: Context,\n        database_path",
    "        event_names: list[str],\n": "        event_names: list[str],\n        ctx: Context,\n",
    "        sql: str,\n": "        sql: str,\n        ctx: Context,\n",
}
for a, bb in sigs.items():
    assert t.count(a) == 1, a
    t = t.replace(a, bb)
# insert _mark_used(ctx) after the docstring of each data tool
names = ["get_loaded_database", "get_database_info", "list_animals", "list_event_types", "get_event_summary", "query_database"]
for n in names:
    i = t.index(f"def {n}(")
    j = t.index('"""', i); j = t.index('"""', j + 3) + 3
    t = t[:j] + "\n        _mark_used(ctx)" + t[j:]
t = t.replace("the AI passes to ``record_user_prompt`` are written to", "the AI passes to ``record_user_prompt`` are written, only once another\ntool is used to answer them, to")
tl.write_text(t, encoding="utf-8")
print("patched")
