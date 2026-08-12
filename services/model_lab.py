import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

from pipeline import model_registry, shadow_report
from pipeline.calibration_common import brier_score, expected_calibration_error, wilson_interval

DB_PATH = "database/picks.db"
UNIT_SIZE = 20.0
DIAGNOSTICS_DIR = Path("reports/training")


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


def _p_value(wins, n, null_p=0.5238):
    if n == 0:
        return 1.0
    mu = n * null_p
    sigma = math.sqrt(n * null_p * (1 - null_p))
    if sigma == 0:
        return 1.0
    z = (wins - 0.5 - mu) / sigma
    return round(0.5 * math.erfc(z / math.sqrt(2)), 4)


def _pick_probs_outcomes(picks):
    return (
        [float(p["model_prob"]) for p in picks],
        [1 if p["status"] == "won" else 0 for p in picks],
    )


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

    ci_low, ci_high = wilson_interval(won, n)
    ci_lo, ci_hi = round(ci_low * 100, 1), round(ci_high * 100, 1)
    pval = _p_value(won, n, null_p=be)
    probs, outcomes = _pick_probs_outcomes(picks)
    brier = round(brier_score(outcomes, probs), 4)
    ece = round(expected_calibration_error(outcomes, probs) * 100, 2)
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
        "candidates": get_all_candidates(),
    }


def _hash_hyperparameters(hyperparameters):
    if not hyperparameters:
        return "none"
    encoded = json.dumps(hyperparameters, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:10]


def _diagnostics_dir(model_name, version):
    return DIAGNOSTICS_DIR / f"{model_name}_{version}"


def _candidate_dict(model_name, version, meta, status):
    extra = meta.get("extra") or {}
    metrics = meta.get("metrics") or {}
    identity = model_registry.model_identity(meta)
    diag_dir = _diagnostics_dir(model_name, version)
    pick_type = "moneyline" if model_name.startswith("moneyline") else "totals"
    return {
        "id": f"{model_name}::{version}",
        "model_name": model_name,
        "version": version,
        "name": f"{model_name} · {identity['model_family']} · {version}",
        "model_family": identity["model_family"],
        "pick_type": pick_type,
        "status": status,
        "training_date": meta.get("trained_at"),
        "dataset_version": identity["dataset_version"],
        "feature_schema_version": identity["feature_schema_version"],
        "calibration_version": identity["calibration_version"],
        "prediction_pipeline_version": identity["prediction_pipeline_version"],
        "feature_count": len(meta.get("feature_list") or []),
        "training_sample_size": extra.get("training_sample_size"),
        "hyperparameter_version": _hash_hyperparameters(meta.get("hyperparameters")),
        "tuning_status": extra.get("tuning_status", "unknown"),
        "walk_forward_score": extra.get("walk_forward_best_log_loss"),
        "auc": metrics.get("auc"),
        "log_loss": metrics.get("log_loss"),
        "brier": metrics.get("brier"),
        "ece": metrics.get("ece"),
        "calibration_score": metrics.get("ece"),
        "n": metrics.get("n"),
        "shadow_status": False,
        "production_status": False,
        "has_diagnostics": diag_dir.exists(),
        "git_commit": meta.get("git_commit"),
    }


def _list_registry_model_names():
    root = model_registry.REGISTRY_DIR
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def get_registry_candidates():
    candidates = []
    for name in _list_registry_model_names():
        versions = model_registry.list_versions(name)
        is_primary = name in ("moneyline", "totals")
        champion_version = model_registry.get_champion_version(name) if is_primary else None
        champion_metrics = None
        if champion_version is not None:
            champion_metrics = model_registry.load_metadata(name, champion_version).get("metrics") or {}
        for version in versions:
            meta = model_registry.load_metadata(name, version)
            metrics = meta.get("metrics") or {}
            status = "experimental"
            if is_primary:
                if version == champion_version:
                    status = "candidate"
                elif champion_metrics is not None:
                    regressions = sum(
                        1
                        for k in ("log_loss", "brier")
                        if metrics.get(k) is not None
                        and champion_metrics.get(k) is not None
                        and metrics[k] > champion_metrics[k]
                    )
                    status = "rejected" if regressions == 2 else "experimental"
            candidates.append(_candidate_dict(name, version, meta, status))
    return candidates


def get_production_shadow_entries():
    all_picks = _load_all_resolved()
    live_variant = next(v for v in VARIANTS if v["id"] == "current_live")
    filtered = apply_filters(all_picks, live_variant["filters"])
    metrics = compute_metrics(filtered)
    entries = [
        {
            "id": "production::live",
            "model_name": "production",
            "version": "live",
            "name": "Production (hand-tuned formula)",
            "model_family": "heuristic",
            "pick_type": "moneyline",
            "status": "production",
            "auc": None,
            "log_loss": None,
            "brier": metrics.get("brier_score"),
            "ece": metrics.get("ece"),
            "win_rate": metrics.get("win_rate"),
            "edge": metrics.get("edge"),
            "flat_roi": metrics.get("flat_roi"),
            "kelly_roi": metrics.get("kelly_roi"),
            "n": metrics.get("n"),
            "shadow_status": False,
            "production_status": True,
            "has_diagnostics": False,
        }
    ]
    for pick_type in ("moneyline", "totals"):
        rows = [r for r in shadow_report._fetch_graded_shadow_rows() if r["pick_type"] == pick_type]
        if rows:
            y_true = [shadow_report._outcome_label(r) for r in rows]
            v2_prob = [r["v2_model_prob"] for r in rows]
            odds_dec = [r["odds_dec"] for r in rows]
            shadow_metrics = shadow_report.compute_metrics(y_true, v2_prob, odds_dec)
        else:
            shadow_metrics = {"n": 0}
        entries.append(
            {
                "id": f"shadow::{pick_type}",
                "model_name": f"{pick_type}_shadow_v2",
                "version": "live",
                "name": f"Shadow v2 LightGBM ({pick_type})",
                "model_family": "lightgbm",
                "pick_type": pick_type,
                "status": "shadow",
                "auc": shadow_metrics.get("auc"),
                "log_loss": shadow_metrics.get("log_loss"),
                "brier": shadow_metrics.get("brier"),
                "ece": None,
                "n": shadow_metrics.get("n"),
                "shadow_status": True,
                "production_status": False,
                "has_diagnostics": False,
            }
        )
    return entries


def get_all_candidates():
    return get_production_shadow_entries() + get_registry_candidates()


def _find_candidate(candidate_id):
    for c in get_all_candidates():
        if c["id"] == candidate_id:
            return c
    return None


def _two_proportion_significance(a, b):
    n1, n2 = a.get("n"), b.get("n")
    wr1, wr2 = a.get("win_rate"), b.get("win_rate")
    if not n1 or not n2 or wr1 is None or wr2 is None:
        return None
    w1 = round(wr1 / 100 * n1)
    w2 = round(wr2 / 100 * n2)
    p_pool = (w1 + w2) / (n1 + n2)
    if p_pool in (0, 1):
        return None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = (wr2 / 100 - wr1 / 100) / se
    p_value = round(math.erfc(abs(z) / math.sqrt(2)), 4)
    return {"z": round(z, 3), "p_value": p_value, "significant": p_value < 0.05}


def compare_candidates(candidate_id_a, candidate_id_b):
    a = _find_candidate(candidate_id_a)
    b = _find_candidate(candidate_id_b)
    if not a or not b:
        return None
    metric_keys = ["auc", "log_loss", "brier", "ece", "win_rate", "edge", "flat_roi", "kelly_roi"]
    lower_is_better = {"log_loss", "brier", "ece"}
    deltas = {}
    for key in metric_keys:
        av, bv = a.get(key), b.get(key)
        if av is None or bv is None:
            continue
        delta = round(bv - av, 5)
        improved = (delta < 0) if key in lower_is_better else (delta > 0)
        deltas[key] = {"delta": delta, "improved": improved}
    return {"a": a, "b": b, "deltas": deltas, "significance": _two_proportion_significance(a, b)}


def get_candidate_detail(candidate_id):
    if candidate_id.startswith("production::") or candidate_id.startswith("shadow::"):
        return _find_candidate(candidate_id)

    model_name, version = candidate_id.split("::", 1)
    meta = model_registry.load_metadata(model_name, version)
    diag_dir = _diagnostics_dir(model_name, version)

    diagnostics = {}
    csv_files = {
        "calibration_table": "calibration_table.csv",
        "calibration_table_merged": "calibration_table_merged.csv",
        "feature_importance_leave_one_out": "feature_importance_leave_one_out.csv",
        "feature_importance_combined": "feature_importance_combined.csv",
        "roc_curve": "roc_curve.csv",
        "pr_curve": "pr_curve.csv",
        "feature_importance_gain": "feature_importance_gain.csv",
        "feature_importance_permutation": "feature_importance_permutation.csv",
        "shap_summary": "shap_summary.csv",
        "feature_redundancy": "feature_redundancy.csv",
        "probability_distribution": "probability_distribution.csv",
        "feature_engineering_verdicts": "feature_engineering_verdicts.csv",
        "engineering_backlog": "engineering_backlog.csv",
    }
    json_files = {
        "confusion_matrix": "confusion_matrix.json",
        "correlation_matrix": "correlation_matrix.json",
        "calibration_bucket_summary": "calibration_bucket_summary.json",
        "feature_importance_provenance": "feature_importance_provenance.json",
        "engineering_audit": "engineering_audit.json",
    }
    if diag_dir.exists():
        for key, fname in csv_files.items():
            fpath = diag_dir / fname
            if fpath.exists() and fpath.stat().st_size > 0:
                try:
                    diagnostics[key] = pd.read_csv(fpath).to_dict("records")
                except pd.errors.EmptyDataError:
                    diagnostics[key] = []
        for key, fname in json_files.items():
            fpath = diag_dir / fname
            if fpath.exists():
                diagnostics[key] = json.loads(fpath.read_text())

    return {
        "id": candidate_id,
        "registry": meta,
        "diagnostics": diagnostics,
        "diagnostics_available": diag_dir.exists(),
        "learning_curve_available": False,
        "walk_forward_history_available": False,
        "feature_drift_available": False,
    }
