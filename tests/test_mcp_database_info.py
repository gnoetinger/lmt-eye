import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp.server.mcpserver.exceptions import ToolError
from mcp_server.tools import build_server


class TestDatabaseInfo(unittest.IsolatedAsyncioTestCase):
    async def test_measured_single_and_empty_frame_tables(self):
        server = build_server()
        with TemporaryDirectory() as temp:
            path = Path(temp) / "experiment.sqlite"
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.executescript("""
                    CREATE TABLE FRAME (FRAMENUMBER INTEGER, TIMESTAMP INTEGER);
                    CREATE TABLE ANIMAL (RFID TEXT);
                    INSERT INTO ANIMAL VALUES ('A');
                """)
            args = {"database_path": str(path)}
            with self.assertRaisesRegex(ToolError, "FRAME table is empty"):
                await server.call_tool("get_database_info", args)
            for frame, timestamp, expected_fps in [(1, 1000, None), (11, 2000, 10)]:
                with closing(sqlite3.connect(path)) as conn, conn:
                    conn.execute("INSERT INTO FRAME VALUES (?, ?)", (frame, timestamp))
                before = hashlib.sha256(path.read_bytes()).digest()
                result = await server.call_tool("get_database_info", args)
                info = json.loads(result.content[0].text)
                self.assertEqual(info["fps"], expected_fps)
                self.assertEqual(info["n_animals"], 1)
                self.assertEqual((info["first_frame"], info["last_frame"]), (1, frame))
                self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)
