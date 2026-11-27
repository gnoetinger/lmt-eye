import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.analyses_comparator import AnalysesComparator
from scripts.db_analyzer import DatabaseAnalyzer
from scripts.settings import AnalysisSettings, ComparisonSettings


def export_recording(folder, genotype, start_ms, bout_end):
    folder.mkdir()
    database = folder / "recording.sqlite"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executescript("""
            CREATE TABLE ANIMAL (ID INTEGER, RFID TEXT, NAME TEXT, GENOTYPE TEXT);
            CREATE TABLE FRAME (FRAMENUMBER INTEGER PRIMARY KEY, TIMESTAMP INTEGER);
            CREATE TABLE DETECTION (ANIMALID INTEGER, FRAMENUMBER INTEGER,
                                    MASS_X REAL, MASS_Y REAL);
            CREATE TABLE EVENT (ID INTEGER PRIMARY KEY, NAME TEXT, DESCRIPTION TEXT,
                                STARTFRAME INTEGER, ENDFRAME INTEGER, IDANIMALA INTEGER,
                                IDANIMALB INTEGER, IDANIMALC INTEGER, IDANIMALD INTEGER,
                                METADATA TEXT);
        """)
        connection.execute("INSERT INTO ANIMAL VALUES (1, '001', 'A', ?)", (genotype,))
        frames = range(1, 22)
        connection.executemany("INSERT INTO FRAME VALUES (?, ?)",
                               [(i, start_ms + i * 100) for i in frames])
        connection.executemany("INSERT INTO DETECTION VALUES (1, ?, ?, 100)",
                               [(i, 100 + i) for i in frames])
        connection.execute("""
            INSERT INTO EVENT (NAME, STARTFRAME, ENDFRAME, IDANIMALA)
            VALUES ('Bout', 2, ?, 1)
        """, (bout_end,))

    settings = AnalysisSettings()
    settings.fps = 10
    settings.time_window = 10
    settings.bin_rounding = False
    settings.events = {"Bout"}
    settings.filter_stop = settings.filter_flickering = False
    analyzer = DatabaseAnalyzer(database, settings)
    analyzer.run_analysis()
    return analyzer.get_output_folder()


class TestAnalysesComparator(unittest.TestCase):
    def test_rejects_ambiguous_or_missing_animal_metadata(self):
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            comparator = AnalysesComparator(ComparisonSettings([folder]))
            table = folder / "Activity_complete_table_Download_data.xlsx"
            pd.DataFrame({"RFID": ["001"]}).to_excel(table, index=False)
            for tags, error in [
                (["001", "001"], pd.errors.MergeError),
                (["002"], ValueError),
            ]:
                with self.subTest(tags=tags):
                    pd.DataFrame({"RFID": tags}).to_excel(
                        folder / ComparisonSettings.MAIN_TABLE, index=False
                    )
                    with self.assertRaises(error):
                        comparator.compare_analyses()

    def test_shared_rfid_keeps_each_recordings_measurements(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            folders = [
                export_recording(root / "first", "control", 1700000000000, 4),
                export_recording(root / "second", "treated", 1700172800000, 7),
            ]
            settings = ComparisonSettings(folders)
            settings.report_color = "GENOTYPE"
            comparator = AnalysesComparator(settings)
            comparator.compare_analyses()
            tables = {
                "Activity_complete_table": ["START_TIME", "DISTANCE"],
                "Bout_complete_table": ["START_TIME", "EVENT_COUNT", "FRAME_COUNT"],
                "Bout_Histogram_of_event_count_over_their_duration": ["NBFRAMES", "COUNT"],
            }
            for table, measurements in tables.items():
                with self.subTest(table=table):
                    filename = f"{table}_Download_data.xlsx"
                    columns = ["GENOTYPE", "RFID", *measurements]
                    sources = []
                    for folder in folders:
                        source = pd.read_excel(folder / filename, dtype={"RFID": str})
                        animals = pd.read_excel(folder / settings.MAIN_TABLE)
                        sources.append(source.assign(GENOTYPE=animals.loc[0, "GENOTYPE"]))
                    expected = pd.concat(sources, ignore_index=True)[columns]
                    actual = pd.read_excel(comparator.get_output_folder() / filename,
                                           dtype={"RFID": str})[columns]
                    if "DISTANCE" in measurements:
                        self.assertEqual(len(expected), 4)
                        self.assertGreater(expected.DISTANCE.sum(), 0)
                        self.assertAlmostEqual(actual.DISTANCE.sum(), expected.DISTANCE.sum())
                    self.assertFalse(expected.empty)
                    pd.testing.assert_frame_equal(
                        actual.sort_values(columns, ignore_index=True),
                        expected.sort_values(columns, ignore_index=True),
                    )
