import math
import sqlite3

DB_PATH = 'database/picks.db'
UNIT_SIZE = 20.0  # Current standard unit size  1 unit = $20


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def get_full_analytics(model_version: str = None) -> dict:
    conn = _conn()

    if model_version:
        resolved = conn.execute(
"""
            SELECT * FROM picks
            WHERE status IN ('won','lost') AND model_version = ?
            ORDER BY date ASC
""",
            (model_version,),
        ).fetchall()
        pending = conn.execute(
"SELECT COUNT(*) FROM picks WHERE status='pending' AND model_version = ?",
            (model_version,),
        ).fetchone()[0]
    else:
        resolved = conn.execute("""
            SELECT * FROM picks
            WHERE status IN ('won','lost')
            ORDER BY date ASC
""").fetchall()
        pending = conn.execute("SELECT COUNT(*) FROM picks WHERE status='pending'").fetchone()[0]
    resolved = [dict(r) for r in resolved]

    conn.close()

    if not resolved:
        return _empty_analytics(pending)

    total = len(resolved)
    won = sum(1 for r in resolved if r["status"] == "won")
    lost = total - won
    win_rate = won / total if total else 0
    total_profit = 0.0
    total_wagered = 0.0
    kelly_profit = 0.0
    kelly_wagered = 0.0

    def _kelly(p):

        k = p.get("kelly_units")
        if k is not None:
            return float(k)

        prob = float(p["model_prob"] or 0)
        odds = float(p["odds"] or 1)
        b = odds - 1
        if b <= 0 or not prob:
            return 0.5
        q = 1 - prob
        return round(min(max(((b * prob - q) / b) * 0.5, 0), 3.0), 3)

    for r in resolved:
        ku = _kelly(r)
        total_wagered += UNIT_SIZE
        kelly_wagered += ku * UNIT_SIZE
        if r["status"] == "won":
            total_profit += (float(r["odds"]) - 1) * UNIT_SIZE
            kelly_profit += (float(r["odds"]) - 1) * ku * UNIT_SIZE
        else:
            total_profit -= UNIT_SIZE
            kelly_profit -= ku * UNIT_SIZE

    roi = (total_profit / total_wagered) * 100 if total_wagered else 0
    kelly_roi = (kelly_profit / kelly_wagered) * 100 if kelly_wagered else 0

    streak = _compute_streak(resolved)

    ml_picks = [r for r in resolved if r["pick_type"] == "moneyline"]
    tot_picks = [r for r in resolved if r["pick_type"] == "totals"]

    ml_stats = _type_stats(ml_picks)
    tot_stats = _type_stats(tot_picks)

    calibration = _calibration_curve(resolved)

    pnl_over_time = _pnl_over_time(resolved)

    ev_analysis = _ev_threshold_analysis(resolved)

    team_stats = _team_breakdown(resolved)

    recommendations = _generate_recommendations(
        ml_stats, tot_stats, calibration, ev_analysis, win_rate
    )
    return {
"summary": {
"total_picks": total,
"won": won,
"lost": lost,
"pending": pending,
"win_rate": round(win_rate * 100, 1),
"total_profit": round(total_profit, 2),
"total_wagered": round(total_wagered, 2),
"roi": round(roi, 1),
"kelly_profit": round(kelly_profit, 2),
"kelly_wagered": round(kelly_wagered, 2),
"kelly_roi": round(kelly_roi, 1),
"streak": streak,
        },
"by_type": {
"moneyline": ml_stats,
"totals": tot_stats,
        },
"calibration": calibration,
"pnl_over_time": pnl_over_time,
"ev_analysis": ev_analysis,
"team_stats": team_stats,
"recommendations": recommendations,
    }


def _type_stats(picks: list) -> dict:
    def _kelly(p):
        k = p.get("kelly_units")
        if k is not None:
            return float(k)
        prob = float(p["model_prob"] or 0)
        odds = float(p["odds"] or 1)
        b = odds - 1
        if b <= 0 or not prob:
            return 0.5
        q = 1 - prob
        return round(min(max(((b * prob - q) / b) * 0.5, 0), 3.0), 3)

    if not picks:
        return {
"n": 0,
"won": 0,
"lost": 0,
"win_rate": 0,
"profit": 0,
"roi": 0,
"kelly_profit": 0,
"kelly_roi": 0,
"avg_ev": 0,
"avg_prob": 0,
"avg_kelly": 0,
"roi_ci_low": 0,
"roi_ci_high": 0,
"roi_se": 0,
        }
    won = sum(1 for p in picks if p["status"] == "won")
    lost = len(picks) - won
    profit = 0.0
    kelly_profit = 0.0
    kelly_wagered = 0.0
    for p in picks:
        ku = _kelly(p)
        kelly_wagered += ku * UNIT_SIZE
        if p["status"] == "won":
            profit += (float(p["odds"]) - 1) * UNIT_SIZE
            kelly_profit += (float(p["odds"]) - 1) * ku * UNIT_SIZE
        else:
            profit -= UNIT_SIZE
            kelly_profit -= ku * UNIT_SIZE
    wagered = len(picks) * UNIT_SIZE
    unit_returns = [(float(p["odds"]) - 1) if p["status"] == "won" else -1.0 for p in picks]
    mean_return = sum(unit_returns) / len(unit_returns)
    if len(unit_returns) > 1:
        variance = sum((value - mean_return) ** 2 for value in unit_returns) / (len(unit_returns) - 1)
        roi_se = math.sqrt(variance / len(unit_returns)) * 100
    else:
        roi_se = 0.0
    roi_low = mean_return * 100 - 1.96 * roi_se
    roi_high = mean_return * 100 + 1.96 * roi_se
    avg_ev = sum(float(p["ev"]) for p in picks) / len(picks)
    avg_prob = sum(float(p["model_prob"]) for p in picks) / len(picks)
    avg_ku = kelly_wagered / len(picks) / UNIT_SIZE
    return {
"n": len(picks),
"won": won,
"lost": lost,
"win_rate": round(won / len(picks) * 100, 1),
"profit": round(profit, 2),
"roi": round(profit / wagered * 100, 1) if wagered else 0,
"kelly_profit": round(kelly_profit, 2),
"kelly_roi": round(kelly_profit / kelly_wagered * 100, 1) if kelly_wagered else 0,
"avg_ev": round(avg_ev, 1),
"avg_prob": round(avg_prob * 100, 1),
"avg_kelly": round(avg_ku, 3),
"roi_ci_low": round(roi_low, 1),
"roi_ci_high": round(roi_high, 1),
"roi_se": round(roi_se, 4),
    }


def _compute_streak(resolved: list) -> str:
    if not resolved:
        return "-"
    streak_count = 0
    last_status = resolved[-1]["status"]
    for r in reversed(resolved):
        if r["status"] == last_status:
            streak_count += 1
        else:
            break
    symbol = "W" if last_status == "won" else "L"
    return f"{streak_count}{symbol}"


def _calibration_curve(resolved: list) -> list:
    ordered = sorted(resolved, key=lambda pick: float(pick["model_prob"]))
    bucket_count = max(2, min(10, int(math.sqrt(len(ordered)))))
    curve = []
    for index in range(bucket_count):
        start = index * len(ordered) // bucket_count
        end = (index + 1) * len(ordered) // bucket_count
        bucket_picks = ordered[start:end]
        if not bucket_picks:
            continue
        probabilities = [float(p["model_prob"]) for p in bucket_picks]
        won = sum(1 for p in bucket_picks if p["status"] == "won")
        predicted = sum(probabilities) / len(probabilities)
        curve.append({
            "prob_range": f"{min(probabilities):.3f}-{max(probabilities):.3f}",
            "prob_mid": round(predicted * 100, 1),
            "predicted": round(predicted * 100, 1),
            "actual": round(won / len(bucket_picks) * 100, 1),
            "n": len(bucket_picks),
            "won": won,
        })
    return curve


def _pnl_over_time(resolved: list) -> list:
    def _kelly(p):
        k = p.get("kelly_units")
        if k is not None:
            return float(k)
        prob = float(p["model_prob"] or 0)
        odds = float(p["odds"] or 1)
        b = odds - 1
        if b <= 0 or not prob:
            return 0.5
        q = 1 - prob
        return round(min(max(((b * prob - q) / b) * 0.5, 0), 3.0), 3)

    by_date = {}
    for p in resolved:
        d = p["date"]
        ku = _kelly(p)
        by_date.setdefault(d, {"won": 0, "lost": 0, "profit": 0.0, "kelly_profit": 0.0})
        if p["status"] == "won":
            by_date[d]["won"] += 1
            by_date[d]["profit"] += (float(p["odds"]) - 1) * UNIT_SIZE
            by_date[d]["kelly_profit"] += (float(p["odds"]) - 1) * ku * UNIT_SIZE
        else:
            by_date[d]["lost"] += 1
            by_date[d]["profit"] -= UNIT_SIZE
            by_date[d]["kelly_profit"] -= ku * UNIT_SIZE

    cumulative = 0.0
    kelly_cumulative = 0.0
    result = []
    for date in sorted(by_date.keys()):
        cumulative += by_date[date]["profit"]
        kelly_cumulative += by_date[date]["kelly_profit"]
        result.append(
            {
"date": date,
"daily_pnl": round(by_date[date]["profit"], 2),
"cumulative": round(cumulative, 2),
"kelly_daily": round(by_date[date]["kelly_profit"], 2),
"kelly_cum": round(kelly_cumulative, 2),
"won": by_date[date]["won"],
"lost": by_date[date]["lost"],
            }
        )
    return result


def _ev_threshold_analysis(resolved: list) -> list:
    values = sorted(float(p["ev"]) for p in resolved)
    quantiles = (0.0, 0.25, 0.50, 0.75, 0.90)
    thresholds = sorted({values[min(int(q * (len(values) - 1)), len(values) - 1)] for q in quantiles})
    results = []
    for threshold in thresholds:
        subset = [p for p in resolved if float(p["ev"]) >= threshold]
        if not subset:
            continue
        won = sum(1 for p in subset if p["status"] == "won")
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE
            for p in subset
        )
        wagered = len(subset) * UNIT_SIZE
        results.append(
            {
"min_ev": threshold,
"n": len(subset),
"win_rate": round(won / len(subset) * 100, 1),
"profit": round(profit, 2),
"roi": round(profit / wagered * 100, 1) if wagered else 0,
            }
        )
    return results


def _team_breakdown(resolved: list) -> dict:
    teams = {}
    for p in resolved:
        pick = p["pick"]

        if pick.startswith("OVER") or pick.startswith("UNDER"):
            continue
        teams.setdefault(pick, {"n": 0, "won": 0})
        teams[pick]["n"] += 1
        if p["status"] == "won":
            teams[pick]["won"] += 1

    result = []
    for team, stats in teams.items():
        if stats["n"] >= 2:
            result.append(
                {
"team": team,
"n": stats["n"],
"won": stats["won"],
"win_rate": round(stats["won"] / stats["n"] * 100, 1),
                }
            )

    result.sort(key=lambda x: x["win_rate"], reverse=True)
    return {"best": result[:5], "worst": result[-5:] if len(result) >= 5 else []}


def _generate_recommendations(ml_stats, tot_stats, calibration, ev_analysis, overall_wr) -> list:
    recs = []

    for label, stats in (("Moneyline", ml_stats), ("Totals", tot_stats)):
        if stats["n"] == 0:
            continue
        positive = stats["roi_ci_low"] > 0
        negative = stats["roi_ci_high"] < 0
        observed = "positive" if stats["roi"] > 0 else "negative"
        recs.append(
            {
"type": "success" if positive else ("warning" if negative else "info"),
"title": f"{label}: {observed} observed return",
"detail": f'{stats["win_rate"]}% win rate, {stats["roi"]:+.1f}% ROI and '
                f'${stats["profit"]:+.2f} profit across {stats["n"]} resolved picks. '
                f'Approximate 95% ROI interval: {stats["roi_ci_low"]:+.1f}% to '
                f'{stats["roi_ci_high"]:+.1f}%; '
                + ("the interval excludes break-even." if positive or negative
                   else "the interval includes break-even, so this is not a profitability conclusion."),
            }
        )

    if ml_stats["n"] and tot_stats["n"]:
        roi_gap = ml_stats["roi"] - tot_stats["roi"]
        better = "Moneyline" if roi_gap >= 0 else "Totals"
        gap_se = math.sqrt(ml_stats["roi_se"] ** 2 + tot_stats["roi_se"] ** 2)
        gap_low = abs(roi_gap) - 1.96 * gap_se
        recs.append(
            {
"type": "success" if gap_low > 0 else "info",
"title": (f"{better} has a statistically separated observed return"
          if gap_low > 0 else "No reliable return difference between pick types"),
"detail": f'Moneyline ROI is {ml_stats["roi"]:+.1f}% versus '
                f'Totals ROI of {tot_stats["roi"]:+.1f}% '
                f"({abs(roi_gap):.1f} percentage-point observed gap). "
                + ("The approximate 95% interval for the gap excludes zero."
                   if gap_low > 0 else "The approximate 95% interval for the gap includes zero."),
            }
        )

    if not recs:
        recs.append(
            {
"type": "info",
"title": "Keep collecting data",
"detail": "There are no resolved picks yet, so no performance-based recommendation can be calculated.",
            }
        )

    return recs


def _build_calibration_corrections(calibration: list) -> dict:
    """Analytics buckets are descriptive and never produce production corrections."""
    return {}


def _save_calibration_corrections(corrections: dict):
    """Deprecated no-op retained for callers from older deployments."""
    return None


def _empty_analytics(pending: int) -> dict:
    return {
"summary": {
"total_picks": 0,
"won": 0,
"lost": 0,
"pending": pending,
"win_rate": 0,
"total_profit": 0,
"total_wagered": 0,
"roi": 0,
"streak": "-",
        },
"by_type": {"moneyline": {}, "totals": {}},
"calibration": [],
"pnl_over_time": [],
"ev_analysis": [],
"team_stats": {"best": [], "worst": []},
"recommendations": [
            {
"type": "info",
"title": "No resolved picks yet",
"detail": "Generate picks and update results to see analytics.",
            }
        ],
    }


def apply_calibration_correction(model_prob: float) -> float:
    """Deprecated compatibility shim; analytics never changes production probability."""
    return model_prob
