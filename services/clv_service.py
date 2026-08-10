import sqlite3
from datetime import datetime

import numpy as np

from config import ODDS_API_KEY, today_et

API_KEY = ODDS_API_KEY
DB_PATH = "database/picks.db"


def _fetch_current_market_odds() -> dict:

    try:
        from services.odds_feed_service import fetch_odds_games

        games = fetch_odds_games("closing", max_age_seconds=120)
    except Exception as e:
        print(f"  CLV fetch error: {e}")
        return {}

    result = {}
    for g in games:
        event_id = g.get("event_id", "")
        home_full = g.get("home_team", "")
        away_full = g.get("away_team", "")
        home_ml_list, away_ml_list, totals_by_line = [], [], {}

        for book in g.get("books", []):
            mkt = book.get("market")
            if mkt == "h2h":
                for o in book.get("outcomes", []):
                    p = o.get("price")
                    if p:
                        if o.get("name") == home_full:
                            home_ml_list.append(float(p))
                        else:
                            away_ml_list.append(float(p))
            elif mkt == "totals":
                for o in book.get("outcomes", []):
                    pt, p, n = o.get("point"), o.get("price"), o.get("name")
                    if pt and p and n:
                        ln = float(pt)
                        totals_by_line.setdefault(ln, {"over": [], "under": []})
                        if n == "Over":
                            totals_by_line[ln]["over"].append(float(p))
                        else:
                            totals_by_line[ln]["under"].append(float(p))

        entry = {"home_full": home_full, "away_full": away_full}
        if home_ml_list:
            entry["home_ml"] = float(np.mean(home_ml_list))
        if away_ml_list:
            entry["away_ml"] = float(np.mean(away_ml_list))
        for line, odds in totals_by_line.items():
            if odds["over"]:
                entry[f"over_{line}"] = float(np.mean(odds["over"]))
            if odds["under"]:
                entry[f"under_{line}"] = float(np.mean(odds["under"]))

        result[event_id] = entry

    return result


def _compute_clv(opening_decimal: float, closing_decimal: float) -> float:

    if not opening_decimal or not closing_decimal:
        return None
    opening_implied = 1.0 / opening_decimal
    closing_implied = 1.0 / closing_decimal
    return round((closing_implied - opening_implied) * 100, 3)


def _get_closing_odds_for_pick(pick: dict, market_map: dict, opposite=False) -> float:

    pick_type = pick["pick_type"]
    pick_str = pick["pick"]
    event_id = _event_id_from_game_id(pick["game_id"])

    if event_id not in market_map:
        return None

    entry = market_map[event_id]

    if pick_type == "moneyline":
        home_full = entry.get("home_full", "")
        away_full = entry.get("away_full", "")

        picked_home = pick_str.lower() in home_full.lower() or home_full.lower() in pick_str.lower()
        if opposite:
            return entry.get("away_ml" if picked_home else "home_ml")
        return entry.get("home_ml" if picked_home else "away_ml")

    elif pick_type == "totals":

        parts = pick_str.split()
        if len(parts) == 2:
            direction = parts[0].upper()
            line = float(parts[1])
            if opposite:
                direction = "UNDER" if direction == "OVER" else "OVER"
            key = f'{"over" if direction == "OVER" else "under"}_{line}'
            return entry.get(key)

    return None


def capture_clv(date_str: str = None, matchups=None) -> dict:

    if date_str is None:
        date_str = today_et()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = """
        SELECT id, game_id, pick_type, pick, opening_odds, odds
        FROM picks
        WHERE date = ? AND closing_odds IS NULL
    """
    params = [date_str]
    if matchups:
        sql += f" AND matchup IN ({','.join('?' for _ in matchups)})"
        params.extend(matchups)
    picks = conn.execute(sql, params).fetchall()
    picks = [dict(p) for p in picks]

    if not picks:
        conn.close()
        return {"status": "ok", "message": "No picks to capture CLV for today", "captured": 0}

    print(f"  Capturing CLV for {len(picks)} picks on {date_str}...")
    market_map = _fetch_current_market_odds()

    if not market_map:
        conn.close()
        return {"status": "error", "message": "Could not fetch market odds"}

    captured = 0
    now_str = datetime.now().isoformat()

    for pick in picks:

        opening = pick["opening_odds"] or pick["odds"]
        closing = _get_closing_odds_for_pick(pick, market_map)
        opposite_closing = _get_closing_odds_for_pick(pick, market_map, opposite=True)

        if closing is None:
            print(f'     No closing line found for pick id={pick["id"]} ({pick["game_id"]})')
            continue

        clv = _compute_clv(opening, closing)

        opposite_opening = conn.execute(
            "SELECT opposite_opening_odds FROM picks WHERE id=?", (pick["id"],)
        ).fetchone()[0]
        opposite_clv = (
            _compute_clv(opposite_opening, opposite_closing)
            if opposite_opening and opposite_closing
            else None
        )
        conn.execute(
            """
            UPDATE picks
            SET closing_odds = ?, clv = ?, clv_captured_at = ?,
                opposite_closing_odds = ?, opposite_clv = ?
            WHERE id = ?
        """,
            (closing, clv, now_str, opposite_closing, opposite_clv, pick["id"]),
        )

        direction = "" if (clv or 0) > 0 else ""
        print(
            f'    {direction} {pick["game_id"]}: open={opening:.3f} → close={closing:.3f} | CLV={clv:+.2f}pp'
        )
        captured += 1

    conn.commit()
    conn.close()

    conn2 = sqlite3.connect(DB_PATH)
    summary = conn2.execute(
        """
        SELECT COUNT(*) n, AVG(clv) avg_clv,
               SUM(CASE WHEN clv > 0 THEN 1 ELSE 0 END) beat_close
        FROM picks WHERE date = ? AND clv IS NOT NULL
    """,
        (date_str,),
    ).fetchone()
    conn2.close()

    return {
        "status": "success",
        "date": date_str,
        "captured": captured,
        "total_with_clv": summary[0] if summary else 0,
        "avg_clv": round(summary[1], 3) if summary and summary[1] else 0,
        "beat_close_pct": round(summary[2] / summary[0] * 100, 1) if summary and summary[0] else 0,
    }


def _event_id_from_game_id(game_id: str) -> str:
    if "_TOTALS" in game_id:
        return game_id.replace("_TOTALS", "")
    if "_ML" in game_id:
        return game_id.rsplit("_ML", 1)[0]
    return game_id


def _build_entry_from_snapshots(conn, event_id: str, matchup: str):

    away, home = (matchup.split(" @ ", 1) + [""])[:2] if matchup else ("", "")

    rows = conn.execute(
        """SELECT bookmaker, market, outcome, price, point, captured_at
        FROM market_snapshots WHERE event_id = ? ORDER BY captured_at""",
        (event_id,),
    ).fetchall()
    if not rows and matchup:
        rows = conn.execute(
            """SELECT bookmaker, market, outcome, price, point, captured_at
            FROM market_snapshots WHERE lower(home_team)=lower(?) AND lower(away_team)=lower(?)
            ORDER BY captured_at""",
            (home, away),
        ).fetchall()
    if not rows:
        return None

    last = {}
    for r in rows:
        key = (r["bookmaker"], r["market"], r["outcome"], r["point"])
        last[key] = r

    home_ml_list, away_ml_list, totals_by_line = [], [], {}
    for (_bookmaker, market, outcome, point), r in last.items():
        if market == "h2h":
            if home and outcome.lower() == home.lower():
                home_ml_list.append(r["price"])
            elif away and outcome.lower() == away.lower():
                away_ml_list.append(r["price"])
        elif market == "totals" and point is not None:
            line = float(point)
            totals_by_line.setdefault(line, {"over": [], "under": []})
            if outcome == "Over":
                totals_by_line[line]["over"].append(r["price"])
            elif outcome == "Under":
                totals_by_line[line]["under"].append(r["price"])

    entry = {"home_full": home, "away_full": away}
    if home_ml_list:
        entry["home_ml"] = float(np.mean(home_ml_list))
    if away_ml_list:
        entry["away_ml"] = float(np.mean(away_ml_list))
    for line, odds in totals_by_line.items():
        if odds["over"]:
            entry[f"over_{line}"] = float(np.mean(odds["over"]))
        if odds["under"]:
            entry[f"under_{line}"] = float(np.mean(odds["under"]))

    if "home_ml" not in entry and "away_ml" not in entry and not totals_by_line:
        return None
    return entry


def backfill_missing_clv(date_str: str = None) -> dict:

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = """SELECT id, game_id, pick_type, pick, opening_odds, odds, matchup, opposite_opening_odds
              FROM picks WHERE closing_odds IS NULL AND status IN ('won','lost')"""
    params = []
    if date_str:
        sql += " AND date = ?"
        params.append(date_str)
    picks = [dict(p) for p in conn.execute(sql, params).fetchall()]

    if not picks:
        conn.close()
        return {
            "status": "ok",
            "message": "No resolved picks need CLV backfill",
            "backfilled": 0,
            "skipped": 0,
        }

    now_str = datetime.now().isoformat()
    backfilled, skipped = 0, 0
    for pick in picks:
        event_id = _event_id_from_game_id(pick["game_id"])
        entry = _build_entry_from_snapshots(conn, event_id, pick["matchup"])
        if entry is None:
            skipped += 1
            continue
        market_map = {event_id: entry}
        closing = _get_closing_odds_for_pick(pick, market_map)
        opposite_closing = _get_closing_odds_for_pick(pick, market_map, opposite=True)
        if closing is None:
            skipped += 1
            continue

        opening = pick["opening_odds"] or pick["odds"]
        clv = _compute_clv(opening, closing)
        opposite_opening = pick.get("opposite_opening_odds")
        opposite_clv = (
            _compute_clv(opposite_opening, opposite_closing)
            if opposite_opening and opposite_closing
            else None
        )

        conn.execute(
            """
            UPDATE picks
            SET closing_odds = ?, clv = ?, clv_captured_at = ?,
                opposite_closing_odds = ?, opposite_clv = ?
            WHERE id = ?
        """,
            (closing, clv, now_str, opposite_closing, opposite_clv, pick["id"]),
        )
        print(
            f'    ⏪ CLV backfill {pick["game_id"]}: open={opening:.3f} → close={closing:.3f} | CLV={clv:+.2f}pp (from stored snapshots)'
        )
        backfilled += 1

    conn.commit()
    conn.close()
    return {
        "status": "success",
        "date": date_str,
        "backfilled": backfilled,
        "skipped_no_snapshot_data": skipped,
        "total_checked": len(picks),
    }


def get_clv_summary() -> dict:

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    all_clv = conn.execute("""
        SELECT clv, pick_type, status
        FROM picks WHERE clv IS NOT NULL
    """).fetchall()
    conn.close()

    if not all_clv:
        return {
            "n": 0,
            "avg_clv": 0,
            "beat_close_pct": 0,
            "ml_avg_clv": 0,
            "tot_avg_clv": 0,
        }

    rows = [dict(r) for r in all_clv]
    avg_clv = np.mean([r["clv"] for r in rows])
    beat_close = sum(1 for r in rows if r["clv"] > 0) / len(rows) * 100

    ml_rows = [r["clv"] for r in rows if r["pick_type"] == "moneyline"]
    tot_rows = [r["clv"] for r in rows if r["pick_type"] == "totals"]

    return {
        "n": len(rows),
        "avg_clv": round(float(avg_clv), 3),
        "beat_close_pct": round(beat_close, 1),
        "ml_avg_clv": round(float(np.mean(ml_rows)), 3) if ml_rows else 0,
        "tot_avg_clv": round(float(np.mean(tot_rows)), 3) if tot_rows else 0,
    }
