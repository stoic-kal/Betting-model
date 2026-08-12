import sys
from pathlib import Path

import numpy as np

from pipeline import engineering_audit
from pipeline.calibration_common import DEFAULT_MIN_BUCKET_N
from pipeline.train_common import (
    KERNEL_SHAP_BACKGROUND,
    KERNEL_SHAP_L1_REG,
    KERNEL_SHAP_NSAMPLES,
    KERNEL_SHAP_ROWS,
    calibration_bucket_summary,
    calibration_table,
    cloned_model_factory,
    combined_importance_table,
    is_tree_model,
    leave_one_feature_out_table,
    merge_calibration_buckets,
    compute_classification_metrics,
    confusion_matrix_dict,
    correlation_matrix_table,
    feature_redundancy_report,
    gain_importance_table,
    permutation_importance_table,
    pr_curve_table,
    probability_distribution,
    roc_curve_table,
    save_json,
    save_table_csv,
    shap_summary_table,
    walk_forward_splits,
)


LOFO_WALK_FORWARD_SPLITS = 4


def generate_importance_tables(model, X, y_true, feature_names, model_factory=None,
                               sample_size=500, lofo_splits=LOFO_WALK_FORWARD_SPLITS):
    sample_n = min(sample_size, len(X))
    X_sample = X.sample(n=sample_n, random_state=42) if len(X) > sample_n else X

    gain_rows = gain_importance_table(model, feature_names)
    permutation_rows = permutation_importance_table(model, X, y_true)
    shap_rows = shap_summary_table(model, X_sample, feature_names)
    shap_explainer = shap_rows[0]["shap_method"] if shap_rows else None
    shap_rows_explained = min(KERNEL_SHAP_ROWS, len(X_sample)) if str(shap_explainer).startswith("kernel") else len(X_sample)

    lofo_features = list(feature_names)
    factory = model_factory or cloned_model_factory(model)
    splits = walk_forward_splits(len(X), n_splits=lofo_splits)
    lofo_rows = leave_one_feature_out_table(factory, X, y_true, lofo_features, splits=splits)

    provenance = {
        "gain_importance": {
            "applicable": gain_rows is not None,
            "reason": None if gain_rows is not None else "model family exposes no native split-gain importance",
            "tree_model": is_tree_model(model),
        },
        "permutation_importance": {"applicable": True, "scoring": "neg_log_loss", "n_repeats": 10, "n_rows": int(len(X))},
        "shap": {
            "applicable": True,
            "explainer": shap_explainer,
            "n_rows_explained": int(shap_rows_explained),
            "kernel_nsamples": KERNEL_SHAP_NSAMPLES,
            "kernel_background_clusters": KERNEL_SHAP_BACKGROUND,
            "kernel_l1_reg": KERNEL_SHAP_L1_REG,
        },
        "leave_one_feature_out": {
            "applicable": True,
            "retrained_per_feature": True,
            "features_evaluated": lofo_features,
            "features_evaluated_count": len(lofo_features),
            "total_features": len(feature_names),
            "validation": "walk_forward",
            "walk_forward_splits": len(splits),
        },
    }
    combined = combined_importance_table(feature_names, gain_rows, permutation_rows, shap_rows, lofo_rows)
    return {
        "gain": gain_rows,
        "permutation": permutation_rows,
        "shap": shap_rows,
        "leave_one_feature_out": lofo_rows,
        "combined": combined,
        "provenance": provenance,
    }


def roi_by_bucket(y_true, values, odds_dec, n_buckets=5, label="bucket"):
    if odds_dec is None:
        return None
    values = np.asarray(values)
    odds_dec = np.asarray(odds_dec, dtype=object)
    y_true = np.asarray(y_true)
    valid = np.array([o is not None for o in odds_dec])
    if valid.sum() == 0:
        return None
    values = values[valid]
    odds_dec = odds_dec[valid].astype(float)
    y_true = y_true[valid]
    edges = np.quantile(values, np.linspace(0, 1, n_buckets + 1))
    edges = np.unique(edges)
    idx = np.clip(np.digitize(values, edges) - 1, 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        mask = idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        profits = np.where(y_true[mask] == 1, odds_dec[mask] - 1.0, -1.0)
        rows.append({
            label: f"{edges[b]:.3f}-{edges[b+1]:.3f}",
            "n": n,
            "roi_pct": round(float(profits.mean()) * 100, 2),
        })
    return rows


def generate_diagnostics_report(model_name, version, y_true, y_prob, X, booster, feature_names,
                                 fitted_model=None, odds_dec=None, ev=None, confidence=None, sample_size=500,
                                 model_factory=None, min_bucket_n=DEFAULT_MIN_BUCKET_N,
                                 lofo_splits=LOFO_WALK_FORWARD_SPLITS,
                                 metadata=None, target=None, segments=None, degraded_rate=None,
                                 schema_excluded_features=None):
    output_dir = Path("reports/training") / f"{model_name}_{version}"
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = compute_classification_metrics(y_true, y_prob)
    save_json(output_dir / "metrics.json", metrics)

    buckets = calibration_table(y_true, y_prob, min_bucket_n=min_bucket_n)
    merged_buckets = merge_calibration_buckets(buckets, min_bucket_n=min_bucket_n)
    save_table_csv(output_dir / "calibration_table.csv", buckets)
    save_table_csv(output_dir / "calibration_table_merged.csv", merged_buckets)
    save_json(output_dir / "calibration_bucket_summary.json", {
        "raw": calibration_bucket_summary(buckets, min_bucket_n=min_bucket_n),
        "merged": calibration_bucket_summary(merged_buckets, min_bucket_n=min_bucket_n),
    })
    save_table_csv(output_dir / "roc_curve.csv", roc_curve_table(y_true, y_prob))
    save_table_csv(output_dir / "pr_curve.csv", pr_curve_table(y_true, y_prob))
    save_json(output_dir / "confusion_matrix.json", confusion_matrix_dict(y_true, y_prob))
    save_table_csv(output_dir / "probability_distribution.csv", probability_distribution(np.asarray(y_prob)))

    importance = generate_importance_tables(
        fitted_model if fitted_model is not None else booster,
        X, y_true, feature_names, model_factory=model_factory,
        sample_size=sample_size, lofo_splits=lofo_splits,
    )
    if importance["gain"] is not None:
        save_table_csv(output_dir / "feature_importance_gain.csv", importance["gain"])
    save_table_csv(output_dir / "feature_importance_permutation.csv", importance["permutation"])
    save_table_csv(output_dir / "shap_summary.csv", importance["shap"])
    save_table_csv(output_dir / "feature_importance_leave_one_out.csv", importance["leave_one_feature_out"])
    save_table_csv(output_dir / "feature_importance_combined.csv", importance["combined"])
    save_json(output_dir / "feature_importance_provenance.json", importance["provenance"])

    save_json(output_dir / "correlation_matrix.json", correlation_matrix_table(X))
    redundancy_rows = feature_redundancy_report(X)
    save_table_csv(output_dir / "feature_redundancy.csv", redundancy_rows)

    if metadata is not None:
        audit = engineering_audit.build_audit(
            model_name, target or model_name, version, metadata,
            fitted_model if fitted_model is not None else booster,
            X, y_true, y_prob, metrics,
            importance["combined"], importance["shap"], redundancy_rows,
            buckets, merged_buckets,
            model_factory or cloned_model_factory(fitted_model if fitted_model is not None else booster),
            walk_forward_splits(len(X), n_splits=lofo_splits),
            segments=segments, degraded_rate=degraded_rate, min_bucket_n=min_bucket_n,
            schema_excluded_features=schema_excluded_features,
        )
        save_json(output_dir / "engineering_audit.json", audit)
        save_table_csv(output_dir / "feature_engineering_verdicts.csv",
                       [{k: v for k, v in row.items() if k != "fold_ranks"}
                        for row in audit["feature_engineering"]["rows"]])
        save_table_csv(output_dir / "engineering_backlog.csv", audit["backlog"]["items"])

    if odds_dec is not None:
        prob_buckets = roi_by_bucket(y_true, y_prob, odds_dec, label="probability_bucket")
        if prob_buckets:
            save_table_csv(output_dir / "roi_by_probability_bucket.csv", prob_buckets)
        odds_buckets = roi_by_bucket(y_true, odds_dec, odds_dec, label="odds_bucket")
        if odds_buckets:
            save_table_csv(output_dir / "roi_by_odds_bucket.csv", odds_buckets)
    if ev is not None and odds_dec is not None:
        ev_buckets = roi_by_bucket(y_true, ev, odds_dec, label="ev_bucket")
        if ev_buckets:
            save_table_csv(output_dir / "roi_by_ev_bucket.csv", ev_buckets)
    if confidence is not None and odds_dec is not None:
        conf_buckets = roi_by_bucket(y_true, confidence, odds_dec, label="confidence_bucket")
        if conf_buckets:
            save_table_csv(output_dir / "roi_by_confidence_bucket.csv", conf_buckets)

    return output_dir, metrics


def regenerate_for_registered_model(model_name, version, lofo_splits=LOFO_WALK_FORWARD_SPLITS):
    metadata, model, target, X_test, y_test, segments, degraded_rate, schema_excluded = _evaluation_context(model_name, version)
    y_prob = model.predict_proba(X_test)[:, 1]
    return generate_diagnostics_report(
        model_name, version, y_test, y_prob, X_test, model, metadata["feature_list"],
        fitted_model=model, lofo_splits=lofo_splits,
        metadata=metadata, target=target, segments=segments, degraded_rate=degraded_rate,
        schema_excluded_features=schema_excluded,
    )


def _evaluation_context(model_name, version):
    from pipeline import feature_store, model_registry
    from pipeline.train_common import time_split

    metadata = model_registry.load_metadata(model_name, version)
    model = model_registry.load_model(model_name, version)
    target = model_name if model_name in feature_store.TARGETS else (
        "moneyline" if model_name.startswith("moneyline") else "totals"
    )
    df = feature_store.load_dataset(metadata["dataset_path"])
    if feature_store.TARGETS[target]["model_type"] == "classification":
        y_raw = df[feature_store.TARGETS[target]["label_column"]].astype(float)
    else:
        y_raw = feature_store.build_totals_targets(df)[0]
    valid = y_raw.notna()
    df = df[valid].reset_index(drop=True)
    y_all = y_raw[valid].astype(int).reset_index(drop=True)
    X_all, degraded_counts = feature_store.build_training_frame(df, target)
    X_all = X_all[metadata["feature_list"]]
    train_df, val_df, _ = time_split(df)
    start = len(train_df) + len(val_df)
    X_test = X_all.iloc[start:].reset_index(drop=True)
    y_test = y_all.iloc[start:].reset_index(drop=True)
    segment_columns = [c for c in ("date", "home_team", "away_team", "home_sp_name", "away_sp_name") if c in df.columns]
    segments = df.iloc[start:][segment_columns].reset_index(drop=True)
    degraded_test = degraded_counts.iloc[start:]
    applicable_counts = degraded_counts.attrs.get("applicable_feature_counts")
    if applicable_counts is not None:
        denominator = sum(applicable_counts[start:])
    else:
        denominator = len(degraded_test) * len(metadata["feature_list"])
    degraded_rate = (float(degraded_test.sum()) / denominator) if len(degraded_test) and denominator else None
    schema_excluded = degraded_counts.attrs.get("schema_excluded_features") or {}
    return metadata, model, target, X_test, y_test, segments, degraded_rate, schema_excluded


def regenerate_audit_for_registered_model(model_name, version, min_bucket_n=DEFAULT_MIN_BUCKET_N,
                                          lofo_splits=LOFO_WALK_FORWARD_SPLITS):
    import pandas as pd

    output_dir = Path("reports/training") / f"{model_name}_{version}"
    combined_path = output_dir / "feature_importance_combined.csv"
    shap_path = output_dir / "shap_summary.csv"
    if not combined_path.exists() or not shap_path.exists():
        raise FileNotFoundError(
            f"{output_dir} lacks feature_importance_combined.csv/shap_summary.csv; run the full diagnostics first"
        )
    metadata, model, target, X_test, y_test, segments, degraded_rate, schema_excluded = _evaluation_context(model_name, version)
    y_prob = model.predict_proba(X_test)[:, 1]
    metrics = compute_classification_metrics(y_test, y_prob)
    buckets = calibration_table(y_test, y_prob, min_bucket_n=min_bucket_n)
    merged_buckets = merge_calibration_buckets(buckets, min_bucket_n=min_bucket_n)
    combined_frame = pd.read_csv(combined_path).astype(object)
    combined_rows = combined_frame.where(combined_frame.notna(), None).to_dict("records")
    shap_rows = pd.read_csv(shap_path).to_dict("records")
    audit = engineering_audit.build_audit(
        model_name, target, version, metadata, model, X_test, y_test, y_prob, metrics,
        combined_rows, shap_rows, feature_redundancy_report(X_test), buckets, merged_buckets,
        cloned_model_factory(model), walk_forward_splits(len(X_test), n_splits=lofo_splits),
        segments=segments, degraded_rate=degraded_rate, min_bucket_n=min_bucket_n,
        schema_excluded_features=schema_excluded,
    )
    save_json(output_dir / "engineering_audit.json", audit)
    save_table_csv(output_dir / "feature_engineering_verdicts.csv",
                   [{k: v for k, v in row.items() if k != "fold_ranks"}
                    for row in audit["feature_engineering"]["rows"]])
    save_table_csv(output_dir / "engineering_backlog.csv", audit["backlog"]["items"])
    return output_dir, audit


if __name__ == "__main__":
    if len(sys.argv) > 5 and sys.argv[3] == "resolve":
        entry = engineering_audit.record_issue_resolution(
            sys.argv[1], sys.argv[4], sys.argv[5].upper(),
            note=sys.argv[6] if len(sys.argv) > 6 else None, version=sys.argv[2],
        )
        print(f"recorded {entry['resolution']} for {entry['issue_id']} ({entry['model_name']})")
    elif len(sys.argv) > 3 and sys.argv[3] == "audit":
        out_dir, out_audit = regenerate_audit_for_registered_model(sys.argv[1], sys.argv[2])
        print(f"engineering audit written to {out_dir}")
        print(f"health={out_audit['health']['score']} "
              f"consistency_failures={out_audit['self_consistency']['failure_count']} "
              f"root_causes={len(out_audit['root_causes']['causes'])} "
              f"backlog={len(out_audit['backlog']['items'])}")
    else:
        out_dir, out_metrics = regenerate_for_registered_model(sys.argv[1], sys.argv[2])
        print(f"diagnostics written to {out_dir}")
        print(out_metrics)
