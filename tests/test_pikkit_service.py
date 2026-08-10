import sqlite3

import services.pikkit_service as pikkit


def test_pikkit_calendar_uses_recorded_units(tmp_path):
    db = tmp_path / "picks.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE picks (id INTEGER PRIMARY KEY, date TEXT,
      matchup TEXT, pick_type TEXT, pick TEXT, status TEXT, odds REAL,
      opening_odds REAL, model_prob REAL, ev REAL, clv REAL,
      kelly_units REAL, model_version TEXT, scheduled_start TEXT, created_at TEXT)""")
    rows = [
        ("2026-08-04", "A @ B", "moneyline", "B", "won", 2.0, 2.0, 0.60, 10, 1.2, 0.5, "v3"),
        ("2026-08-04", "C @ D", "totals", "UNDER 8.5", "lost", 1.9, 1.9, 0.58, 8, None, 0.25, "v3"),
    ]
    conn.executemany(
"""INSERT INTO picks(date,matchup,pick_type,pick,status,odds,
      opening_odds,model_prob,ev,clv,kelly_units,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    conn.close()
    original = pikkit.DB_PATH
    try:
        pikkit.DB_PATH = str(db)
        data = pikkit.get_pikkit_calendar("2026-08", unit_size=40)
    finally:
        pikkit.DB_PATH = original
    assert data["summary"]["wins"] == 1
    assert data["summary"]["losses"] == 1
    assert data["summary"]["net_units"] == 0.25
    assert data["summary"]["net_dollars"] == 10
    assert data["days"][0]["net_units"] == 0.25
    assert data["days"][0]["picks"][0]["profit_dollars"] == 20


def test_pikkit_rejects_invalid_month():
    try:
        pikkit.get_pikkit_calendar("2026-8")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid month accepted")
