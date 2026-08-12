import json
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import shap
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    confusion_matrix,
    log_loss,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from pipeline.calibration_common import (
    DEFAULT_MIN_BUCKET_N,
    calibration_bucket_summary,
    calibration_table,
    compute_classification_metrics,
    expected_calibration_error,
    fit_selected_calibration,
    merge_calibration_buckets,
    wilson_interval,
)

optuna.logging.set_verbosity(optuna.logging.WARNING)


def time_split(df, val_frac=0.15, test_frac=0.15):
    n = len(df)
    test_start = int(n * (1 - test_frac))
    val_start = int(n * (1 - test_frac - val_frac))
    train_df = df.iloc[:val_start].reset_index(drop=True)
    val_df = df.iloc[val_start:test_start].reset_index(drop=True)
    test_df = df.iloc[test_start:].reset_index(drop=True)
    return train_df, val_df, test_df


def walk_forward_splits(n_rows, n_splits=4, min_train_frac=0.5):
    min_train = int(n_rows * min_train_frac)
    remaining = n_rows - min_train
    fold_size = remaining // n_splits
    splits = []
    for i in range(n_splits):
        train_end = min_train + i * fold_size
        val_end = train_end + fold_size if i < n_splits - 1 else n_rows
        if val_end <= train_end:
            continue
        splits.append((np.arange(0, train_end), np.arange(train_end, val_end)))
    return splits


def walk_forward_evaluation(model_factory, X, y, n_splits=4):
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y)).reset_index(drop=True)
    folds = []
    for fold, (train_idx, val_idx) in enumerate(walk_forward_splits(len(X), n_splits=n_splits)):
        model = model_factory()
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        prob = model.predict_proba(X.iloc[val_idx])[:, 1]
        metrics = compute_classification_metrics(y.iloc[val_idx], prob)
        metrics["fold"] = fold
        folds.append(metrics)
    keys = ("accuracy", "precision", "recall", "f1", "auc", "log_loss", "brier", "ece")
    summary = {}
    for key in keys:
        values = [f[key] for f in folds if f.get(key) is not None]
        summary[f"mean_{key}"] = float(np.mean(values)) if values else None
        summary[f"std_{key}"] = float(np.std(values)) if values else None
    return {"folds": folds, "summary": summary}


def roc_curve_table(y_true, y_prob):
    fpr, tpr, thresholds = roc_curve(y_true, y_prob)
    return [{"fpr": round(float(f), 4), "tpr": round(float(t), 4), "threshold": round(float(th), 4)}
            for f, t, th in zip(fpr, tpr, thresholds)]


def pr_curve_table(y_true, y_prob):
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    rows = []
    for i in range(len(thresholds)):
        rows.append({
            "precision": round(float(precision[i]), 4),
            "recall": round(float(recall[i]), 4),
            "threshold": round(float(thresholds[i]), 4),
        })
    return rows


def confusion_matrix_dict(y_true, y_prob, threshold=0.5):
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {"true_negative": int(tn), "false_positive": int(fp), "false_negative": int(fn), "true_positive": int(tp)}


def probability_distribution(y_prob, n_bins=10):
    hist, edges = np.histogram(y_prob, bins=n_bins, range=(0.0, 1.0))
    return [{"bin": f"{edges[i]:.1f}-{edges[i+1]:.1f}", "count": int(hist[i])} for i in range(n_bins)]


TREE_MODEL_MARKERS = (
    "LGBMClassifier", "XGBClassifier", "CatBoostClassifier", "RandomForestClassifier",
    "ExtraTreesClassifier", "GradientBoostingClassifier", "DecisionTreeClassifier",
)


def unwrap_estimator(model):
    inner = model
    while True:
        if hasattr(inner, "calibrated_classifiers_") and inner.calibrated_classifiers_:
            candidate = getattr(inner.calibrated_classifiers_[0], "estimator", None)
            if candidate is None:
                candidate = getattr(inner, "estimator", None)
        elif type(inner).__name__ == "CalibratedClassifierCV":
            candidate = getattr(inner, "estimator", None)
        else:
            candidate = None
        if candidate is None or candidate is inner:
            return inner
        inner = candidate


def is_tree_model(model):
    return type(unwrap_estimator(model)).__name__ in TREE_MODEL_MARKERS


def _raw_gain_values(model, feature_names):
    inner = unwrap_estimator(model)
    if hasattr(inner, "booster_"):
        return np.asarray(inner.booster_.feature_importance(importance_type="gain"), dtype=float)
    if hasattr(inner, "get_booster"):
        scores = inner.get_booster().get_score(importance_type="gain")
        return np.array([float(scores.get(name, scores.get(f"f{i}", 0.0)))
                         for i, name in enumerate(feature_names)])
    if hasattr(inner, "get_feature_importance"):
        return np.asarray(inner.get_feature_importance(type="FeatureImportance"), dtype=float)
    return None


def gain_importance_table(booster, feature_names):
    gains = _raw_gain_values(booster, feature_names)
    if gains is None or len(gains) != len(feature_names):
        return None
    total = gains.sum() if gains.sum() > 0 else 1.0
    rows = sorted(zip(feature_names, gains), key=lambda r: -r[1])
    return [{"feature": name, "gain": float(g), "gain_pct": round(float(g / total * 100), 2)} for name, g in rows]


def permutation_importance_table(model, X, y, n_repeats=10, random_state=42):
    result = permutation_importance(model, X, y, n_repeats=n_repeats, random_state=random_state, scoring="neg_log_loss")
    rows = sorted(
        zip(X.columns, result.importances_mean, result.importances_std),
        key=lambda r: -r[1],
    )
    return [{"feature": name, "importance_mean": float(m), "importance_std": float(s)} for name, m, s in rows]


KERNEL_SHAP_ROWS = 150
KERNEL_SHAP_BACKGROUND = 20
KERNEL_SHAP_NSAMPLES = 500
KERNEL_SHAP_L1_REG = 0


def _shap_matrix(shap_values, n_features):
    values = np.asarray(shap_values)
    if isinstance(shap_values, list):
        values = np.asarray(shap_values[-1])
    if values.ndim == 3:
        values = values[:, :, -1]
    if values.ndim == 2 and values.shape[1] != n_features and values.shape[0] == n_features:
        values = values.T
    return values


def shap_summary_table(booster, X_sample, feature_names, method=None):
    inner = unwrap_estimator(booster)
    resolved = method or ("tree" if is_tree_model(inner) else "kernel")
    explain_on = X_sample
    if resolved == "tree":
        try:
            explainer = shap.TreeExplainer(inner)
            values = _shap_matrix(explainer.shap_values(X_sample), len(feature_names))
        except Exception:
            resolved = "kernel_tree_explainer_unsupported"
    if resolved != "tree":
        rows = min(KERNEL_SHAP_ROWS, len(X_sample))
        explain_on = X_sample.iloc[:rows]
        background = shap.kmeans(X_sample, min(KERNEL_SHAP_BACKGROUND, len(X_sample)))
        explainer = shap.KernelExplainer(lambda data: booster.predict_proba(
            pd.DataFrame(data, columns=list(X_sample.columns)))[:, 1], background)
        values = _shap_matrix(
            explainer.shap_values(explain_on, nsamples=KERNEL_SHAP_NSAMPLES, silent=True,
                                  l1_reg=KERNEL_SHAP_L1_REG),
            len(feature_names),
        )
    mean_abs = np.abs(values).mean(axis=0)
    mean_signed = values.mean(axis=0)
    value_corr = []
    for i, name in enumerate(feature_names):
        column = explain_on[name].to_numpy(dtype=float)
        contribution = values[:, i]
        if np.std(column) == 0 or np.std(contribution) == 0:
            value_corr.append(0.0)
        else:
            value_corr.append(float(np.corrcoef(column, contribution)[0, 1]))
    ordered = sorted(zip(feature_names, mean_abs, mean_signed, value_corr), key=lambda r: -r[1])
    return [{"feature": name, "mean_abs_shap": float(v), "mean_shap": float(signed),
             "value_shap_corr": round(float(corr), 4), "shap_method": resolved}
            for name, v, signed, corr in ordered]


def leave_one_feature_out_table(model_factory, X, y, features, holdout_frac=0.2, splits=None):
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y)).reset_index(drop=True)
    if splits is None:
        train_end = int(len(X) * (1 - holdout_frac))
        splits = [(np.arange(0, train_end), np.arange(train_end, len(X)))]

    def score(columns):
        losses, aucs = [], []
        for train_idx, val_idx in splits:
            model = model_factory()
            model.fit(X.iloc[train_idx][columns], y.iloc[train_idx])
            prob = model.predict_proba(X.iloc[val_idx][columns])[:, 1]
            losses.append(log_loss(y.iloc[val_idx], prob, labels=[0, 1]))
            if len(set(y.iloc[val_idx].tolist())) > 1:
                aucs.append(roc_auc_score(y.iloc[val_idx], prob))
        return float(np.mean(losses)), (float(np.mean(aucs)) if aucs else None)

    all_columns = list(X.columns)
    base_log_loss, base_auc = score(all_columns)
    rows = []
    for feature in features:
        remaining = [c for c in all_columns if c != feature]
        if not remaining:
            continue
        feat_log_loss, feat_auc = score(remaining)
        rows.append({
            "feature": feature,
            "baseline_log_loss": round(base_log_loss, 6),
            "log_loss_without": round(feat_log_loss, 6),
            "log_loss_delta": round(feat_log_loss - base_log_loss, 6),
            "baseline_auc": round(base_auc, 6) if base_auc is not None else None,
            "auc_without": round(feat_auc, 6) if feat_auc is not None else None,
            "auc_delta": round(feat_auc - base_auc, 6) if (feat_auc is not None and base_auc is not None) else None,
        })
    return sorted(rows, key=lambda r: -r["log_loss_delta"])


def _rank_map(rows, key):
    if not rows:
        return {}
    ordered = sorted(rows, key=lambda r: -(r[key] if r[key] is not None else float("-inf")))
    return {r["feature"]: i + 1 for i, r in enumerate(ordered)}


def combined_importance_table(feature_names, gain_rows, permutation_rows, shap_rows, lofo_rows):
    gain_by = {r["feature"]: r for r in (gain_rows or [])}
    perm_by = {r["feature"]: r for r in (permutation_rows or [])}
    shap_by = {r["feature"]: r for r in (shap_rows or [])}
    lofo_by = {r["feature"]: r for r in (lofo_rows or [])}
    gain_rank = _rank_map(gain_rows, "gain")
    perm_rank = _rank_map(permutation_rows, "importance_mean")
    shap_rank = _rank_map(shap_rows, "mean_abs_shap")
    lofo_rank = _rank_map(lofo_rows, "log_loss_delta")
    rows = []
    for name in feature_names:
        rows.append({
            "feature": name,
            "gain": gain_by[name]["gain"] if name in gain_by else None,
            "gain_rank": gain_rank.get(name),
            "permutation_importance": perm_by[name]["importance_mean"] if name in perm_by else None,
            "permutation_rank": perm_rank.get(name),
            "mean_abs_shap": shap_by[name]["mean_abs_shap"] if name in shap_by else None,
            "shap_rank": shap_rank.get(name),
            "lofo_log_loss_delta": lofo_by[name]["log_loss_delta"] if name in lofo_by else None,
            "lofo_auc_delta": lofo_by[name]["auc_delta"] if name in lofo_by else None,
            "lofo_rank": lofo_rank.get(name),
        })
    for row in rows:
        available = [row[k] for k in ("gain_rank", "permutation_rank", "shap_rank", "lofo_rank") if row[k] is not None]
        row["mean_rank"] = round(float(np.mean(available)), 2) if available else None
    return sorted(rows, key=lambda r: (r["mean_rank"] is None, r["mean_rank"] or 0.0))


def cloned_model_factory(model):
    inner = unwrap_estimator(model)
    return lambda: clone(inner)


def correlation_matrix_table(X):
    corr = X.corr()
    return corr.round(4).to_dict()


def feature_redundancy_report(X, threshold=0.9):
    corr = X.corr().abs()
    pairs = []
    columns = corr.columns
    for i in range(len(columns)):
        for j in range(i + 1, len(columns)):
            value = corr.iloc[i, j]
            if value >= threshold:
                pairs.append({"feature_a": columns[i], "feature_b": columns[j], "correlation": round(float(value), 4)})
    return sorted(pairs, key=lambda r: -r["correlation"])


def run_optuna_search(objective, n_trials=15, direction="minimize", seed=42):
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction=direction, sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return study.best_params, study.best_value, study


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def save_table_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)
