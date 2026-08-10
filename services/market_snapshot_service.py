import sqlite3
from datetime import datetime, timezone

from config import now_et

DB_PATH = "database/picks.db"


def record_market_snapshot(games, stage="current"):

    if not games:
        return 0
    captured = now_et().isoformat(timespec="seconds")
    rows = []
    for game in games:
        event_id = game.get("event_id") or game.get("id", "")
        home = game.get("home_team", "")
        away = game.get("away_team", "")
        commence = (
            game.get("commence_time")
            or game.get("commenceTime")
            or game.get("start_time")
            or game.get("startTime")
        )

        if commence:
            try:
                start = datetime.fromisoformat(str(commence).replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if start <= datetime.now(timezone.utc):
                    continue
            except (TypeError, ValueError):

                pass
        for book in game.get("books", game.get("bookmakers", [])):

            bookmaker = (
                book.get("book")
                or book.get("key")
                or book.get("title")
                or book.get("bookmaker")
                or book.get("sportsbook")
                or "unknown"
            )

            markets = book.get("markets") or [book]
            for market in markets:
                market_key = market.get("key") or market.get("market") or "unknown"
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if price is None:
                        continue
                    rows.append(
                        (
                            captured,
                            stage,
                            event_id,
                            commence,
                            home,
                            away,
                            bookmaker,
                            market_key,
                            outcome.get("name", ""),
                            float(price),
                            outcome.get("point"),
                        )
                    )
    if not rows:
        return 0
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL,
        stage TEXT NOT NULL, event_id TEXT, commence_time TEXT,
        home_team TEXT, away_team TEXT, bookmaker TEXT, market TEXT,
        outcome TEXT, price REAL, point REAL,
        UNIQUE(captured_at,event_id,bookmaker,market,outcome,point))""")
    conn.executemany(
"""INSERT OR IGNORE INTO market_snapshots
        (captured_at,stage,event_id,commence_time,home_team,away_team,bookmaker,market,outcome,price,point)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    count = conn.total_changes
    conn.close()
    return count


def movement_for_matchup(away_team, home_team):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in conn.execute(
"""SELECT captured_at,stage,bookmaker,market,outcome,price,point
        FROM market_snapshots WHERE lower(away_team)=lower(?) AND lower(home_team)=lower(?)
        ORDER BY captured_at""",
            (away_team, home_team),
        ).fetchall()
    ]
    conn.close()
    sharp = [r for r in rows if "pinnacle" in r["bookmaker"].lower()]
    return {
"snapshots": rows,
"sharp_book_available": bool(sharp),
"sharp_book": "Pinnacle" if sharp else None,
"note": (
"Pinnacle-specific movement available."
            if sharp
            else "No Pinnacle feed available; consensus movement is reported without a sharp label."
        ),
    }
