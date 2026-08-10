import sqlite3
import requests
import json
from datetime import datetime
from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY
DB_PATH = "database/picks.db"


def detect_signal(prev, curr: dict) -> str:

    if prev is None:
        return "MARKET OPEN"

    total_prev = prev.get("total")
    total_curr = curr.get("total")
    hml_prev = prev.get("home_ml")
    hml_curr = curr.get("home_ml")

    signals = []

    if total_prev and total_curr:
        delta = total_curr - total_prev
        if delta <= -0.5:
            signals.append("SHARP TOTAL UNDER STEAM")
        elif delta >= 0.5:
            signals.append("SHARP TOTAL OVER STEAM")

    if hml_prev and hml_curr:

        delta = hml_curr - hml_prev
        if delta <= -10:
            signals.append("SHARP HOME ML ACTION")
        elif delta >= 10:
            signals.append("SHARP AWAY ML ACTION")

    if not signals:

        away_prev = prev.get("away_ml")
        away_curr = curr.get("away_ml")
        if away_prev and away_curr and (away_curr - away_prev) <= -10:
            signals.append("STEADY AWAY STEAM")
        else:
            signals.append("STEADY")

    return " / ".join(signals)


def american_odds(decimal_odds: float) -> int:

    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1)))


def setup_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS line_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id      TEXT NOT NULL,
            home_team     TEXT,
            away_team     TEXT,
            home_ml       INTEGER,   -- American odds
            away_ml       INTEGER,
            total         REAL,
            spread        TEXT,
            market_signal TEXT,
            snapshot_time TEXT NOT NULL
        )
    """)
    conn.commit()


def fetch_and_store():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    setup_db(conn)

    try:
        resp = requests.get(
            "https://api.theoddsapi.com/odds/",
            headers={"x-api-key": API_KEY},
            params={
                "sport_key": "baseball_mlb",
                "markets": "h2h,spreads,totals",
                "oddsFormat": "decimal",
            },
            timeout=15,
        )
        games = resp.json().get("data", [])
    except Exception as e:
        print(f"API error: {e}")
        conn.close()
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    stored = 0

    for game in games:
        event_id = game.get("event_id", "")
        home_team = game.get("home_team", "")
        away_team = game.get("away_team", "")

        home_ml_list, away_ml_list, totals_list = [], [], []

        for book in game.get("books", []):
            mkt = book.get("market")
            if mkt == "h2h":
                for o in book.get("outcomes", []):
                    p = o.get("price")
                    if p:
                        if o.get("name") == home_team:
                            home_ml_list.append(float(p))
                        else:
                            away_ml_list.append(float(p))
            elif mkt == "totals":
                for o in book.get("outcomes", []):
                    pt = o.get("point")
                    if pt and o.get("name") == "Over":
                        totals_list.append(float(pt))

        if not home_ml_list or not away_ml_list:
            continue

        fair_home = sum(home_ml_list) / len(home_ml_list)
        fair_away = sum(away_ml_list) / len(away_ml_list)
        fair_total = sum(totals_list) / len(totals_list) if totals_list else None

        home_ml_am = american_odds(fair_home)
        away_ml_am = american_odds(fair_away)
        spread_str = f"CWS/ARI -1.5" if away_ml_am < -130 else ""

        prev = conn.execute(
            "SELECT * FROM line_snapshots WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)
        ).fetchone()
        prev_dict = dict(prev) if prev else None

        curr_dict = {"home_ml": home_ml_am, "away_ml": away_ml_am, "total": fair_total}
        signal = detect_signal(prev_dict, curr_dict)

        conn.execute(
            """INSERT INTO line_snapshots
               (event_id, home_team, away_team, home_ml, away_ml, total, spread, market_signal, snapshot_time)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                event_id,
                home_team,
                away_team,
                home_ml_am,
                away_ml_am,
                fair_total,
                spread_str,
                signal,
                now,
            ),
        )
        stored += 1

    conn.commit()
    conn.close()
    print(f"Stored {stored} snapshots at {now}")


if __name__ == "__main__":
    fetch_and_store()
