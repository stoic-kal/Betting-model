import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import services.market_snapshot_service as market_snapshots
import services.model_learning_service as model_learning
import services.totals_model_v3 as totals_model
from services.ml_model_v3 import compute_ml_prob
from services.opposite_model_service import _complement_odds, _opposite_pick
from services.record_tracker_service import _feature_context
from services.totals_model_v3 import _baseball_innings, _fetch_expected_starter_usage
from src.update_results import ResultsUpdater

NEUTRAL_CONTEXT = {
"context_complete": False,
"lineup_ops_adv": 0,
"rest_adv": 0,
"bullpen_fatigue_adv": 0,
"defense_adv": 0,
"home_lineup_confirmed": False,
"away_lineup_confirmed": False,
"home_lineup_count": 0,
"away_lineup_count": 0,
"home_lineup_ops": 0.720,
"away_lineup_ops": 0.720,
"home_left_bats": 0,
"away_left_bats": 0,
"home_rest_days": 1,
"away_rest_days": 1,
"home_games_last_3": 0,
"away_games_last_3": 0,
"home_bullpen_fatigue": 0,
"away_bullpen_fatigue": 0,
"home_fielding_pct": 0.985,
"away_fielding_pct": 0.985,
"travel_timezone_adv": 0,
}


class RegressionTests(unittest.TestCase):
    def test_dashboard_analytics_has_complete_summary_shape(self):
        from research.analytics.pick_analyzer import get_full_analytics

        payload = get_full_analytics()
        self.assertIn("summary", payload)
        self.assertIn("total_picks", payload["summary"])
        self.assertIn("moneyline", payload["by_type"])
        self.assertIn("totals", payload["by_type"])

    def test_baseball_innings_notation_is_converted_to_outs(self):
        self.assertAlmostEqual(_baseball_innings("5.1"), 5 + 1 / 3)
        self.assertAlmostEqual(_baseball_innings("5.2"), 5 + 2 / 3)
        self.assertEqual(_baseball_innings("6.0"), 6.0)

    def test_expected_starter_usage_sorts_and_weights_latest_starts(self):
        splits = [
            {
"date": "2026-08-05",
"stat": {"gamesStarted": 1, "inningsPitched": "4.0", "numberOfPitches": 70},
            },
            {
"date": "2026-07-20",
"stat": {"gamesStarted": 1, "inningsPitched": "7.0", "numberOfPitches": 100},
            },
            {
"date": "2026-08-01",
"stat": {"gamesStarted": 1, "inningsPitched": "5.2", "numberOfPitches": 88},
            },
            {
"date": "2026-07-25",
"stat": {"gamesStarted": 1, "inningsPitched": "6.0", "numberOfPitches": 94},
            },
            {
"date": "2026-07-15",
"stat": {"gamesStarted": 1, "inningsPitched": "8.0", "numberOfPitches": 105},
            },
            {
"date": "2026-07-30",
"stat": {"gamesStarted": 1, "inningsPitched": "5.0", "numberOfPitches": 82},
            },
        ]
        response = type("Response", (), {"json": lambda self: {"stats": [{"splits": splits}]}})()
        old_cache = totals_model._rsg_cache
        totals_model._rsg_cache = {}
        try:
            with patch("services.totals_model_v3.requests.get", return_value=response), patch(
"services.totals_model_v3._maybe_clear_cache"
            ):
                usage = _fetch_expected_starter_usage(123)
            self.assertTrue(usage["available"])
            self.assertEqual(usage["starts_used"], 5)
            self.assertAlmostEqual(usage["expected_innings"], 5.11, places=2)
            self.assertEqual(usage["expected_bullpen_innings"], 3.89)
        finally:
            totals_model._rsg_cache = old_cache

    def test_record_tracker_reads_both_lineup_snapshot_shapes(self):
        _, moneyline = _feature_context(
            {"features": {"home_lineup_confirmed": True, "away_lineup_confirmed": True}}
        )
        _, totals = _feature_context(
            {"context": {"home_lineup_confirmed": True, "away_lineup_confirmed": True}}
        )
        self.assertTrue(moneyline["home_lineup_confirmed"])
        self.assertTrue(totals["away_lineup_confirmed"])

    def _learning_db(self, path):
        conn = sqlite3.connect(path)
        conn.execute("""CREATE TABLE picks (
            id INTEGER PRIMARY KEY, game_id TEXT, date TEXT, matchup TEXT,
            pick_type TEXT, pick TEXT, odds REAL, model_prob REAL, status TEXT,
            feature_snapshot TEXT, forecast_stage TEXT, scheduled_start TEXT,
            created_at TEXT, model_version TEXT)""")
        conn.commit()
        conn.close()

    def test_learning_ignores_non_official_history_and_is_noop_while_collecting(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            previous = model_learning.DB_PATH
            model_learning.DB_PATH = handle.name
            model_learning._active_cache = {"loaded_at": 0.0, "models": {}}
            try:
                self._learning_db(handle.name)
                conn = sqlite3.connect(handle.name)
                conn.execute(
"""INSERT INTO picks VALUES
                    (1,'g1','2026-08-01','Away @ Home','moneyline','Home',1.9,.62,
'won',?,'final_lock','2026-08-01T20:00:00Z','x','v3')""",
                    ('{"market_home":0.55}',),
                )
                conn.commit()
                conn.close()
                result = model_learning.run_learning_cycle()["results"][0]
                self.assertEqual(result["eligible_examples"], 0)
                self.assertEqual(result["status"], "collecting")
                self.assertEqual(
                    model_learning.apply_active_calibration("moneyline", 0.61, 0.56), 0.61
                )
            finally:
                model_learning.DB_PATH = previous
                model_learning._active_cache = {"loaded_at": 0.0, "models": {}}

    def test_learning_requires_repeated_qualified_runs_before_promotion(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            previous = model_learning.DB_PATH
            model_learning.DB_PATH = handle.name
            model_learning._active_cache = {"loaded_at": 0.0, "models": {}}
            try:
                self._learning_db(handle.name)
                conn = sqlite3.connect(handle.name)
                for i in range(300):
                    status = "won" if i % 5 < 3 else "lost"
                    conn.execute(
"INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            i,
                            f"g{i}",
                            f"2026-07-{i % 28 + 1:02d}",
"Away @ Home",
"moneyline",
"Home",
                            1.92,
                            0.80,
                            status,
'{"market_home":0.52}',
"lineup_lock",
                            f"{i:04d}",
"x",
"v3",
                        ),
                    )
                conn.commit()
                conn.close()
                statuses = [model_learning.run_learning_cycle()["results"][0]["status"]]
                for batch in range(2):
                    conn = sqlite3.connect(handle.name)
                    for j in range(10):
                        i = 300 + batch * 10 + j
                        status = "won" if i % 5 < 3 else "lost"
                        conn.execute(
"INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                i,
                                f"g{i}",
                                f"2026-08-{i % 28 + 1:02d}",
"Away @ Home",
"moneyline",
"Home",
                                1.92,
                                0.80,
                                status,
'{"market_home":0.52}',
"lineup_lock",
                                f"{i:04d}",
"x",
"v3",
                            ),
                        )
                    conn.commit()
                    conn.close()
                    statuses.append(model_learning.run_learning_cycle()["results"][0]["status"])
                self.assertEqual(statuses, ["qualified", "qualified", "promoted"])
                calibrated = model_learning.apply_active_calibration("moneyline", 0.80, 0.52)
                self.assertLess(calibrated, 0.70)
                conn = sqlite3.connect(handle.name)
                for i in range(320, 360):
                    conn.execute(
"INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            i,
                            f"g{i}",
                            f"2026-09-{i % 28 + 1:02d}",
"Away @ Home",
"moneyline",
"Home",
                            1.92,
                            0.90,
"lost",
'{"market_home":0.52}',
"lineup_lock",
                            f"{i:04d}",
"x",
"v3",
                        ),
                    )
                conn.commit()
                conn.close()
                reviewed = model_learning.run_learning_cycle()["results"][0]
                self.assertEqual(reviewed["rollback"]["status"], "rolled_back")
                self.assertEqual(
                    model_learning.apply_active_calibration("moneyline", 0.61, 0.56), 0.61
                )
            finally:
                model_learning.DB_PATH = previous
                model_learning._active_cache = {"loaded_at": 0.0, "models": {}}

    def test_opposite_pick_is_derived_without_mutating_source(self):
        total = {"pick_type": "totals", "pick": "OVER 9.0", "matchup": "Away @ Home"}
        ml = {"pick_type": "moneyline", "pick": "Home", "matchup": "Away @ Home"}
        self.assertEqual(_opposite_pick(total), "UNDER 9.0")
        self.assertEqual(_opposite_pick(ml), "Away")
        self.assertAlmostEqual(_complement_odds(2.0), 2.0)

    def _market_only_probability(self, market_home):
        patches = [
            patch("services.ml_model_v3._fetch_pitcher_fip", return_value=3.90),
            patch("services.ml_model_v3._fetch_team_venue_rsg", return_value=4.60),
            patch("services.ml_model_v3._fetch_team_l10_wl", return_value=0.500),
            patch("services.ml_model_v3._fetch_team_bullpen_era", return_value=4.20),
            patch("services.ml_model_v3._fetch_team_season_wpct", return_value=0.500),
            patch("services.game_context_service.get_game_context", return_value=NEUTRAL_CONTEXT),
        ]
        with ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            return compute_ml_prob("AWY", "HME", 1, 2, market_home, 1 - market_home)["model_home"]

    def test_moneyline_calibration_is_symmetric(self):
        high_home = self._market_only_probability(0.80)
        high_away = self._market_only_probability(0.20)
        self.assertAlmostEqual(high_home, 1 - high_away, places=4)
        self.assertLessEqual(high_home, 0.645)

    def test_integer_total_equal_to_line_is_push(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute("""CREATE TABLE picks (
                id INTEGER PRIMARY KEY, date TEXT, matchup TEXT, pick TEXT,
                pick_type TEXT, status TEXT, updated_at TEXT
            )""")
            conn.execute("""INSERT INTO picks VALUES
                (1,'2026-08-03','Washington Nationals @ Philadelphia Phillies',
'OVER 8.0','totals','pending',NULL)""")
            conn.commit()
            conn.close()

            updater = ResultsUpdater(handle.name)
            updater.get_final_scores = lambda _: {
"nationals @ phillies": {
"home_runs": 5,
"away_runs": 3,
"total_runs": 8,
"home_won": True,
"home_team": "phillies",
"away_team": "nationals",
                }
            }
            self.assertEqual(updater.update_all_results("2026-08-03"), 1)
            conn = sqlite3.connect(handle.name)
            status = conn.execute("SELECT status FROM picks WHERE id=1").fetchone()[0]
            conn.close()
            self.assertEqual(status, "push")

    def test_full_moneyline_team_name_matches_normalized_result(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            conn = sqlite3.connect(handle.name)
            conn.execute("""CREATE TABLE picks (
                id INTEGER PRIMARY KEY, date TEXT, matchup TEXT, pick TEXT,
                pick_type TEXT, status TEXT, updated_at TEXT
            )""")
            conn.execute("""INSERT INTO picks VALUES
                (1,'2026-08-03','St. Louis Cardinals @ New York Yankees',
'New York Yankees','moneyline','pending',NULL)""")
            conn.commit()
            conn.close()
            updater = ResultsUpdater(handle.name)
            updater.get_final_scores = lambda _: {
"cardinals @ yankees": {
"home_runs": 7,
"away_runs": 13,
"total_runs": 20,
"home_won": False,
"home_team": "yankees",
"away_team": "cardinals",
                }
            }
            self.assertEqual(updater.update_all_results("2026-08-03"), 1)
            conn = sqlite3.connect(handle.name)
            status = conn.execute("SELECT status FROM picks WHERE id=1").fetchone()[0]
            conn.close()
            self.assertEqual(status, "lost")

    def test_market_snapshot_preserves_bookmaker_identity(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            previous = market_snapshots.DB_PATH
            market_snapshots.DB_PATH = handle.name
            try:
                games = [
                    {
"event_id": "evt1",
"home_team": "Home",
"away_team": "Away",
"books": [
                            {
"key": "pinnacle",
"market": "h2h",
"outcomes": [
                                    {"name": "Home", "price": 1.8},
                                    {"name": "Away", "price": 2.1},
                                ],
                            }
                        ],
                    }
                ]
                self.assertEqual(market_snapshots.record_market_snapshot(games, "opening"), 2)
                movement = market_snapshots.movement_for_matchup("Away", "Home")
                self.assertTrue(movement["sharp_book_available"])
                self.assertEqual(movement["sharp_book"], "Pinnacle")
            finally:
                market_snapshots.DB_PATH = previous

    def test_market_snapshot_reads_provider_book_field(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            previous = market_snapshots.DB_PATH
            market_snapshots.DB_PATH = handle.name
            try:
                games = [
                    {
"event_id": "e2",
"away_team": "Away",
"home_team": "Home",
"books": [
                            {
"book": "fanduel",
"market": "h2h",
"outcomes": [{"name": "Home", "price": 1.8}],
                            }
                        ],
                    }
                ]
                self.assertEqual(market_snapshots.record_market_snapshot(games, "opening"), 1)
                db = sqlite3.connect(handle.name)
                self.assertEqual(
                    db.execute("select bookmaker from market_snapshots").fetchone()[0], "fanduel"
                )
                db.close()
            finally:
                market_snapshots.DB_PATH = previous

    def test_market_snapshot_excludes_live_events(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            previous = market_snapshots.DB_PATH
            market_snapshots.DB_PATH = handle.name
            try:
                started = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                games = [
                    {
"event_id": "live1",
"away_team": "Away",
"home_team": "Home",
"commence_time": started,
"books": [
                            {
"book": "test",
"market": "h2h",
"outcomes": [{"name": "Home", "price": 1.2}],
                            }
                        ],
                    }
                ]
                self.assertEqual(market_snapshots.record_market_snapshot(games, "lineup_lock"), 0)
            finally:
                market_snapshots.DB_PATH = previous


class PitcherPropsRegressionTests(unittest.TestCase):

    def test_ip_to_outs_standard_notation(self):

        from services.pitcher_workload_service import ip_to_outs

        self.assertEqual(ip_to_outs(5.1), 16)
        self.assertEqual(ip_to_outs(5.2), 17)
        self.assertEqual(ip_to_outs(6.0), 18)

    def test_ip_to_outs_full_innings(self):
        from services.pitcher_workload_service import ip_to_outs

        self.assertEqual(ip_to_outs(0.0), 0)
        self.assertEqual(ip_to_outs(1.0), 3)
        self.assertEqual(ip_to_outs(7.0), 21)
        self.assertEqual(ip_to_outs(9.0), 27)

    def test_ip_to_outs_clamps_extra_outs_at_2(self):

        from services.pitcher_workload_service import ip_to_outs

        self.assertLessEqual(ip_to_outs(5.3), 17)

    def test_outs_to_ip_roundtrip(self):
        from services.pitcher_workload_service import ip_to_outs, outs_to_ip

        for outs in [0, 1, 2, 3, 10, 15, 16, 17, 18, 21, 27]:
            ip = outs_to_ip(outs)
            self.assertEqual(ip_to_outs(ip), outs, f"Roundtrip failed for {outs} outs → {ip} IP")

    def test_outs_distribution_sums_to_one(self):
        from services.pitcher_workload_service import _outs_distribution

        dist = _outs_distribution(expected_outs=15.0, std_outs=3.0)
        total = sum(dist.values())
        self.assertAlmostEqual(total, 1.0, places=4, msg="Distribution must sum to 1.0")

    def test_outs_distribution_no_negative_probs(self):
        from services.pitcher_workload_service import _outs_distribution

        dist = _outs_distribution(expected_outs=12.0, std_outs=4.0)
        for outs, p in dist.items():
            self.assertGreaterEqual(p, 0, f"Negative probability at {outs} outs")

    def test_outs_distribution_max_27(self):
        from services.pitcher_workload_service import _outs_distribution

        dist = _outs_distribution(expected_outs=25.0, std_outs=2.0)
        self.assertNotIn(28, dist)
        self.assertNotIn(30, dist)

    def test_push_on_integer_line(self):
        from services.pitcher_prop_grader_service import determine_result_status

        status, reason = determine_result_status(
            result_value=15,
            line=15.0,
            direction="Over",
            pitcher_started=True,
            pitcher_found=True,
        )
        self.assertEqual(status, "push")
        self.assertIsNone(reason)

    def test_no_push_on_half_line(self):
        from services.pitcher_prop_grader_service import determine_result_status

        status, _ = determine_result_status(
            result_value=15,
            line=15.5,
            direction="Over",
            pitcher_started=True,
            pitcher_found=True,
        )
        self.assertEqual(status, "lost")

        status, _ = determine_result_status(
            result_value=15,
            line=15.5,
            direction="Under",
            pitcher_started=True,
            pitcher_found=True,
        )
        self.assertEqual(status, "won")

    def test_over_win_and_loss(self):
        from services.pitcher_prop_grader_service import determine_result_status

        won, _ = determine_result_status(16, 15.5, "Over", True, True)
        lost, _ = determine_result_status(15, 15.5, "Over", True, True)
        self.assertEqual(won, "won")
        self.assertEqual(lost, "lost")

    def test_under_win_and_loss(self):
        from services.pitcher_prop_grader_service import determine_result_status

        won, _ = determine_result_status(15, 15.5, "Under", True, True)
        lost, _ = determine_result_status(16, 15.5, "Under", True, True)
        self.assertEqual(won, "won")
        self.assertEqual(lost, "lost")

    def test_pitcher_dnp_is_void(self):
        from services.pitcher_prop_grader_service import determine_result_status

        status, reason = determine_result_status(
            result_value=0,
            line=15.5,
            direction="Over",
            pitcher_started=False,
            pitcher_found=False,
        )
        self.assertEqual(status, "void")
        self.assertIsNotNone(reason)

    def test_pitcher_not_starter_is_void(self):
        from services.pitcher_prop_grader_service import determine_result_status

        status, reason = determine_result_status(
            result_value=6,
            line=5.5,
            direction="Over",
            pitcher_started=False,
            pitcher_found=True,
        )
        self.assertEqual(status, "void")

    def test_strikeouts_classification_is_always_research(self):
        from services.pitcher_strikeouts_service import CLASSIFICATION

        self.assertEqual(CLASSIFICATION, "Research Only")

    def test_hits_classification_is_always_research(self):
        from services.pitcher_hits_service import CLASSIFICATION

        self.assertEqual(CLASSIFICATION, "Research Only")

    def test_walks_classification_is_always_research(self):
        from services.pitcher_walks_service import CLASSIFICATION

        self.assertEqual(CLASSIFICATION, "Research Only")

    def test_research_props_blocked_from_learning_promotion(self):
        from services.pitcher_prop_learning_service import RESEARCH_ONLY_PROPS

        for prop in ("strikeouts", "hits_allowed", "walks_allowed"):
            self.assertIn(prop, RESEARCH_ONLY_PROPS)

    def test_official_lock_cannot_be_overwritten(self):
        from services.pitcher_prop_db import migrate, save_official_lock

        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            migrate(handle.name)
            lock = {
"lock_date": "2026-08-05",
"game_id": "game_test_001",
"game_pk": 123,
"player_id": 999,
"player_name": "Test Pitcher",
"team": "TST",
"opponent": "OPP",
"prop_type": "outs_recorded",
"line": 15.5,
"pick_direction": "Over",
"model_prob": 0.55,
"market_prob": 0.50,
"edge_pp": 5.0,
"ev_pct": 3.5,
"odds_dec": 1.90,
"sportsbook": "test",
"fair_odds_dec": 1.82,
"expected_value_stat": 16.2,
"distribution_json": "{}",
"data_quality_score": 0.70,
"data_quality_label": "Good",
"classification": "Qualified Pick",
"forecast_stage": "lineup_lock",
"model_version": "outs_v1.0",
"feature_snapshot": "{}",
"scheduled_start": "2026-08-05T18:10:00Z",
"created_at": "2026-08-05T17:00:00Z",
            }
            first_id = save_official_lock(lock, path=handle.name)
            second_id = save_official_lock(lock, path=handle.name)
            self.assertIsNotNone(first_id, "First lock should succeed")
            self.assertIsNone(second_id, "Second lock must be rejected — uniqueness constraint")

    def test_no_ev_without_market_price(self):
        from services.pitcher_outs_service import classify

        cls = classify(
            model_prob=0.65,
            market_prob=None,
            edge_pp=None,
            ev_pct=None,
            dq_score=0.80,
            lineup_confirmed=True,
            has_market=False,
        )
        self.assertNotIn(
            cls,
            ("Qualified Pick", "Strong Lock"),
"Must not generate Qualified/Strong without market price",
        )

    def test_over_under_probs_sum_near_one(self):
        from services.pitcher_workload_service import _outs_distribution, _over_under_push

        dist = _outs_distribution(expected_outs=15.0, std_outs=3.0)

        result = _over_under_push(dist, 15.5)
        self.assertAlmostEqual(result["over"] + result["under"], 1.0, places=3)

    def test_integer_line_probs_sum_to_one_including_push(self):
        from services.pitcher_workload_service import _outs_distribution, _over_under_push

        dist = _outs_distribution(expected_outs=15.0, std_outs=3.0)
        result = _over_under_push(dist, 15.0)
        total = result["over"] + result["under"] + result["push"]
        self.assertAlmostEqual(total, 1.0, places=3)

    def test_migrations_idempotent(self):
        from services.pitcher_prop_db import migrate

        with tempfile.NamedTemporaryFile(suffix=".db") as handle:

            migrate(handle.name)
            migrate(handle.name)

    def test_grade_lock_is_idempotent(self):
        from services.pitcher_prop_db import grade_lock, migrate, save_official_lock

        with tempfile.NamedTemporaryFile(suffix=".db") as handle:
            migrate(handle.name)
            lock = {
"lock_date": "2026-08-05",
"game_id": "grade_test_001",
"game_pk": 456,
"player_id": 998,
"player_name": "Grade Pitcher",
"team": "GRD",
"opponent": "OPP",
"prop_type": "outs_recorded",
"line": 14.5,
"pick_direction": "Under",
"model_prob": 0.57,
"market_prob": 0.51,
"edge_pp": 6.0,
"ev_pct": 4.2,
"odds_dec": 1.92,
"sportsbook": "test",
"fair_odds_dec": 1.75,
"expected_value_stat": 13.8,
"distribution_json": "{}",
"data_quality_score": 0.72,
"data_quality_label": "Good",
"classification": "Qualified Pick",
"forecast_stage": "lineup_lock",
"model_version": "outs_v1.0",
"feature_snapshot": "{}",
"scheduled_start": "2026-08-05T18:10:00Z",
"created_at": "2026-08-05T17:00:00Z",
            }
            lock_id = save_official_lock(lock, path=handle.name)
            self.assertIsNotNone(lock_id)
            first = grade_lock(lock_id, 13, "won", path=handle.name)
            second = grade_lock(lock_id, 99, "lost", path=handle.name)
            self.assertTrue(first, "First grading should succeed")
            self.assertFalse(second, "Second grading must be rejected — already graded")


if __name__ == "__main__":
    unittest.main()
