import hashlib
import json
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp.server.mcpserver.exceptions import ToolError
from mcp_server.tools import build_server


class TestCatalog(unittest.IsolatedAsyncioTestCase):
    async def test_discover_download_and_replay(self):
        server = build_server()
        listing = await server.call_tool("list_analysis_methods", {})
        method = listing.structured_content["result"][0]
        result = await server.call_tool(
            "get_analysis_method", {"method_id": method["id"], "version": method["version"]}
        )
        entry = json.loads(result.content[0].text)
        source = entry["source"].encode("utf-8")
        self.assertEqual(hashlib.sha256(source).hexdigest(), entry["sha256"])
        fixture = entry["validation"]
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            script = folder / "download.py"
            script.write_bytes(source)
            database = folder / "example.sqlite"
            with closing(sqlite3.connect(database)) as conn, conn:
                conn.execute(fixture["schema_sql"])
                conn.executemany("INSERT INTO EVENT VALUES (?, ?, ?, ?)", fixture["rows"])
            args = fixture["arguments"]
            output = subprocess.check_output(
                [sys.executable, str(script), str(database), args["event"],
                 str(args["animal_id"]), str(args["start"]), str(args["end"])],
                text=True,
            )
            self.assertEqual(json.loads(output), fixture["expected"])
        with self.assertRaises(ToolError):
            await server.call_tool("get_analysis_method", {"method_id": method["id"], "version": "0"})
