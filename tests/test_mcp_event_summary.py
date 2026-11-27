import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp.server.mcpserver.exceptions import ToolError
from mcp_server.tools import build_server


class TestEventSummary(unittest.IsolatedAsyncioTestCase):
    async def test_summary_and_replay(self):
        server = build_server()
        with TemporaryDirectory() as temp:
            path = Path(temp) / "recording.sqlite"
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.executescript("""
                    CREATE TABLE FRAME(FRAMENUMBER, TIMESTAMP);
                    INSERT INTO FRAME VALUES (1,1000),(21,3000);
                    CREATE TABLE ANIMAL(ID, RFID);
                    INSERT INTO ANIMAL VALUES (1,'A'),(2,'B');
                    CREATE TABLE EVENT(NAME, STARTFRAME, ENDFRAME, IDANIMALA,
                                       IDANIMALB, IDANIMALC, IDANIMALD);
                    INSERT INTO EVENT VALUES ('Stop',2,4,1,NULL,NULL,NULL),
                        ('Stop',5,6,1,NULL,NULL,NULL), ('Contact',8,11,1,2,NULL,NULL),
                        ('Contact',8,11,2,1,NULL,NULL), ('Follow',3,4,1,2,NULL,NULL),
                        ('Follow',5,7,2,1,NULL,NULL);
                """)
            args = {"database_path": str(path), "fps": 10}
            for selection, expected in [
                ({"event_name": "Stop"}, [(1, 0.5), (0, 0)]),
                ({"event_name": "Contact", "group_by": "pair", "directional": False}, [(1, 0.4)]),
                ({"event_name": "Follow", "group_by": "pair", "directional": True}, [(1, 0.2), (1, 0.3)]),
            ]:
                with self.subTest(selection=selection):
                    result = await server.call_tool("get_event_summary", {**args, **selection})
                    receipt = json.loads(result.content[0].text)
                    self.assertEqual([(r["count"], r["total_duration_s"]) for r in receipt["results"]], expected)
                    replay = await server.call_tool(receipt["tool"], receipt["arguments"])
                    self.assertEqual(json.loads(replay.content[0].text), receipt)
            with self.assertRaisesRegex(ToolError, "directional"):
                await server.call_tool("get_event_summary", {**args, "event_name": "Follow", "group_by": "pair"})
