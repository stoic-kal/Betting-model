import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import services.model_learning_service as learning


class LossReviewLearningTests(unittest.TestCase):
    def test_totals_learning_excludes_pre_fix_input_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "picks.db")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("""CREATE TABLE picks (
                id INTEGER PRIMARY KEY, date TEXT, created_at TEXT, scheduled_start TEXT,
                matchup TEXT, pick_type TEXT, pick TEXT, odds REAL, model_prob REAL,
                status TEXT, model_version TEXT, forecast_stage TEXT, feature_snapshot TEXT)""")
            for pick_id, snapshot in (
                (1, {"market_line": 8.5}),
                (2, {"market_line": 8.5, "totals_input_version": 2}),
            ):
                conn.execute(
                    "INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pick_id, "2026-08-01", "2026-08-01", None, "A @ H", "totals",
                     "OVER 8.5", 1.91, .56, "lost", "v3", "lineup_lock", json.dumps(snapshot)),
                )
            conn.commit()
            rows = learning._eligible_rows(conn, "totals")
            conn.close()

        self.assertEqual([row["id"] for row in rows], [2])

    def test_reviewed_losses_are_idempotent_and_consumed_without_reason_code_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "picks.db")
            conn = sqlite3.connect(db_path)
            conn.execute("""CREATE TABLE picks (
                id INTEGER PRIMARY KEY, date TEXT, created_at TEXT, scheduled_start TEXT,
                matchup TEXT, pick_type TEXT, pick TEXT, odds REAL, model_prob REAL,
                status TEXT, model_version TEXT, forecast_stage TEXT, feature_snapshot TEXT)""")
            for pick_id in range(1, 51):
                won = pick_id % 2 == 0
                snapshot = json.dumps({"market_home": .52})
                conn.execute(
                    "INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pick_id, f"2026-06-{(pick_id-1)%28+1:02d}", "2026-01-01", None,
                     "A @ H", "moneyline", "H", 1.91, .54 + (pick_id % 3) * .01,
                     "won" if won else "lost", "v3", "lineup_lock", snapshot),
                )
            conn.commit(); conn.close()

            with patch.object(learning, "DB_PATH", db_path):
                for pick_id in range(1, 51, 2):
                    first = learning.record_loss_review_lesson(
                        pick_id, "moneyline", ["market_disagreement", "one_run_loss"]
                    )
                    second = learning.record_loss_review_lesson(
                        pick_id, "moneyline", ["market_disagreement", "one_run_loss"]
                    )
                    self.assertTrue(first["eligible_for_learning"])
                    self.assertTrue(second["eligible_for_learning"])

                result = learning.run_learning_cycle()["results"][0]
                self.assertIn(result["status"], ("shadow", "qualified", "promoted"))
                status = learning.get_learning_status()
                review = status["loss_reviews"]["moneyline"]
                self.assertEqual(review["reviewed_losses"], 25)
                self.assertEqual(review["used_for_training"] + review["used_for_holdout"], 25)
                self.assertEqual(
                    status["policy"]["inputs"],
                    ["locked model probability", "locked market probability"],
                )
                self.assertIn("postgame diagnostics", status["policy"]["excluded"])


if __name__ == "__main__":
    unittest.main()
