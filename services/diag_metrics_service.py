import json
import math
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pipeline.calibration_common import (
    DEFAULT_MIN_BUCKET_N,
    brier_score,
    expected_calibration_error,
    wilson_interval,
)

DB_PATH = Path(__file__).parent.parent / "database" / "picks.db"
HISTORY_DIR = Path(__file__).parent.parent / "research" / "diagnostics" / "totals" / "history"
LATEST_PATH = HISTORY_DIR / "latest.json"
PREVIOUS_PATH = HISTORY_DIR / "previous.json"


def compute_diag_metrics(db_path=DB_PATH):

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM picks WHERE pick_type='totals' ORDER BY date ASC").fetchall()
    conn.close()

    picks = []
    for r in rows:
        d = dict(r)
        try:
            snap = json.loads(d.get("feature_snapshot") or "{}")
            ctx = snap.get("context", {})
            d["snap"] = {
"market_line": snap.get("market_line"),
"expected_total": snap.get("expected_total"),
"home_fip": snap.get("home_fip"),
"away_fip": snap.get("away_fip"),
"home_rsg": snap.get("home_rsg"),
"away_rsg": snap.get("away_rsg"),
"lineup_runs_adj": snap.get("lineup_runs_adj"),
"bullpen_workload_adj": snap.get("bullpen_workload_adj"),
"defense_runs_adj": snap.get("defense_runs_adj"),
"home_lineup_ops": ctx.get("home_lineup_ops"),
"away_lineup_ops": ctx.get("away_lineup_ops"),
"home_fielding_pct": ctx.get("home_fielding_pct"),
"away_fielding_pct": ctx.get("away_fielding_pct"),
            }
        except Exception:
            d["snap"] = {}
        d["direction"] = "OVER" if str(d.get("pick", "")).upper().startswith("OVER") else "UNDER"
        picks.append(d)

    resolved = [p for p in picks if p.get("status") in ("won", "lost")]
    won = [p for p in resolved if p["status"] == "won"]
    snapped = [p for p in resolved if any(v is not None for v in p["snap"].values())]

    def safe_mean(lst, key):
        vals = [float(x[key]) for x in lst if x.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    def safe_roi(lst):
        vals = [float(x["odds"]) - 1 if x["status"] == "won" else -1 for x in lst]
        return round(sum(vals) / len(lst) * 100, 2) if lst else 0

    over_r = [p for p in resolved if p["direction"] == "OVER"]
    under_r = [p for p in resolved if p["direction"] == "UNDER"]
    over_won = [p for p in over_r if p["status"] == "won"]
    under_won = [p for p in under_r if p["status"] == "won"]

    clv_picks = [p for p in resolved if p.get("clv") is not None]
    avg_clv = round(sum(float(p["clv"]) for p in clv_picks) / len(clv_picks), 3) if clv_picks else 0
    beat_close = len([p for p in clv_picks if float(p["clv"]) > 0]) if clv_picks else 0

    summary = {
"total_picks": len(picks),
"resolved": len(resolved),
"with_snapshot": len(snapped),
"won": len(won),
"date_min": resolved[0]["date"] if resolved else None,
"date_max": resolved[-1]["date"] if resolved else None,
"overall_wr": round(len(won) / len(resolved) * 100, 1) if resolved else 0,
"overall_roi": safe_roi(resolved),
"over_record": [len(over_won), len(over_r) - len(over_won)],
"over_wr": round(len(over_won) / len(over_r) * 100, 1) if over_r else 0,
"over_roi": safe_roi(over_r),
"under_record": [len(under_won), len(under_r) - len(under_won)],
"under_wr": round(len(under_won) / len(under_r) * 100, 1) if under_r else 0,
"under_roi": safe_roi(under_r),
"avg_ev": safe_mean(resolved, "ev"),
"avg_prob": safe_mean(resolved, "model_prob"),
"avg_clv": avg_clv,
"beat_close": round(beat_close / len(clv_picks) * 100, 1) if clv_picks else 0,
"clv_picks": len(clv_picks),
    }

    calib_picks = [p for p in resolved if p.get("model_prob") is not None]
    bins, pred_centers, actual_wr, bin_counts = [], [], [], []
    actual_ci_lower, actual_ci_upper, bin_reliable = [], [], []
    for lo in [0.5, 0.52, 0.55, 0.58, 0.60, 0.62, 0.65, 0.70, 0.75]:
        hi = lo + 0.05
        bucket = [p for p in calib_picks if lo <= float(p["model_prob"]) < hi]
        if bucket:
            bucket_won = [p for p in bucket if p["status"] == "won"]
            ci_low, ci_high = wilson_interval(len(bucket_won), len(bucket))
            bins.append(f"{int(lo*100)}-{int(hi*100)}%")
            pred_centers.append(round((lo + hi) / 2 * 100, 1))
            actual_wr.append(round(len(bucket_won) / len(bucket) * 100, 1))
            actual_ci_lower.append(round(ci_low * 100, 1))
            actual_ci_upper.append(round(ci_high * 100, 1))
            bin_counts.append(len(bucket))
            bin_reliable.append(len(bucket) >= DEFAULT_MIN_BUCKET_N)

    calib_probs = [float(p["model_prob"]) for p in calib_picks]
    calib_outcomes = [int(p["status"] == "won") for p in calib_picks]
    brier = round(brier_score(calib_outcomes, calib_probs), 4) if calib_picks else None
    ece = round(expected_calibration_error(calib_outcomes, calib_probs), 4) if calib_picks else None

    calibration = {
"bins": bins,
"pred_centers": pred_centers,
"actual_wr": actual_wr,
"actual_ci_lower": actual_ci_lower,
"actual_ci_upper": actual_ci_upper,
"bin_counts": bin_counts,
"bin_reliable": bin_reliable,
"brier": brier,
"ece": ece,
"baseline_brier": (
            round(len(won) / len(resolved) * (1 - len(won) / len(resolved)), 4)
            if resolved
            else None
        ),
    }

    by_date = {}
    for p in resolved:
        by_date.setdefault(p["date"], []).append(p)
    dates_sorted = sorted(by_date.keys())
    cum_pnl, rolling_wr, dates_out = [], [], []
    pnl = 0
    rolling_window = []
    for d in dates_sorted:
        for p in by_date[d]:
            pnl += (float(p["odds"]) - 1) if p["status"] == "won" else -1
            rolling_window.append(1 if p["status"] == "won" else 0)
        cum_pnl.append(round(pnl, 2))
        rw = rolling_window[-10:] if len(rolling_window) >= 5 else rolling_window
        rolling_wr.append(round(sum(rw) / len(rw) * 100, 1))
        dates_out.append(d)

    temporal = {"dates": dates_out, "cum_pnl": cum_pnl, "rolling_wr": rolling_wr}

    feat_keys = [
"home_fip",
"away_fip",
"home_rsg",
"away_rsg",
"lineup_runs_adj",
"bullpen_workload_adj",
"defense_runs_adj",
"home_lineup_ops",
"away_lineup_ops",
"home_fielding_pct",
"expected_total",
"market_line",
    ]
    features = []
    for fk in feat_keys:
        vals_won = [
            float(p["snap"][fk])
            for p in snapped
            if p["snap"].get(fk) is not None and p["status"] == "won"
        ]
        vals_lost = [
            float(p["snap"][fk])
            for p in snapped
            if p["snap"].get(fk) is not None and p["status"] == "lost"
        ]
        all_vals = vals_won + vals_lost
        if len(all_vals) < 5:
            continue
        n = len(all_vals)
        m_all = sum(all_vals) / n
        m_won = sum(vals_won) / len(vals_won) if vals_won else 0
        std = math.sqrt(sum((v - m_all) ** 2 for v in all_vals) / n) if n > 1 else 1
        p_won = len(vals_won) / n
        corr = ((m_won - m_all) / std) * math.sqrt(p_won * (1 - p_won)) if std > 0 else 0
        features.append(
            {
"name": fk.replace("_", " ").title(),
"key": fk,
"corr": round(corr, 3),
"n": n,
"mean_won": round(sum(vals_won) / len(vals_won), 3) if vals_won else None,
"mean_lost": round(sum(vals_lost) / len(vals_lost), 3) if vals_lost else None,
            }
        )
    features.sort(key=lambda x: abs(x["corr"]), reverse=True)

    team_map = {}
    for p in resolved:
        for t in p.get("matchup", "").split(" @ "):
            t = t.strip()
            if t:
                team_map.setdefault(t, []).append(p)
    teams_out = []
    for t, tpicks in team_map.items():
        if len(tpicks) < 2:
            continue
        t_won = [x for x in tpicks if x["status"] == "won"]
        teams_out.append(
            {
"name": t,
"picks": len(tpicks),
"wr": round(len(t_won) / len(tpicks) * 100, 1),
"roi": safe_roi(tpicks),
"avg_ev": safe_mean(tpicks, "ev"),
            }
        )
    teams_out.sort(key=lambda x: x["roi"], reverse=True)

    ev_buckets = []
    for lo, hi, label in [
        (0, 5, "0-5%"),
        (5, 10, "5-10%"),
        (10, 15, "10-15%"),
        (15, 20, "15-20%"),
        (20, 999, "20%+"),
    ]:
        b = [p for p in resolved if p.get("ev") is not None and lo <= float(p["ev"]) < hi]
        if b:
            bw = [x for x in b if x["status"] == "won"]
            ev_buckets.append(
                {
"label": label,
"n": len(b),
"wr": round(len(bw) / len(b) * 100, 1),
"roi": safe_roi(b),
                }
            )

    filters_out = []

    def flt(label, fn):
        b = [p for p in resolved if fn(p)]
        if not b:
            return
        bw = [x for x in b if x["status"] == "won"]
        filters_out.append(
            {
"label": label,
"n": len(b),
"wr": round(len(bw) / len(b) * 100, 1),
"roi": safe_roi(b),
"avg_ev": safe_mean(b, "ev"),
            }
        )

    flt("OVER only", lambda p: p["direction"] == "OVER")
    flt("UNDER only", lambda p: p["direction"] == "UNDER")
    flt("CLV > 0", lambda p: p.get("clv") and float(p["clv"]) > 0)
    flt("CLV > 1", lambda p: p.get("clv") and float(p["clv"]) > 1)
    flt(
"UNDER + CLV > 0",
        lambda p: p["direction"] == "UNDER" and p.get("clv") and float(p["clv"]) > 0,
    )
    flt(
"UNDER + CLV > 1",
        lambda p: p["direction"] == "UNDER" and p.get("clv") and float(p["clv"]) > 1,
    )
    flt("Prob ≥ 0.60", lambda p: p.get("model_prob") and float(p["model_prob"]) >= 0.60)
    flt("Prob ≥ 0.65", lambda p: p.get("model_prob") and float(p["model_prob"]) >= 0.65)
    flt("EV ≥ 10%", lambda p: p.get("ev") and float(p["ev"]) >= 10)
    flt("EV ≥ 15%", lambda p: p.get("ev") and float(p["ev"]) >= 15)
    flt(
"UNDER + EV ≥ 10%",
        lambda p: p["direction"] == "UNDER" and p.get("ev") and float(p["ev"]) >= 10,
    )
    flt(
"Line 8.0–8.5",
        lambda p: p.get("snap")
        and p["snap"].get("market_line")
        and 8.0 <= float(p["snap"]["market_line"]) <= 8.5,
    )
    flt(
"Low FIP (< 3.0)",
        lambda p: p.get("snap")
        and p["snap"].get("home_fip")
        and float(p["snap"]["home_fip"]) < 3.0,
    )
    filters_out.sort(key=lambda x: x["roi"], reverse=True)

    recent = []
    for p in reversed(resolved[-30:]):
        recent.append(
            {
"date": p.get("date", ""),
"matchup": p.get("matchup", ""),
"pick": p.get("pick", ""),
"direction": p.get("direction", ""),
"status": p.get("status", ""),
"prob": round(float(p["model_prob"]) * 100, 1) if p.get("model_prob") else None,
"ev": round(float(p["ev"]), 1) if p.get("ev") else None,
"odds": round(float(p["odds"]), 3) if p.get("odds") else None,
"clv": round(float(p["clv"]), 2) if p.get("clv") else None,
"version": p.get("model_version", ""),
            }
        )

    snap_fields = [
"home_fip",
"away_fip",
"home_rsg",
"away_rsg",
"expected_total",
"market_line",
"lineup_runs_adj",
"bullpen_workload_adj",
"defense_runs_adj",
    ]
    health = []
    for fk in snap_fields:
        has = [p for p in picks if p.get("snap") and p["snap"].get(fk) is not None]
        vals = [float(p["snap"][fk]) for p in has if p["snap"].get(fk) is not None]
        health.append(
            {
"name": fk,
"coverage": round(len(has) / len(picks) * 100, 1) if picks else 0,
"mean": round(sum(vals) / len(vals), 3) if vals else None,
"std": (
                    round(
                        math.sqrt(sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / len(vals)),
                        3,
                    )
                    if len(vals) > 1
                    else 0
                ),
"constant": len(set(round(v, 4) for v in vals)) == 1 if vals else True,
            }
        )

    return {
"summary": summary,
"calibration": calibration,
"temporal": temporal,
"features": features,
"teams": teams_out,
"ev_buckets": ev_buckets,
"filters": filters_out,
"recent_picks": recent,
"data_health": health,
    }


def save_run_snapshot(metrics=None, section_results=None):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if metrics is None:
        metrics = compute_diag_metrics()
    if LATEST_PATH.exists():
        shutil.copyfile(LATEST_PATH, PREVIOUS_PATH)
    snapshot = {
"run_at": datetime.now(timezone.utc).isoformat(),
"summary": metrics.get("summary"),
"calibration": metrics.get("calibration"),
"data_health": metrics.get("data_health"),
"features": metrics.get("features", [])[:10],
"sections": section_results or {},
    }
    LATEST_PATH.write_text(json.dumps(snapshot, indent=2, default=str))
    return snapshot


def _get(d, *path):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _diff_scalars(latest, previous):

    fields = [
        ("Overall Win Rate", "summary", "overall_wr", "%"),
        ("Overall ROI", "summary", "overall_roi", "%"),
        ("OVER Win Rate", "summary", "over_wr", "%"),
        ("OVER ROI", "summary", "over_roi", "%"),
        ("UNDER Win Rate", "summary", "under_wr", "%"),
        ("UNDER ROI", "summary", "under_roi", "%"),
        ("Avg EV", "summary", "avg_ev", "%"),
        ("Avg CLV", "summary", "avg_clv", "pp"),
        ("Beat Closing Line", "summary", "beat_close", "%"),
        ("Brier Score", "calibration", "brier", ""),
        ("ECE (Calibration)", "calibration", "ece", ""),
    ]
    out = []
    for label, section, key, unit in fields:
        lv = _get(latest, section, key)
        pv = _get(previous, section, key)
        if lv is None or pv is None:
            continue
        delta = round(float(lv) - float(pv), 4)

        lower_is_better = key in ("brier", "ece")
        improved = (delta < 0) if lower_is_better else (delta > 0)
        out.append(
            {
"label": label,
"key": key,
"unit": unit,
"latest": lv,
"previous": pv,
"delta": delta,
"improved": improved if delta != 0 else None,
            }
        )

    lh = latest.get("data_health") or []
    ph = previous.get("data_health") or []
    l_constant = sum(1 for f in lh if f.get("constant"))
    p_constant = sum(1 for f in ph if f.get("constant"))
    if lh and ph:
        out.append(
            {
"label": "Constant/Dead Features",
"key": "constant_features",
"unit": "",
"latest": l_constant,
"previous": p_constant,
"delta": l_constant - p_constant,
"improved": (l_constant < p_constant) if l_constant != p_constant else None,
            }
        )
    return out


def load_history():
    latest = json.loads(LATEST_PATH.read_text()) if LATEST_PATH.exists() else None
    previous = json.loads(PREVIOUS_PATH.read_text()) if PREVIOUS_PATH.exists() else None
    diff = _diff_scalars(latest, previous) if latest and previous else None
    return {"latest": latest, "previous": previous, "diff": diff}
