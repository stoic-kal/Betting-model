import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.calibration_common import (
    DEFAULT_MIN_BUCKET_N,
    calibration_bucket_summary,
    calibration_table,
    compute_classification_metrics,
    merge_calibration_buckets,
)
from services.prediction_math import kelly_units

DB_PATH = "database/picks.db"


def _fetch_graded_shadow_rows():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT s.pick_type, s.matchup, s.production_model_prob, s.v2_model_prob, s.odds_dec, "
        "s.degraded_features, s.created_at, p.status, p.pick, p.pick_type AS p_pick_type "
        "FROM shadow_v2_predictions s "
        "JOIN picks p ON p.matchup = s.matchup AND p.pick_type = s.pick_type "
        "WHERE p.status IN ('won', 'lost') AND s.odds_dec IS NOT NULL"
    ).fetchall()
    conn.close()
    return rows


def _roi(y_true, odds_dec):
    profits = []
    for won, odds in zip(y_true, odds_dec):
        if odds is None:
            continue
        profits.append((odds - 1.0) if won else -1.0)
    if not profits:
        return None
    return float(np.mean(profits)) * 100.0


def _kelly_roi(y_true, y_prob, odds_dec):
    profits = []
    for won, prob, odds in zip(y_true, y_prob, odds_dec):
        if odds is None:
            continue
        units = kelly_units(prob, odds)
        if units <= 0:
            continue
        profit = units * (odds - 1.0) if won else -units
        profits.append(profit)
    if not profits:
        return None
    return float(np.sum(profits)) / len(profits) * 100.0


def _outcome_label(row):
    if row["pick_type"] == "moneyline":
        return 1 if row["status"] == "won" else 0
    return 1 if row["status"] == "won" else 0


def compute_metrics(y_true, y_prob, odds_dec, min_bucket_n=DEFAULT_MIN_BUCKET_N):
    y_true_arr = np.asarray(y_true)
    y_prob_arr = np.asarray(y_prob)
    if len(set(y_true_arr.tolist())) < 2:
        return {"n": int(len(y_true_arr)), "insufficient_class_variation": True}
    buckets = calibration_table(y_true_arr, y_prob_arr, min_bucket_n=min_bucket_n)
    merged_buckets = merge_calibration_buckets(buckets, min_bucket_n=min_bucket_n)
    return {
        **compute_classification_metrics(y_true_arr, y_prob_arr),
        "roi": _roi(y_true, odds_dec),
        "kelly_roi": _kelly_roi(y_true, y_prob, odds_dec),
        "calibration_table": buckets,
        "calibration_table_merged": merged_buckets,
        "calibration_bucket_summary": calibration_bucket_summary(buckets, min_bucket_n=min_bucket_n),
        "calibration_bucket_summary_merged": calibration_bucket_summary(merged_buckets, min_bucket_n=min_bucket_n),
    }


def _evaluate(label, y_true, y_prob, odds_dec):
    metrics = compute_metrics(y_true, y_prob, odds_dec)
    if metrics.get("insufficient_class_variation"):
        print(f"\n--- {label} (n={metrics['n']}) --- not enough class variation to score yet")
        return metrics
    print(f"\n--- {label} (n={metrics['n']}) ---")
    print(f"  accuracy:  {metrics['accuracy']:.4f}")
    print(f"  auc:       {metrics['auc']:.4f}")
    print(f"  log_loss:  {metrics['log_loss']:.4f}")
    print(f"  brier:     {metrics['brier']:.4f}")
    print(f"  roi:       {metrics['roi']:.2f}%" if metrics["roi"] is not None else "  roi:       n/a")
    print(f"  kelly_roi: {metrics['kelly_roi']:.2f}%" if metrics["kelly_roi"] is not None else "  kelly_roi: n/a")
    for row in metrics["calibration_table"]:
        flag = "" if row["reliable"] else "  low-confidence (n<25)"
        print(f"    {row['bin']:<12} n={row['n']:<4} pred={row['avg_predicted']:<7} actual={row['actual_rate']:<7} "
              f"95% CI=[{row['actual_ci_lower']}, {row['actual_ci_upper']}]{flag}")
    print("  merged buckets (min sample size 25):")
    for row in metrics["calibration_table_merged"]:
        print(f"    {row['bin']:<12} n={row['n']:<4} pred={row['avg_predicted']:<7} actual={row['actual_rate']:<7} "
              f"95% CI=[{row['actual_ci_lower']}, {row['actual_ci_upper']}]")
    return metrics


def main():
    rows = _fetch_graded_shadow_rows()
    print(f"Graded shadow predictions available: {len(rows)}")
    if len(rows) < 30:
        print("Fewer than 30 graded shadow predictions exist. Any metrics below are not yet statistically")
        print("meaningful. This report becomes useful once shadow mode has run for real games over time.")
    if not rows:
        return

    y_true = [_outcome_label(r) for r in rows]
    prod_prob = [r["production_model_prob"] for r in rows]
    v2_prob = [r["v2_model_prob"] for r in rows]
    odds_dec = [r["odds_dec"] for r in rows]

    degraded_counts = [len(json.loads(r["degraded_features"])) if r["degraded_features"] else 0 for r in rows]
    print(f"Average degraded feature groups per shadow prediction: {np.mean(degraded_counts):.1f}")

    _evaluate("Production (hand-tuned engine)", y_true, prod_prob, odds_dec)
    _evaluate("V2 LightGBM (shadow engine)", y_true, v2_prob, odds_dec)


if __name__ == "__main__":
    main()
