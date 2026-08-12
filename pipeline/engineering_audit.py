import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr
from sklearn.inspection import permutation_importance

from pipeline import model_registry
from pipeline.calibration_common import (
    DEFAULT_MIN_BUCKET_N,
    WILSON_Z_95,
    brier_score,
    expected_calibration_error,
    log_loss_score,
    wilson_interval,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_HISTORY_PATH = REPO_ROOT / "reports" / "training" / "engineering_audit_history.jsonl"

MIN_ROWS_FOR_VERDICT = 200
MIN_FOLDS_FOR_STABILITY = 3
FOLD_PERMUTATION_REPEATS = 5
STABILITY_UNSTABLE = 0.50
STABILITY_STABLE = 0.70
AGREEMENT_HIGH = 0.85
AGREEMENT_MEDIUM = 0.65
BOTTOM_TIER_FRACTION = 0.75
MID_TIER_FRACTION = 0.50
LOFO_KEEP_DELTA = 1e-4
LOFO_REMOVE_DELTA = 0.0
OUTCOME_CORR_SIGNAL = 0.05
SHAP_DIRECTION_THRESHOLD = 0.05

MIN_SEGMENT_N = 40
MIN_CLV_N = 25
REDUNDANCY_THRESHOLD = 0.9

ALPHA = 0.05
STRONG_ALPHA = 0.01
NULL_SIMULATIONS = 400
BOOTSTRAP_RESAMPLES = 400
RANDOM_SEED = 42
MIN_EFFORT_KLOC = 0.05

BLOCKING_REMEDIATION = "new_data_acquisition"
RESOLUTION_SUPPRESSING = ("IMPLEMENTED", "TESTED", "REJECTED")
RESOLUTION_REOPENING = ("REOPENED",)
RESOLUTIONS = RESOLUTION_SUPPRESSING + RESOLUTION_REOPENING

THRESHOLD_PROVENANCE = {
    "ALPHA": "two-sided significance level 0.05, the conventional statistical standard used for every hypothesis test in this module",
    "STRONG_ALPHA": "0.01, used only to separate a High from a Medium confidence label once a p-value already exists",
    "WILSON_Z_95": "normal quantile for a two-sided 95% interval, imported from pipeline/calibration_common.py",
    "MIN_SEGMENT_N": "minimum rows before a segment estimate is reported at all; significance itself is decided by the Wilson interval, not by this floor",
    "MIN_CLV_N": "minimum graded picks before a CLV proportion test is attempted; significance itself is decided by the Wilson interval",
    "REDUNDANCY_THRESHOLD": "inherited from pipeline/train_common.feature_redundancy_report; a pair is only reported when the Fisher-z 95% interval for |r| also excludes this value",
    "MIN_ROWS_FOR_VERDICT": "evidence floor for per-feature verdicts; below it every feature resolves to NOT ENOUGH DATA rather than a guess",
    "MIN_FOLDS_FOR_STABILITY": "minimum walk-forward folds before a rank-stability statistic is defined",
}

CORE_METRIC_DEFINITIONS = (
    "wilson_interval",
    "brier_score",
    "log_loss_score",
    "expected_calibration_error",
    "compute_classification_metrics",
    "merge_calibration_buckets",
)


def _clamp(value, low=0.0, high=1.0):
    return float(max(low, min(high, value)))


def _band(score):
    if score >= 2.0 / 3.0:
        return "High"
    if score >= 1.0 / 3.0:
        return "Medium"
    return "Low"


def _confidence_label(evidence_probability):
    if evidence_probability is None:
        return "Low"
    if evidence_probability >= 1.0 - STRONG_ALPHA:
        return "High"
    if evidence_probability >= 1.0 - ALPHA:
        return "Medium"
    return "Low"


def impact_scales(metrics, y_true):
    base_rate = float(np.mean(np.asarray(y_true, dtype=float))) if len(y_true) else 0.0
    ece = metrics.get("ece")
    log_loss = metrics.get("log_loss")
    auc = metrics.get("auc")
    return {
        "ece": float(ece) if ece else None,
        "log_loss": float(log_loss) if log_loss else None,
        "auc": float(auc) - 0.5 if auc is not None and auc > 0.5 else None,
        "rate": 1.0,
        "base_rate": base_rate,
    }


def _relative_impact(metric, value, scales):
    if value is None:
        return 0.0
    scale = (scales or {}).get(metric)
    if not scale:
        return 0.0
    return _clamp(abs(float(value)) / abs(float(scale)))


def _normal_two_sided_p(z):
    if z is None or z != z:
        return 1.0
    return float(2.0 * (1.0 - norm.cdf(abs(float(z)))))


def _normal_one_sided_p(z):
    if z is None or z != z:
        return 1.0
    return float(1.0 - norm.cdf(float(z)))


def _proportion_z(successes, n, p_null):
    if n <= 0 or p_null <= 0 or p_null >= 1:
        return None
    se = np.sqrt(p_null * (1 - p_null) / n)
    if se == 0:
        return None
    return float((successes / n - p_null) / se)


def _auc_test(auc, y_true):
    y = np.asarray(y_true, dtype=float)
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    if auc is None or positives == 0 or negatives == 0:
        return None
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    variance = (auc * (1 - auc) + (positives - 1) * (q1 - auc * auc)
                + (negatives - 1) * (q2 - auc * auc)) / (positives * negatives)
    if variance <= 0:
        return None
    se = float(np.sqrt(variance))
    z = (auc - 0.5) / se
    return {
        "auc": round(float(auc), 4),
        "standard_error": round(se, 5),
        "z_vs_chance": round(float(z), 3),
        "p_value": round(_normal_one_sided_p(z), 6),
        "ci_lower": round(float(auc - WILSON_Z_95 * se), 4),
        "ci_upper": round(float(auc + WILSON_Z_95 * se), 4),
        "positives": positives,
        "negatives": negatives,
        "method": "Hanley-McNeil standard error of the ROC area, one-sided test against chance (AUC=0.5)",
    }


def _ece_null_test(y_true, y_prob, simulations=NULL_SIMULATIONS, seed=RANDOM_SEED):
    y_prob = np.asarray(y_prob, dtype=float)
    observed = expected_calibration_error(y_true, y_prob)
    if observed is None or len(y_prob) == 0:
        return None
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(simulations):
        simulated = (rng.random(len(y_prob)) < y_prob).astype(float)
        value = expected_calibration_error(simulated, y_prob)
        if value is not None:
            draws.append(value)
    if not draws:
        return None
    draws = np.asarray(draws, dtype=float)
    exceedances = int((draws >= observed).sum())
    return {
        "observed_ece": round(float(observed), 6),
        "null_mean_ece": round(float(draws.mean()), 6),
        "null_p95_ece": round(float(np.quantile(draws, 1 - ALPHA)), 6),
        "simulations": len(draws),
        "p_value": round((exceedances + 1) / (len(draws) + 1), 6),
        "method": ("parametric bootstrap: outcomes redrawn from the model's own predicted probabilities, so the null "
                   "distribution is the calibration error a perfectly calibrated model of this size would still show"),
    }


def _bootstrap_fraction(values, statistic, resamples=BOOTSTRAP_RESAMPLES, seed=RANDOM_SEED):
    rng = np.random.default_rng(seed)
    n = len(values[0])
    hits = 0
    for _ in range(resamples):
        idx = rng.integers(0, n, n)
        if statistic([np.asarray(v)[idx] for v in values]):
            hits += 1
    return hits / resamples


def _skill_bootstrap(y_true, y_prob, resamples=BOOTSTRAP_RESAMPLES, seed=RANDOM_SEED):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    n = len(y_true)
    if n < 2:
        return None
    base_rate = float(y_true.mean())
    observed = log_loss_score(y_true, np.full(n, base_rate)) - log_loss_score(y_true, y_prob)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(resamples):
        idx = rng.integers(0, n, n)
        yt = y_true[idx]
        if len(set(yt.tolist())) < 2:
            continue
        rate = float(yt.mean())
        draws.append(log_loss_score(yt, np.full(n, rate)) - log_loss_score(yt, y_prob[idx]))
    if len(draws) < 2:
        return None
    draws = np.asarray(draws, dtype=float)
    se = float(draws.std(ddof=1))
    z = observed / se if se > 0 else None
    return {
        "log_loss_skill": round(float(observed), 6),
        "bootstrap_standard_error": round(se, 6),
        "ci_lower": round(float(np.quantile(draws, ALPHA / 2)), 6),
        "ci_upper": round(float(np.quantile(draws, 1 - ALPHA / 2)), 6),
        "resamples": len(draws),
        "z": round(float(z), 3) if z is not None else None,
        "p_value": round(_normal_one_sided_p(z), 6) if z is not None else 1.0,
        "method": ("non-parametric bootstrap over evaluation rows of the log-loss improvement over a base-rate "
                   "constant predictor; the evaluation set is underpowered when this improvement is not separable "
                   "from zero at the 95% level"),
    }


def _fisher_correlation_ci(r, n):
    if n <= 3 or abs(r) >= 1.0:
        return None
    z = np.arctanh(abs(float(r)))
    se = 1.0 / np.sqrt(n - 3)
    return (float(np.tanh(z - WILSON_Z_95 * se)), float(np.tanh(z + WILSON_Z_95 * se)), float(se))


def recommendation_block(finding, action, confidence, gain_band, files, evidence=None):
    return {
        "status": "OK",
        "finding": finding,
        "recommendation": action,
        "confidence": confidence,
        "expected_gain": gain_band,
        "files": list(files),
        "evidence": evidence or {},
    }


def insufficient_evidence_block(reason, files=()):
    return {
        "status": "Insufficient evidence",
        "finding": "Insufficient evidence",
        "recommendation": "Insufficient evidence",
        "confidence": "Insufficient evidence",
        "expected_gain": "Insufficient evidence",
        "files": list(files),
        "evidence": {"reason": reason},
    }


def _python_sources():
    for path in REPO_ROOT.rglob("*.py"):
        parts = set(path.parts)
        if "venv" in parts or "__pycache__" in parts or "archive" in parts:
            continue
        yield path


def _duplicate_metric_implementations():
    duplicates = []
    allowed = REPO_ROOT / "pipeline" / "calibration_common.py"
    for path in _python_sources():
        if path == allowed:
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for name in CORE_METRIC_DEFINITIONS:
            if re.search(rf"^def {name}\(", text, re.MULTILINE):
                duplicates.append({"file": str(path.relative_to(REPO_ROOT)), "function": name})
    return duplicates


def _registry_integrity():
    problems = []
    root = model_registry.REGISTRY_DIR
    if not Path(root).exists():
        return [{"path": str(root), "problem": "registry directory missing"}]
    for model_dir in sorted(Path(root).iterdir()):
        if not model_dir.is_dir():
            continue
        for version_dir in sorted(model_dir.iterdir()):
            if not version_dir.is_dir():
                continue
            meta_path = version_dir / "metadata.json"
            if not meta_path.exists():
                problems.append({"path": str(version_dir), "problem": "metadata.json missing"})
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                problems.append({"path": str(version_dir), "problem": f"metadata.json unreadable: {exc}"})
                continue
            if not (version_dir / "model.pkl").exists():
                problems.append({"path": str(version_dir), "problem": "model.pkl missing"})
            for key in ("feature_list", "metrics", "dataset_path"):
                if meta.get(key) is None:
                    problems.append({"path": str(version_dir), "problem": f"metadata missing '{key}'"})
    return problems


def _shadow_version_stamp_check(db_path):
    import sqlite3

    if not Path(db_path).exists():
        return {"rows": 0, "stamped": 0, "unknown_versions": [], "column_present": False}
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(shadow_v2_predictions)").fetchall()}
        if not columns:
            return {"rows": 0, "stamped": 0, "unknown_versions": [], "column_present": False}
        total = conn.execute("SELECT COUNT(*) FROM shadow_v2_predictions").fetchone()[0]
        if "model_version" not in columns:
            return {"rows": int(total), "stamped": 0, "unknown_versions": [], "column_present": False}
        rows = conn.execute(
            "SELECT model_name, model_version FROM shadow_v2_predictions WHERE model_version IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    unknown = []
    for model_name, version in rows:
        registered = model_registry.list_versions(model_name or "")
        if version not in registered:
            unknown.append({"model_name": model_name, "model_version": version})
    return {"rows": int(total), "stamped": len(rows), "unknown_versions": unknown, "column_present": True}


def self_consistency_checks(model_name, target, version, metadata, model, y_true, calibration_rows,
                            db_path="database/picks.db"):
    from pipeline import feature_store

    checks = []
    trained_features = list(metadata.get("feature_list") or [])
    live_features = list(feature_store.get_feature_list(target))

    checks.append({
        "check": "feature_list_matches_trained_model",
        "status": "PASS" if set(trained_features) == set(live_features) else "FAIL",
        "detail": (
            f"champion {model_name}/{version} trained on {len(trained_features)} features; "
            f"feature_store.get_feature_list('{target}') returns {len(live_features)}; "
            f"missing_live={sorted(set(trained_features) - set(live_features))}; "
            f"extra_live={sorted(set(live_features) - set(trained_features))}"
        ),
    })
    checks.append({
        "check": "feature_order_matches_trained_model",
        "status": "PASS" if trained_features == live_features else "FAIL",
        "detail": (
            f"ordered comparison over {len(trained_features)} names; first divergence index "
            f"{next((i for i, (a, b) in enumerate(zip(trained_features, live_features)) if a != b), -1)}"
        ),
    })

    trained_schema = metadata.get("feature_schema_version")
    live_schema = feature_store.get_schema_version()
    schema_match = trained_schema == live_schema
    checks.append({
        "check": "feature_schema_version_consistency",
        "status": "PASS" if schema_match else "INFO",
        "detail": (
            f"champion recorded feature_schema_version={trained_schema}, live feature_store reports {live_schema}; "
            f"names+order identical={trained_features == live_features} "
            f"(version bump without name/order change is not a functional break)"
        ),
    })

    resolved_champion = model_registry.get_champion_version(model_name)
    loaded = model is not None and hasattr(model, "predict_proba")
    checks.append({
        "check": "champion_model_loaded",
        "status": "PASS" if (resolved_champion is not None and loaded) else "FAIL",
        "detail": (
            f"get_champion_version('{model_name}')={resolved_champion}; diagnostics running on {version}; "
            f"model object={type(model).__name__} predict_proba={loaded}"
        ),
    })

    bucket_total = int(sum(r["n"] for r in calibration_rows)) if calibration_rows else 0
    checks.append({
        "check": "calibration_computed_on_full_test_set",
        "status": "PASS" if bucket_total == len(y_true) else "FAIL",
        "detail": f"calibration buckets cover {bucket_total} rows; evaluation set holds {len(y_true)} rows",
    })

    shadow = _shadow_version_stamp_check(db_path)
    if shadow["rows"] == 0:
        shadow_status = "INFO"
        shadow_detail = "shadow_v2_predictions holds 0 rows; nothing to verify"
    elif not shadow["column_present"]:
        shadow_status = "FAIL"
        shadow_detail = (
            f"shadow_v2_predictions holds {shadow['rows']} rows but has no model_version column, "
            f"so shadow predictions cannot be attributed to a registered model version"
        )
    elif shadow["unknown_versions"]:
        shadow_status = "FAIL"
        shadow_detail = f"{len(shadow['unknown_versions'])} shadow rows stamp versions absent from the registry: {shadow['unknown_versions'][:5]}"
    else:
        shadow_status = "PASS"
        shadow_detail = f"{shadow['stamped']}/{shadow['rows']} shadow rows stamp a registered model version"
    checks.append({"check": "shadow_uses_registered_model_version", "status": shadow_status, "detail": shadow_detail})

    problems = _registry_integrity()
    checks.append({
        "check": "no_stale_registry_entries",
        "status": "PASS" if not problems else "FAIL",
        "detail": (f"{len(problems)} registry problems: {problems[:5]}" if problems
                   else f"all {len(model_registry.list_versions(model_name))} {model_name} versions plus every other registry entry carry readable metadata.json and model.pkl"),
    })

    duplicates = _duplicate_metric_implementations()
    checks.append({
        "check": "no_duplicated_metric_implementations",
        "status": "PASS" if not duplicates else "FAIL",
        "detail": (f"reimplementations found outside pipeline/calibration_common.py: {duplicates}" if duplicates
                   else f"scanned {len(list(_python_sources()))} python files for {len(CORE_METRIC_DEFINITIONS)} core metric definitions; only pipeline/calibration_common.py defines them"),
    })

    failures = [c for c in checks if c["status"] == "FAIL"]
    return {
        "checks": checks,
        "failures": failures,
        "failure_count": len(failures),
        "passed": not failures,
        "recommendation": (
            recommendation_block(
                f"{len(failures)} of {len(checks)} self-consistency checks failed: "
                + "; ".join(f"{c['check']} ({c['detail']})" for c in failures),
                f"Resolve the {len(failures)} failing invariant(s) before trusting any downstream diagnostics number in this report.",
                "High",
                "High",
                ["pipeline/engineering_audit.py", "pipeline/model_registry.py", "services/shadow_inference_service.py"],
                {"failed_checks": [c["check"] for c in failures]},
            )
            if failures else
            recommendation_block(
                f"All {len(checks)} self-consistency checks passed for {model_name}/{version} "
                f"({len(trained_features)} features, schema trained={trained_schema} live={live_schema}, "
                f"calibration covers {bucket_total}/{len(y_true)} rows).",
                "No corrective action required; downstream diagnostics in this report rest on verified invariants.",
                "High",
                "Low",
                ["pipeline/engineering_audit.py"],
                {"checks_passed": len(checks)},
            )
        ),
    }


def fold_importance_stability(model_factory, X, y, feature_names, splits,
                              n_repeats=FOLD_PERMUTATION_REPEATS, random_state=42):
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y)).reset_index(drop=True)
    fold_ranks = {name: [] for name in feature_names}
    usable = 0
    for train_idx, val_idx in splits:
        if len(set(y.iloc[train_idx].tolist())) < 2 or len(set(y.iloc[val_idx].tolist())) < 2:
            continue
        model = model_factory()
        model.fit(X.iloc[train_idx][feature_names], y.iloc[train_idx])
        result = permutation_importance(
            model, X.iloc[val_idx][feature_names], y.iloc[val_idx],
            n_repeats=n_repeats, random_state=random_state, scoring="neg_log_loss",
        )
        order = sorted(zip(feature_names, result.importances_mean), key=lambda r: -r[1])
        for rank, (name, _) in enumerate(order):
            fold_ranks[name].append(rank + 1)
        usable += 1

    max_std = (len(feature_names) - 1) / 2.0 if len(feature_names) > 1 else 1.0
    rows = []
    for name in feature_names:
        ranks = fold_ranks[name]
        if len(ranks) < 2:
            rows.append({"feature": name, "fold_ranks": ranks, "fold_count": len(ranks),
                         "rank_std": None, "stability": None})
            continue
        std = float(np.std(ranks, ddof=1))
        rows.append({
            "feature": name,
            "fold_ranks": ranks,
            "fold_count": len(ranks),
            "rank_std": round(std, 3),
            "stability": round(_clamp(1.0 - std / max_std), 4),
        })

    pairwise = []
    matrix = [[fold_ranks[name][i] for name in feature_names] for i in range(usable)]
    for i in range(usable):
        for j in range(i + 1, usable):
            rho = spearmanr(matrix[i], matrix[j]).statistic
            if rho == rho:
                pairwise.append(float(rho))
    return {
        "rows": rows,
        "fold_count": usable,
        "mean_pairwise_spearman": round(float(np.mean(pairwise)), 4) if pairwise else None,
        "n_repeats": n_repeats,
    }


def outcome_correlations(X, y_true, feature_names):
    y = np.asarray(y_true, dtype=float)
    out = {}
    for name in feature_names:
        values = X[name].to_numpy(dtype=float)
        if np.std(values) == 0 or np.std(y) == 0:
            out[name] = 0.0
            continue
        out[name] = round(float(np.corrcoef(values, y)[0, 1]), 4)
    return out


def _confidence_from_agreement(agreement, methods):
    if methods < 2 or agreement is None:
        return "Low"
    if agreement >= AGREEMENT_HIGH and methods >= 3:
        return "High"
    if agreement >= AGREEMENT_MEDIUM:
        return "Medium"
    return "Low"


def _verdict(row, n_features, n_rows, fold_count):
    mean_rank = row["mean_rank"]
    stability = row["stability"]
    confidence = row["confidence"]
    lofo = row["lofo_log_loss_delta"]
    corr = row["outcome_correlation"]
    if n_rows < MIN_ROWS_FOR_VERDICT or fold_count < MIN_FOLDS_FOR_STABILITY or mean_rank is None or stability is None:
        return "NOT ENOUGH DATA", (
            f"evaluation rows={n_rows} (threshold {MIN_ROWS_FOR_VERDICT}), walk-forward folds={fold_count} "
            f"(threshold {MIN_FOLDS_FOR_STABILITY}), mean_rank={mean_rank}, stability={stability}"
        )
    bottom_tier = mean_rank >= BOTTOM_TIER_FRACTION * n_features
    mid_tier = mean_rank >= MID_TIER_FRACTION * n_features
    if lofo is not None and lofo >= LOFO_KEEP_DELTA:
        return "KEEP", (
            f"walk-forward ablation over {fold_count} folds regressed log loss by {lofo:+.6f} when this feature was "
            f"dropped, mean_rank {mean_rank}/{n_features}, stability {stability}, agreement {confidence}"
        )
    if bottom_tier and stability >= STABILITY_STABLE and confidence == "High" and lofo is not None and lofo <= LOFO_REMOVE_DELTA:
        return "REMOVE", (
            f"mean_rank {mean_rank}/{n_features} is bottom-{int((1 - BOTTOM_TIER_FRACTION) * 100)}%, stability "
            f"{stability} ≥ {STABILITY_STABLE}, method agreement High, and a real walk-forward ablation retrain over "
            f"{fold_count} folds changed log loss by {lofo:+.6f} (no regression)"
        )
    if corr is not None and abs(corr) >= OUTCOME_CORR_SIGNAL and mid_tier:
        return "RE-ENCODE", (
            f"point-biserial correlation with outcome {corr:+.4f} exceeds {OUTCOME_CORR_SIGNAL} but mean_rank "
            f"{mean_rank}/{n_features} sits below the median, so the raw encoding carries signal the model is not "
            f"extracting (ablation delta {lofo:+.6f})" if lofo is not None else
            f"point-biserial correlation with outcome {corr:+.4f} exceeds {OUTCOME_CORR_SIGNAL} but mean_rank "
            f"{mean_rank}/{n_features} sits below the median"
        )
    if stability < STABILITY_UNSTABLE:
        return "INVESTIGATE", (
            f"rank stability {stability} < {STABILITY_UNSTABLE} across {fold_count} walk-forward folds "
            f"(fold ranks {row['fold_ranks']}), mean_rank {mean_rank}/{n_features}, agreement {confidence}"
        )
    return "KEEP", (
        f"mean_rank {mean_rank}/{n_features}, stability {stability}, agreement {confidence}, walk-forward ablation "
        f"delta {lofo:+.6f}" if lofo is not None else
        f"mean_rank {mean_rank}/{n_features}, stability {stability}, agreement {confidence}"
    )


def feature_engineering_table(combined_rows, shap_rows, stability_result, correlations, n_rows):
    shap_by = {r["feature"]: r for r in (shap_rows or [])}
    stability_by = {r["feature"]: r for r in stability_result["rows"]}
    n_features = len(combined_rows)
    max_std = (n_features - 1) / 2.0 if n_features > 1 else 1.0
    rows = []
    for base in combined_rows:
        name = base["feature"]
        ranks = [base[k] for k in ("gain_rank", "permutation_rank", "shap_rank", "lofo_rank") if base[k] is not None]
        agreement = round(_clamp(1.0 - float(np.std(ranks, ddof=1)) / max_std), 4) if len(ranks) >= 2 else None
        confidence = _confidence_from_agreement(agreement, len(ranks))
        shap_row = shap_by.get(name, {})
        value_corr = shap_row.get("value_shap_corr")
        if value_corr is None:
            direction = "UNKNOWN"
        elif value_corr >= SHAP_DIRECTION_THRESHOLD:
            direction = "POSITIVE"
        elif value_corr <= -SHAP_DIRECTION_THRESHOLD:
            direction = "NEGATIVE"
        else:
            direction = "MIXED"
        stability_row = stability_by.get(name, {})
        row = dict(base)
        row.update({
            "stability": stability_row.get("stability"),
            "rank_std_across_folds": stability_row.get("rank_std"),
            "fold_ranks": stability_row.get("fold_ranks"),
            "fold_count": stability_row.get("fold_count", 0),
            "outcome_correlation": correlations.get(name),
            "mean_shap": shap_row.get("mean_shap"),
            "value_shap_corr": value_corr,
            "direction": direction,
            "method_agreement": agreement,
            "methods_available": len(ranks),
            "confidence": confidence,
        })
        verdict, reason = _verdict(row, n_features, n_rows, stability_row.get("fold_count", 0))
        row["engineering_verdict"] = verdict
        row["verdict_reason"] = reason
        rows.append(row)
    return rows


def feature_importance_recommendation(rows, stability_result, n_rows):
    if not rows:
        return insufficient_evidence_block("no combined importance rows were produced", ["pipeline/train_common.py"])
    counts = {}
    for row in rows:
        counts[row["engineering_verdict"]] = counts.get(row["engineering_verdict"], 0) + 1
    if counts.get("NOT ENOUGH DATA", 0) == len(rows):
        return insufficient_evidence_block(
            f"every feature resolved to NOT ENOUGH DATA: evaluation rows={n_rows} (threshold {MIN_ROWS_FOR_VERDICT}), "
            f"walk-forward folds={stability_result['fold_count']} (threshold {MIN_FOLDS_FOR_STABILITY})",
            ["pipeline/engineering_audit.py", "pipeline/train_common.py"],
        )
    actionable = [r for r in rows if r["engineering_verdict"] in ("REMOVE", "RE-ENCODE", "INVESTIGATE")]
    unstable = [r for r in rows if r["stability"] is not None and r["stability"] < STABILITY_UNSTABLE]
    mean_stability = float(np.mean([r["stability"] for r in rows if r["stability"] is not None])) if rows else 0.0
    gain = len(actionable) / len(rows)
    return recommendation_block(
        f"Across {len(rows)} features over {stability_result['fold_count']} walk-forward folds (mean pairwise "
        f"Spearman {stability_result['mean_pairwise_spearman']}, mean stability {mean_stability:.3f}), verdicts are "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        + f"; {len(unstable)} features fall below stability {STABILITY_UNSTABLE}.",
        (
            f"Action the {len(actionable)} non-KEEP features first: "
            + "; ".join(f"{r['feature']} → {r['engineering_verdict']} ({r['verdict_reason']})" for r in actionable[:5])
            if actionable else
            f"No feature met a REMOVE/RE-ENCODE/INVESTIGATE threshold; keep the current {len(rows)}-feature set."
        ),
        _band(_clamp(mean_stability)) if actionable else "Medium",
        _band(gain),
        ["pipeline/train_common.py", "pipeline/engineering_audit.py", "pipeline/feature_store.py"],
        {"verdict_counts": counts, "mean_stability": round(mean_stability, 4),
         "mean_pairwise_spearman": stability_result["mean_pairwise_spearman"]},
    )


def calibration_report(y_true, y_prob, raw_rows, merged_rows, min_bucket_n=DEFAULT_MIN_BUCKET_N, dates=None):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    total = len(y_true)
    enriched = []
    for row in merged_rows:
        mask = (y_prob >= row["bin_lower"]) & (y_prob <= row["bin_upper"] if row["bin_upper"] >= 1.0 else y_prob < row["bin_upper"])
        n = int(mask.sum())
        if n == 0:
            continue
        actual = float(y_true[mask].mean())
        item = dict(row)
        item.update({
            "outcome_variance": round(float(np.var(y_true[mask])), 6),
            "bernoulli_variance": round(actual * (1 - actual), 6),
            "predicted_variance": round(float(np.var(y_prob[mask])), 6),
            "gap": round(float(row["avg_predicted"] - row["actual_rate"]), 4),
            "abs_gap": round(abs(float(row["avg_predicted"] - row["actual_rate"])), 4),
            "weight": round(n / total, 4),
            "weighted_gap": round(abs(float(row["avg_predicted"] - row["actual_rate"])) * n / total, 6),
            "outside_ci": bool(row["avg_predicted"] < row["actual_ci_lower"] or row["avg_predicted"] > row["actual_ci_upper"]),
        })
        enriched.append(item)

    missing_fields = sorted({
        field for row in raw_rows for field in ("n", "actual_ci_lower", "actual_ci_upper", "reliable")
        if field not in row
    })
    unreliable_raw = [r["bin"] for r in raw_rows if not r["reliable"]]
    unreliable_merged = [r["bin"] for r in merged_rows if not r["reliable"]]

    ranked = sorted(enriched, key=lambda r: -r["weighted_gap"])
    top_issues = [r for r in ranked if r["weighted_gap"] > 0][:5]
    significant = [r for r in enriched if r["outside_ci"]]
    expected_ece_reduction = round(float(sum(r["weighted_gap"] for r in significant)), 6)

    root_causes = []
    if top_issues:
        centres = [(r["bin_lower"] + r["bin_upper"]) / 2 for r in top_issues]
        weights = [r["weighted_gap"] for r in top_issues]
        centre = float(np.average(centres, weights=weights))
        overall_centre = float(np.average(y_prob))
        centre_se = float(np.std(y_prob, ddof=1) / np.sqrt(total)) if total > 1 else 0.0
        separation_z = abs(centre - overall_centre) / centre_se if centre_se > 0 else None
        clustered = separation_z is not None and separation_z >= WILSON_Z_95
        root_causes.append({
            "pattern": f"weighted miscalibration mass centres at predicted probability {centre:.3f} versus a mean "
                       f"prediction of {overall_centre:.3f}",
            "cause": (
                f"the miscalibration centre sits {abs(centre - overall_centre):.4f} "
                f"{'above' if centre > overall_centre else 'below'} the mean prediction, which is "
                f"{separation_z:.2f} standard errors of the mean prediction ({centre_se:.5f}) and therefore "
                f"separable from the prediction distribution at the {int((1 - ALPHA) * 100)}% level"
                if clustered else
                f"the miscalibration centre sits {abs(centre - overall_centre):.4f} from the mean prediction, "
                f"{'' if separation_z is None else f'{separation_z:.2f} standard errors, '}which does not exceed "
                f"{WILSON_Z_95:.2f} standard errors of the mean prediction, so no location-specific pattern is "
                f"established by this evaluation set"
            ),
            "corroborated": bool(clustered),
            "evidence": {"weighted_gap_centre": round(centre, 4), "mean_prediction": round(overall_centre, 4),
                         "mean_prediction_standard_error": round(centre_se, 6),
                         "separation_z": round(separation_z, 3) if separation_z is not None else None,
                         "z_threshold": round(float(WILSON_Z_95), 3)},
        })
    if dates is not None and len(dates) == total and total >= 2 * min_bucket_n:
        order = np.argsort(np.asarray(dates, dtype=str))
        half = total // 2
        early, late = order[:half], order[half:]
        ece_early = expected_calibration_error(y_true[early], y_prob[early])
        ece_late = expected_calibration_error(y_true[late], y_prob[late])
        observed_delta = (abs(ece_late - ece_early)
                          if ece_early is not None and ece_late is not None else None)
        permutation_p = None
        null_p95 = None
        if observed_delta is not None:
            rng = np.random.default_rng(RANDOM_SEED)
            draws = []
            for _ in range(NULL_SIMULATIONS):
                shuffled = rng.permutation(total)
                a = expected_calibration_error(y_true[shuffled[:half]], y_prob[shuffled[:half]])
                b = expected_calibration_error(y_true[shuffled[half:]], y_prob[shuffled[half:]])
                if a is not None and b is not None:
                    draws.append(abs(b - a))
            if draws:
                draws = np.asarray(draws, dtype=float)
                permutation_p = float((int((draws >= observed_delta).sum()) + 1) / (len(draws) + 1))
                null_p95 = float(np.quantile(draws, 1 - ALPHA))
        drifted = permutation_p is not None and permutation_p < ALPHA
        root_causes.append({
            "pattern": f"ECE on the earlier half of the evaluation window is {ece_early:.4f} versus {ece_late:.4f} on "
                       f"the later half ({total} rows split chronologically)",
            "cause": (
                f"the chronological split changes ECE by {ece_late - ece_early:+.4f}, larger than "
                f"{100 * (1 - permutation_p):.1f}% of the {NULL_SIMULATIONS} random splits of the same rows "
                f"(random-split 95th percentile {null_p95:.4f}), so the difference is not explained by which rows "
                f"landed in which half"
                if drifted else
                f"the chronological split changes ECE by "
                f"{0.0 if observed_delta is None else ece_late - ece_early:+.4f}, which random splits of the same "
                f"rows reproduce with probability "
                f"{'undetermined' if permutation_p is None else f'{permutation_p:.3f}'}, so no time-dependent "
                f"pattern is established by this evaluation set"
            ),
            "corroborated": bool(drifted),
            "evidence": {"ece_first_half": round(ece_early, 4) if ece_early is not None else None,
                         "ece_second_half": round(ece_late, 4) if ece_late is not None else None,
                         "permutation_p_value": round(permutation_p, 6) if permutation_p is not None else None,
                         "random_split_p95_delta": round(null_p95, 6) if null_p95 is not None else None,
                         "permutations": NULL_SIMULATIONS},
        })

    fixes = []
    for issue in top_issues[:3]:
        fixes.append({
            "bucket": issue["bin"],
            "fix": (
                f"Refit the probability calibrator with additional resolution in {issue['bin']}: predicted "
                f"{issue['avg_predicted']:.4f} versus actual {issue['actual_rate']:.4f} over n={issue['n']} "
                f"(Wilson 95% CI {issue['actual_ci_lower']:.4f}–{issue['actual_ci_upper']:.4f}, "
                f"{'predicted rate falls outside the CI' if issue['outside_ci'] else 'predicted rate stays inside the CI'})"
            ),
            "justifying_metric": {"abs_gap": issue["abs_gap"], "n": issue["n"], "weight": issue["weight"],
                                  "weighted_gap": issue["weighted_gap"], "outside_ci": issue["outside_ci"]},
            "expected_impact_ece_points": issue["weighted_gap"],
        })

    ece = expected_calibration_error(y_true, y_prob)
    if not enriched:
        rec = insufficient_evidence_block(
            f"no calibration bucket survived merging at min N={min_bucket_n} over {total} evaluation rows",
            ["pipeline/calibration_common.py"],
        )
    else:
        rec = recommendation_block(
            f"Overall ECE is {ece:.4f} across {len(enriched)} merged buckets covering {total} rows; the largest "
            f"weighted miscalibration is {top_issues[0]['bin']} (predicted {top_issues[0]['avg_predicted']:.4f} vs "
            f"actual {top_issues[0]['actual_rate']:.4f}, n={top_issues[0]['n']}, weighted gap "
            f"{top_issues[0]['weighted_gap']:.6f}); {len(significant)} bucket(s) place the predicted rate outside "
            f"their Wilson 95% CI." if top_issues else
            f"Overall ECE is {ece:.4f} across {len(enriched)} merged buckets covering {total} rows with no positive "
            f"weighted miscalibration gap.",
            (f"Recalibrate targeting {', '.join(r['bin'] for r in significant)}; eliminating the statistically "
             f"significant gaps would lower ECE by up to {expected_ece_reduction:.6f} "
             f"({expected_ece_reduction / ece * 100:.1f}% of current ECE)."
             if significant and ece else
             f"No bucket is miscalibrated beyond its Wilson 95% CI at n≥{min_bucket_n}; leave the calibrator as-is."),
            "High" if significant and all(r["n"] >= min_bucket_n for r in significant) else "Medium",
            _band(_relative_impact("ece", expected_ece_reduction, {"ece": ece})),
            ["pipeline/calibration_common.py", "pipeline/train_moneyline.py", "pipeline/diagnostics.py"],
            {"ece": round(ece, 6) if ece is not None else None,
             "expected_ece_reduction": expected_ece_reduction,
             "significant_buckets": [r["bin"] for r in significant]},
        )

    return {
        "buckets": enriched,
        "field_audit": {
            "required_fields_present": not missing_fields,
            "missing_fields": missing_fields,
            "min_bucket_n": min_bucket_n,
            "raw_unreliable_buckets": unreliable_raw,
            "merged_unreliable_buckets": unreliable_merged,
            "auto_merge_applied": len(merged_rows) <= len(raw_rows),
            "auto_merge_resolved_all": not unreliable_merged,
        },
        "top_issues": top_issues,
        "null_test": _ece_null_test(y_true, y_prob),
        "root_causes": root_causes,
        "suggested_fixes": fixes,
        "expected_impact_ece_points": expected_ece_reduction,
        "recommendation": rec,
    }


def residual_analysis(y_true, y_prob, n_deciles=10):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    residuals = y_true - y_prob
    n = len(residuals)
    mean = float(residuals.mean())
    std = float(residuals.std(ddof=1)) if n > 1 else 0.0
    se = std / np.sqrt(n) if n > 1 and std > 0 else None
    edges = np.quantile(y_prob, np.linspace(0, 1, n_deciles + 1))
    edges = np.unique(edges)
    idx = np.clip(np.digitize(y_prob, edges) - 1, 0, len(edges) - 2)
    deciles = []
    for b in range(len(edges) - 1):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        block = residuals[mask]
        block_mean = float(block.mean())
        block_se = float(block.std(ddof=1) / np.sqrt(count)) if count > 1 and block.std(ddof=1) > 0 else None
        deciles.append({
            "range": f"{edges[b]:.4f}-{edges[b+1]:.4f}",
            "n": count,
            "mean_residual": round(block_mean, 5),
            "abs_mean_residual": round(abs(block_mean), 5),
            "standard_error": round(block_se, 6) if block_se else None,
            "z": round(block_mean / block_se, 3) if block_se else None,
            "p_value": round(_normal_two_sided_p(block_mean / block_se), 6) if block_se else None,
        })
    tested = [d for d in deciles if d["p_value"] is not None]
    bonferroni_alpha = ALPHA / len(tested) if tested else None
    for row in deciles:
        row["significant"] = bool(row["p_value"] is not None and bonferroni_alpha is not None
                                  and row["p_value"] < bonferroni_alpha)
        row["bonferroni_alpha"] = round(bonferroni_alpha, 6) if bonferroni_alpha else None
    significant = sorted([d for d in deciles if d["significant"]], key=lambda d: d["p_value"])
    worst = max(deciles, key=lambda d: d["abs_mean_residual"]) if deciles else None
    bias_z = mean / se if se else None

    current_log_loss = log_loss_score(y_true, y_prob)
    shifted = np.clip(y_prob + mean, 1e-9, 1 - 1e-9)
    bias_gain = (current_log_loss - log_loss_score(y_true, shifted)) if current_log_loss is not None else None
    recentred = y_prob.copy()
    for b in range(len(edges) - 1):
        mask = idx == b
        if mask.sum():
            recentred[mask] = recentred[mask] + float(residuals[mask].mean())
    recentred = np.clip(recentred, 1e-9, 1 - 1e-9)
    decile_gain = (current_log_loss - log_loss_score(y_true, recentred)) if current_log_loss is not None else None
    return {
        "n": n,
        "mean_residual": round(mean, 5),
        "std_residual": round(std, 5),
        "standard_error": round(float(se), 5) if se else None,
        "bias_z": round(bias_z, 3) if bias_z is not None else None,
        "bias_p_value": round(_normal_two_sided_p(bias_z), 6) if bias_z is not None else None,
        "bias_z_threshold": round(float(WILSON_Z_95), 3),
        "biased": bool(bias_z is not None and abs(bias_z) >= WILSON_Z_95),
        "deciles": deciles,
        "worst_decile": worst,
        "current_log_loss": round(float(current_log_loss), 6) if current_log_loss is not None else None,
        "bias_correction_log_loss_gain": round(float(bias_gain), 6) if bias_gain is not None else None,
        "decile_correction_log_loss_gain": round(float(decile_gain), 6) if decile_gain is not None else None,
        "significant_deciles": significant,
        "bonferroni_alpha": round(bonferroni_alpha, 6) if bonferroni_alpha else None,
        "decile_test_method": ("two-sided z-test of each probability decile's mean residual against zero, "
                               "Bonferroni-corrected across the deciles actually tested"),
    }


def prediction_distribution_stats(y_prob):
    y_prob = np.asarray(y_prob, dtype=float)
    return {
        "n": int(len(y_prob)),
        "mean": round(float(y_prob.mean()), 5),
        "std": round(float(y_prob.std(ddof=1)), 5) if len(y_prob) > 1 else 0.0,
        "min": round(float(y_prob.min()), 5),
        "max": round(float(y_prob.max()), 5),
        "p05": round(float(np.quantile(y_prob, 0.05)), 5),
        "p95": round(float(np.quantile(y_prob, 0.95)), 5),
        "range": round(float(y_prob.max() - y_prob.min()), 5),
    }


def segment_analysis(segments, y_true, y_prob, column, min_n=MIN_SEGMENT_N):
    if segments is None or column not in segments.columns:
        return {"available": False, "reason": f"column '{column}' is absent from the evaluation frame",
                "column": column, "rows": []}
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    values = segments[column].astype(str).to_numpy()
    eligible_values = [value for value in sorted(set(values)) if int((values == value).sum()) >= min_n]
    tests = len(eligible_values)
    if tests == 0:
        return {
            "available": False,
            "reason": (f"no value of '{column}' reached the {min_n}-row minimum needed for a statistically meaningful "
                       f"segment estimate across {len(y_true)} evaluation rows"),
            "column": column, "min_n": min_n, "rows": [], "significant": [],
        }
    family_alpha = ALPHA / tests
    z_adjusted = float(norm.ppf(1.0 - family_alpha / 2.0))
    rows = []
    for value in eligible_values:
        mask = values == value
        n = int(mask.sum())
        residual = float((y_true[mask] - y_prob[mask]).mean())
        low, high = wilson_interval(int(y_true[mask].sum()), n, z=z_adjusted)
        predicted = float(y_prob[mask].mean())
        z_stat = _proportion_z(int(y_true[mask].sum()), n, min(max(predicted, 1e-6), 1 - 1e-6))
        rows.append({
            "segment": value,
            "n": n,
            "mean_predicted": round(predicted, 4),
            "actual_rate": round(float(y_true[mask].mean()), 4),
            "mean_residual": round(residual, 4),
            "ci_lower": round(low, 4),
            "ci_upper": round(high, 4),
            "p_value": round(_normal_two_sided_p(z_stat), 6) if z_stat is not None else None,
            "outside_ci": bool(predicted < low or predicted > high),
        })
    return {
        "available": True,
        "reason": None,
        "column": column,
        "min_n": min_n,
        "tests": tests,
        "family_alpha": round(family_alpha, 6),
        "z_adjusted": round(z_adjusted, 4),
        "test_method": (f"Wilson interval on each segment's actual rate at a Bonferroni-corrected level "
                        f"({int((1 - ALPHA) * 100)}% family-wise across {tests} segments of '{column}')"),
        "rows": sorted(rows, key=lambda r: -abs(r["mean_residual"])),
        "significant": [r for r in rows if r["outside_ci"]],
    }


def _source_lines(relative_path):
    path = REPO_ROOT / relative_path
    if not path.exists() or not path.is_file():
        return 0
    try:
        return sum(1 for line in path.read_text().splitlines() if line.strip())
    except OSError:
        return 0


def effort_kloc(files):
    measured = {f: _source_lines(f) for f in files}
    total = sum(measured.values())
    return max(total / 1000.0, MIN_EFFORT_KLOC), measured


def _cause(cause_id, title, evidence, evidence_probability, impact_metric, impact_value, fix, files, remediation,
           scales):
    impact = _relative_impact(impact_metric, impact_value, scales)
    effort, measured = effort_kloc(files)
    return {
        "id": cause_id,
        "title": title,
        "evidence": evidence,
        "evidence_probability": round(float(evidence_probability), 6),
        "confidence": _confidence_label(evidence_probability),
        "gain_metric": impact_metric,
        "estimated_gain_value": impact_value,
        "estimated_gain_score": round(impact, 4),
        "estimated_gain_band": _band(impact),
        "effort_kloc": round(effort, 4),
        "effort_measured_lines": measured,
        "expected_value_per_kloc": round(impact * float(evidence_probability) / effort, 4),
        "suggested_fix": fix,
        "related_files": list(files),
        "remediation_class": remediation,
    }


def root_cause_engine(metrics, feature_rows, calibration, residuals, distribution, segment_results,
                      clv_summary, redundancy_rows, degraded_rate, stability_result, y_true, y_prob, scales,
                      max_causes=10):
    causes = []
    n = metrics.get("n") or 0
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)

    auc_test = _auc_test(metrics.get("auc"), y_true)
    if auc_test is not None and auc_test["ci_lower"] <= 0.5:
        headroom = auc_test["ci_upper"] - 0.5
        unestablished = _clamp(1.0 - (auc_test["auc"] - 0.5) / headroom) if headroom > 0 else 1.0
        causes.append(_cause(
            "weak_discrimination",
            f"AUC {auc_test['auc']:.4f} on {n} held-out rows has a {int((1 - ALPHA) * 100)}% interval of "
            f"{auc_test['ci_lower']:.4f}–{auc_test['ci_upper']:.4f} (Hanley-McNeil standard error "
            f"{auc_test['standard_error']:.5f} over {auc_test['positives']} positives and {auc_test['negatives']} "
            f"negatives), so the interval still contains chance (0.5) at p={auc_test['p_value']:.4f}; the ranking "
            f"achieved on this evaluation set is not separable from no ranking at all.",
            auc_test,
            auc_test["p_value"],
            "rate", unestablished,
            f"The measured ranking edge is {auc_test['auc'] - 0.5:+.4f} against a sampling error of "
            f"{auc_test['standard_error']:.5f}; either the feature set carries no separable ranking signal on these "
            f"{n} rows or the evaluation set cannot resolve it, and the two are not distinguishable from this run.",
            ["pipeline/feature_store.py", "pipeline/build_features_v2.py", "pipeline/train_moneyline.py"],
            "feature_engineering", scales,
        ))

    ece = metrics.get("ece")
    null_test = calibration.get("null_test")
    if ece is not None and null_test is not None and null_test["p_value"] < ALPHA:
        significant = calibration["recommendation"]["evidence"].get("significant_buckets", []) if calibration["recommendation"]["status"] == "OK" else []
        causes.append(_cause(
            "calibration_error",
            f"Measured ECE {ece:.4f} exceeds the {null_test['null_p95_ece']:.4f} 95th percentile of the "
            f"{null_test['simulations']} calibration errors produced when outcomes are redrawn from the model's own "
            f"probabilities (null mean {null_test['null_mean_ece']:.4f}, p={null_test['p_value']:.4f}), so the gap is "
            f"larger than sampling noise alone produces at n={n}; {len(significant)} merged bucket(s) place their "
            f"predicted rate outside a {int((1 - ALPHA) * 100)}% Wilson interval "
            f"({', '.join(significant) if significant else 'none individually'}).",
            {"ece": round(ece, 5), "null_test": null_test, "significant_buckets": significant,
             "recoverable_ece": calibration["expected_impact_ece_points"]},
            1.0 - null_test["p_value"],
            "ece", calibration["expected_impact_ece_points"],
            (f"Refitting the calibrator on the {len(significant)} statistically significant bucket(s) removes at most "
             f"{calibration['expected_impact_ece_points']:.6f} ECE points, "
             f"{calibration['expected_impact_ece_points'] / ece * 100:.1f}% of the measured {ece:.4f}."
             if calibration["expected_impact_ece_points"] > 0 else
             f"No merged bucket places its predicted rate outside its Wilson interval at min N="
             f"{min(b['n'] for b in calibration['buckets'])}, so the excess over the null is not attributable to any "
             f"single bucket of the {len(calibration['buckets'])} measured."),
            ["pipeline/calibration_common.py", "pipeline/train_moneyline.py"],
            "retrain", scales,
        ))

    span = distribution["p95"] - distribution["p05"]
    base_low, base_high = wilson_interval(int(y_true.sum()), len(y_true))
    resolution_floor = float(base_high - base_low)
    if len(y_true) and span < resolution_floor:
        collapse_probability = _bootstrap_fraction(
            [y_true, y_prob],
            lambda arrays: float(np.quantile(arrays[1], 0.95) - np.quantile(arrays[1], 0.05))
            < float(wilson_interval(int(arrays[0].sum()), len(arrays[0]))[1]
                    - wilson_interval(int(arrays[0].sum()), len(arrays[0]))[0]),
        )
        causes.append(_cause(
            "prediction_collapse",
            f"The central 90% of predictions spans {span:.5f} ({distribution['p05']:.4f}–{distribution['p95']:.4f}, "
            f"standard deviation {distribution['std']:.5f} over {distribution['n']} rows), which is narrower than the "
            f"{resolution_floor:.5f} width of the {int((1 - ALPHA) * 100)}% Wilson interval on the base rate at this "
            f"sample size, so no two predictions in that span correspond to outcome rates this evaluation set can "
            f"tell apart; {collapse_probability * 100:.1f}% of bootstrap resamples reproduce that ordering.",
            {**distribution, "p05_p95_span": round(span, 5), "base_rate_ci_width": round(resolution_floor, 5),
             "bootstrap_support": collapse_probability},
            collapse_probability,
            "rate", _clamp(1.0 - span / resolution_floor) if resolution_floor > 0 else 0.0,
            f"Any decision rule built on differences within the {span:.5f}-wide prediction band is acting on "
            f"distinctions smaller than the {resolution_floor:.5f} sampling resolution measured here.",
            ["pipeline/train_moneyline.py", "pipeline/train_common.py"],
            "retrain", scales,
        ))

    if residuals["biased"]:
        causes.append(_cause(
            "residual_bias",
            f"Mean residual {residuals['mean_residual']:+.5f} over {residuals['n']} rows is "
            f"{abs(residuals['bias_z']):.2f} standard errors from zero (standard error "
            f"{residuals['standard_error']:.5f}, two-sided p={residuals['bias_p_value']:.6f}), a systematic "
            f"{'under' if residuals['mean_residual'] > 0 else 'over'}-prediction of {abs(residuals['mean_residual']):.5f} "
            f"probability points.",
            {k: v for k, v in residuals.items() if k != "deciles"},
            1.0 - (residuals["bias_p_value"] or 1.0),
            "log_loss", residuals["bias_correction_log_loss_gain"],
            f"Shifting every prediction by {residuals['mean_residual']:+.5f} lowers log loss on this evaluation set "
            f"from {residuals['current_log_loss']:.6f} by {residuals['bias_correction_log_loss_gain']:.6f}.",
            ["pipeline/train_moneyline.py", "pipeline/calibration_common.py"],
            "retrain", scales,
        ))

    significant_deciles = residuals["significant_deciles"]
    if significant_deciles:
        lead = significant_deciles[0]
        causes.append(_cause(
            "residual_heteroscedasticity",
            f"{len(significant_deciles)} of {len(residuals['deciles'])} probability deciles carry a mean residual "
            f"that differs from zero after Bonferroni correction (family alpha {residuals['bonferroni_alpha']:.6f}); "
            f"the strongest is {lead['range']} at {lead['mean_residual']:+.5f} over n={lead['n']} "
            f"(z={lead['z']:.2f}, p={lead['p_value']:.6f}), against an overall mean residual of "
            f"{residuals['mean_residual']:+.5f}.",
            {"significant_deciles": significant_deciles, "overall_mean_residual": residuals["mean_residual"],
             "bonferroni_alpha": residuals["bonferroni_alpha"]},
            1.0 - min(1.0, (lead["p_value"] or 1.0) * len(residuals["deciles"])),
            "log_loss", residuals["decile_correction_log_loss_gain"],
            f"Recentring each probability decile on its own measured residual lowers log loss on this evaluation set "
            f"from {residuals['current_log_loss']:.6f} by {residuals['decile_correction_log_loss_gain']:.6f}, "
            f"{residuals['decile_correction_log_loss_gain'] - (residuals['bias_correction_log_loss_gain'] or 0):.6f} "
            f"of which a single constant shift does not capture.",
            ["pipeline/diagnostics.py", "pipeline/calibration_common.py"],
            "retrain", scales,
        ))

    problem_features = [r for r in feature_rows if r["engineering_verdict"] in ("REMOVE", "RE-ENCODE")]
    if problem_features:
        agreements = [r["method_agreement"] for r in problem_features if r["method_agreement"] is not None]
        causes.append(_cause(
            "feature_set_quality",
            f"{len(problem_features)} of {len(feature_rows)} features carry a non-KEEP engineering verdict: "
            + "; ".join(f"{r['feature']}={r['engineering_verdict']}" for r in problem_features[:5]) + ".",
            {"features": [{"feature": r["feature"], "verdict": r["engineering_verdict"],
                           "mean_rank": r["mean_rank"], "stability": r["stability"],
                           "outcome_correlation": r["outcome_correlation"],
                           "method_agreement": r["method_agreement"],
                           "lofo_log_loss_delta": r["lofo_log_loss_delta"]} for r in problem_features]},
            float(np.mean(agreements)) if agreements else 0.0,
            "rate", len(problem_features) / len(feature_rows),
            "; ".join(f"{r['feature']}: {r['verdict_reason']}" for r in problem_features[:3]),
            ["pipeline/feature_store.py", "pipeline/train_common.py", "pipeline/train_moneyline.py"],
            "feature_engineering", scales,
        ))

    rho = stability_result["mean_pairwise_spearman"]
    ranked_items = len([r for r in feature_rows if r["stability"] is not None])
    if rho is not None and ranked_items > 2:
        rho_se = 1.0 / np.sqrt(ranked_items - 1)
        rho_p = _normal_one_sided_p(rho / rho_se)
        if rho_p >= ALPHA:
            unstable = sorted([r for r in feature_rows if r["stability"] is not None], key=lambda r: r["stability"])
            causes.append(_cause(
                "unstable_feature_importance",
                f"Importance rankings do not reproduce across the {stability_result['fold_count']} walk-forward "
                f"folds: mean pairwise Spearman {rho:.4f} over {ranked_items} ranked features is "
                f"{rho / rho_se:.2f} standard errors above zero (standard error {rho_se:.4f}, one-sided "
                f"p={rho_p:.4f}), which does not reach alpha {ALPHA}; least stable is {unstable[0]['feature']} at "
                f"stability {unstable[0]['stability']} with fold ranks {unstable[0]['fold_ranks']}.",
                {"mean_pairwise_spearman": rho, "spearman_standard_error": round(float(rho_se), 4),
                 "p_value": round(rho_p, 6), "ranked_features": ranked_items,
                 "least_stable": [{"feature": r["feature"], "stability": r["stability"],
                                   "fold_ranks": r["fold_ranks"]} for r in unstable[:10]]},
                rho_p,
                "rate", sum(1 for r in feature_rows if r["stability"] is not None
                            and r["stability"] < STABILITY_UNSTABLE) / max(len(feature_rows), 1),
                f"Fold-to-fold rank agreement of {rho:.4f} means the per-feature importances in this report describe "
                f"the fold they were fitted on; only the {sum(1 for r in feature_rows if r['stability'] is not None and r['stability'] >= STABILITY_STABLE)} "
                f"features at stability ≥ {STABILITY_STABLE} carry an ordering that repeated across folds.",
                ["pipeline/train_moneyline.py", "pipeline/train_common.py"],
                "retrain", scales,
            ))

    confirmed_pairs = []
    for pair in redundancy_rows or []:
        interval = _fisher_correlation_ci(pair["correlation"], n)
        if interval is None:
            continue
        low, high, se = interval
        if low > REDUNDANCY_THRESHOLD:
            confirmed_pairs.append({**pair, "ci_lower": round(low, 4), "ci_upper": round(min(high, 1.0), 4),
                                    "fisher_standard_error": round(se, 5)})
    if confirmed_pairs:
        lead = confirmed_pairs[0]
        causes.append(_cause(
            "feature_redundancy",
            f"{len(confirmed_pairs)} of {len(redundancy_rows)} correlated feature pairs keep |r| above "
            f"{REDUNDANCY_THRESHOLD} at the lower end of their Fisher-z {int((1 - ALPHA) * 100)}% interval; the "
            f"strongest is {lead['feature_a']} ↔ {lead['feature_b']} at r={lead['correlation']} "
            f"(interval {lead['ci_lower']}–{lead['ci_upper']}), meaning each explains at least "
            f"{lead['ci_lower'] ** 2 * 100:.1f}% of the other's variance on these {n} rows.",
            {"pairs": confirmed_pairs[:10], "pairs_screened": len(redundancy_rows)},
            1.0 - _normal_one_sided_p((np.arctanh(min(abs(lead["correlation"]), 0.999999))
                                       - np.arctanh(REDUNDANCY_THRESHOLD)) * np.sqrt(max(n - 3, 1))),
            "rate", len(confirmed_pairs) / max(len(feature_rows), 1),
            f"Each confirmed pair contributes at most {100 - lead['ci_lower'] ** 2 * 100:.1f}% independent variance "
            f"beyond its partner as measured on this evaluation set.",
            ["pipeline/feature_store.py", "pipeline/train_common.py"],
            "feature_engineering", scales,
        ))

    if degraded_rate is not None and degraded_rate > 0:
        causes.append(_cause(
            "degraded_feature_inputs",
            f"{degraded_rate * 100:.2f}% of feature values in the evaluation frame failed validation and were "
            f"replaced by fallbacks, so that share of the inputs behind every other number in this report is imputed "
            f"rather than observed.",
            {"degraded_feature_rate": round(degraded_rate, 6)},
            1.0,
            "rate", degraded_rate,
            f"The fallback path in pipeline/feature_store.py supplied {degraded_rate * 100:.2f}% of feature values on "
            f"these {n} rows; that share is a direct count, not an estimate.",
            ["pipeline/feature_store.py", "pipeline/features_common.py", "pipeline/build_features_v2.py"],
            "data_pipeline", scales,
        ))

    clv_n = (clv_summary or {}).get("n", 0)
    if clv_n >= MIN_CLV_N:
        beat_fraction = clv_summary["beat_close_pct"] / 100.0
        beat_low, beat_high = wilson_interval(int(round(beat_fraction * clv_n)), clv_n)
        clv_z = _proportion_z(int(round(beat_fraction * clv_n)), clv_n, 0.5)
        if beat_high < 0.5:
            causes.append(_cause(
                "negative_clv",
                f"{clv_summary['beat_close_pct']}% of {clv_n} graded picks beat the close, a "
                f"{int((1 - ALPHA) * 100)}% Wilson interval of {beat_low:.4f}–{beat_high:.4f} that lies entirely "
                f"below the 0.5 a price-neutral entry would produce (z={clv_z:.2f}, p="
                f"{_normal_two_sided_p(clv_z):.6f}); average CLV is {clv_summary['avg_clv']:+.3f} "
                f"(moneyline {clv_summary['ml_avg_clv']:+.3f}, totals {clv_summary['tot_avg_clv']:+.3f}).",
                {**clv_summary, "beat_close_ci_lower": round(beat_low, 4), "beat_close_ci_upper": round(beat_high, 4),
                 "z_vs_coin_flip": round(clv_z, 3) if clv_z is not None else None},
                1.0 - _normal_two_sided_p(clv_z),
                "rate", 0.5 - beat_fraction,
                f"Entry prices are worse than the close on {(1 - beat_fraction) * 100:.1f}% of graded picks, a gap of "
                f"{0.5 - beat_fraction:.4f} against the coin-flip rate that is measured on pick timestamps rather "
                f"than on model probabilities.",
                ["services/clv_service.py", "services/market_signals_service.py", "poll_odds.py"],
                "data_pipeline", scales,
            ))

    for segment in segment_results:
        if segment["available"] and segment["significant"]:
            worst_segment = segment["significant"][0]
            p_values = [r["p_value"] for r in segment["significant"] if r["p_value"] is not None]
            causes.append(_cause(
                f"segment_bias_{segment['column']}",
                f"Segment '{worst_segment['segment']}' of column {segment['column']} predicts "
                f"{worst_segment['mean_predicted']:.4f} against an actual {worst_segment['actual_rate']:.4f} over "
                f"n={worst_segment['n']}, outside its {segment['test_method']} interval "
                f"{worst_segment['ci_lower']:.4f}–{worst_segment['ci_upper']:.4f}; "
                f"{len(segment['significant'])} of {segment['tests']} tested segments do the same.",
                {"column": segment["column"], "significant": segment["significant"][:5], "min_n": segment["min_n"],
                 "tests": segment["tests"], "family_alpha": segment["family_alpha"]},
                1.0 - min(p_values) * segment["tests"] if p_values else 0.0,
                "rate", abs(worst_segment["mean_residual"]),
                f"The {len(segment['significant'])} significant segment(s) of {segment['column']} carry residuals up "
                f"to {abs(worst_segment['mean_residual']):.4f} that survive Bonferroni correction across "
                f"{segment['tests']} tests, so they are not explained by testing many segments.",
                ["pipeline/feature_store.py", "pipeline/build_features_v2.py"],
                "feature_engineering", scales,
            ))

    skill = _skill_bootstrap(y_true, y_prob)
    if skill is not None and skill["ci_lower"] <= 0 <= skill["ci_upper"]:
        needed = WILSON_Z_95 * skill["bootstrap_standard_error"]
        causes.append(_cause(
            "insufficient_evaluation_power",
            f"On {n} held-out rows the model's log-loss improvement over a base-rate constant predictor is "
            f"{skill['log_loss_skill']:+.6f} with a bootstrap {int((1 - ALPHA) * 100)}% interval of "
            f"{skill['ci_lower']:+.6f}–{skill['ci_upper']:+.6f} over {skill['resamples']} resamples, an interval "
            f"that contains zero (p={skill['p_value']:.4f}); no finding in this report that depends on that skill "
            f"is separable from resampling noise at this sample size.",
            skill,
            skill["p_value"],
            "rate", _clamp(1.0 - abs(skill["log_loss_skill"]) / needed) if needed > 0 else 1.0,
            f"The measured skill of {skill['log_loss_skill']:+.6f} would need to reach {needed:.6f} at the current "
            f"bootstrap standard error of {skill['bootstrap_standard_error']:.6f} before it clears zero; that gap "
            f"is a property of the {n}-row evaluation set, not of any single component.",
            ["pipeline/build_features_v2.py", "pipeline/dataset_append.py"],
            "new_data_acquisition", scales,
        ))

    causes.sort(key=lambda c: -c["expected_value_per_kloc"])
    return causes[:max_causes]


def _history_records():
    if not AUDIT_HISTORY_PATH.exists():
        return []
    records = []
    for line in AUDIT_HISTORY_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _load_prior_issue_ids(model_name):
    seen = set()
    for record in _history_records():
        if record.get("type", "audit_run") == "audit_run" and record.get("model_name") == model_name:
            seen.update(record.get("issue_ids") or [])
    return seen


def load_issue_resolutions(model_name):
    resolved = {}
    for record in _history_records():
        if record.get("type") != "resolution" or record.get("model_name") != model_name:
            continue
        issue_id = record.get("issue_id")
        resolution = record.get("resolution")
        if not issue_id or resolution not in RESOLUTIONS:
            continue
        if resolution in RESOLUTION_REOPENING:
            resolved.pop(issue_id, None)
        else:
            resolved[issue_id] = record
    return resolved


def record_issue_resolution(model_name, issue_id, resolution, note=None, version=None):
    if resolution not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of {RESOLUTIONS}, got {resolution!r}")
    record = {"type": "resolution", "model_name": model_name, "version": version,
              "issue_id": issue_id, "resolution": resolution, "note": note}
    AUDIT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_HISTORY_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def _append_history(model_name, version, issue_ids, health_score):
    AUDIT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_HISTORY_PATH, "a") as f:
        f.write(json.dumps({"type": "audit_run", "model_name": model_name, "version": version,
                            "issue_ids": sorted(issue_ids), "health_score": health_score}) + "\n")


def engineering_backlog(model_name, causes, feature_rows, calibration, consistency, scales, resolutions=None):
    prior = _load_prior_issue_ids(model_name)
    resolutions = load_issue_resolutions(model_name) if resolutions is None else resolutions
    items = []

    for check in consistency["failures"]:
        items.append({
            "id": f"consistency::{check['check']}",
            "issue": f"Self-consistency check '{check['check']}' failed",
            "evidence": check["detail"],
            "evidence_probability": 1.0,
            "gain_metric": "rate",
            "estimated_gain_value": 1.0,
            "remediation_class": "code_fix",
            "affected_files": ["pipeline/engineering_audit.py", "services/shadow_inference_service.py",
                               "pipeline/model_registry.py"],
        })

    for cause in causes:
        items.append({
            "id": f"root_cause::{cause['id']}",
            "issue": cause["title"],
            "evidence": json.dumps(cause["evidence"], default=str)[:600],
            "evidence_probability": cause["evidence_probability"],
            "gain_metric": cause["gain_metric"],
            "estimated_gain_value": cause["estimated_gain_value"],
            "remediation_class": cause["remediation_class"],
            "affected_files": cause["related_files"],
        })

    for row in feature_rows:
        if row["engineering_verdict"] in ("REMOVE", "RE-ENCODE", "INVESTIGATE"):
            items.append({
                "id": f"feature_verdict::{row['feature']}",
                "issue": f"Feature '{row['feature']}' verdict {row['engineering_verdict']}",
                "evidence": row["verdict_reason"],
                "evidence_probability": row["method_agreement"] if row["method_agreement"] is not None else 0.0,
                "gain_metric": "log_loss",
                "estimated_gain_value": abs(row["lofo_log_loss_delta"]) if row["lofo_log_loss_delta"] is not None else 0.0,
                "remediation_class": "feature_engineering" if row["engineering_verdict"] != "INVESTIGATE" else "retrain",
                "affected_files": ["pipeline/feature_store.py", "pipeline/train_common.py"],
            })

    for fix in calibration["suggested_fixes"]:
        metric = fix["justifying_metric"]
        items.append({
            "id": f"calibration::{fix['bucket']}",
            "issue": f"Calibration bucket {fix['bucket']} miscalibrated",
            "evidence": fix["fix"],
            "evidence_probability": (1.0 - ALPHA) if metric["outside_ci"] else 0.0,
            "gain_metric": "ece",
            "estimated_gain_value": fix["expected_impact_ece_points"],
            "remediation_class": "retrain",
            "affected_files": ["pipeline/calibration_common.py", "pipeline/train_moneyline.py"],
        })

    suppressed = []
    ranked = []
    for item in items:
        resolution = resolutions.get(item["id"])
        if resolution is not None:
            suppressed.append({
                "id": item["id"],
                "issue": item["issue"],
                "resolution": resolution["resolution"],
                "note": resolution.get("note"),
                "recorded_for_version": resolution.get("version"),
                "reason": (f"suppressed: {AUDIT_HISTORY_PATH.name} records this issue id as "
                           f"{resolution['resolution']} for {model_name}, so it is not re-recommended"),
            })
            continue
        gain_score = _relative_impact(item["gain_metric"], item["estimated_gain_value"], scales)
        probability = _clamp(item["evidence_probability"])
        effort, measured = effort_kloc(item["affected_files"])
        if item["remediation_class"] == BLOCKING_REMEDIATION:
            status = "BLOCKED"
        elif item["id"] in prior:
            status = "IN_PROGRESS"
        else:
            status = "NEW"
        ranked.append({
            **item,
            "evidence_probability": round(probability, 6),
            "confidence": _confidence_label(probability),
            "estimated_gain_score": round(gain_score, 4),
            "estimated_gain": _band(gain_score),
            "effort_kloc": round(effort, 4),
            "priority": round(100.0 * gain_score * probability / effort, 2),
            "priority_formula": ("priority = 100 * relative_impact * evidence_probability / effort_kloc, where "
                                 "relative_impact is this run's measured gain as a share of the affected metric's "
                                 "current value, evidence_probability is 1 - p of the test that produced the "
                                 "finding, and effort_kloc is the measured non-blank source lines of the files the "
                                 "fix touches"),
            "difficulty_basis": (
                f"{int(effort * 1000)} non-blank source lines measured across {len(item['affected_files'])} file(s): "
                + ", ".join(f"{name} ({lines} lines)" for name, lines in measured.items())
            ),
            "status": status,
        })
    ranked.sort(key=lambda r: -r["priority"])

    efforts = sorted(r["effort_kloc"] for r in ranked)
    if len(efforts) >= 3:
        low_cut, high_cut = (float(np.quantile(efforts, 1.0 / 3.0)), float(np.quantile(efforts, 2.0 / 3.0)))
    else:
        low_cut = high_cut = float(efforts[0]) if efforts else 0.0
    for row in ranked:
        row["difficulty"] = ("High" if row["effort_kloc"] > high_cut else
                             "Low" if row["effort_kloc"] <= low_cut else "Medium")
        row["difficulty_basis"] = (
            row["difficulty_basis"]
            + f"; ranked against this run's {len(ranked)} backlog items, whose measured effort splits at "
              f"{low_cut:.3f} and {high_cut:.3f} kLOC"
        )

    if not ranked:
        rec = insufficient_evidence_block(
            "no diagnostics module produced an evidence-backed issue on this run",
            ["pipeline/engineering_audit.py"],
        )
    else:
        top = ranked[0]
        rec = recommendation_block(
            f"{len(ranked)} evidence-backed backlog items were aggregated from "
            f"{len(consistency['failures'])} consistency failures, {len(causes)} root causes, "
            f"{sum(1 for r in feature_rows if r['engineering_verdict'] in ('REMOVE', 'RE-ENCODE', 'INVESTIGATE'))} "
            f"feature verdicts and {len(calibration['suggested_fixes'])} calibration fixes; "
            f"{sum(1 for r in ranked if r['status'] == 'BLOCKED')} are BLOCKED, "
            f"{sum(1 for r in ranked if r['status'] == 'IN_PROGRESS')} recur from a prior run and "
            f"{len(suppressed)} were suppressed as already resolved.",
            f"Start with '{top['issue']}' (priority {top['priority']}, relative impact {top['estimated_gain_score']} "
            f"of the affected metric, evidence probability {top['evidence_probability']}, effort "
            f"{top['effort_kloc']} kLOC, files {', '.join(top['affected_files'])}).",
            top["confidence"],
            top["estimated_gain"],
            top["affected_files"],
            {"items": len(ranked), "top_priority": top["priority"], "suppressed": len(suppressed)},
        )
    return {"items": ranked, "suppressed": suppressed, "recommendation": rec,
            "priority_definition": ("expected value per unit of implementation effort: "
                                    "100 * relative_impact * evidence_probability / effort_kloc")}


HEALTH_WEIGHTS = {
    "calibration_ece": 0.20,
    "log_loss_skill": 0.20,
    "brier_skill": 0.15,
    "auc": 0.20,
    "feature_stability": 0.10,
    "prediction_variance": 0.05,
    "data_quality": 0.05,
    "clv": 0.05,
}
HEALTH_SCALES = {
    "calibration_ece": "1 - ece/0.10",
    "log_loss_skill": "(base_rate_log_loss - log_loss) / (0.05 * base_rate_log_loss)",
    "brier_skill": "(base_rate_brier - brier) / (0.05 * base_rate_brier)",
    "auc": "(auc - 0.5) / 0.10",
    "feature_stability": "mean per-feature walk-forward rank stability",
    "prediction_variance": "std(predicted_probability) / 0.10",
    "data_quality": "1 - degraded_feature_rate over schema-applicable features only",
    "clv": "(avg_clv + 2.0) / 4.0",
}


def model_health_score(metrics, y_true, y_prob, feature_rows, distribution, degraded_rate, clv_summary,
                       schema_excluded_features=None):
    base_rate = float(np.mean(np.asarray(y_true, dtype=float)))
    base_probs = np.full(len(y_true), base_rate)
    base_log_loss = log_loss_score(y_true, base_probs)
    base_brier = brier_score(y_true, base_probs)

    components = {}
    excluded = {}

    ece = metrics.get("ece")
    if ece is None:
        excluded["calibration_ece"] = "ECE could not be computed on this evaluation set"
    else:
        components["calibration_ece"] = _clamp(1.0 - ece / 0.10)

    ll = metrics.get("log_loss")
    if ll is None or not base_log_loss:
        excluded["log_loss_skill"] = "log loss or its base-rate reference is unavailable"
    else:
        components["log_loss_skill"] = _clamp((base_log_loss - ll) / (0.05 * base_log_loss))

    brier = metrics.get("brier")
    if brier is None or not base_brier:
        excluded["brier_skill"] = "brier or its base-rate reference is unavailable"
    else:
        components["brier_skill"] = _clamp((base_brier - brier) / (0.05 * base_brier))

    auc = metrics.get("auc")
    if auc is None:
        excluded["auc"] = "AUC is undefined (evaluation set is single-class)"
    else:
        components["auc"] = _clamp((auc - 0.5) / 0.10)

    stabilities = [r["stability"] for r in feature_rows if r["stability"] is not None]
    if not stabilities:
        excluded["feature_stability"] = f"fewer than {MIN_FOLDS_FOR_STABILITY} usable walk-forward folds produced per-feature ranks"
    else:
        components["feature_stability"] = _clamp(float(np.mean(stabilities)))

    components["prediction_variance"] = _clamp(distribution["std"] / 0.10)

    if degraded_rate is None:
        excluded["data_quality"] = "degraded feature counts were not returned by feature_store.build_training_frame"
    else:
        components["data_quality"] = _clamp(1.0 - degraded_rate)
    if schema_excluded_features:
        excluded["data_quality_schema_exclusions"] = (
            f"{len(schema_excluded_features)} feature(s) were removed from the data-quality denominator because "
            f"they did not exist at the schema version their rows were written under: "
            + "; ".join(f"{name} ({reason})" for name, reason in sorted(schema_excluded_features.items()))
        )

    clv_n = (clv_summary or {}).get("n", 0)
    if clv_n < MIN_CLV_N:
        excluded["clv"] = f"only {clv_n} graded picks carry CLV, below the {MIN_CLV_N}-row minimum"
    else:
        components["clv"] = _clamp((clv_summary["avg_clv"] + 2.0) / 4.0)

    excluded["roi"] = ("the registry champion has no graded production picks of its own; live ROI belongs to the "
                       "hand-tuned production formula, not this model, so including it would misattribute results")
    excluded["concept_drift"] = ("no drift-detection module exists in this codebase (services/model_lab.py exposes "
                                 "feature_drift_available=False and nothing computes a drift statistic), and building "
                                 "one is out of scope for this audit")

    total_weight = sum(HEALTH_WEIGHTS[k] for k in components)
    contributions = {}
    score = 0.0
    for key, value in components.items():
        normalized_weight = HEALTH_WEIGHTS[key] / total_weight
        contribution = value * normalized_weight * 100
        contributions[key] = {
            "raw_weight": HEALTH_WEIGHTS[key],
            "normalized_weight": round(normalized_weight, 4),
            "component_score": round(value, 4),
            "scale": HEALTH_SCALES[key],
            "points": round(contribution, 2),
        }
        score += contribution

    formula = " + ".join(
        f"{contributions[k]['normalized_weight']}*clamp01({HEALTH_SCALES[k]})" for k in sorted(contributions)
    )
    score = round(score, 1)
    return {
        "score": score,
        "formula": f"health = 100 * ({formula})",
        "components": contributions,
        "excluded": excluded,
        "reference_values": {
            "base_rate": round(base_rate, 4),
            "base_rate_log_loss": round(base_log_loss, 6) if base_log_loss else None,
            "base_rate_brier": round(base_brier, 6) if base_brier else None,
        },
        "recommendation": recommendation_block(
            f"Model health scores {score}/100 from {len(contributions)} measured components "
            + ", ".join(f"{k}={contributions[k]['component_score']} ({contributions[k]['points']} pts)"
                        for k in sorted(contributions, key=lambda x: -contributions[x]["points"]))
            + f"; {len(excluded)} component(s) excluded ({', '.join(sorted(excluded))}).",
            (f"Attack the lowest-scoring component first: "
             f"{min(contributions, key=lambda k: contributions[k]['component_score'])} at "
             f"{min(contributions.values(), key=lambda c: c['component_score'])['component_score']} on scale "
             f"'{HEALTH_SCALES[min(contributions, key=lambda k: contributions[k]['component_score'])]}'."),
            "High" if len(contributions) >= 5 else "Medium",
            _band(1.0 - score / 100.0),
            ["pipeline/engineering_audit.py", "pipeline/train_moneyline.py", "pipeline/feature_store.py"],
            {"score": score, "components_included": sorted(contributions), "components_excluded": sorted(excluded)},
        ) if contributions else insufficient_evidence_block(
            "no health component could be measured on this evaluation set",
            ["pipeline/engineering_audit.py"],
        ),
    }


def build_audit(model_name, target, version, metadata, model, X, y_true, y_prob, metrics,
                combined_rows, shap_rows, redundancy_rows, raw_calibration_rows, merged_calibration_rows,
                model_factory, splits, segments=None, degraded_rate=None,
                min_bucket_n=DEFAULT_MIN_BUCKET_N, db_path="database/picks.db",
                schema_excluded_features=None):
    feature_names = list(metadata.get("feature_list") or list(X.columns))

    consistency = self_consistency_checks(
        model_name, target, version, metadata, model, y_true, raw_calibration_rows, db_path=db_path
    )

    stability_result = fold_importance_stability(model_factory, X, y_true, feature_names, splits)
    correlations = outcome_correlations(X, y_true, feature_names)
    feature_rows = feature_engineering_table(combined_rows, shap_rows, stability_result, correlations, len(y_true))
    feature_recommendation = feature_importance_recommendation(feature_rows, stability_result, len(y_true))

    dates = segments["date"].tolist() if segments is not None and "date" in segments.columns else None
    calibration = calibration_report(y_true, y_prob, raw_calibration_rows, merged_calibration_rows,
                                     min_bucket_n=min_bucket_n, dates=dates)

    residuals = residual_analysis(y_true, y_prob)
    distribution = prediction_distribution_stats(y_prob)

    segment_results = []
    for column in ("home_team", "away_team", "home_sp_name", "away_sp_name"):
        segment_results.append(segment_analysis(segments, y_true, y_prob, column))

    try:
        from services.clv_service import get_clv_summary

        clv_summary = get_clv_summary()
    except Exception as exc:
        clv_summary = {"n": 0, "error": str(exc)}

    scales = impact_scales(metrics, y_true)
    resolutions = load_issue_resolutions(model_name)
    all_causes = root_cause_engine(metrics, feature_rows, calibration, residuals, distribution, segment_results,
                                   clv_summary, redundancy_rows, degraded_rate, stability_result,
                                   y_true, y_prob, scales)
    suppressed_causes = [c for c in all_causes if f"root_cause::{c['id']}" in resolutions]
    causes = [c for c in all_causes if f"root_cause::{c['id']}" not in resolutions]
    backlog = engineering_backlog(model_name, all_causes, feature_rows, calibration, consistency, scales,
                                  resolutions=resolutions)
    health = model_health_score(metrics, y_true, y_prob, feature_rows, distribution, degraded_rate, clv_summary,
                                schema_excluded_features=schema_excluded_features)

    if causes:
        top = causes[0]
        root_cause_rec = recommendation_block(
            f"{len(causes)} evidence-backed root causes were derived from this run; the highest-ranked is "
            f"{top['title']}",
            f"{top['suggested_fix']} (measured effect "
            f"{'unavailable' if top['estimated_gain_value'] is None else format(top['estimated_gain_value'], '.6f')} "
            f"{top['gain_metric']}, {top['estimated_gain_score']} of that metric's current value, evidence "
            f"probability {top['evidence_probability']}, effort {top['effort_kloc']} kLOC)",
            top["confidence"],
            top["estimated_gain_band"],
            top["related_files"],
            {"cause_ids": [c["id"] for c in causes]},
        )
    else:
        root_cause_rec = insufficient_evidence_block(
            f"no root-cause threshold was crossed on {len(y_true)} evaluation rows "
            f"(AUC {metrics.get('auc')}, ECE {metrics.get('ece')}, prediction std {distribution['std']})",
            ["pipeline/engineering_audit.py"],
        )

    unavailable_segments = [s for s in segment_results if not s["available"]]
    if any(s["available"] for s in segment_results):
        available = [s for s in segment_results if s["available"]]
        segment_rec = recommendation_block(
            f"{len(available)} of {len(segment_results)} segment breakdowns reached the {MIN_SEGMENT_N}-row minimum; "
            + "; ".join(f"{s['column']}: {len(s['rows'])} segments, {len(s['significant'])} outside CI" for s in available),
            (f"Add adjustments for the {sum(len(s['significant']) for s in available)} segment(s) whose predicted rate "
             f"falls outside their Wilson 95% CI.") if any(s["significant"] for s in available) else
            (f"No segment with n≥{MIN_SEGMENT_N} is mispriced beyond its Wilson 95% CI; no segment-level fix is "
             f"justified by this evaluation set."),
            "Medium",
            _band(sum(len(s["significant"]) for s in available) / max(sum(len(s["rows"]) for s in available), 1)),
            ["pipeline/feature_store.py", "pipeline/build_features_v2.py"],
            {"columns": [s["column"] for s in available]},
        )
    else:
        segment_rec = insufficient_evidence_block(
            "; ".join(f"{s['column']}: {s['reason']}" for s in unavailable_segments),
            ["pipeline/feature_store.py"],
        )

    clv_n = clv_summary.get("n", 0)
    if clv_n >= MIN_CLV_N:
        beat_successes = int(round(clv_summary["beat_close_pct"] / 100.0 * clv_n))
        beat_low, beat_high = wilson_interval(beat_successes, clv_n)
        beat_contains_half = beat_low <= 0.5 <= beat_high
        clv_rec = recommendation_block(
            f"CLV is recorded on {clv_n} graded picks with average {clv_summary['avg_clv']:+.3f} and "
            f"{clv_summary['beat_close_pct']}% beating the close (moneyline {clv_summary['ml_avg_clv']:+.3f}, "
            f"totals {clv_summary['tot_avg_clv']:+.3f}).",
            (f"The {clv_summary['beat_close_pct']}% beat-close rate over {clv_n} picks sits "
             f"{abs(clv_summary['beat_close_pct'] - 50.0):.1f} points "
             f"{'below' if clv_summary['beat_close_pct'] < 50 else 'above'} the 50% a price-neutral entry produces; "
             f"its {int((1 - ALPHA) * 100)}% Wilson interval {beat_low:.4f}–{beat_high:.4f} "
             f"{'contains' if beat_contains_half else 'excludes'} 0.5, so entry timing "
             f"{'is not' if beat_contains_half else 'is'} separable from a coin flip against the close on this "
             f"sample."),
            "High" if clv_n >= 100 else "Medium",
            _band(_clamp(abs(clv_summary["beat_close_pct"] / 100.0 - 0.5) / 0.5)),
            ["services/clv_service.py", "poll_odds.py"],
            clv_summary,
        )
    else:
        clv_rec = insufficient_evidence_block(
            f"only {clv_n} picks carry a CLV value, below the {MIN_CLV_N}-row minimum for a CLV finding",
            ["services/clv_service.py"],
        )

    issue_ids = {item["id"] for item in backlog["items"]}
    _append_history(model_name, version, issue_ids, health["score"])

    return {
        "model_name": model_name,
        "version": version,
        "evaluation_rows": int(len(y_true)),
        "self_consistency": consistency,
        "feature_engineering": {
            "rows": feature_rows,
            "stability": {k: v for k, v in stability_result.items() if k != "rows"},
            "decision_rule": {
                "min_rows_for_verdict": MIN_ROWS_FOR_VERDICT,
                "min_folds_for_stability": MIN_FOLDS_FOR_STABILITY,
                "bottom_tier_fraction": BOTTOM_TIER_FRACTION,
                "mid_tier_fraction": MID_TIER_FRACTION,
                "stability_stable": STABILITY_STABLE,
                "stability_unstable": STABILITY_UNSTABLE,
                "lofo_keep_delta": LOFO_KEEP_DELTA,
                "lofo_remove_delta": LOFO_REMOVE_DELTA,
                "outcome_correlation_signal": OUTCOME_CORR_SIGNAL,
                "agreement_high": AGREEMENT_HIGH,
                "agreement_medium": AGREEMENT_MEDIUM,
            },
            "recommendation": feature_recommendation,
        },
        "calibration": calibration,
        "residuals": residuals,
        "prediction_distribution": distribution,
        "segments": {"results": segment_results, "recommendation": segment_rec},
        "clv": {"summary": clv_summary, "recommendation": clv_rec},
        "root_causes": {"causes": causes, "suppressed": [
            {"id": c["id"], "title": c["title"],
             "resolution": resolutions[f"root_cause::{c['id']}"]["resolution"],
             "note": resolutions[f"root_cause::{c['id']}"].get("note")}
            for c in suppressed_causes
        ], "recommendation": root_cause_rec},
        "backlog": backlog,
        "health": health,
        "impact_scales": scales,
        "threshold_provenance": THRESHOLD_PROVENANCE,
    }
