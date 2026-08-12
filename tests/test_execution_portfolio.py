import sqlite3

import pandas as pd

from services.execution_service import allocate_realized_stake, sanitize_odds_quotes
from services.portfolio_risk_service import complete_history_portfolio_audit


def _execution_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE picks (
        game_id TEXT, date TEXT, matchup TEXT, pick_type TEXT, status TEXT,
        odds REAL, theoretical_kelly_units REAL, realized_stake_units REAL,
        wager_status TEXT, created_at TEXT)""")
    return conn


def test_malformed_odds_are_rejected():
    valid, rejected = sanitize_odds_quotes([1.91, "bad", 1.0, float("inf"), 2.05])
    assert valid == [1.91, 2.05]
    assert len(rejected) == 3


def test_zero_kelly_never_creates_wager_and_game_exposure_is_capped():
    conn = _execution_db()
    zero = allocate_realized_stake(
        conn, date="2026-08-11", matchup="A @ H", game_id="g0",
        theoretical_kelly=0, recommendation_tier="qualified_pick",
    )
    assert zero["realized_stake_units"] == 0
    assert zero["wager_status"] == "no_wager"

    first = allocate_realized_stake(
        conn, date="2026-08-11", matchup="A @ H", game_id="g1",
        theoretical_kelly=1, recommendation_tier="qualified_pick",
    )
    conn.execute(
        "INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("g1", "2026-08-11", "A @ H", "moneyline", "pending", 1.9, 1, first["realized_stake_units"], "wagered", "now"),
    )
    second = allocate_realized_stake(
        conn, date="2026-08-11", matchup="A @ H", game_id="g2",
        theoretical_kelly=1, recommendation_tier="qualified_pick",
    )
    assert first["realized_stake_units"] == 0.5
    assert second["realized_stake_units"] == 0.5


def test_complete_history_correlation_uses_wins_and_losses(tmp_path):
    db = tmp_path / "picks.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE picks (
        id INTEGER, game_id TEXT, date TEXT, matchup TEXT, pick_type TEXT,
        status TEXT, odds REAL, kelly_units REAL, theoretical_kelly_units REAL,
        realized_stake_units REAL, wager_status TEXT, created_at TEXT)""")
    for game in range(4):
        for pick_type in ("moneyline", "totals"):
            won = game in (0, 2) if pick_type == "moneyline" else game in (0, 3)
            conn.execute(
                "INSERT INTO picks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (game * 2 + (pick_type == "totals"), f"g{game}-{pick_type}", "2026-08-01",
                 f"A{game} @ H{game}", pick_type, "won" if won else "lost", 2.0,
                 .25, .25, None, "historical_unknown", str(game)),
            )
    conn.commit(); conn.close()
    report = complete_history_portfolio_audit(str(db))
    assert report["simultaneous_wager_correlation"]["paired_games"] == 4
    assert report["data_quality"]["realized_stake_coverage_resolved"] == 0


def test_run_distribution_report_has_interval_and_distribution_metrics():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "research" / "diagnostics" / "totals" / "run_distribution_diagnostics.py"
    spec = importlib.util.spec_from_file_location("run_distribution_test", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    frame = pd.DataFrame({
        "game_id": [str(i) for i in range(20)],
        "date": pd.date_range("2026-01-01", periods=20),
        "matchup": ["A @ H"] * 20,
        "snap_expected_total": [8.5] * 20,
        "actual_total": list(range(4, 14)) * 2,
    })
    report = module.build_run_distribution_report(frame)
    assert report["sample_size"] == 20
    assert set(report["prediction_intervals"]) == {"80", "90", "95"}
    assert report["distribution_diagnostics"]["mean_crps"] > 0
