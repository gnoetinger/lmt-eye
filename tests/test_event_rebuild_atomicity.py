import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from events.official import BuildEventStop
from scripts.events_rebuilder import EventsRebuilder


class TestRebuildAtomicity(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "recording.sqlite"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE FRAME (FRAMENUMBER INTEGER, TIMESTAMP INTEGER);
            INSERT INTO FRAME VALUES (1, 1000), (21, 3000);
            CREATE TABLE EVENT (ID INTEGER PRIMARY KEY, NAME TEXT, DESCRIPTION TEXT, STARTFRAME INTEGER,
                                ENDFRAME INTEGER, IDANIMALA INTEGER, IDANIMALB INTEGER,
                                IDANIMALC INTEGER, IDANIMALD INTEGER);
            INSERT INTO EVENT (ID, NAME, STARTFRAME, ENDFRAME, IDANIMALA)
                              VALUES (1, 'Stop isolated', 1, 3, 1),
                                     (2, 'Unrelated', 10, 16, 1);
        """)
        self.runner = EventsRebuilder(self.db, fps=10, processing_window=10)

    def published(self):
        with closing(sqlite3.connect(self.path)) as reader:
            return reader.execute(
                "SELECT NAME, STARTFRAME, ENDFRAME FROM EVENT ORDER BY STARTFRAME"
            ).fetchall()

    def test_interruption_after_flush(self):
        original = self.published()
        with patch.object(self.runner, "_rebuild_window", side_effect=RuntimeError("stop")):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                self.runner.rebuild({BuildEventStop})
        self.assertEqual(self.published(), original)

    def test_midway_failure_and_retry(self):
        original = self.published()
        observed = []

        def replace_window(modules, window, progress_callback, window_progress):
            self.db.execute(
                "INSERT INTO EVENT (NAME, STARTFRAME, ENDFRAME, IDANIMALA) "
                "VALUES ('Stop isolated', ?, ?, 1)", window
            )
            self.db.commit()  # builders commit individual windows
            observed.append(self.published())

        def fail_on_second_window(*args, **kwargs):
            if observed:
                raise RuntimeError("interrupted after first window")
            replace_window(*args, **kwargs)

        with patch.object(self.runner, "_rebuild_window", side_effect=fail_on_second_window):
            with self.assertRaisesRegex(RuntimeError, "interrupted after first window"):
                self.runner.rebuild({BuildEventStop})
        self.assertEqual(observed, [original])
        self.assertEqual(self.published(), original)

        observed.clear()
        with patch.object(self.runner, "_rebuild_window", side_effect=replace_window):
            self.runner.rebuild({BuildEventStop})
        self.assertEqual(observed, [original, original])
        self.assertEqual(self.published(), [
            ("Stop isolated", 1, 10), ("Unrelated", 10, 16), ("Stop isolated", 11, 20)
        ])

    def test_official_stop_builder(self):
        self.db.executescript("""
            CREATE TABLE ANIMAL (ID INTEGER, RFID TEXT, NAME TEXT, GENOTYPE TEXT);
            INSERT INTO ANIMAL VALUES (1, 'A', 'A', 'control');
            CREATE TABLE DETECTION (ID, ANIMALID, FRAMENUMBER, MASS_X, MASS_Y, MASS_Z,
                FRONT_X, FRONT_Y, FRONT_Z, BACK_X, BACK_Y, BACK_Z, REARING, LOOK_UP, LOOK_DOWN);
            INSERT INTO EVENT (NAME, STARTFRAME, ENDFRAME, IDANIMALA)
                VALUES ('Stop', 5, 8, 1), ('Detection', 1, 20, 1);
        """)
        self.runner.rebuild({BuildEventStop})
        self.assertEqual([r for r in self.published() if r[0] == "Stop isolated"],
                         [("Stop isolated", 5, 8)])

    def test_caller_transaction_is_preserved(self):
        self.db.execute("UPDATE EVENT SET ENDFRAME=4 WHERE ID=1")
        with self.assertRaisesRegex(ValueError, "current transaction"):
            self.runner.rebuild({BuildEventStop})
        self.assertTrue(self.db.in_transaction)
        self.assertIn(("Stop isolated", 1, 3), self.published())
        self.assertEqual(self.db.execute("SELECT ENDFRAME FROM EVENT WHERE ID=1").fetchone(), (4,))
