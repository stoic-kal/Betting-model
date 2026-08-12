import csv
import io
import re
import sqlite3

from pipeline.calibration_common import brier_score

DB_PATH = "database/picks.db"
UNIT_DOLLARS = 20.0


def _complement_odds(decimal_odds):
    if not decimal_odds or float(decimal_odds) <= 1:
        return None
    implied = 1 / float(decimal_odds)
    return round(1 / (1 - implied), 4) if implied < 1 else None


def _opposite_pick(row):
    if row["pick_type"] == "totals":
        match = re.match(r"^\s*(OVER|UNDER)\s+(.+?)\s*$", row["pick"], re.I)
        return (
            f"{'UNDER' if match and match.group(1).upper() == 'OVER' else 'OVER'} {match.group(2)}"
            if match
            else f"OPPOSITE OF {row['pick']}"
        )
    teams = row["matchup"].split(" @ ", 1)
    if len(teams) != 2:
        return f"OPPOSITE OF {row['pick']}"
    away, home = teams
    picked = row["pick"].lower()
    return away if picked in home.lower() or home.lower() in picked else home


def _kelly_tier(probability, odds):
    if not probability or not odds or odds <= 1:
        return 0.0
    half = (((odds - 1) * probability - (1 - probability)) / (odds - 1)) * 0.5
    return 0.0 if half <= 0 else 0.25 if half < 0.05 else 0.50 if half < 0.10 else 1.0


def _summary(rows):
    resolved = [r for r in rows if r["opposite_status"] in ("won", "lost")]
    wins = sum(r["opposite_status"] == "won" for r in resolved)
    profit = sum(r["shadow_profit"] for r in resolved if r["shadow_profit"] is not None)
    wagered = sum(UNIT_DOLLARS for r in resolved if r["shadow_profit"] is not None)
    brier = brier_score(
        [1 if r["opposite_status"] == "won" else 0 for r in resolved],
        [r["opposite_prob"] for r in resolved],
    )
    return {
"picks": len(rows),
"resolved": len(resolved),
"wins": wins,
"losses": len(resolved) - wins,
"win_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
"shadow_profit": round(profit, 2),
"shadow_roi": round(profit / wagered * 100, 1) if wagered else None,
"brier": round(brier, 4) if brier is not None else None,
    }


def get_opposite_model(model_version=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM picks"
    params = []
    if model_version:
        sql += " WHERE model_version = ?"
        params.append(model_version)
    sql += " ORDER BY date DESC, created_at DESC, id DESC"
    source = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    rows = []
    for row in source:
        actual_open = row.get("opposite_opening_odds")
        actual_close = row.get("opposite_closing_odds")
        opening = actual_open or _complement_odds(row.get("opening_odds") or row.get("odds"))
        closing = actual_close or _complement_odds(row.get("closing_odds"))
        price_source = (
            row.get("opposite_price_source")
            if actual_open
            else "synthetic fair complement (legacy fallback)"
        )
        probability = round(1 - float(row["model_prob"]), 6)
        status = {"won": "lost", "lost": "won", "push": "push"}.get(row["status"], "pending")
        clv = round((1 / closing - 1 / opening) * 100, 3) if opening and closing else None
        ev = round((probability * opening - 1) * 100, 2) if opening else None
        profit = (
            (
                (opening - 1) * UNIT_DOLLARS
                if status == "won"
                else -UNIT_DOLLARS if status == "lost" else 0.0
            )
            if opening and status != "pending"
            else None
        )
        rows.append(
            {
"date": row["date"],
"game": row["matchup"],
"type": row["pick_type"],
"model_pick": row["pick"],
"opposite_pick": _opposite_pick(row),
"opposite_prob": probability,
"opening_odds": opening,
"closing_odds": closing,
"clv": clv,
"ev": ev,
"kelly_units": _kelly_tier(probability, opening),
"opposite_status": status,
"shadow_profit": round(profit, 2) if profit is not None else None,
"price_source": price_source,
"model_version": row.get("model_version"),
"model_build": row.get("model_build"),
            }
        )
    by_type = {
        kind: _summary([r for r in rows if r["type"] == kind]) for kind in ("moneyline", "totals")
    }
    return {
"summary": _summary(rows),
"by_type": by_type,
"rows": rows,
"methodology": {
"purpose": "Counterfactual diagnostic only",
"prices": "New picks use stored opposing sportsbook quotes at generation and close. Legacy picks use a labeled synthetic fair-complement fallback.",
"interpretation": "Use result patterns to locate systematic side or direction errors. Do not use shadow ROI as evidence of a tradable strategy.",
        },
    }


def opposite_csv(model_version=None):
    rows = get_opposite_model(model_version)["rows"]
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue()
