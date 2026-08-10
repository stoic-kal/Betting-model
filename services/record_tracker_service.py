import csv
import io
import json
import sqlite3
from collections import defaultdict

DB_PATH = "database/picks.db"
UNIT = 20.0


def _num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _snapshot(raw):
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _feature_context(snapshot):

    features = snapshot.get("features", snapshot)
    context = features.get("context") or snapshot.get("context") or features
    return features, context


def _dig(obj, *keys):
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _bucket(rows, key, bounds):
    out = []
    for label, lo, hi in bounds:
        sub = [r for r in rows if r[key] is not None and lo <= r[key] < hi]
        resolved = [r for r in sub if r["status"] in ("won", "lost")]
        wins = sum(r["status"] == "won" for r in resolved)
        profit = sum(r["profit"] or 0 for r in resolved)
        out.append(
            {
"label": label,
"n": len(resolved),
"win_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
"roi": round(profit / (len(resolved) * UNIT) * 100, 1) if resolved else None,
"profit": round(profit, 2),
            }
        )
    return out


def get_record_tracker(version="v3"):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM picks"
    params = []
    if version:
        sql += " WHERE model_version=?"
        params.append(version)
    sql += " ORDER BY date,created_at,id"
    source = [dict(r) for r in conn.execute(sql, params)]
    conn.close()
    rows = []
    cum = 0
    for r in source:
        s = _snapshot(r.get("feature_snapshot"))
        f, c = _feature_context(s)

        a = c.get("advanced", {})
        home_sc = a.get("home_pitcher_statcast", {})
        away_sc = a.get("away_pitcher_statcast", {})
        odds = _num(r.get("opening_odds") or r.get("odds"))
        prob = _num(r.get("model_prob"))
        status = r.get("status")
        profit = (
            round((odds - 1) * UNIT, 2)
            if status == "won" and odds
            else (-UNIT if status == "lost" else 0 if status == "push" else None)
        )
        if profit is not None:
            cum += profit
        expected = _num(s.get("expected_total"))
        actual = _num(r.get("actual_total"))
        home_usage = s.get("home_starter_usage") or {}
        away_usage = s.get("away_starter_usage") or {}
        row = {
"id": r["id"],
"game_id": r["game_id"],
"date": r["date"],
"game": r["matchup"],
"type": r["pick_type"],
"pick": r["pick"],
"model_prob": prob,
"opening_odds": odds,
"closing_odds": _num(r.get("closing_odds")),
"clv": _num(r.get("clv")),
"ev": _num(r.get("ev")),
"kelly_units": _num(r.get("kelly_units"), 0),
"status": status,
"profit": profit,
"cumulative_profit": round(cum, 2),
"opposite_opening_odds": _num(r.get("opposite_opening_odds")),
"opposite_closing_odds": _num(r.get("opposite_closing_odds")),
"opposite_clv": _num(r.get("opposite_clv")),
"opposite_price_source": r.get("opposite_price_source"),
"home_score": r.get("home_score"),
"away_score": r.get("away_score"),
"actual_total": actual,
"expected_total": expected,
"total_error": (
                round(actual - expected, 2) if actual is not None and expected is not None else None
            ),
"market_line": _num(s.get("market_line")),
"market_home_prob": _num(s.get("market_home")),
"home_fip": _num(f.get("home_fip", s.get("home_fip"))),
"away_fip": _num(f.get("away_fip", s.get("away_fip"))),
"home_xera": _num(home_sc.get("xera")),
"away_xera": _num(away_sc.get("xera")),
"home_xwoba": _num(home_sc.get("xwoba_allowed")),
"away_xwoba": _num(away_sc.get("xwoba_allowed")),
"home_velocity": _num(home_sc.get("avg_velocity")),
"away_velocity": _num(away_sc.get("avg_velocity")),
"home_rsg": _num(f.get("home_rsg", s.get("home_rsg"))),
"away_rsg": _num(f.get("away_rsg", s.get("away_rsg"))),
"home_lineup_confirmed": c.get("home_lineup_confirmed"),
"away_lineup_confirmed": c.get("away_lineup_confirmed"),
"home_lineup_ops": _num(c.get("home_lineup_ops")),
"away_lineup_ops": _num(c.get("away_lineup_ops")),
"home_bp_pitches_3d": c.get("home_bullpen_pitches_3d"),
"away_bp_pitches_3d": c.get("away_bullpen_pitches_3d"),
"home_unavailable_relievers": c.get("home_unavailable_relievers"),
"away_unavailable_relievers": c.get("away_unavailable_relievers"),
"home_expected_starter_ip": _num(home_usage.get("expected_innings")),
"away_expected_starter_ip": _num(away_usage.get("expected_innings")),
"home_starter_usage_role": home_usage.get("role"),
"away_starter_usage_role": away_usage.get("role"),
"home_available_bullpen_era": _num(s.get("home_team_available_bp_era")),
"away_available_bullpen_era": _num(s.get("away_team_available_bp_era")),
"home_rest_days": c.get("home_rest_days"),
"away_rest_days": c.get("away_rest_days"),
"roof_status": _dig(a, "game_day", "roof_status"),
"day_night": _dig(a, "game_day", "day_night"),
"series_game": _dig(a, "game_day", "series_game_number"),
"model_version": r.get("model_version"),
"model_build": r.get("model_build"),
"created_at": r.get("created_at"),
"clv_captured_at": r.get("clv_captured_at"),
        }
        row["forecast_stage"] = r.get("forecast_stage")
        row["scheduled_start"] = r.get("scheduled_start")
        row["recommendation_tier"] = r.get("recommendation_tier") or "legacy_unclassified"
        rows.append(row)
    resolved = [r for r in rows if r["status"] in ("won", "lost")]
    wins = sum(r["status"] == "won" for r in resolved)
    profit = sum(r["profit"] for r in resolved)
    summary = {
"picks": len(rows),
"resolved": len(resolved),
"pending": sum(r["status"] == "pending" for r in rows),
"wins": wins,
"losses": len(resolved) - wins,
"win_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
"profit": round(profit, 2),
"roi": round(profit / (len(resolved) * UNIT) * 100, 1) if resolved else None,
"avg_clv": round(
            sum(r["clv"] for r in resolved if r["clv"] is not None)
            / max(1, sum(r["clv"] is not None for r in resolved)),
            2,
        ),
"clv_coverage": (
            round(sum(r["closing_odds"] is not None for r in rows) / len(rows) * 100, 1)
            if rows
            else 0
        ),
    }
    by_type = []
    for kind in ("moneyline", "totals"):
        sub = [r for r in resolved if r["type"] == kind]
        w = sum(r["status"] == "won" for r in sub)
        p = sum(r["profit"] for r in sub)
        by_type.append(
            {
"label": kind,
"n": len(sub),
"win_rate": round(w / len(sub) * 100, 1) if sub else None,
"roi": round(p / (len(sub) * UNIT) * 100, 1) if sub else None,
"profit": round(p, 2),
            }
        )
    monthly = defaultdict(list)
    for r in resolved:
        monthly[r["date"][:7]].append(r)
    months = []
    for label, sub in monthly.items():
        w = sum(r["status"] == "won" for r in sub)
        p = sum(r["profit"] for r in sub)
        months.append(
            {
"label": label,
"n": len(sub),
"win_rate": round(w / len(sub) * 100, 1),
"profit": round(p, 2),
            }
        )
    return {
"summary": summary,
"rows": list(reversed(rows)),
"timeline": rows,
"by_type": by_type,
"monthly": months,
"probability_buckets": _bucket(
            resolved,
"model_prob",
            [
                ("45–50%", 0.45, 0.50),
                ("50–55%", 0.50, 0.55),
                ("55–60%", 0.55, 0.60),
                ("60–65%", 0.60, 0.65),
                ("65–70%", 0.65, 0.70),
                ("70%+", 0.70, 1.01),
            ],
        ),
"ev_buckets": _bucket(
            resolved,
"ev",
            [
                ("<0%", -999, 0),
                ("0–5%", 0, 5),
                ("5–10%", 5, 10),
                ("10–20%", 10, 20),
                ("20–30%", 20, 30),
                ("30%+", 30, 999),
            ],
        ),
"odds_buckets": _bucket(
            resolved,
"opening_odds",
            [
                ("<1.50", 1, 1.5),
                ("1.50–1.75", 1.5, 1.75),
                ("1.75–2.00", 1.75, 2),
                ("2.00–2.50", 2, 2.5),
                ("2.50+", 2.5, 99),
            ],
        ),
"kelly_buckets": _bucket(
            resolved,
"kelly_units",
            [("0u", 0, 0.01), ("0.25u", 0.01, 0.375), ("0.50u", 0.375, 0.75), ("1.00u", 0.75, 2)],
        ),
    }


def record_csv(version="v3"):
    rows = get_record_tracker(version)["rows"]
    out = io.StringIO()
    if rows:
        w = csv.DictWriter(out, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return out.getvalue()
