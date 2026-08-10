import sqlite3
import json
import sqlite3
from datetime import datetime
from pathlib import Path

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
    buckets = [
        (0.00, 0.45),
        (0.45, 0.50),
        (0.50, 0.525),
        (0.525, 0.55),
        (0.55, 0.575),
        (0.575, 0.60),
        (0.60, 0.65),
        (0.65, 0.70),
        (0.70, 0.75),
        (0.75, 1.00),
    ]
    curve = []
    for lo, hi in buckets:
        bucket_picks = [p for p in resolved if lo <= float(p["model_prob"]) < hi]
        if len(bucket_picks) >= 3:
            won = sum(1 for p in bucket_picks if p["status"] == "won")
            curve.append(
                {
"prob_range": f"{lo:.2f}-{hi:.2f}",
"prob_mid": round((lo + hi) / 2 * 100, 1),
"predicted": round((lo + hi) / 2 * 100, 1),
"actual": round(won / len(bucket_picks) * 100, 1),
"n": len(bucket_picks),
"won": won,
                }
            )
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
    thresholds = [0, 5, 10, 15, 20, 25, 30]
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
        profitable = stats["roi"] > 0
        enough_data = stats["n"] >= 30
        recs.append(
            {
"type": (
"success"
                    if profitable and enough_data
                    else ("warning" if not profitable else "info")
                ),
"title": f'{label}: {"profitable" if profitable else "underperforming"} on current results',
"detail": f'{stats["win_rate"]}% win rate, {stats["roi"]:+.1f}% ROI and '
                f'${stats["profit"]:+.2f} profit across {stats["n"]} resolved picks. '
                + (
"The sample is still small; treat this as directional."
                    if not enough_data
                    else "This recommendation uses the full current sample."
                ),
            }
        )

    if ml_stats["n"] and tot_stats["n"]:
        roi_gap = ml_stats["roi"] - tot_stats["roi"]
        better = "Moneyline" if roi_gap >= 0 else "Totals"
        recs.append(
            {
"type": "success" if abs(roi_gap) >= 10 else "info",
"title": f"{better} currently has the stronger return",
"detail": f'Moneyline ROI is {ml_stats["roi"]:+.1f}% versus '
                f'Totals ROI of {tot_stats["roi"]:+.1f}% '
                f"({abs(roi_gap):.1f} percentage-point gap).",
            }
        )

    for bucket in calibration:
        if bucket["n"] >= 5:
            gap = abs(bucket["actual"] - bucket["predicted"])
            if gap > 10 and bucket["predicted"] > 60:
                recs.append(
                    {
"type": "warning",
"title": f'Model overconfident at {bucket["prob_range"]} probability',
"detail": f'Model predicts {bucket["predicted"]}% but actual win rate is {bucket["actual"]}%. '
                        f'Correction is recalculated from all {bucket["n"]} picks in this bucket.',
                    }
                )

    eligible_ev = [row for row in ev_analysis if row["n"] >= 10]
    if eligible_ev:
        best = max(eligible_ev, key=lambda row: (row["roi"], row["n"]))
        baseline = next((row for row in ev_analysis if row["min_ev"] == 0), None)
        recs.append(
            {
"type": "success" if best["roi"] > 0 else "warning",
"title": f'Current data favors an EV floor of ≥{best["min_ev"]}%',
"detail": f'That filter produces {best["win_rate"]}% wins and '
                f'{best["roi"]:+.1f}% ROI across {best["n"]} picks.'
                + (f' The unfiltered sample is {baseline["roi"]:+.1f}% ROI.' if baseline else ""),
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

    corrections = {}
    for bucket in calibration:
        if bucket["n"] >= 5:
            predicted = bucket["predicted"] / 100
            actual = bucket["actual"] / 100
            if predicted > 0:
                corrections[bucket["prob_range"]] = {
"predicted": predicted,
"actual": actual,
"correction": round(actual / predicted, 4),
"n": bucket["n"],
                }
    return corrections


def _save_calibration_corrections(corrections: dict):

    Path("analytics").mkdir(exist_ok=True)
    with open("analytics/calibration_corrections.json", "w") as f:
        json.dump(
            {
"updated_at": datetime.now().isoformat(),
"corrections": corrections,
            },
            f,
            indent=2,
        )


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
    """
    Apply saved calibration correction to a raw model probability.
    Call this before using model_prob in EV calculation.
    """
    try:
        with open('analytics/calibration_corrections.json') as f:
            data = json.load(f)
        corrections = data.get('corrections', {})
    except Exception:
        return model_prob
    for bucket_range, corr in corrections.items():
        lo, hi = [float(x) for x in bucket_range.split("-")]
        if lo <= model_prob < hi:
            corrected = model_prob * corr['correction']
            return max(0.48, min(0.72, corrected))

    return model_prob
