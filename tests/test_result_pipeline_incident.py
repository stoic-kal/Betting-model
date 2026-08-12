import sqlite3
import tempfile
from concurrent.futures import ThreadPoolExecutor

from src.update_results import ResultsUpdater


def _database(path, status="pending"):
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE picks (
        id INTEGER PRIMARY KEY, game_id TEXT, date TEXT, matchup TEXT,
        pick_type TEXT, pick TEXT, odds REAL, status TEXT, updated_at TEXT
    )""")
    conn.execute(
        "INSERT INTO picks VALUES (1,'g1','2026-08-11','Away @ Home','totals','OVER 8.0',2.0,?,NULL)",
        (status,),
    )
    conn.commit(); conn.close()


def _game(state="Final", total=8):
    return {123: {
        "game_pk": 123, "matchup": "away @ home",
        "mlb_abstract_state": state, "mlb_detailed_state": state,
        "home_runs": 5, "away_runs": total - 5, "total_runs": total,
        "home_won": 5 > total - 5, "home_team": "home", "away_team": "away",
    }}


def test_non_final_mlb_state_cannot_grade():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        _database(handle.name)
        updater = ResultsUpdater(handle.name)
        updater.get_final_scores = lambda _: _game("Live")
        assert updater.update_all_results("2026-08-11") == 0
        conn = sqlite3.connect(handle.name)
        assert conn.execute("SELECT status,graded_at FROM picks").fetchone() == ("pending", None)
        conn.close()


def test_grade_and_outbox_are_idempotent_including_push():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        _database(handle.name)
        updater = ResultsUpdater(handle.name)
        updater.get_final_scores = lambda _: _game("Final", 8)
        assert updater.update_all_results("2026-08-11") == 1
        assert updater.update_all_results("2026-08-11") == 0
        conn = sqlite3.connect(handle.name)
        assert conn.execute("SELECT status FROM picks").fetchone()[0] == "push"
        assert conn.execute("SELECT COUNT(*) FROM notification_outbox").fetchone()[0] == 1
        conn.close()


def test_two_graders_cannot_grade_or_notify_same_pick_twice():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        _database(handle.name)
        delivered = []

        def run_one(_):
            updater = ResultsUpdater(handle.name, notifier=lambda payload, key: delivered.append(key) or True)
            updater.is_production_db = True
            updater.get_final_scores = lambda _: _game("Final", 9)
            return updater.update_all_results("2026-08-11")

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run_one, range(2)))
        assert sorted(results) == [0, 1]
        assert len(delivered) == 1
        conn = sqlite3.connect(handle.name)
        assert conn.execute("SELECT status,notification_sent FROM picks").fetchone() == ("won", 1)
        assert conn.execute("SELECT status,attempts FROM notification_outbox").fetchone() == ("sent", 1)
        conn.close()


def test_resolved_push_cannot_mutate_to_win_without_explicit_revert():
    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        _database(handle.name, status="push")
        updater = ResultsUpdater(handle.name)
        updater.get_final_scores = lambda _: _game("Final", 10)
        assert updater.update_all_results("2026-08-11") == 0
        conn = sqlite3.connect(handle.name)
        assert conn.execute("SELECT status FROM picks").fetchone()[0] == "push"
        conn.close()
