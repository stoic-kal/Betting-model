import sqlite3

import pandas as pd


def _module():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "totals_diagnostics" / "calibration_attribution.py"
    spec = importlib.util.spec_from_file_location("calibration_attribution_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bucket_contributions_reconcile_and_require_shadow_confirmation(tmp_path):
    attribution = _module()
    rows = []
    for index in range(80):
        probability = 0.52 if index < 40 else 0.67
        won = 1 if (index < 40 and index % 2 == 0) else 0
        rows.append(
            {
                "game_id": str(index),
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=index),
                "won": won,
                "model_prob": probability,
                "odds": 1.91,
                "ev": 5.0,
                "clv": 1.0,
                "profit": 18.2 if won else -20.0,
                "wagered": 20.0,
                "direction": "OVER" if index % 2 else "UNDER",
                "snap_home_fip": 4.0 + index / 100,
            }
        )
    db_path = tmp_path / "picks.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE shadow_v2_predictions (pick_type TEXT)")
    conn.execute("CREATE TABLE picks (matchup TEXT, date TEXT, pick_type TEXT, status TEXT)")
    conn.close()

    report = attribution.build_attribution(pd.DataFrame(rows), db_path)

    assert abs(
        sum(row["ece_contribution"] for row in report["buckets_ranked_by_ece"])
        - report["weighted_ece"]
    ) < 1e-7
    assert report["buckets_responsible_for_80pct"]
    assert report["live_shadow"]["resolved_predictions"] == 0
    assert all(
        row["persistence_verdict"] != "persistent"
        for row in report["buckets_ranked_by_ece"]
    )


def test_wilson_interval_contains_observed_rate():
    attribution = _module()
    low, high = attribution.wilson_interval(5, 10)
    assert low < 0.5 < high
