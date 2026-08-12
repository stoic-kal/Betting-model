import pickle
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss, accuracy_score

from pipeline.calibration_common import DEFAULT_MIN_BUCKET_N, calibration_table

DATA_PATH = "data/games_v2_features_final.csv"
ML_MODEL_PATH = "models/lgbm_v2_moneyline.pkl"
TOTALS_MODEL_PATH = "models/lgbm_v2_totals.pkl"
RECENT_HOLDOUT_FRACTION = 0.15


def load_pickle(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def evaluate(name, y_true, y_prob):
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    y_pred = (y_prob >= 0.5).astype(int)
    print(f"\n--- {name} (n={len(y_true)}) ---")
    print(f"  base rate (actual positive %): {y_true.mean():.3f}")
    print(f"  accuracy:   {accuracy_score(y_true, y_pred):.4f}")
    print(f"  auc:        {roc_auc_score(y_true, y_prob):.4f}")
    print(f"  log_loss:   {log_loss(y_true, y_prob, labels=[0, 1]):.4f}")
    print(f"  brier:      {brier_score_loss(y_true, y_prob):.4f}")
    baseline_prob = np.full_like(y_prob, y_true.mean())
    print(f"  baseline log_loss (predict base rate always): {log_loss(y_true, baseline_prob, labels=[0, 1]):.4f}")
    print(f"  baseline brier (predict base rate always):    {brier_score_loss(y_true, baseline_prob):.4f}")
    print("  calibration (10 bins):")
    for row in calibration_table(y_true, y_prob, min_bucket_n=DEFAULT_MIN_BUCKET_N):
        flag = "" if row["reliable"] else f"  low-confidence (n<{DEFAULT_MIN_BUCKET_N})"
        print(f"    {row['bin']:<12} n={row['n']:<5} pred={row['avg_predicted']:<6} actual={row['actual_rate']:<6} "
              f"95% CI=[{row['actual_ci_lower']}, {row['actual_ci_upper']}]{flag}")


def main():
    df = pd.read_csv(DATA_PATH, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    cutoff_idx = int(len(df) * (1 - RECENT_HOLDOUT_FRACTION))
    cutoff_date = df.iloc[cutoff_idx]["date"]
    print(f"Total games: {len(df)}  date range: {df['date'].min().date()} to {df['date'].max().date()}")
    print(f"Recent-slice cutoff: {cutoff_date.date()} (last {RECENT_HOLDOUT_FRACTION:.0%} of games chronologically)")
    print("NOTE: models were built after this entire date range, so this dataset was very likely")
    print("used (in full or in part) for their original training. Metrics below are NOT a clean")
    print("out-of-sample test. 'Recent slice' numbers are a weaker but still useful check for")
    print("performance degradation on the most recent games relative to the full sample.")

    ml_model = load_pickle(ML_MODEL_PATH)
    ml_features = list(ml_model.feature_names_in_)
    X_ml_full = df[ml_features]
    y_ml_full = df["home_win"].astype(int)
    p_ml_full = ml_model.predict_proba(X_ml_full)[:, 1]

    X_ml_recent = df.iloc[cutoff_idx:][ml_features]
    y_ml_recent = df.iloc[cutoff_idx:]["home_win"].astype(int)
    p_ml_recent = ml_model.predict_proba(X_ml_recent)[:, 1]

    print("\n================ MONEYLINE (lgbm_v2_moneyline.pkl) ================")
    evaluate("Full dataset (2024-03 to 2025-11)", y_ml_full, p_ml_full)
    evaluate(f"Recent slice (since {cutoff_date.date()})", y_ml_recent, p_ml_recent)

    totals_artifact = load_pickle(TOTALS_MODEL_PATH)
    totals_model = totals_artifact["model"]
    totals_features = totals_artifact["features"]
    median_total = totals_artifact["median_total"]
    df["over_label"] = (df["total_runs"] > median_total).astype(int)

    X_tot_full = df[totals_features]
    y_tot_full = df["over_label"]
    p_tot_full = totals_model.predict_proba(X_tot_full)[:, 1]

    X_tot_recent = df.iloc[cutoff_idx:][totals_features]
    y_tot_recent = df.iloc[cutoff_idx:]["over_label"]
    p_tot_recent = totals_model.predict_proba(X_tot_recent)[:, 1]

    print(f"\n================ TOTALS (lgbm_v2_totals.pkl, line={median_total}) ================")
    evaluate("Full dataset (2024-03 to 2025-11)", y_tot_full, p_tot_full)
    evaluate(f"Recent slice (since {cutoff_date.date()})", y_tot_recent, p_tot_recent)


if __name__ == "__main__":
    main()
