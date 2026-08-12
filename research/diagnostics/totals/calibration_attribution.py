import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


BUCKET_EDGES = [0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 1.000001]
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "diagnostics"


def wilson_interval(wins, n, z=1.959963984540054):
    if not n:
        return (None, None)
    p = wins / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - radius), min(1.0, centre + radius))


def _bucket_labels():
    return [
        f"{BUCKET_EDGES[i]:.2f}–{min(BUCKET_EDGES[i + 1], 1.0):.2f}"
        for i in range(len(BUCKET_EDGES) - 1)
    ]


def add_calibration_columns(frame):
    data = frame.copy().sort_values(["date", "game_id"], kind="stable")
    data = data.dropna(subset=["won", "model_prob"])
    data["won"] = data["won"].astype(int)
    data["model_prob"] = data["model_prob"].astype(float).clip(1e-6, 1 - 1e-6)
    data["market_probability"] = pd.to_numeric(data.get("odds"), errors="coerce").map(
        lambda odds: 1 / odds if pd.notna(odds) and odds > 1 else np.nan
    )
    data["market_disagreement"] = data["model_prob"] - data["market_probability"]
    data["confidence"] = (data["model_prob"] - 0.5).abs() * 2
    data["row_log_loss"] = -(
        data["won"] * np.log(data["model_prob"])
        + (1 - data["won"]) * np.log(1 - data["model_prob"])
    )
    data["row_brier"] = (data["model_prob"] - data["won"]) ** 2
    data["calibration_bucket"] = pd.cut(
        data["model_prob"], BUCKET_EDGES, labels=_bucket_labels(), right=False, include_lowest=True
    )
    return data.dropna(subset=["calibration_bucket"])


def _numeric_feature_columns(data):
    excluded = {
        "snap_schema_version", "snap_fip_formula_version", "snap_totals_input_version",
    }
    columns = []
    for col in data.columns:
        if not col.startswith("snap_") or col in excluded:
            continue
        if col.startswith("snap_qualification_checklist_"):
            continue
        values = pd.to_numeric(data[col], errors="coerce")
        if values.notna().sum() >= 5 and values.nunique(dropna=True) > 1:
            columns.append(col)
    return columns


def _bucket_record(group, total_n, feature_columns, overall_means, overall_stds):
    n = len(group)
    wins = int(group["won"].sum())
    predicted = float(group["model_prob"].mean())
    observed = wins / n
    low, high = wilson_interval(wins, n)
    gap = observed - predicted
    averages = {}
    shifts = []
    for col in feature_columns:
        values = pd.to_numeric(group[col], errors="coerce")
        if values.notna().any():
            mean = float(values.mean())
            averages[col.removeprefix("snap_")] = round(mean, 6)
            std = overall_stds.get(col)
            if std and np.isfinite(std) and std > 0:
                shifts.append(
                    {
                        "feature": col.removeprefix("snap_"),
                        "bucket_mean": round(mean, 6),
                        "overall_mean": round(overall_means[col], 6),
                        "standardized_shift": round((mean - overall_means[col]) / std, 3),
                    }
                )
    shifts.sort(key=lambda row: abs(row["standardized_shift"]), reverse=True)
    significant = predicted < low or predicted > high
    input_versions = (
        pd.to_numeric(group["snap_totals_input_version"], errors="coerce")
        if "snap_totals_input_version" in group
        else pd.Series(np.nan, index=group.index)
    )
    corrected_inputs = int((input_versions >= 2).sum()) if input_versions.notna().any() else 0
    return {
        "bucket": str(group["calibration_bucket"].iloc[0]),
        "sample_size": n,
        "wins": wins,
        "predicted_probability": round(predicted, 6),
        "observed_win_rate": round(observed, 6),
        "wilson_95_low": round(low, 6),
        "wilson_95_high": round(high, 6),
        "calibration_gap": round(gap, 6),
        "error_direction": "underconfident" if gap > 0 else "overconfident" if gap < 0 else "aligned",
        "statistically_significant": bool(significant),
        "corrected_input_rows": corrected_inputs,
        "legacy_input_rows": int(n - corrected_inputs),
        "legacy_input_share": round((n - corrected_inputs) / n, 6),
        "ece_contribution": round(n / total_n * abs(gap), 8),
        "log_loss_contribution": round(float(group["row_log_loss"].sum()) / total_n, 8),
        "brier_contribution": round(float(group["row_brier"].sum()) / total_n, 8),
        "average_ev": _mean(group, "ev"),
        "average_roi": _roi(group),
        "average_clv": _mean(group, "clv"),
        "average_market_disagreement": _mean(group, "market_disagreement"),
        "average_confidence": _mean(group, "confidence"),
        "direction_mix": {
            str(key): round(float(value), 4)
            for key, value in group["direction"].value_counts(normalize=True).items()
        },
        "average_features": averages,
        "largest_feature_shifts": shifts[:5],
    }


def _mean(frame, column):
    values = pd.to_numeric(frame.get(column), errors="coerce")
    return round(float(values.mean()), 6) if values.notna().any() else None


def _roi(frame):
    wagered = pd.to_numeric(frame.get("wagered"), errors="coerce").sum()
    profit = pd.to_numeric(frame.get("profit"), errors="coerce").sum()
    return round(float(profit / wagered * 100), 4) if wagered else None


def _fold_attribution(data, min_initial=40, folds=4):
    n = len(data)
    start = min(max(min_initial, int(n * 0.40)), max(n - folds, 0))
    remaining = n - start
    if remaining < folds:
        return []
    blocks = np.array_split(np.arange(start, n), folds)
    rows = []
    for fold, indexes in enumerate(blocks, 1):
        validation = data.iloc[indexes]
        for bucket, group in validation.groupby("calibration_bucket", observed=True):
            size = len(group)
            wins = int(group["won"].sum())
            predicted = float(group["model_prob"].mean())
            observed = wins / size
            low, high = wilson_interval(wins, size)
            rows.append(
                {
                    "fold": fold,
                    "train_end_index": int(indexes[0] - 1),
                    "validation_start": str(validation["date"].min()),
                    "validation_end": str(validation["date"].max()),
                    "bucket": str(bucket),
                    "sample_size": size,
                    "predicted_probability": predicted,
                    "observed_win_rate": observed,
                    "calibration_gap": observed - predicted,
                    "wilson_95_low": low,
                    "wilson_95_high": high,
                    "statistically_significant": bool(predicted < low or predicted > high),
                }
            )
    return rows


def _shadow_evidence(db_path):
    result = {
        "source": "shadow_v2_predictions joined to resolved totals by matchup and creation date",
        "total_predictions": 0,
        "resolved_predictions": 0,
        "status": "unavailable",
        "reason": "no resolved live-shadow totals are available",
    }
    try:
        conn = sqlite3.connect(db_path)
        result["total_predictions"] = conn.execute(
            "SELECT COUNT(*) FROM shadow_v2_predictions WHERE pick_type='totals'"
        ).fetchone()[0]
        resolved = conn.execute(
            """SELECT s.production_model_prob AS model_prob,
                      CASE WHEN p.status='won' THEN 1 ELSE 0 END AS won
               FROM shadow_v2_predictions s JOIN picks p
                 ON p.matchup=s.matchup AND p.date=substr(s.created_at,1,10)
               WHERE s.pick_type='totals' AND p.pick_type='totals'
                 AND p.status IN ('won','lost')"""
        ).fetchall()
        conn.close()
        result["resolved_predictions"] = len(resolved)
        if resolved:
            result["status"] = "available"
            result["reason"] = None
    except (sqlite3.Error, OSError) as exc:
        result["reason"] = f"shadow evidence query failed: {exc}"
    return result


def build_attribution(frame, db_path):
    data = add_calibration_columns(frame)
    features = _numeric_feature_columns(data)
    means = {col: float(pd.to_numeric(data[col], errors="coerce").mean()) for col in features}
    stds = {col: float(pd.to_numeric(data[col], errors="coerce").std()) for col in features}
    buckets = [
        _bucket_record(group, len(data), features, means, stds)
        for _, group in data.groupby("calibration_bucket", observed=True)
    ]
    total_ece = sum(row["ece_contribution"] for row in buckets)
    ranked = sorted(buckets, key=lambda row: row["ece_contribution"], reverse=True)
    cumulative = 0.0
    attribution_80 = []
    for rank, row in enumerate(ranked, 1):
        row["ece_rank"] = rank
        row["ece_share"] = round(row["ece_contribution"] / total_ece, 6) if total_ece else 0
        cumulative += row["ece_contribution"]
        row["cumulative_ece_share"] = round(cumulative / total_ece, 6) if total_ece else 0
        if cumulative - row["ece_contribution"] < total_ece * 0.8:
            attribution_80.append(row["bucket"])

    folds = _fold_attribution(data)
    shadow = _shadow_evidence(db_path)
    fold_frame = pd.DataFrame(folds)
    overall_over = float((data["direction"] == "OVER").mean())
    for row in ranked:
        history = fold_frame[fold_frame["bucket"] == row["bucket"]] if len(fold_frame) else pd.DataFrame()
        significant = history[history["statistically_significant"] == True] if len(history) else history
        same_direction = significant[
            np.sign(significant["calibration_gap"]) == np.sign(row["calibration_gap"])
        ] if len(significant) else significant
        persistent_history = len(history) >= 2 and len(same_direction) >= 2
        row["walk_forward"] = {
            "folds_evaluated": int(len(history)),
            "significant_folds": int(len(significant)),
            "same_direction_significant_folds": int(len(same_direction)),
            "persistent_across_history": bool(persistent_history),
        }
        row["persistence_verdict"] = (
            "persistent"
            if persistent_history and shadow["status"] == "available"
            else "historical_pattern_not_live_confirmed"
            if persistent_history
            else "likely_sampling_noise_or_insufficient_history"
        )
        row["engineering_attribution"] = _explain(row, overall_over, shadow)
        row["recalibration_recommendation"] = (
            "not recommended: resolved live-shadow confirmation is absent"
            if shadow["status"] != "available"
            else "not recommended from attribution alone; investigate associated inputs first"
        )

    result = {
        "method": {
            "bucket_edges": BUCKET_EDGES,
            "ece_definition": "sum(bucket_n / total_n * abs(observed_rate - mean_prediction))",
            "confidence_interval": "95% Wilson interval around observed win rate",
            "statistical_significance": "mean predicted probability lies outside Wilson interval",
            "walk_forward": "four chronological validation blocks after an expanding initial history",
            "confidence_definition": "2 * abs(model_probability - 0.5)",
            "market_probability": "1 / locked decimal odds for the selected side",
        },
        "sample_size": len(data),
        "weighted_ece": round(total_ece, 8),
        "brier": round(float(data["row_brier"].mean()), 8),
        "log_loss": round(float(data["row_log_loss"].mean()), 8),
        "buckets_ranked_by_ece": ranked,
        "buckets_responsible_for_80pct": attribution_80,
        "walk_forward_folds": folds,
        "live_shadow": shadow,
        "global_recommendation": (
            "Do not recalibrate: no bucket can satisfy the required live-shadow confirmation yet."
        ),
    }
    return result


def _explain(row, overall_over, shadow):
    evidence = []
    if row.get("legacy_input_share", 0) > 0:
        evidence.append(
            f"{row['legacy_input_share']:.0%} of rows predate totals input v2 and therefore carry the known FIP/travel/bullpen-label defects"
        )
    over_share = row["direction_mix"].get("OVER", 0.0)
    if abs(over_share - overall_over) >= 0.15:
        evidence.append(
            f"direction mix differs from the full sample (OVER {over_share:.0%} vs {overall_over:.0%})"
        )
    disagreement = row.get("average_market_disagreement")
    if disagreement is not None:
        evidence.append(f"mean model-minus-market disagreement is {disagreement:+.3f}")
    shifts = row.get("largest_feature_shifts", [])[:3]
    if shifts:
        evidence.append(
            "largest associations are "
            + ", ".join(f"{item['feature']} ({item['standardized_shift']:+.2f} SD)" for item in shifts)
        )
    if not row["statistically_significant"]:
        evidence.append("the bucket prediction remains inside its Wilson interval")
    else:
        evidence.append("the bucket prediction lies outside its Wilson interval")
    evidence.append(
        "resolved live-shadow evidence is unavailable"
        if shadow["status"] != "available"
        else "resolved live-shadow evidence is available"
    )
    return (
        "Observed associations, not proven causes: " + "; ".join(evidence) + "."
    )


def write_reports(report, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "calibration_attribution.json").write_text(json.dumps(report, indent=2))
    flat_rows = []
    for row in report["buckets_ranked_by_ece"]:
        flat_rows.append({key: value for key, value in row.items() if not isinstance(value, (dict, list))})
    pd.DataFrame(flat_rows).to_csv(report_dir / "calibration_attribution_buckets.csv", index=False)
    pd.DataFrame(report["walk_forward_folds"]).to_csv(
        report_dir / "calibration_attribution_folds.csv", index=False
    )
    lines = [
        "# Totals calibration attribution",
        "",
        f"Sample: {report['sample_size']} resolved picks; weighted ECE: {report['weighted_ece']:.4f}.",
        f"80% attribution set: {', '.join(report['buckets_responsible_for_80pct']) or 'none'}.",
        f"Live shadow: {report['live_shadow']['resolved_predictions']} resolved of {report['live_shadow']['total_predictions']} predictions.",
        "",
    ]
    for row in report["buckets_ranked_by_ece"]:
        lines.extend(
            [
                f"## {row['bucket']}",
                "",
                f"n={row['sample_size']}; predicted={row['predicted_probability']:.1%}; observed={row['observed_win_rate']:.1%}; "
                f"Wilson 95%={row['wilson_95_low']:.1%}–{row['wilson_95_high']:.1%}; "
                f"ECE contribution={row['ece_contribution']:.4f} ({row['ece_share']:.1%} of ECE).",
                "",
                row["engineering_attribution"],
                "",
                f"Persistence: {row['persistence_verdict']}. {row['recalibration_recommendation']}.",
                "",
            ]
        )
    (report_dir / "calibration_attribution.md").write_text("\n".join(lines))
    return report_dir
