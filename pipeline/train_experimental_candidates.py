import sys
from pathlib import Path

from catboost import CatBoostClassifier
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    VotingClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import feature_store, model_registry
from pipeline.train_common import (
    compute_classification_metrics,
    fit_selected_calibration,
    time_split,
    walk_forward_evaluation,
)

DATASET_PATH = "data/games_v2_features_final.csv"

FAMILY_BUILDERS = {
    "catboost": lambda: CatBoostClassifier(random_state=42, iterations=150, depth=6, learning_rate=0.05, verbose=False),
    "xgboost": lambda: XGBClassifier(random_state=42, n_jobs=-1, n_estimators=150, max_depth=6, learning_rate=0.05, eval_metric="logloss"),
    "random_forest": lambda: RandomForestClassifier(random_state=42, n_jobs=-1, n_estimators=300, max_depth=6),
    "extra_trees": lambda: ExtraTreesClassifier(random_state=42, n_jobs=-1, n_estimators=300, max_depth=6),
    "hist_gradient_boosting": lambda: HistGradientBoostingClassifier(random_state=42, max_depth=6, learning_rate=0.05),
    "logistic_regression": lambda: Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, C=1.0))]),
}

ENSEMBLE_MEMBERS = ("logistic_regression", "random_forest", "extra_trees")

FAMILY_BUILDERS["ensemble"] = lambda: VotingClassifier(
    estimators=[(name, FAMILY_BUILDERS[name]()) for name in ENSEMBLE_MEMBERS],
    voting="soft",
)


def run_family(target, family, X_train, y_train, X_val, y_val, X_test, y_test, training_features, dataset_hash_source,
               model_name=None):
    raw_model = FAMILY_BUILDERS[family]()
    raw_model.fit(X_train, y_train)
    calibrated_model, calibration_choice, calibration_selection = fit_selected_calibration(raw_model, X_val, y_val)

    test_prob = calibrated_model.predict_proba(X_test)[:, 1]
    raw_metrics = compute_classification_metrics(y_test, raw_model.predict_proba(X_test)[:, 1])
    calibrated_metrics = compute_classification_metrics(y_test, test_prob)
    walk_forward = walk_forward_evaluation(FAMILY_BUILDERS[family], X_train, y_train)

    model_name = model_name or f"{target}_{family}"
    version = model_registry.new_version()
    metadata = model_registry.register_model(
        model_name=model_name,
        version=version,
        model_object=calibrated_model,
        feature_schema_version=feature_store.get_schema_version(),
        feature_list=training_features,
        dataset_path=dataset_hash_source,
        metrics=calibrated_metrics,
        calibration_metrics={
            "raw": raw_metrics,
            "calibrated": calibrated_metrics,
            "method_selection": calibration_selection,
        },
        hyperparameters={},
        extra={
            "model_family": family,
            "tuning_status": "untuned_baseline_fixed_params",
            "training_sample_size": len(X_train),
            "calibration_method_selected": calibration_choice,
            "walk_forward": walk_forward,
        },
    )
    print(f"registered {model_name} version {metadata['version']} calibration={calibration_choice} "
          f"test_log_loss={calibrated_metrics.get('log_loss')} test_auc={calibrated_metrics.get('auc')}")
    return metadata


def run_target(target, label_fn):
    df = feature_store.load_dataset(DATASET_PATH)
    y_raw = label_fn(df)
    valid_mask = y_raw.notna()
    n_skipped = int((~valid_mask).sum())
    if n_skipped:
        print(f"{target}: skipping {n_skipped} rows with no usable target")
    df = df[valid_mask].reset_index(drop=True)
    y_all = y_raw[valid_mask].astype(int).reset_index(drop=True)
    if len(df) < 30:
        print(f"{target}: fewer than 30 usable rows, skipping experimental candidate training")
        return

    X_all, _ = feature_store.build_training_frame(df, target)
    training_features = feature_store.get_training_feature_list(target)
    X_all = X_all[training_features]
    train_df, val_df, test_df = time_split(df)

    n_train, n_val = len(train_df), len(val_df)
    X_train, y_train = X_all.iloc[:n_train], y_all.iloc[:n_train]
    X_val, y_val = X_all.iloc[n_train:n_train + n_val], y_all.iloc[n_train:n_train + n_val]
    X_test, y_test = X_all.iloc[n_train + n_val:], y_all.iloc[n_train + n_val:]

    for family in FAMILY_BUILDERS:
        run_family(target, family, X_train, y_train, X_val, y_val, X_test, y_test, training_features, DATASET_PATH)


def main():
    run_target("moneyline", lambda df: df["home_win"].astype(int))
    run_target("totals", lambda df: feature_store.build_totals_targets(df)[0])


if __name__ == "__main__":
    main()
