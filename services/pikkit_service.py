import calendar
import csv
import io
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

from config import today_et

DB_PATH = "database/picks.db"
VALID_TYPES = {"all", "moneyline", "totals"}
VALID_BASIS = {"recorded", "flat"}
VALID_TIERS = {"all", "recommended", "strong_lock", "daily_forecast"}


def _month(value):
    value = value or today_et()[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValueError("Invalid month; use YYYY-MM.")
    datetime.strptime(value, "%Y-%m")
    return value


def _unit_profit(row, basis):
    stake = 1.0 if basis == "flat" else float(row["kelly_units"] or 0)
    if row["status"] == "won":
        return stake * (float(row["opening_odds"] or row["odds"]) - 1), stake
    if row["status"] == "lost":
        return -stake, stake
    if row["status"] == "push":
        return 0.0, stake
    return None, stake


def get_pikkit_calendar(
    month=None, pick_type="all", basis="recorded", version="v3", unit_size=20, tier="all"
):
    month = _month(month)
    if pick_type not in VALID_TYPES or basis not in VALID_BASIS or tier not in VALID_TIERS:
        raise ValueError("Invalid Pikkit filter.")
    try:
        unit_size = float(unit_size)
    except (TypeError, ValueError):
        raise ValueError("Unit size must be a number.")
    if not 0.01 <= unit_size <= 100000:
        raise ValueError("Unit size must be between $0.01 and $100,000.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM picks WHERE date LIKE ? AND model_version=?"
    params = [month + "-%", version]
    if pick_type != "all":
        sql += " AND pick_type=?"
        params.append(pick_type)
    if tier == "recommended":
        sql += " AND recommendation_tier IN ('qualified_pick','strong_lock')"
    elif tier != "all":
        sql += " AND recommendation_tier=?"
        params.append(tier)
    sql += " ORDER BY date, COALESCE(scheduled_start,created_at), id"
    source = [dict(row) for row in conn.execute(sql, params)]
    conn.close()

    days = defaultdict(list)
    for row in source:
        profit, stake = _unit_profit(row, basis)
        days[row["date"]].append(
            {
"id": row["id"],
"game": row["matchup"],
"type": row["pick_type"],
"pick": row["pick"],
"status": row["status"],
"odds": row["opening_odds"] or row["odds"],
"model_prob": row["model_prob"],
"ev": row["ev"],
"clv": row["clv"],
"stake_units": round(stake, 2),
"profit_units": round(profit, 2) if profit is not None else None,
"profit_dollars": round(profit * unit_size, 2) if profit is not None else None,
"recommendation_tier": row.get("recommendation_tier") or "legacy_unclassified",
            }
        )

    daily = []
    for date_str, rows in sorted(days.items()):
        resolved = [r for r in rows if r["status"] in ("won", "lost", "push")]
        wins = sum(r["status"] == "won" for r in resolved)
        losses = sum(r["status"] == "lost" for r in resolved)
        pushes = sum(r["status"] == "push" for r in resolved)
        net = sum(r["profit_units"] or 0 for r in resolved)
        daily.append(
            {
"date": date_str,
"day": int(date_str[-2:]),
"wins": wins,
"losses": losses,
"pushes": pushes,
"pending": sum(r["status"] == "pending" for r in rows),
"net_units": round(net, 2),
"picks": rows,
            }
        )

    resolved = [r for day in daily for r in day["picks"] if r["status"] in ("won", "lost", "push")]
    wins = sum(r["status"] == "won" for r in resolved)
    losses = sum(r["status"] == "lost" for r in resolved)
    pushes = sum(r["status"] == "push" for r in resolved)
    year, month_number = map(int, month.split("-"))
    first_weekday, days_in_month = calendar.monthrange(year, month_number)
    return {
"month": month,
"month_label": datetime(year, month_number, 1).strftime("%B %Y"),
"first_weekday": first_weekday,
"days_in_month": days_in_month,
"filters": {
"type": pick_type,
"basis": basis,
"version": version,
"unit_size": round(unit_size, 2),
"tier": tier,
        },
"summary": {
"wins": wins,
"losses": losses,
"pushes": pushes,
"resolved": len(resolved),
"win_rate": round(wins / (wins + losses) * 100, 1) if wins + losses else None,
"net_units": round(sum(r["profit_units"] or 0 for r in resolved), 2),
"net_dollars": round(sum(r["profit_units"] or 0 for r in resolved) * unit_size, 2),
"winning_days": sum(day["net_units"] > 0 for day in daily),
"losing_days": sum(day["net_units"] < 0 for day in daily),
        },
"days": daily,
    }


def pikkit_csv(
    month=None, pick_type="all", basis="recorded", version="v3", unit_size=20, tier="all"
):
    data = get_pikkit_calendar(month, pick_type, basis, version, unit_size, tier)
    rows = [{"date": day["date"], **pick} for day in data["days"] for pick in day["picks"]]
    output = io.StringIO()
    fields = [
"date",
"game",
"type",
"pick",
"status",
"odds",
"model_prob",
"ev",
"clv",
"stake_units",
"profit_units",
"profit_dollars",
"recommendation_tier",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
