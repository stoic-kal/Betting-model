import math

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

DEFAULT_MIN_BUCKET_N = 25
WILSON_Z_95 = 1.959963984540054


def wilson_interval(successes, n, z=WILSON_Z_95):
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denominator = 1.0 + (z * z) / n
    center = (p + (z * z) / (2 * n)) / denominator
    margin = (z * math.sqrt((p * (1 - p) / n) + (z * z) / (4 * n * n))) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def brier_score(y_true, y_prob):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    if len(y_true) == 0:
        return None
    return float(np.mean((y_prob - y_true) ** 2))


def log_loss_score(y_true, y_prob, eps=1e-9):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.clip(np.asarray(y_prob, dtype=float), eps, 1.0 - eps)
    if len(y_true) == 0:
        return None
    return float(-np.mean(y_true * np.log(y_prob) + (1 - y_true) * np.log(1 - y_prob)))


def expected_calibration_error(y_true, y_prob, n_bins=10):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    if len(y_true) == 0:
        return None
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)
    n = len(y_true)
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        ece += (count / n) * abs(float(y_prob[mask].mean()) - float(y_true[mask].mean()))
    return float(ece)


def compute_classification_metrics(y_true, y_prob):
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    y_pred = (y_prob >= 0.5).astype(int)
    return {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc": float(roc_auc_score(y_true, y_prob)) if len(set(y_true.tolist())) > 1 else None,
        "log_loss": log_loss_score(y_true, y_prob),
        "brier": brier_score(y_true, y_prob),
        "ece": expected_calibration_error(y_true, y_prob),
    }


CALIBRATION_METHODS = ("sigmoid", "isotonic")
CALIBRATION_SELECTION_FOLDS = 4


def _calibration_selection_score(y_true, y_prob):
    return (log_loss_score(y_true, y_prob), brier_score(y_true, y_prob), expected_calibration_error(y_true, y_prob))


def select_calibration_method(raw_model, X_val, y_val, methods=CALIBRATION_METHODS,
                              n_splits=CALIBRATION_SELECTION_FOLDS, random_state=42):
    y_val = np.asarray(y_val)
    folds = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    table = []
    for method in methods:
        probs = np.zeros(len(y_val), dtype=float)
        for fit_idx, score_idx in folds.split(X_val, y_val):
            calibrator = CalibratedClassifierCV(raw_model, method=method, cv="prefit")
            calibrator.fit(X_val.iloc[fit_idx], y_val[fit_idx])
            probs[score_idx] = calibrator.predict_proba(X_val.iloc[score_idx])[:, 1]
        log_loss_value, brier, ece = _calibration_selection_score(y_val, probs)
        table.append({"method": method, "log_loss": log_loss_value, "brier": brier, "ece": ece})
    best = min(table, key=lambda r: (r["log_loss"], r["brier"], r["ece"]))
    return best["method"], table


def fit_selected_calibration(raw_model, X_val, y_val, methods=CALIBRATION_METHODS):
    method, table = select_calibration_method(raw_model, X_val, y_val, methods=methods)
    calibrated = CalibratedClassifierCV(raw_model, method=method, cv="prefit")
    calibrated.fit(X_val, y_val)
    return calibrated, method, table


def _bucket_row(lower, upper, n, successes, predicted_sum, min_bucket_n):
    ci_lower, ci_upper = wilson_interval(successes, n)
    return {
        "bin": f"{lower:.2f}-{upper:.2f}",
        "bin_lower": round(float(lower), 4),
        "bin_upper": round(float(upper), 4),
        "n": int(n),
        "successes": int(successes),
        "predicted_sum": round(float(predicted_sum), 6),
        "avg_predicted": round(float(predicted_sum / n), 4),
        "actual_rate": round(float(successes / n), 4),
        "actual_ci_lower": round(float(ci_lower), 4),
        "actual_ci_upper": round(float(ci_upper), 4),
        "ci_width": round(float(ci_upper - ci_lower), 4),
        "reliable": bool(n >= min_bucket_n),
    }


def calibration_table(y_true, y_prob, n_bins=10, min_bucket_n=DEFAULT_MIN_BUCKET_N):
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = idx == b
        count = int(mask.sum())
        if count == 0:
            continue
        rows.append(_bucket_row(bins[b], bins[b + 1], count, y_true[mask].sum(), y_prob[mask].sum(), min_bucket_n))
    return rows


def merge_calibration_buckets(rows, min_bucket_n=DEFAULT_MIN_BUCKET_N):
    ordered = sorted(rows, key=lambda r: r["bin_lower"])
    merged = []
    pending = None
    for row in ordered:
        if pending is None:
            pending = dict(row)
        else:
            pending = {
                "bin_lower": pending["bin_lower"],
                "bin_upper": row["bin_upper"],
                "n": pending["n"] + row["n"],
                "successes": pending["successes"] + row["successes"],
                "predicted_sum": pending["predicted_sum"] + row["predicted_sum"],
            }
        if pending["n"] >= min_bucket_n:
            merged.append(_bucket_row(pending["bin_lower"], pending["bin_upper"], pending["n"],
                                      pending["successes"], pending["predicted_sum"], min_bucket_n))
            pending = None
    if pending is not None:
        if merged:
            last = merged.pop()
            combined_n = last["n"] + pending["n"]
            merged.append(_bucket_row(last["bin_lower"], pending["bin_upper"], combined_n,
                                      last["successes"] + pending["successes"],
                                      last["predicted_sum"] + pending["predicted_sum"], min_bucket_n))
        else:
            merged.append(_bucket_row(pending["bin_lower"], pending["bin_upper"], pending["n"],
                                      pending["successes"], pending["predicted_sum"], min_bucket_n))
    return merged


def calibration_bucket_summary(rows, min_bucket_n=DEFAULT_MIN_BUCKET_N):
    return {
        "buckets": len(rows),
        "min_bucket_n": min_bucket_n,
        "low_confidence_buckets": [r["bin"] for r in rows if not r["reliable"]],
        "all_buckets_reliable": all(r["reliable"] for r in rows) if rows else False,
        "interval_method": "wilson_score_95",
    }
