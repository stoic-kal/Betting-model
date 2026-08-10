import json
import sqlite3
from collections import defaultdict
from datetime import datetime

DB_PATH = "database/picks.db"
UNIT_DOLLARS = 20.0


def _snapshot(raw):
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _market_prob(row, snap):
    if row["pick_type"] == "moneyline":
        home = row["matchup"].split(" @ ")[-1]
        return snap.get("market_home") if row["pick"] == home else snap.get("market_away")
    return 1 / row["odds"] if row["odds"] else None


def _quality(row, snap):
    f = snap.get("features", snap)
    c = f.get("context", snap.get("context", {}))
    if row["pick_type"] == "moneyline":
        advanced = f.get("advanced", {})
        checks = {
"lineups": f.get("home_lineup_confirmed") and f.get("away_lineup_confirmed"),
"starters": f.get("home_fip") is not None and f.get("away_fip") is not None,
"offense": f.get("home_rsg") is not None and f.get("away_rsg") is not None,
"bullpen": f.get("home_bp_era") is not None and f.get("away_bp_era") is not None,
"defense": f.get("defense_adv") is not None,
"rest_travel": f.get("rest_adv") is not None
            and f.get("travel_timezone_adv") is not None,
"market": snap.get("market_home") is not None,
"statcast": advanced.get("home_pitcher_statcast", {}).get("available")
            and advanced.get("away_pitcher_statcast", {}).get("available"),
"reliever availability": advanced.get("home_bullpen", {}).get("available")
            and advanced.get("away_bullpen", {}).get("available"),
"handedness context": advanced.get("lineup_handedness", {})
            .get("home_vs_away_sp", {})
            .get("available"),
        }
    else:
        advanced = c.get("advanced", {})
        checks = {
"lineups": c.get("home_lineup_confirmed") and c.get("away_lineup_confirmed"),
"starters": snap.get("home_fip") is not None and snap.get("away_fip") is not None,
"offense": snap.get("home_rsg") is not None and snap.get("away_rsg") is not None,
"bullpen": snap.get("bullpen_workload_adj") is not None,
"defense": snap.get("defense_runs_adj") is not None,
"rest_travel": c.get("rest_adv") is not None
            and c.get("travel_timezone_adv") is not None,
"market": snap.get("market_line") is not None,
"statcast": advanced.get("home_pitcher_statcast", {}).get("available")
            and advanced.get("away_pitcher_statcast", {}).get("available"),
"reliever availability": advanced.get("home_bullpen", {}).get("available")
            and advanced.get("away_bullpen", {}).get("available"),
"dynamic starter innings": bool(
                snap.get("home_starter_usage", {}).get("available")
                and snap.get("away_starter_usage", {}).get("available")
            ),
"available reliever quality": bool(
                snap.get("home_team_available_bp_era") is not None
                and snap.get("away_team_available_bp_era") is not None
            ),
"roof/series context": advanced.get("game_day", {}).get("available"),
        }
    score = sum(bool(v) for v in checks.values()) / len(checks)
    if score >= 0.99:
        label = "Strong evidence"
    elif score >= 0.80:
        label = "Qualified"
    elif score >= 0.55:
        label = "Incomplete inputs"
    else:
        label = "Research only"
    return {
"score": round(score * 100, 1),
"label": label,
"missing": [k.replace("_", " ") for k, ok in checks.items() if not ok],
    }


def _attribution(row, snap, market_prob):
    if row["pick_type"] != "moneyline" or market_prob is None:
        return []
    f = snap.get("features", {})
    terms = [
        ("Starting pitchers", 0.22, f.get("fip_adv", 0)),
        ("Venue offense", 0.18, f.get("rsg_adv", 0)),
        ("Recent form", 0.35, f.get("form_adv", 0)),
        ("Bullpen", 0.15, f.get("bp_adv", 0)),
        ("Season record", 0.28, f.get("wpct_adv", 0)),
        ("Confirmed lineups", 1.0, f.get("lineup_ops_adv", 0)),
        ("Rest", 0.05, f.get("rest_adv", 0)),
        ("Bullpen workload", 0.06, f.get("bullpen_fatigue_adv", 0)),
        ("Defense", 0.10, f.get("defense_adv", 0)),
    ]
    picked_home = row["pick"] == row["matchup"].split(" @ ")[-1]
    direction = 1 if picked_home else -1

    scale = market_prob * (1 - market_prob) * 0.55 * 100 * direction
    return [
        {"feature": name, "effect_pp": round(beta * float(value or 0) * scale, 2)}
        for name, beta, value in terms
    ]


def _summary(rows):
    resolved = [r for r in rows if r["status"] in ("won", "lost")]
    wins = sum(r["status"] == "won" for r in resolved)
    stake = len(resolved) * UNIT_DOLLARS
    profit = sum(
        (r["odds"] - 1) * UNIT_DOLLARS if r["status"] == "won" else -UNIT_DOLLARS for r in resolved
    )
    return {
"picks": len(rows),
"resolved": len(resolved),
"wins": wins,
"win_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
"profit": round(profit, 2),
"roi": round(profit / stake * 100, 1) if stake else None,
    }


def get_model_control():
    from services.model_learning_service import get_learning_status

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in conn.execute("SELECT * FROM picks ORDER BY date, created_at, id").fetchall()
    ]
    audit = [
        dict(r)
        for r in conn.execute(
"SELECT * FROM prediction_audit ORDER BY id DESC LIMIT 250"
        ).fetchall()
    ]
    market_snapshots = [
        dict(r)
        for r in conn.execute(
"SELECT * FROM market_snapshots ORDER BY captured_at DESC LIMIT 2000"
        ).fetchall()
    ]
    api_calls = [
        dict(r)
        for r in conn.execute("SELECT * FROM api_call_log ORDER BY id DESC LIMIT 250").fetchall()
    ]
    conn.close()

    movement_groups = defaultdict(list)
    for snap in reversed(market_snapshots):
        key = (snap["event_id"], snap["bookmaker"], snap["market"], snap["outcome"], snap["point"])
        movement_groups[key].append(snap)
    market_movements = []
    for (_, bookmaker, market, outcome, point), history in movement_groups.items():
        if len(history) < 2:
            continue
        opening, latest = history[0], history[-1]
        if opening["price"] == latest["price"] and opening["point"] == latest["point"]:
            continue
        market_movements.append(
            {
"game": f"{latest['away_team']} @ {latest['home_team']}",
"bookmaker": bookmaker,
"market": market,
"outcome": outcome,
"point": point,
"opening_price": opening["price"],
"latest_price": latest["price"],
"implied_move_pp": round((1 / latest["price"] - 1 / opening["price"]) * 100, 2),
"first_seen": opening["captured_at"],
"last_seen": latest["captured_at"],
"sharp_label": (
"Pinnacle movement" if "pinnacle" in bookmaker.lower() else "Book movement"
                ),
            }
        )

    enriched, bankroll, errors, alerts = [], [], [], []
    flat_bank = kelly_bank = 1000.0
    peak = 1000.0
    model_sq, market_sq, starter_sq, core_sq = [], [], [], []
    for row in rows:
        snap = _snapshot(row.get("feature_snapshot"))
        market = _market_prob(row, snap)
        quality = _quality(row, snap)
        resolved = row["status"] in ("won", "lost")
        outcome = 1 if row["status"] == "won" else 0
        flat_pl = (
            ((row["odds"] - 1) * UNIT_DOLLARS if row["status"] == "won" else -UNIT_DOLLARS)
            if resolved
            else 0
        )
        units = float(row.get("kelly_units") or 0)
        kelly_stake = units * UNIT_DOLLARS
        kelly_pl = (
            ((row["odds"] - 1) * kelly_stake if row["status"] == "won" else -kelly_stake)
            if resolved
            else 0
        )
        if resolved:
            flat_bank += flat_pl
            kelly_bank += kelly_pl
            peak = max(peak, kelly_bank)
            bankroll.append(
                {
"date": row["date"],
"matchup": row["matchup"],
"pick": row["pick"],
"flat_bankroll": round(flat_bank, 2),
"kelly_bankroll": round(kelly_bank, 2),
"drawdown": round(kelly_bank - peak, 2),
"flat_pl": round(flat_pl, 2),
"kelly_pl": round(kelly_pl, 2),
                }
            )
            model_sq.append((row["model_prob"] - outcome) ** 2)
            if market is not None:
                market_sq.append((market - outcome) ** 2)
        expected = snap.get("expected_total")
        actual = row.get("actual_total")
        if row["pick_type"] == "totals" and actual is not None and expected is not None:
            errors.append(
                {
"date": row["date"],
"matchup": row["matchup"],
"pick": row["pick"],
"predicted_total": expected,
"actual_total": actual,
"signed_error": round(actual - expected, 2),
"absolute_error": round(abs(actual - expected), 2),
                }
            )
        if row.get("closing_odds"):
            move = (row["closing_odds"] / row["odds"] - 1) * 100
            alerts.append(
                {
"date": row["date"],
"matchup": row["matchup"],
"pick": row["pick"],
"kind": "toward pick" if move < 0 else "away from pick",
"price_move_pct": round(move, 1),
"clv": row.get("clv"),
                }
            )
        attribution = _attribution(row, snap, market)
        if resolved and market is not None and attribution:
            effects = {a["feature"]: a["effect_pp"] / 100 for a in attribution}
            starter_p = min(0.99, max(0.01, market + effects.get("Starting pitchers", 0)))
            core_p = min(
                0.99,
                max(0.01, starter_p + effects.get("Venue offense", 0) + effects.get("Bullpen", 0)),
            )
            starter_sq.append((starter_p - outcome) ** 2)
            core_sq.append((core_p - outcome) ** 2)
        item = {k: v for k, v in row.items() if k != "feature_snapshot"}
        item.update(
            {
"market_prob": market,
"quality": quality,
"attribution": attribution,
"expected_total": expected,
"brier_error": round((row["model_prob"] - outcome) ** 2, 4) if resolved else None,
            }
        )
        enriched.append(item)

    resolved = [r for r in enriched if r["status"] in ("won", "lost")]
    by_type = {
        kind: _summary([r for r in enriched if r["pick_type"] == kind])
        for kind in ("moneyline", "totals")
    }
    by_month = []
    groups = defaultdict(list)
    for r in enriched:
        groups[r["date"][:7]].append(r)
    for period, group in sorted(groups.items()):
        by_month.append({"period": period, **_summary(group)})

    walk_forward = []
    for start in range(0, len(resolved), 25):
        block = resolved[start : start + 25]
        if block:
            walk_forward.append(
                {"period": f"{block[0]['date']} → {block[-1]['date']}", **_summary(block)}
            )

    brier_model = sum(model_sq) / len(model_sq) if model_sq else None
    brier_market = sum(market_sq) / len(market_sq) if market_sq else None
    baselines = [
        {
"name": "Full model forecast",
"brier": round(brier_model, 4) if brier_model is not None else None,
        },
        {
"name": "Market-only forecast",
"brier": round(brier_market, 4) if brier_market is not None else None,
        },
        {
"name": "Market + starter challenger",
"brier": round(sum(starter_sq) / len(starter_sq), 4) if starter_sq else None,
        },
        {
"name": "Market + SP/offense/bullpen challenger",
"brier": round(sum(core_sq) / len(core_sq), 4) if core_sq else None,
        },
        {"name": "Uninformed 50/50 forecast", "brier": 0.25 if resolved else None},
    ]
    recent = resolved[-20:]
    warnings = []
    if brier_model is not None and brier_model > 0.25:
        warnings.append(
            {
"level": "danger",
"text": "Model Brier score is worse than an uninformed 50/50 forecast.",
            }
        )
    if brier_model is not None and brier_market is not None and brier_model > brier_market:
        warnings.append(
            {
"level": "danger",
"text": "Model probabilities are currently less accurate than market probabilities.",
            }
        )
    if recent and _summary(recent)["roi"] < 0:
        warnings.append(
            {"level": "warning", "text": "The latest 20 resolved picks have negative flat-bet ROI."}
        )
    if not alerts:
        warnings.append(
            {
"level": "warning",
"text": "Closing lines are missing; CLV and market-movement evidence are incomplete.",
            }
        )
    totals = [r for r in enriched if r["pick_type"] == "totals"]
    if (
        totals
        and max(sum("UNDER" in r["pick"] for r in totals), sum("OVER" in r["pick"] for r in totals))
        / len(totals)
        > 0.75
    ):
        warnings.append(
            {"level": "warning", "text": "Totals selections show a direction imbalance above 75%."}
        )
    if not warnings:
        warnings.append(
            {"level": "ok", "text": "No automatic health thresholds are currently breached."}
        )

    return {
"generated_at": datetime.now().isoformat(),
"summary": _summary(enriched),
"by_type": by_type,
"by_month": by_month,
"bankroll": bankroll,
"errors": errors,
"alerts": alerts[-100:],
"baselines": baselines,
"walk_forward": walk_forward,
"health_warnings": warnings,
"picks": enriched[-250:],
"audit": audit,
"market_snapshots": market_snapshots,
"api_calls": api_calls,
"market_movements": market_movements,
"learning": get_learning_status(),
"method_notes": {
"walk_forward": "Chronological 25-pick evaluation blocks; monitoring only, not model retraining.",
"attribution": "First-order approximation of stored v3 moneyline logit contributions.",
"bankroll": "Paper bankroll starts at $1,000; one unit equals $20.",
        },
    }
