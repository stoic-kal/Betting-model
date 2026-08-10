import math
import sqlite3
from collections import defaultdict

DB_PATH = "database/picks.db"
UNIT_SIZE = 20.0


VARIANTS = [
    {
        "id": "ultra_conservative",
        "name": "Ultra Conservative",
        "group": "Intensity",
        "desc": "EV≥20%, Prob≥60%, Edge≥3%. Fewest picks, highest bar.",
        "filters": {"min_ev": 20, "min_prob": 0.60, "min_edge": 3.0, "pick_types": ["moneyline"]},
    },
    {
        "id": "conservative",
        "name": "Conservative",
        "group": "Intensity",
        "desc": "EV≥15%, Prob≥57.5%, Edge≥2%.",
        "filters": {"min_ev": 15, "min_prob": 0.575, "min_edge": 2.0, "pick_types": ["moneyline"]},
    },
    {
        "id": "current_live",
        "name": "Live v3.1",
        "group": "Intensity",
        "desc": "Current live model: EV≥10%, Prob≥55.5%, Edge≥1.5%.",
        "filters": {"min_ev": 10, "min_prob": 0.555, "min_edge": 1.5, "pick_types": ["moneyline"]},
    },
    {
        "id": "moderate",
        "name": "Moderate",
        "group": "Intensity",
        "desc": "EV≥8%, Prob≥54%, Edge≥1%.",
        "filters": {"min_ev": 8, "min_prob": 0.54, "min_edge": 1.0, "pick_types": ["moneyline"]},
    },
    {
        "id": "aggressive",
        "name": "Aggressive",
        "group": "Intensity",
        "desc": "EV≥5%, Prob≥52%, Edge≥0.5%. High volume.",
        "filters": {"min_ev": 5, "min_prob": 0.52, "min_edge": 0.5, "pick_types": ["moneyline"]},
    },
    {
        "id": "all_positive_ev",
        "name": "All +EV",
        "group": "Intensity",
        "desc": "Every pick with EV>0. No other filters.",
        "filters": {
            "min_ev": 0.01,
            "min_prob": 0.50,
            "min_edge": 0.0,
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "ev_signal_only",
        "name": "EV Signal Only",
        "group": "Signal",
        "desc": "EV≥20% only. Tests if our EV calculation adds value alone.",
        "filters": {
            "min_ev": 20,
            "min_prob": 0.0,
            "min_edge": 0.0,
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "prob_signal_only",
        "name": "Prob Signal Only",
        "group": "Signal",
        "desc": "Prob≥60% only. Tests if model confidence adds value alone.",
        "filters": {
            "min_ev": 0.0,
            "min_prob": 0.60,
            "min_edge": 0.0,
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "edge_signal_only",
        "name": "Edge Signal Only",
        "group": "Signal",
        "desc": "Edge≥4% only. Tests if market disagreement adds value alone.",
        "filters": {
            "min_ev": 0.0,
            "min_prob": 0.0,
            "min_edge": 4.0,
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "kelly_signal_only",
        "name": "Kelly Signal Only",
        "group": "Signal",
        "desc": "Kelly≥0.15u. Tests if model sizing confidence predicts wins.",
        "filters": {
            "min_ev": 0.0,
            "min_prob": 0.0,
            "min_edge": 0.0,
            "min_kelly": 0.15,
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "favorites",
        "name": "Favorites Only",
        "group": "Odds Range",
        "desc": "Only picks priced < 1.91 (-110 or better). Tests edge in favorites.",
        "filters": {
            "min_ev": 10,
            "min_prob": 0.555,
            "min_edge": 1.5,
            "max_odds": 1.909,
            "pick_types": ["moneyline"],
        },
    },
    {
        "id": "dogs",
        "name": "Underdogs Only",
        "group": "Odds Range",
        "desc": "Only picks priced > 2.10 (+110). Tests edge in underdogs.",
        "filters": {
            "min_ev": 10,
            "min_prob": 0.555,
            "min_edge": 1.5,
            "min_odds": 2.10,
            "pick_types": ["moneyline"],
        },
    },
    {
        "id": "close_lines",
        "name": "Close Lines",
        "group": "Odds Range",
        "desc": "Odds 1.85–2.15 (pick'em games). Tests near-50/50 edge.",
        "filters": {
            "min_ev": 10,
            "min_prob": 0.555,
            "min_edge": 1.5,
            "min_odds": 1.85,
            "max_odds": 2.15,
            "pick_types": ["moneyline"],
        },
    },
    {
        "id": "v3_only",
        "name": "🆕 v3 Picks Only",
        "group": "Version",
        "desc": "Only picks from model v3 (real per-game features). Small sample.",
        "filters": {
            "min_ev": 0,
            "min_prob": 0.0,
            "min_edge": 0.0,
            "model_versions": ["v3"],
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "v3_filtered",
        "name": "🆕 v3 + Live Filters",
        "group": "Version",
        "desc": "v3 picks with current live filters applied.",
        "filters": {
            "min_ev": 10,
            "min_prob": 0.555,
            "min_edge": 1.5,
            "model_versions": ["v3"],
            "pick_types": ["moneyline"],
        },
    },
    {
        "id": "v2_only",
        "name": "v2 Picks Only",
        "group": "Version",
        "desc": "Only picks from model v2. Comparison baseline.",
        "filters": {
            "min_ev": 0,
            "min_prob": 0.0,
            "min_edge": 0.0,
            "model_versions": ["v2"],
            "pick_types": ["moneyline", "totals"],
        },
    },
    {
        "id": "ml_only",
        "name": "ML Only (no filter)",
        "group": "Type",
        "desc": "All moneyline picks, no filters. True model baseline.",
        "filters": {"min_ev": 0, "min_prob": 0.0, "min_edge": 0.0, "pick_types": ["moneyline"]},
    },
    {
        "id": "totals_only",
        "name": "Totals Only",
        "group": "Type",
        "desc": "All totals picks, no filters. Shows raw totals model performance.",
        "filters": {"min_ev": 0, "min_prob": 0.0, "min_edge": 0.0, "pick_types": ["totals"]},
    },
]


def _load_all_resolved() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM picks WHERE status IN ('won','lost') ORDER BY date ASC, id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def apply_filters(picks: list, filters: dict) -> list:
    result = []
    for p in picks:
        ev = float(p.get("ev") or 0)
        prob = float(p.get("model_prob") or 0)
        odds = float(p.get("odds") or 1)
        kelly = float(p.get("kelly_units") or 0)
        ptype = p.get("pick_type", "")
        version = p.get("model_version", "")

        mkt_prob = 1 / odds if odds > 1 else 0.5
        edge_pp = (prob - mkt_prob) * 100

        if filters.get("pick_types") and ptype not in filters["pick_types"]:
            continue
        if filters.get("model_versions") and version not in filters["model_versions"]:
            continue
        if ev < filters.get("min_ev", 0):
            continue
        if prob < filters.get("min_prob", 0):
            continue
        if edge_pp < filters.get("min_edge", 0):
            continue
        if kelly < filters.get("min_kelly", 0):
            continue
        if "min_odds" in filters and odds < filters["min_odds"]:
            continue
        if "max_odds" in filters and odds > filters["max_odds"]:
            continue

        result.append({**p, "_edge_pp": round(edge_pp, 2)})
    return result


def _wilson_ci(wins, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p_hat = wins / n
    d = 1 + z**2 / n
    c = (p_hat + z**2 / (2 * n)) / d
    m = (z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))) / d
    return round(max(0, c - m) * 100, 1), round(min(1, c + m) * 100, 1)


def _p_value(wins, n, null_p=0.5238):
    if n == 0:
        return 1.0
    mu = n * null_p
    sigma = math.sqrt(n * null_p * (1 - null_p))
    if sigma == 0:
        return 1.0
    z = (wins - 0.5 - mu) / sigma
    return round(0.5 * math.erfc(z / math.sqrt(2)), 4)


def _brier(picks):
    if not picks:
        return None
    return round(
        sum((float(p["model_prob"]) - (1 if p["status"] == "won" else 0)) ** 2 for p in picks)
        / len(picks),
        4,
    )


def _ece(picks):
    if not picks:
        return None
    buckets = [(0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.0)]
    total_n = len(picks)
    ece = 0.0
    for lo, hi in buckets:
        sub = [p for p in picks if lo <= float(p["model_prob"]) < hi]
        if not sub:
            continue
        pred = (lo + hi) / 2
        act = sum(1 for p in sub if p["status"] == "won") / len(sub)
        ece += len(sub) / total_n * abs(pred - act)
    return round(ece * 100, 2)


def _max_drawdown(pnl_series):

    if not pnl_series:
        return 0.0
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnl_series:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)


def _profit_factor(wins_pnl, losses_pnl):

    gross_win = sum(w for w in wins_pnl if w > 0)
    gross_loss = abs(sum(l for l in losses_pnl if l < 0))
    if gross_loss == 0:
        return None
    return round(gross_win / gross_loss, 3)


def _sharpe(daily_pnl):

    if len(daily_pnl) < 3:
        return None
    mu = sum(daily_pnl) / len(daily_pnl)
    var = sum((x - mu) ** 2 for x in daily_pnl) / (len(daily_pnl) - 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return round(mu / std * math.sqrt(162), 3)


def _streaks(picks):

    if not picks:
        return 0, 0
    max_w = max_l = cur_w = cur_l = 0
    for p in picks:
        if p["status"] == "won":
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_w = max(max_w, cur_w)
        max_l = max(max_l, cur_l)
    return max_w, max_l


def compute_metrics(picks: list) -> dict:

    if not picks:
        return _empty_metrics()

    n = len(picks)
    won = sum(1 for p in picks if p["status"] == "won")
    lost = n - won
    wr = won / n

    avg_odds = sum(float(p["odds"]) for p in picks) / n
    be = 1 / avg_odds if avg_odds > 1 else 0.5238

    flat_pnl = []
    flat_profit = 0.0
    for p in picks:
        o = float(p["odds"])
        if p["status"] == "won":
            g = (o - 1) * UNIT_SIZE
            flat_profit += g
            flat_pnl.append(g)
        else:
            flat_profit -= UNIT_SIZE
            flat_pnl.append(-UNIT_SIZE)
    flat_wagered = n * UNIT_SIZE
    flat_roi = flat_profit / flat_wagered * 100

    kelly_pnl = []
    kelly_profit = 0.0
    kelly_wagered = 0.0
    for p in picks:
        stored_ku = p.get("kelly_units")
        ku = float(stored_ku) if stored_ku is not None else 0.5
        o = float(p["odds"])
        kelly_wagered += ku * UNIT_SIZE
        if p["status"] == "won":
            g = (o - 1) * ku * UNIT_SIZE
            kelly_profit += g
            kelly_pnl.append(g)
        else:
            kelly_profit -= ku * UNIT_SIZE
            kelly_pnl.append(-ku * UNIT_SIZE)
    kelly_roi = kelly_profit / kelly_wagered * 100 if kelly_wagered else 0

    by_date = defaultdict(float)
    for i, p in enumerate(picks):
        by_date[p["date"]] += flat_pnl[i]
    daily_pnl = list(by_date.values())

    ci_lo, ci_hi = _wilson_ci(won, n)
    pval = _p_value(won, n, null_p=be)
    brier = _brier(picks)
    ece = _ece(picks)
    max_dd = _max_drawdown(flat_pnl)
    pf = _profit_factor(flat_pnl, flat_pnl)
    sharpe = _sharpe(daily_pnl)
    max_w, max_l = _streaks(picks)

    avg_kelly = sum(float(p.get("kelly_units") or 0) for p in picks) / n
    avg_ev = sum(float(p.get("ev") or 0) for p in picks) / n
    avg_edge = sum(p.get("_edge_pp", 0) for p in picks) / n

    return {
        "n": n,
        "won": won,
        "lost": lost,
        "win_rate": round(wr * 100, 1),
        "break_even": round(be * 100, 1),
        "edge": round((wr - be) * 100, 1),
        "flat_profit": round(flat_profit, 2),
        "flat_roi": round(flat_roi, 1),
        "kelly_profit": round(kelly_profit, 2),
        "kelly_roi": round(kelly_roi, 1),
        "p_value": pval,
        "p_value_pct": round(pval * 100, 1),
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "ci_width": round(ci_hi - ci_lo, 1),
        "brier_score": brier,
        "ece": ece,
        "max_drawdown": max_dd,
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
        "win_streak": max_w,
        "loss_streak": max_l,
        "avg_kelly": round(avg_kelly, 3),
        "avg_ev": round(avg_ev, 1),
        "avg_odds": round(avg_odds, 3),
        "avg_model_edge": round(avg_edge, 1),
        "roi_per_pick": round(flat_roi / n if n else 0, 3),
    }


def _empty_metrics():
    return {
        k: None
        for k in [
            "n",
            "won",
            "lost",
            "win_rate",
            "break_even",
            "edge",
            "flat_profit",
            "flat_roi",
            "kelly_profit",
            "kelly_roi",
            "p_value",
            "p_value_pct",
            "ci_lo",
            "ci_hi",
            "ci_width",
            "brier_score",
            "ece",
            "max_drawdown",
            "profit_factor",
            "sharpe_ratio",
            "win_streak",
            "loss_streak",
            "avg_kelly",
            "avg_ev",
            "avg_odds",
            "avg_model_edge",
            "roi_per_pick",
        ]
    } | {"n": 0}


SCORE_WEIGHTS = {
    "edge": (+5, "higher"),
    "flat_roi": (+4, "higher"),
    "kelly_roi": (+3, "higher"),
    "p_value": (-3, "lower"),
    "brier_score": (-2, "lower"),
    "ece": (-2, "lower"),
    "sharpe_ratio": (+3, "higher"),
    "max_drawdown": (-2, "lower"),
    "profit_factor": (+2, "higher"),
    "roi_per_pick": (+2, "higher"),
}


def _composite_score(results: list) -> list:

    metric_names = list(SCORE_WEIGHTS.keys())
    n_models = len(results)
    if n_models == 0:
        return results

    for metric, (weight, direction) in SCORE_WEIGHTS.items():
        vals = [
            (i, r["metrics"].get(metric))
            for i, r in enumerate(results)
            if r["metrics"].get(metric) is not None and r["metrics"]["n"] > 0
        ]
        if len(vals) < 2:
            continue

        reverse = direction == "higher"
        sorted_vals = sorted(vals, key=lambda x: x[1], reverse=reverse)
        for rank, (idx, _) in enumerate(sorted_vals):

            pts = (n_models - rank) * abs(weight)
            results[idx].setdefault("_raw_score", 0)
            results[idx]["_raw_score"] += pts

    max_score = max((r.get("_raw_score", 0) for r in results), default=1)
    min_score = min((r.get("_raw_score", 0) for r in results), default=0)
    rng = max_score - min_score or 1
    for r in results:
        raw = r.get("_raw_score", 0)
        r["composite_score"] = round((raw - min_score) / rng * 100, 1)

    return results


def run_model_lab() -> dict:

    all_picks = _load_all_resolved()
    results = []

    for variant in VARIANTS:
        filtered = apply_filters(all_picks, variant["filters"])
        metrics = compute_metrics(filtered)
        results.append(
            {
                "id": variant["id"],
                "name": variant["name"],
                "group": variant["group"],
                "desc": variant["desc"],
                "filters": variant["filters"],
                "metrics": metrics,
            }
        )

    results = _composite_score(results)

    results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

    metric_winners = {}
    all_metrics = [
        "edge",
        "flat_roi",
        "kelly_roi",
        "p_value",
        "brier_score",
        "ece",
        "sharpe_ratio",
        "max_drawdown",
        "profit_factor",
        "roi_per_pick",
        "win_rate",
        "win_streak",
    ]
    for metric in all_metrics:
        direction = SCORE_WEIGHTS.get(metric, (1, "higher"))[1]
        candidates = [
            (r["id"], r["metrics"].get(metric))
            for r in results
            if r["metrics"].get(metric) is not None and r["metrics"]["n"] > 0
        ]
        if candidates:
            best = max(candidates, key=lambda x: x[1] if direction == "higher" else -x[1])
            metric_winners[metric] = best[0]

    return {
        "variants": results,
        "total_picks": len(all_picks),
        "metric_winners": metric_winners,
        "n_variants": len(results),
    }
