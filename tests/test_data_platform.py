import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.data_platform import american_to_decimal, connect, normalize_team
from pipeline.historical_odds_import import ingest as ingest_json
from pipeline.vegas_ingestion import ingest as ingest_vegas


class DataPlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "warehouse.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalization_and_odds_conversion(self):
        self.assertEqual(normalize_team("CHA"), "CWS")
        self.assertEqual(normalize_team("WAS"), "WSH")
        self.assertAlmostEqual(american_to_decimal(-120), 1.8333333333)
        self.assertEqual(american_to_decimal(150), 2.5)

    def test_vegas_ingestion_is_idempotent_and_preserves_doubleheaders(self):
        path = Path(self.tmp.name) / "oddsData.csv"
        pd.DataFrame([
            ["2021-05-27","V","COL",1,115,1.5,-220,5,-120,100],
            ["2021-05-27","H","NYM",1,-125,-1.5,195,5,-120,100],
            ["2021-05-27","V","COL",2,105,1.5,-210,6,-110,-110],
            ["2021-05-27","H","NYM",2,-115,-1.5,185,6,-110,-110],
        ], columns="date at team gameNumber line runLine runLineOdds total overOdds underOdds".split()).to_csv(path,index=False)
        pd.DataFrame([
            ["2021-05-27",2021,"COL","NYM",115,5,-120,100],
            ["2021-05-27",2021,"NYM","COL",-125,5,-120,100],
            ["2021-05-27",2021,"COL","NYM",105,6,-110,-110],
            ["2021-05-27",2021,"NYM","COL",-115,6,-110,-110],
        ], columns="date season team opponent moneyLine total overOdds underOdds".split()).to_csv(
            Path(self.tmp.name) / "oddsDataMLB.csv", index=False)
        first = ingest_vegas(path, self.db)
        second = ingest_vegas(path, self.db)
        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM canonical_games").fetchone()[0], 2)
        self.assertEqual([r[0] for r in conn.execute(
            "SELECT doubleheader_number FROM canonical_games ORDER BY doubleheader_number")], [1, 2])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM historical_market_snapshots").fetchone()[0], 8)
        conn.close()
        self.assertEqual(first["market_rows_inserted"], 8)
        self.assertEqual(second["market_rows_inserted"], 0)

    def test_historical_json_keeps_each_snapshot(self):
        path = Path(self.tmp.name) / "odds.json"
        path.write_text(json.dumps([{"id":"e1","commence_time":"2024-06-01T20:00:00Z","bookmakers":[
            {"key":"pinnacle","last_update":"2024-06-01T19:00:00Z","markets":[
                {"key":"totals","outcomes":[{"name":"Over","price":-110,"point":8.5},
                                                {"name":"Under","price":-110,"point":8.5}]}]}]}]))
        report = ingest_json(path, self.db)
        self.assertEqual(report["market_rows_inserted"], 2)


if __name__ == "__main__":
    unittest.main()
