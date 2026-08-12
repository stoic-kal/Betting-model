import json
import math
import sqlite3
from collections import defaultdict

import numpy as np


DB_PATH = "database/picks.db"


def _return_units(row, stake_field):
    stake = row.get(stake_field)
    if stake is None or row.get("status") not in ("won", "lost"):
        return None
    stake = float(stake)
    if stake <= 0:
        return 0.0
    return stake * (float(row["odds"]) - 1) if row["status"] == "won" else -stake


def _max_drawdown(values):
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return abs(worst)


def _risk_metrics(daily_returns):
    values = np.asarray(daily_returns, dtype=float)
    if not len(values):
        return {"active_days": 0}
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    downside = values[values < 0]
    downside_std = float(np.sqrt(np.mean(downside ** 2))) if len(downside) else 0.0
    var95 = float(np.quantile(values, 0.05))
    tail = values[values <= var95]
    return {
        "active_days": int(len(values)),
        "net_units": round(float(values.sum()), 4),
        "mean_daily_units": round(mean, 4),
        "daily_volatility_units": round(std, 4),
        "downside_deviation_units": round(downside_std, 4),
        "sharpe_per_active_day": round(mean / std, 4) if std else None,
        "sortino_per_active_day": round(mean / downside_std, 4) if downside_std else None,
        "historical_var_95_units": round(var95, 4),
        "historical_cvar_95_units": round(float(tail.mean()), 4) if len(tail) else None,
        "max_drawdown_units": round(_max_drawdown(values), 4),
        "winning_day_rate": round(float((values > 0).mean()), 4),
    }


def complete_history_portfolio_audit(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM picks ORDER BY date,created_at,id")]
    conn.close()

    valid_odds = [row for row in rows if _valid_odds(row.get("odds"))]
    malformed = [row for row in rows if not _valid_odds(row.get("odds"))]
    resolved = [row for row in valid_odds if row.get("status") in ("won", "lost")]
    paired = defaultdict(dict)
    for row in resolved:
        paired[(row["date"], row["matchup"])][row["pick_type"]] = row
    simultaneous = [pair for pair in paired.values() if {"moneyline", "totals"} <= set(pair)]
    ml = np.asarray([int(pair["moneyline"]["status"] == "won") for pair in simultaneous])
    totals = np.asarray([int(pair["totals"]["status"] == "won") for pair in simultaneous])
    correlation = (
        float(np.corrcoef(ml, totals)[0, 1])
        if len(simultaneous) >= 3 and ml.std() > 0 and totals.std() > 0
        else None
    )

    theoretical_daily = defaultdict(float)
    realized_daily = defaultdict(float)
    game_exposures = defaultdict(float)
    daily_exposures = defaultdict(float)
    theoretical_game_exposures = defaultdict(float)
    theoretical_daily_exposures = defaultdict(float)
    realized_rows = 0
    for row in resolved:
        theoretical = _return_units(row, "theoretical_kelly_units")
        if theoretical is None:
            theoretical = _return_units(row, "kelly_units")
        if theoretical is not None:
            theoretical_daily[row["date"]] += theoretical
        theoretical_stake = float(
            row.get("theoretical_kelly_units")
            if row.get("theoretical_kelly_units") is not None
            else row.get("kelly_units") or 0
        )
        theoretical_game_exposures[(row["date"], row["matchup"])] += theoretical_stake
        theoretical_daily_exposures[row["date"]] += theoretical_stake
        realized = _return_units(row, "realized_stake_units")
        if row.get("realized_stake_units") is not None:
            realized_rows += 1
            game_exposures[(row["date"], row["matchup"])] += float(row["realized_stake_units"] or 0)
            daily_exposures[row["date"]] += float(row["realized_stake_units"] or 0)
        if realized is not None:
            realized_daily[row["date"]] += realized

    all_theoretical_stakes = [
        float(row.get("theoretical_kelly_units") if row.get("theoretical_kelly_units") is not None else row.get("kelly_units") or 0)
        for row in valid_odds
    ]
    total_stake = sum(all_theoretical_stakes)
    hhi = sum((stake / total_stake) ** 2 for stake in all_theoretical_stakes) if total_stake else None
    return {
        "scope": "complete picks history; won/lost outcomes for return and correlation metrics",
        "data_quality": {
            "total_picks": len(rows),
            "resolved_picks": len(resolved),
            "malformed_odds": len(malformed),
            "realized_stake_coverage_resolved": round(realized_rows / len(resolved), 4) if resolved else 0,
            "note": "legacy realized stakes remain unknown and are not backfilled",
        },
        "simultaneous_wager_correlation": {
            "paired_games": len(simultaneous),
            "pearson_win_indicator": round(correlation, 4) if correlation is not None else None,
            "both_lost_rate": round(float(np.mean((ml == 0) & (totals == 0))), 4) if len(ml) else None,
            "both_won_rate": round(float(np.mean((ml == 1) & (totals == 1))), 4) if len(ml) else None,
        },
        "theoretical_kelly_portfolio": _risk_metrics(
            [theoretical_daily[key] for key in sorted(theoretical_daily)]
        ),
        "realized_stake_portfolio": _risk_metrics(
            [realized_daily[key] for key in sorted(realized_daily)]
        ),
        "exposure": {
            "max_theoretical_game_units": round(max(theoretical_game_exposures.values()), 4) if theoretical_game_exposures else None,
            "max_theoretical_day_units": round(max(theoretical_daily_exposures.values()), 4) if theoretical_daily_exposures else None,
            "max_realized_game_units": round(max(game_exposures.values()), 4) if game_exposures else None,
            "max_realized_day_units": round(max(daily_exposures.values()), 4) if daily_exposures else None,
            "theoretical_stake_hhi": round(hhi, 6) if hhi is not None else None,
        },
    }


def _valid_odds(value):
    try:
        value = float(value)
        return math.isfinite(value) and 1 < value <= 100
    except (TypeError, ValueError):
        return False
