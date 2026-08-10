import math
import sqlite3
from datetime import datetime

from config import today_et

DB_PATH = "database/picks.db"
UNIT_SIZE = 20.0


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _load_resolved(pick_type: str = None, model_version: str = None) -> list:
    conn = _conn()
    q = "SELECT * FROM picks WHERE status IN ('won','lost') ORDER BY date ASC, id ASC"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    conn.close()
    if pick_type:
        rows = [r for r in rows if r["pick_type"] == pick_type]
    if model_version:
        rows = [r for r in rows if r["model_version"] == model_version]
    return rows


def _load_pending() -> list:
    conn = _conn()
    rows = [
        dict(r)
        for r in conn.execute(
"SELECT * FROM picks WHERE status='pending' ORDER BY date DESC, id DESC"
        ).fetchall()
    ]
    conn.close()
    return rows


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple:

    if n == 0:
        return (0.0, 1.0)
    p_hat = wins / n
    denom = 1 + z**2 / n
    centre = (p_hat + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))) / denom
    return (max(0, centre - margin), min(1, centre + margin))


def _binomial_p_value(wins: int, n: int, null_p: float = 0.5238) -> float:

    if n == 0:
        return 1.0
    mu = n * null_p
    sigma = math.sqrt(n * null_p * (1 - null_p))
    if sigma == 0:
        return 1.0
    z = (wins - 0.5 - mu) / sigma

    p = 0.5 * math.erfc(z / math.sqrt(2))
    return round(p, 4)


def _break_even_rate(avg_odds_decimal: float) -> float:

    if avg_odds_decimal <= 1:
        return 0.5238
    return 1.0 / avg_odds_decimal


def significance_analysis(picks: list) -> dict:

    if not picks:
        return {
"n": 0,
"wins": 0,
"win_rate": 0,
"edge": 0,
"p_value": 1.0,
"significant": False,
"ci_lo": 0,
"ci_hi": 0,
"break_even": 52.38,
        }

    n = len(picks)
    wins = sum(1 for p in picks if p["status"] == "won")
    wr = wins / n

    avg_odds = sum(float(p["odds"]) for p in picks) / n
    be = _break_even_rate(avg_odds)
    edge = wr - be

    ci_lo, ci_hi = _wilson_ci(wins, n)
    p_val = _binomial_p_value(wins, n, null_p=be)

    significant = p_val < 0.10

    avg_kelly_optimal = max(0, edge / (avg_odds - 1)) if avg_odds > 1 else 0

    return {
"n": n,
"wins": wins,
"losses": n - wins,
"win_rate": round(wr * 100, 1),
"break_even": round(be * 100, 1),
"edge": round(edge * 100, 1),
"p_value": p_val,
"p_value_pct": round(p_val * 100, 1),
"significant": significant,
"ci_lo": round(ci_lo * 100, 1),
"ci_hi": round(ci_hi * 100, 1),
"avg_odds": round(avg_odds, 3),
"avg_kelly_optimal": round(avg_kelly_optimal * 100, 1),
"confidence_label": _confidence_label(p_val, n),
    }


def _confidence_label(p: float, n: int) -> str:
    if n < 20:
        return "INSUFFICIENT DATA"
    if p < 0.01:
        return "VERY HIGH (p<1%)"
    if p < 0.05:
        return "HIGH (p<5%)"
    if p < 0.10:
        return "MODERATE (p<10%)"
    if p < 0.20:
        return "WEAK (p<20%)"
    return "NOT SIGNIFICANT"


def _brier_score(picks: list) -> float:

    if not picks:
        return None
    total = sum((float(p["model_prob"]) - (1 if p["status"] == "won" else 0)) ** 2 for p in picks)
    return round(total / len(picks), 4)


def _log_loss(picks: list) -> float:

    if not picks:
        return None
    eps = 1e-9
    total = 0.0
    for p in picks:
        prob = max(eps, min(1 - eps, float(p["model_prob"])))
        outcome = 1 if p["status"] == "won" else 0
        total += -(outcome * math.log(prob) + (1 - outcome) * math.log(1 - prob))
    return round(total / len(picks), 4)


def _ece(calibration_curve: list) -> float:

    if not calibration_curve:
        return None
    total_n = sum(b["n"] for b in calibration_curve)
    if total_n == 0:
        return None
    ece = sum(b["n"] / total_n * abs(b["predicted"] - b["actual"]) / 100 for b in calibration_curve)
    return round(ece, 4)


def _standard_ece(picks: list, bins: int = 5) -> float:

    if not picks:
        return None
    total = len(picks)
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [
            p
            for p in picks
            if low <= float(p["model_prob"]) < high
            or (index == bins - 1 and float(p["model_prob"]) == 1.0)
        ]
        if bucket:
            predicted = sum(float(p["model_prob"]) for p in bucket) / len(bucket)
            actual = sum(p["status"] == "won" for p in bucket) / len(bucket)
            error += len(bucket) / total * abs(predicted - actual)
    return round(error, 4)


def calibration_analysis(picks: list) -> dict:

    brier = _brier_score(picks)
    ll = _log_loss(picks)

    bucket_edges = [0.45, 0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65, 0.70, 0.75, 1.0]
    curve = []
    for i in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[i], bucket_edges[i + 1]
        sub = [p for p in picks if lo <= float(p["model_prob"]) < hi]
        if sub:
            won = sum(1 for p in sub if p["status"] == "won")

            predicted = round(sum(float(p["model_prob"]) for p in sub) / len(sub) * 100, 1)
            actual = round(won / len(sub) * 100, 1)
            gap = actual - predicted
            curve.append(
                {
"range": f"{lo:.3f}–{hi:.3f}",
"label": f"{lo*100:.1f}–{hi*100:.1f}%",
"predicted": predicted,
"actual": actual,
"gap": round(gap, 1),
"n": len(sub),
"won": won,
"reliable": len(sub) >= 5,
                }
            )

    ece = _standard_ece(picks, bins=5)

    return {
"brier_score": brier,
"brier_skill": round(1 - brier / 0.25, 3) if brier else None,
"log_loss": ll,
"ece": ece,
"ece_pct": round(ece * 100, 1) if ece else None,
"curve": curve,
"sample_size": len(picks),
"provisional": len(picks) < 50,
"ece_bins": 5,
"verdict": _calibration_verdict(ece, brier),
    }


def _calibration_verdict(ece, brier) -> dict:
    if ece is None:
        return {"grade": "?", "label": "Insufficient data", "color": "#888"}
    if ece < 0.03:
        return {"grade": "A", "label": "Well calibrated", "color": "#00c851"}
    if ece < 0.06:
        return {"grade": "B", "label": "Slightly off", "color": "#ffbb33"}
    if ece < 0.10:
        return {"grade": "C", "label": "Overconfident", "color": "#ff8800"}
    return {"grade": "D", "label": "Badly miscalibrated", "color": "#ff4444"}


def _spearman_correlation(x: list, y: list) -> float:

    if len(x) < 5:
        return None
    n = len(x)

    def _ranks(lst):
        sorted_idx = sorted(range(n), key=lambda i: lst[i])
        ranks = [0] * n
        for rank, idx in enumerate(sorted_idx):
            ranks[idx] = rank + 1
        return ranks

    rx = _ranks(x)
    ry = _ranks(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    rho = 1 - 6 * d2 / (n * (n**2 - 1))
    return round(rho, 4)


def ev_signal_analysis(picks: list) -> dict:

    if len(picks) < 10:
        return {"rho": None, "verdict": "Need ≥10 picks", "buckets": []}

    evs = [float(p["ev"]) for p in picks]
    outcomes = [1 if p["status"] == "won" else 0 for p in picks]
    rho = _spearman_correlation(evs, outcomes)

    bucket_defs = [
        ("< 0%", None, 0),
        ("0–10%", 0, 10),
        ("10–20%", 10, 20),
        ("20–30%", 20, 30),
        ("30–50%", 30, 50),
        ("50%+", 50, 9999),
    ]
    buckets = []
    for label, lo, hi in bucket_defs:
        if lo is None:
            sub = [p for p in picks if float(p["ev"]) < hi]
        elif hi == 9999:
            sub = [p for p in picks if float(p["ev"]) >= lo]
        else:
            sub = [p for p in picks if lo <= float(p["ev"]) < hi]
        if sub:
            won = sum(1 for p in sub if p["status"] == "won")
            avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
            be = _break_even_rate(avg_odds)
            profit = sum(
                (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE
                for p in sub
            )
            buckets.append(
                {
"label": label,
"n": len(sub),
"wins": won,
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / len(sub) - be) * 100, 1),
"profit": round(profit, 2),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
                }
            )

    return {
"rho": rho,
"rho_pct": round(rho * 100, 1) if rho else None,
"verdict": _ev_verdict(rho),
"buckets": buckets,
    }


def _ev_verdict(rho) -> str:
    if rho is None:
        return "Need more data"
    if rho > 0.20:
        return "Strong positive signal — EV predicts outcomes"
    if rho > 0.05:
        return "Weak positive signal — EV partially predictive"
    if rho > -0.05:
        return "No signal — EV is not predicting outcomes"
    return "Negative signal — high EV picks are LOSING more"


def odds_analysis(picks: list) -> list:

    ranges = [
        ("Heavy Fav  (<-200)", 1.01, 1.50),
        ("Solid Fav  (-200 to -120)", 1.50, 1.83),
        ("Slight Fav  (-120 to -105)", 1.83, 1.95),
        ("Pick'em  (-105 to +105)", 1.95, 2.05),
        ("Slight Dog  (+105 to +150)", 2.05, 2.50),
        ("Big Dog  (+150 to +250)", 2.50, 3.50),
        ("Longshot  (>+250)", 3.50, 99.0),
    ]
    result = []
    for label, lo, hi in ranges:
        sub = [p for p in picks if lo <= float(p["odds"]) < hi]
        if not sub:
            continue
        won = sum(1 for p in sub if p["status"] == "won")
        avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
        be = _break_even_rate(avg_odds)
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE for p in sub
        )
        result.append(
            {
"label": label,
"n": len(sub),
"wins": won,
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / len(sub) - be) * 100, 1),
"profit": round(profit, 2),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
"avg_odds": round(avg_odds, 3),
            }
        )
    return result


def kelly_efficiency(picks: list) -> dict:

    if not picks:
        return {"buckets": [], "flat_roi": 0, "kelly_roi": 0, "efficiency": 0}

    kb = [
        ("0 units (filtered)", 0.00, 0.001),
        ("0.25u", 0.249, 0.251),
        ("0.50u", 0.499, 0.501),
        ("1.00u", 0.999, 1.001),
    ]
    buckets = []
    for label, lo, hi in kb:
        sub = [p for p in picks if lo <= float(p.get("kelly_units") or 0) < hi]
        if not sub:
            continue
        won = sum(1 for p in sub if p["status"] == "won")
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE for p in sub
        )
        avg_k = sum(float(p.get("kelly_units") or 0) for p in sub) / len(sub)
        avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
        be = _break_even_rate(avg_odds)
        buckets.append(
            {
"label": label,
"n": len(sub),
"wins": won,
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / len(sub) - be) * 100, 1),
"avg_kelly": round(avg_k, 3),
"profit": round(profit, 2),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
            }
        )

    flat_profit = 0.0
    kelly_profit = 0.0
    kelly_wagered = 0.0
    for p in picks:
        stored_ku = p.get("kelly_units")
        ku = float(stored_ku) if stored_ku is not None else 0.5
        kelly_wagered += ku * UNIT_SIZE
        if p["status"] == "won":
            flat_profit += (float(p["odds"]) - 1) * UNIT_SIZE
            kelly_profit += (float(p["odds"]) - 1) * ku * UNIT_SIZE
        else:
            flat_profit -= UNIT_SIZE
            kelly_profit -= ku * UNIT_SIZE

    flat_wagered = len(picks) * UNIT_SIZE
    flat_roi = round(flat_profit / flat_wagered * 100, 1) if flat_wagered else 0
    kelly_roi = round(kelly_profit / kelly_wagered * 100, 1) if kelly_wagered else 0

    return {
"buckets": buckets,
"flat_profit": round(flat_profit, 2),
"kelly_profit": round(kelly_profit, 2),
"flat_roi": flat_roi,
"kelly_roi": kelly_roi,
"efficiency": round(kelly_roi - flat_roi, 1),
"verdict": (
"Kelly outperforming flat" if kelly_roi > flat_roi else "Flat outperforming Kelly"
        ),
    }


def rolling_performance(picks: list, window: int = 10) -> list:

    if len(picks) < window:
        return []

    result = []
    for i in range(window - 1, len(picks)):
        chunk = picks[i - window + 1 : i + 1]
        won = sum(1 for p in chunk if p["status"] == "won")
        avg_odds = sum(float(p["odds"]) for p in chunk) / len(chunk)
        be = _break_even_rate(avg_odds)
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE
            for p in chunk
        )
        result.append(
            {
"pick_idx": i + 1,
"date": picks[i]["date"],
"win_rate": round(won / window * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / window - be) * 100, 1),
"cum_profit": round(profit, 2),
            }
        )
    return result


def totals_deep_dive(picks: list) -> dict:

    overs = [p for p in picks if p["pick"].startswith("OVER")]
    unders = [p for p in picks if p["pick"].startswith("UNDER")]

    def _stats(sub, label):
        if not sub:
            return {"label": label, "n": 0, "win_rate": 0, "roi": 0}
        won = sum(1 for p in sub if p["status"] == "won")
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE for p in sub
        )
        avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
        avg_line = None
        lines = []
        for p in sub:
            try:
                parts = p["pick"].split()
                if len(parts) >= 2:
                    lines.append(float(parts[1]))
            except Exception:
                pass
        if lines:
            avg_line = round(sum(lines) / len(lines), 1)
        return {
"label": label,
"n": len(sub),
"wins": won,
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(_break_even_rate(avg_odds) * 100, 1),
"edge": round((won / len(sub) - _break_even_rate(avg_odds)) * 100, 1),
"profit": round(profit, 2),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
"avg_line": avg_line,
"avg_ev": round(sum(float(p["ev"]) for p in sub) / len(sub), 1),
        }

    return {
"over": _stats(overs, "OVER"),
"under": _stats(unders, "UNDER"),
"imbalance": len(overs) - len(unders),
"verdict": _totals_verdict(
            _stats(overs, "OVER"),
            _stats(unders, "UNDER"),
        ),
    }


def _totals_verdict(over_s, under_s) -> str:
    if over_s["n"] == 0 and under_s["n"] == 0:
        return "No totals picks"
    if over_s["n"] == 0:
        return "Only UNDER picks taken"
    if under_s["n"] == 0:
        return "Only OVER picks taken"
    if over_s["win_rate"] > 55 and under_s["win_rate"] < 45:
        return "Model is directionally biased toward OVERs — investigate"
    if under_s["win_rate"] > 55 and over_s["win_rate"] < 45:
        return "Model is directionally biased toward UNDERs — investigate"
    if over_s["win_rate"] > 55 and under_s["win_rate"] > 55:
        return "Both sides profitable — rare, keep going"
    if over_s["win_rate"] < 45 and under_s["win_rate"] < 45:
        return "Both sides losing — Poisson expected runs needs recalibration"
    return "Mixed performance"


LIVE_BETAS = {
"fip": 0.22,
"rsg": 0.18,
"form": 0.35,
"bp": 0.15,
"wpct": 0.28,
"shrink": 0.45,
}


def sandbox_simulate(picks: list, beta_overrides: dict = None) -> dict:

    betas = {**LIVE_BETAS, **(beta_overrides or {})}

    ev_sweep = []
    for threshold in [0, 5, 8, 10, 12, 15, 18, 20, 25, 30]:
        sub = [p for p in picks if float(p["ev"]) >= threshold]
        if not sub:
            continue
        won = sum(1 for p in sub if p["status"] == "won")
        avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
        be = _break_even_rate(avg_odds)
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE for p in sub
        )
        ev_sweep.append(
            {
"min_ev": threshold,
"n": len(sub),
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / len(sub) - be) * 100, 1),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
"profit": round(profit, 2),
            }
        )

    prob_sweep = []
    for threshold in [0.50, 0.52, 0.54, 0.55, 0.56, 0.57, 0.58, 0.60, 0.62, 0.65]:
        sub = [p for p in picks if float(p["model_prob"]) >= threshold]
        if not sub:
            continue
        won = sum(1 for p in sub if p["status"] == "won")
        avg_odds = sum(float(p["odds"]) for p in sub) / len(sub)
        be = _break_even_rate(avg_odds)
        profit = sum(
            (float(p["odds"]) - 1) * UNIT_SIZE if p["status"] == "won" else -UNIT_SIZE for p in sub
        )
        prob_sweep.append(
            {
"min_prob": round(threshold * 100, 1),
"n": len(sub),
"win_rate": round(won / len(sub) * 100, 1),
"break_even": round(be * 100, 1),
"edge": round((won / len(sub) - be) * 100, 1),
"roi": round(profit / (len(sub) * UNIT_SIZE) * 100, 1),
"profit": round(profit, 2),
            }
        )

    best_ev_roi = max(ev_sweep, key=lambda x: x["roi"]) if ev_sweep else None
    best_prob_roi = max(prob_sweep, key=lambda x: x["roi"]) if prob_sweep else None

    return {
"live_betas": betas,
"ev_sweep": ev_sweep,
"prob_sweep": prob_sweep,
"best_ev_filter": best_ev_roi,
"best_prob_filter": best_prob_roi,
    }


def get_full_analytics_v2(model_version: str = None) -> dict:

    all_resolved = _load_resolved(model_version=model_version)
    ml_picks = [p for p in all_resolved if p["pick_type"] == "moneyline"]
    tot_picks = [p for p in all_resolved if p["pick_type"] == "totals"]
    pending = _load_pending()

    overall_sig = significance_analysis(all_resolved)
    overall_cal = calibration_analysis(all_resolved)
    overall_ev = ev_signal_analysis(all_resolved)
    overall_odds = odds_analysis(all_resolved)
    overall_roll = rolling_performance(all_resolved, window=min(10, len(all_resolved)))
    overall_kelly = kelly_efficiency(all_resolved)

    ml_sig = significance_analysis(ml_picks)
    ml_cal = calibration_analysis(ml_picks)
    ml_ev = ev_signal_analysis(ml_picks)
    ml_odds = odds_analysis(ml_picks)
    ml_kelly = kelly_efficiency(ml_picks)
    ml_roll = rolling_performance(ml_picks, window=min(10, len(ml_picks)))

    tot_sig = significance_analysis(tot_picks)
    tot_cal = calibration_analysis(tot_picks)
    tot_ev = ev_signal_analysis(tot_picks)
    tot_deep = totals_deep_dive(tot_picks)
    tot_kelly = kelly_efficiency(tot_picks)
    tier_rows = []
    for tier, label in [
        ("daily_forecast", "Daily forecast / no bet"),
        ("qualified_pick", "Qualified pick"),
        ("strong_lock", "Strong lock"),
    ]:
        subset = [p for p in tot_picks if p.get("recommendation_tier") == tier]
        resolved_tier = [p for p in subset if p.get("status") in ("won", "lost")]
        wins_tier = sum(p["status"] == "won" for p in resolved_tier)
        profit_units = sum(
            (float(p.get("odds") or 1) - 1) if p["status"] == "won" else -1 for p in resolved_tier
        )
        tier_rows.append(
            {
"tier": tier,
"label": label,
"n": len(resolved_tier),
"wins": wins_tier,
"losses": len(resolved_tier) - wins_tier,
"win_rate": (
                    round(wins_tier / len(resolved_tier) * 100, 1) if resolved_tier else None
                ),
"flat_units": round(profit_units, 2),
            }
        )

    sandbox = sandbox_simulate(all_resolved)
    ml_sandbox = sandbox_simulate(ml_picks)

    pending_today = [p for p in pending if p["date"] == today_et()]

    return {
"generated_at": datetime.now().isoformat(),
"sample_size": {
"total": len(all_resolved),
"ml": len(ml_picks),
"totals": len(tot_picks),
"pending": len(pending),
        },
"overall": {
"significance": overall_sig,
"calibration": overall_cal,
"ev_signal": overall_ev,
"odds": overall_odds,
"rolling": overall_roll,
"kelly": overall_kelly,
        },
"moneyline": {
"significance": ml_sig,
"calibration": ml_cal,
"ev_signal": ml_ev,
"odds": ml_odds,
"kelly": ml_kelly,
"rolling": ml_roll,
        },
"totals": {
"significance": tot_sig,
"calibration": tot_cal,
"ev_signal": tot_ev,
"deep_dive": tot_deep,
"kelly": tot_kelly,
"recommendation_tiers": tier_rows,
        },
"sandbox": sandbox,
"ml_sandbox": ml_sandbox,
"pending_today": pending_today,
    }
