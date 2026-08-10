import csv
import io
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from statistics import median

from config import today_et

DB_PATH = "database/picks.db"


def _imp(price):
    try:
        return 1 / float(price) if float(price) > 1 else None
    except (TypeError, ValueError):
        return None


def get_market_signals(date_str=None):
    date_str = date_str or today_et()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    picks = [
        dict(r)
        for r in conn.execute(
"SELECT game_id,date,matchup,pick_type,pick,model_prob,ev,forecast_stage,status,scheduled_start FROM picks WHERE model_version='v3' AND date=?",
            (date_str,),
        )
    ]
    dates = [
        r[0]
        for r in conn.execute(
"SELECT DISTINCT date FROM picks WHERE model_version='v3' ORDER BY date DESC"
        )
    ]
    all_snaps = [
        dict(r) for r in conn.execute("SELECT * FROM market_snapshots ORDER BY captured_at,id")
    ]
    conn.close()
    pick_map = {(p["matchup"], p["pick_type"]): p for p in picks}
    tracked_games = {p["matchup"] for p in picks}
    event_ids = set()
    starts = {}
    for p in picks:
        event = p["game_id"].replace("_TOTALS", "").rsplit("_ML", 1)[0]
        event_ids.add(event)
        if p.get("scheduled_start"):
            starts[event] = p["scheduled_start"]

    def pregame_snapshot(s):
        if s.get("bookmaker") in (None, "", "unknown") or s.get("event_id") not in event_ids:
            return False
        start = starts.get(s.get("event_id")) or s.get("commence_time")
        if not start:
            return False
        try:
            captured = datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00"))
            first_pitch = datetime.fromisoformat(start.replace("Z", "+00:00"))
            return captured < first_pitch
        except (TypeError, ValueError):
            return False

    snaps = [s for s in all_snaps if pregame_snapshot(s)]
    histories = defaultdict(list)
    for s in snaps:
        histories[
            (
                s["event_id"],
                s["away_team"],
                s["home_team"],
                s["bookmaker"],
                s["market"],
                s["outcome"],
                s["point"],
            )
        ].append(s)
    movements = []
    for (event_id, away, home, book, market, outcome, point), h in histories.items():
        if len(h) < 2:
            continue
        first, last = h[0], h[-1]
        a, b = _imp(first["price"]), _imp(last["price"])
        if a is None or b is None:
            continue
        move = round((b - a) * 100, 2)
        line_move = (last.get("point") or 0) - (first.get("point") or 0)
        if abs(move) < 0.01 and abs(line_move) < 0.01:
            continue
        matchup = f"{away} @ {home}"
        ptype = "moneyline" if market == "h2h" else "totals"
        pick = pick_map.get((matchup, ptype))
        agrees = None
        if pick and ptype == "totals":
            line_match = re.search(r"(\d+(?:\.\d+)?)", pick["pick"])
            pick_line = float(line_match.group(1)) if line_match else None
            if point is None or pick_line is None or abs(float(point) - pick_line) > 0.001:
                continue
        if pick:
            if ptype == "moneyline":
                agrees = (
                    outcome.lower() in pick["pick"].lower()
                    or pick["pick"].lower() in outcome.lower()
                )
            else:
                agrees = pick["pick"].upper().startswith(outcome.upper()) and (
                    point is None or str(point) in pick["pick"]
                )
        movements.append(
            {
"event_id": event_id,
"game": matchup,
"bookmaker": book,
"market": market,
"outcome": outcome,
"point": point,
"opening_price": first["price"],
"latest_price": last["price"],
"implied_move_pp": move,
"line_move": round(line_move, 2),
"first_seen": first["captured_at"],
"last_seen": last["captured_at"],
"is_pinnacle": "pinnacle" in book.lower(),
"model_pick": pick["pick"] if pick else None,
"agrees_with_pick": agrees,
"pick_stage": pick.get("forecast_stage") if pick else None,
            }
        )
    signal_groups = defaultdict(list)
    for m in movements:
        signal_groups[(m["event_id"], m["game"], m["market"], m["outcome"], m["point"])].append(m)
    signals = []
    for (event_id, game, market, outcome, point), moves in signal_groups.items():
        meaningful = [m for m in moves if abs(m["implied_move_pp"]) >= 0.5]
        positive = sum(m["implied_move_pp"] >= 0.5 for m in meaningful)
        negative = sum(m["implied_move_pp"] <= -0.5 for m in meaningful)
        direction = "toward" if positive > negative else "away" if negative > positive else "mixed"
        same = max(positive, negative)
        pinnacle = next((m for m in moves if m["is_pinnacle"]), None)
        dominant_sign = 1 if positive > negative else -1 if negative > positive else 0
        pinnacle_confirms = bool(
            pinnacle and dominant_sign and pinnacle["implied_move_pp"] * dominant_sign >= 1
        )
        if pinnacle_confirms:
            label = "Pinnacle-led pressure"
        elif same >= 3:
            label = "Cross-book steam"
        elif same >= 2:
            label = "Multi-book movement"
        else:
            label = "Isolated/noisy movement"
        avg = round(sum(m["implied_move_pp"] for m in moves) / len(moves), 2)
        signals.append(
            {
"event_id": event_id,
"game": game,
"market": market,
"outcome": outcome,
"point": point,
"signal": label,
"direction": direction,
"books_moving": same,
"books_observed": len(moves),
"average_move_pp": avg,
"pinnacle_move_pp": pinnacle["implied_move_pp"] if pinnacle else None,
"pinnacle_confirms": pinnacle_confirms,
"model_pick": moves[0]["model_pick"],
"agrees_with_pick": moves[0]["agrees_with_pick"],
"last_seen": max(m["last_seen"] for m in moves),
            }
        )
    signals.sort(key=lambda x: (x["last_seen"], abs(x["average_move_pp"])), reverse=True)
    movements.sort(key=lambda x: x["last_seen"], reverse=True)
    movement_picks = []
    for signal in signals:
        if signal["direction"] != "toward" or signal["average_move_pp"] < 0.5:
            continue
        if signal["signal"] not in ("Cross-book steam", "Pinnacle-led pressure"):
            continue
        ratio = signal["books_moving"] / max(signal["books_observed"], 1)
        if signal["books_moving"] < 3 or ratio < 0.60:
            continue
        related = [
            m
            for m in movements
            if m["event_id"] == signal["event_id"]
            and m["market"] == signal["market"]
            and m["outcome"] == signal["outcome"]
            and m["point"] == signal["point"]
        ]
        latest = round(median([m["latest_price"] for m in related]), 3) if related else None
        score = min(
            100,
            round(
                min(signal["books_moving"], 10) * 3
                + min(signal["average_move_pp"], 5) * 6
                + ratio * 20
                + (20 if signal["pinnacle_confirms"] else 0)
            ),
        )
        confidence = "STRONG" if score >= 75 else "MODERATE" if score >= 55 else "WATCH"
        pick_text = (
            signal["outcome"]
            if signal["market"] == "h2h"
            else f"{signal['outcome'].upper()} {signal['point']}"
        )
        relationship = (
"ALIGNS WITH MODEL"
            if signal["agrees_with_pick"] is True
            else (
"CONTRADICTS MODEL"
                if signal["agrees_with_pick"] is False
                else "NO MODEL COMPARISON"
            )
        )
        movement_picks.append(
            {
"game": signal["game"],
"market": signal["market"],
"movement_pick": pick_text,
"consensus_odds": latest,
"confidence": confidence,
"signal_score": score,
"books_moving": signal["books_moving"],
"books_observed": signal["books_observed"],
"average_move_pp": signal["average_move_pp"],
"pinnacle_confirms": signal["pinnacle_confirms"],
"model_pick": signal["model_pick"],
"model_relationship": relationship,
"last_seen": signal["last_seen"],
"reason": f"{signal['books_moving']} of {signal['books_observed']} books moved toward this side"
                + (" with Pinnacle confirmation." if signal["pinnacle_confirms"] else "."),
            }
        )
    movement_picks.sort(key=lambda x: (x["signal_score"], x["books_moving"]), reverse=True)
    bookmakers = sorted({s["bookmaker"] for s in snaps})
    game_books = defaultdict(set)
    for s in snaps:
        game_books[f"{s['away_team']} @ {s['home_team']}"].add(s["bookmaker"])
    coverage = [
        {"game": g, "book_count": len(bs), "bookmakers": sorted(bs)}
        for g, bs in sorted(game_books.items())
    ]
    summary = {
"snapshots": len(snaps),
"movements": len(movements),
"signals": len(signals),
"books": len(bookmakers),
"games": len(tracked_games),
"pinnacle_signals": sum(s["pinnacle_move_pp"] is not None for s in signals),
"steam_signals": sum(s["signal"] == "Cross-book steam" for s in signals),
"agreeing": sum(
            s["agrees_with_pick"] is True and s["direction"] == "toward" for s in signals
        ),
"opposing": sum(
            s["agrees_with_pick"] is True
            and s["direction"] == "away"
            or s["agrees_with_pick"] is False
            and s["direction"] == "toward"
            for s in signals
        ),
    }
    return {
"selected_date": date_str,
"available_dates": dates,
"bookmakers": bookmakers,
"book_coverage": coverage,
"summary": summary,
"signals": signals,
"movements": movements,
"movement_picks": movement_picks,
"snapshots": list(reversed(snaps[-1000:])),
"methodology": {
"measured": "Every price and point change is calculated from timestamped bookmaker snapshots.",
"inferred": "Cross-book steam requires at least three books moving the same implied-probability direction. Pinnacle-led pressure requires an identified Pinnacle quote moving at least 1 percentage point.",
"limitation": "Without verified ticket and handle data, these are market-pressure inferences—not proof of sharp money.",
        },
    }


def signals_csv(dataset="signals", date_str=None):
    data = get_market_signals(date_str)
    rows = data.get(dataset, [])
    out = io.StringIO()
    if rows:
        w = csv.DictWriter(out, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out.getvalue()
