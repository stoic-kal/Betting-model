import sys
from pathlib import Path

import numpy as np
from lightgbm import LGBMClassifier
from sklearn.metrics import log_loss

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import feature_store, model_registry
from pipeline.diagnostics import generate_diagnostics_report
from pipeline.train_common import (
    compute_classification_metrics,
    fit_selected_calibration,
    run_optuna_search,
    time_split,
    walk_forward_evaluation,
    walk_forward_splits,
)

DATASET_PATH = "data/games_v2_features_final.csv"
EXPANDED_DATASET_PATH = "data/games_v2_features_context.csv"
MODEL_NAME = "moneyline"
EXPANDED_TARGET = "moneyline_v23"
N_TRIALS = 15


def build_model(params):
    return LGBMClassifier(
        objective="binary",
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
        **params,
    )


def make_objective(X_train, y_train):
    splits = walk_forward_splits(len(X_train), n_splits=4)

    def objective(trial):
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 8, 64),
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 400),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 60),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        }
        scores = []
        for train_idx, val_idx in splits:
            model = build_model(params)
            model.fit(X_train.iloc[train_idx], y_train.iloc[train_idx])
            prob = model.predict_proba(X_train.iloc[val_idx])[:, 1]
            scores.append(log_loss(y_train.iloc[val_idx], prob, labels=[0, 1]))
        return float(np.mean(scores))

    return objective


def main(target=MODEL_NAME, dataset_path=DATASET_PATH):
    df = feature_store.load_dataset(dataset_path)
    X_all, degraded_counts = feature_store.build_training_frame(df, target)
    training_features = feature_store.get_training_feature_list(target)
    X_all = X_all[training_features]
    y_all = df["home_win"].astype(int)

    train_df, val_df, test_df = time_split(df)
    X_train, y_train = X_all.iloc[:len(train_df)], y_all.iloc[:len(train_df)]
    X_val, y_val = X_all.iloc[len(train_df):len(train_df) + len(val_df)], y_all.iloc[len(train_df):len(train_df) + len(val_df)]
    X_test, y_test = X_all.iloc[len(train_df) + len(val_df):], y_all.iloc[len(train_df) + len(val_df):]

    print(f"train={len(X_train)} val={len(X_val)} test={len(X_test)}")
    print("running hyperparameter search")
    best_params, best_value, _ = run_optuna_search(make_objective(X_train, y_train), n_trials=N_TRIALS)
    print(f"best walk-forward log_loss={best_value:.4f} params={best_params}")

    raw_model = build_model(best_params)
    raw_model.fit(X_train, y_train)

    calibrated_model, calibration_choice, calibration_selection = fit_selected_calibration(raw_model, X_val, y_val)
    print(f"calibration selected={calibration_choice} selection={calibration_selection}")

    test_prob_raw = raw_model.predict_proba(X_test)[:, 1]
    test_prob_calibrated = calibrated_model.predict_proba(X_test)[:, 1]

    raw_metrics = compute_classification_metrics(y_test, test_prob_raw)
    calibrated_metrics = compute_classification_metrics(y_test, test_prob_calibrated)
    print(f"test raw metrics: {raw_metrics}")
    print(f"test calibrated metrics: {calibrated_metrics}")

    version = model_registry.new_version()
    output_dir, _ = generate_diagnostics_report(
        target, version, y_test, test_prob_calibrated, X_test, raw_model,
        training_features, fitted_model=calibrated_model,
        model_factory=lambda: build_model(best_params),
    )
    print(f"diagnostics written to {output_dir}")

    metadata = model_registry.register_model(
        model_name=target,
        version=version,
        model_object=calibrated_model,
        feature_schema_version=feature_store.get_schema_version(),
        feature_list=training_features,
        dataset_path=dataset_path,
        metrics=calibrated_metrics,
        calibration_metrics={
            "raw": raw_metrics,
            "calibrated": calibrated_metrics,
            "method_selection": calibration_selection,
        },
        hyperparameters=best_params,
        extra={
            "walk_forward_best_log_loss": best_value,
            "walk_forward": walk_forward_evaluation(lambda: build_model(best_params), X_train, y_train),
            "calibration_method_selected": calibration_choice,
            "avg_degraded_features_per_row": float(degraded_counts.mean()),
            "rfe_excluded_features": feature_store.RFE_VALIDATED_EXCLUSIONS[target],
            "model_family": "lightgbm",
            "tuning_status": "optuna_tuned",
            "training_sample_size": len(X_train),
        },
    )
    print(f"registered {target} version {metadata['version']}")
    return metadata


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "expanded":
        main(target=EXPANDED_TARGET, dataset_path=EXPANDED_DATASET_PATH)
    else:
        main()
