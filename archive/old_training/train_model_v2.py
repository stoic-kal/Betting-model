import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, brier_score_loss
import lightgbm as lgb

FEATURES_PATH = "data/games_v2_features.csv"
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)


ML_FEATURES = [
    "home_k_rate",
    "home_bb_rate",
    "home_hr_rate",
    "home_hard_hit_pct",
    "home_fb_velo",
    "home_xwoba_against",
    "home_fip",
    "home_is_lefty",
    "home_days_rest",
    "away_k_rate",
    "away_bb_rate",
    "away_hr_rate",
    "away_hard_hit_pct",
    "away_fb_velo",
    "away_xwoba_against",
    "away_fip",
    "away_is_lefty",
    "away_days_rest",
    "home_bat_k_rate",
    "home_bat_hard_hit_pct",
    "home_bat_iso",
    "home_bat_woba",
    "away_bat_k_rate",
    "away_bat_hard_hit_pct",
    "away_bat_iso",
    "away_bat_woba",
    "home_L10_wr",
    "home_L10_rs",
    "home_L10_ra",
    "away_L10_wr",
    "away_L10_rs",
    "away_L10_ra",
    "park_factor",
    "is_dome",
    "is_coors",
    "temp_f",
    "wind_mph",
    "wind_out_factor",
]


TOTALS_FEATURES = [
    "home_k_rate",
    "home_bb_rate",
    "home_hr_rate",
    "home_hard_hit_pct",
    "home_fb_velo",
    "home_xwoba_against",
    "home_fip",
    "home_days_rest",
    "away_k_rate",
    "away_bb_rate",
    "away_hr_rate",
    "away_hard_hit_pct",
    "away_fb_velo",
    "away_xwoba_against",
    "away_fip",
    "away_days_rest",
    "home_bat_woba",
    "home_bat_hard_hit_pct",
    "home_bat_iso",
    "away_bat_woba",
    "away_bat_hard_hit_pct",
    "away_bat_iso",
    "home_L10_rs",
    "home_L10_ra",
    "away_L10_rs",
    "away_L10_ra",
    "park_factor",
    "is_dome",
    "is_coors",
    "temp_f",
    "wind_mph",
    "wind_out_factor",
]

LGBM_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "n_estimators": 600,
    "learning_rate": 0.02,
    "num_leaves": 31,
    "max_depth": 5,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}


print("Loading features...")
df = pd.read_csv(FEATURES_PATH, parse_dates=["date"])
df = df.sort_values("date").reset_index(drop=True)
print(f"  {len(df):,} games  |  {df['date'].min().date()} → {df['date'].max().date()}")


missing = [f for f in ML_FEATURES if f not in df.columns]
if missing:
    print(f"   Missing features (will be 0): {missing}")
    for f in missing:
        df[f] = 0.0


median_total = df["total_runs"].median()
df["over_median"] = (df["total_runs"] > median_total).astype(int)
print(f"  Median total runs: {median_total:.1f}")
print(f"  Home win rate: {df['home_win'].mean():.3f}")
print(f"  Over-median rate: {df['over_median'].mean():.3f}")

tscv = TimeSeriesSplit(n_splits=5)


print("\n" + "=" * 50)
print("MONEYLINE MODEL")
print("=" * 50)
X_ml = df[ML_FEATURES].values
y_ml = df["home_win"].values

aucs, briers = [], []
for fold, (tr, va) in enumerate(tscv.split(X_ml)):
    m = lgb.LGBMClassifier(**LGBM_PARAMS)
    m.fit(
        X_ml[tr],
        y_ml[tr],
        eval_set=[(X_ml[va], y_ml[va])],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )
    p = m.predict_proba(X_ml[va])[:, 1]
    aucs.append(roc_auc_score(y_ml[va], p))
    briers.append(brier_score_loss(y_ml[va], p))
    print(f"  Fold {fold+1}: AUC={aucs[-1]:.4f}  Brier={briers[-1]:.4f}")

print(f"\n  Mean AUC:   {np.mean(aucs):.4f} ± {np.std(aucs):.4f}")
print(f"  Mean Brier: {np.mean(briers):.4f}")

print("  Fitting final model + calibrating...")
final_ml = lgb.LGBMClassifier(**LGBM_PARAMS)
final_ml.fit(pd.DataFrame(X_ml, columns=ML_FEATURES), y_ml)

cal_ml = CalibratedClassifierCV(final_ml, method="sigmoid", cv=5)
cal_ml.fit(pd.DataFrame(X_ml, columns=ML_FEATURES), y_ml)

with open(MODEL_DIR / "lgbm_v2_moneyline.pkl", "wb") as f:
    pickle.dump(cal_ml, f)
print("  Saved models/lgbm_v2_moneyline.pkl")

imps = pd.Series(final_ml.feature_importances_, index=ML_FEATURES).sort_values(ascending=False)
print("\n  Top 10 features (moneyline):")
for feat, imp in imps.head(10).items():
    print(f"    {feat:<38} {imp}")


print("\n" + "=" * 50)
print("TOTALS MODEL")
print("=" * 50)
X_tot = df[TOTALS_FEATURES].values
y_tot = df["over_median"].values

aucs_tot, briers_tot = [], []
for fold, (tr, va) in enumerate(tscv.split(X_tot)):
    m = lgb.LGBMClassifier(**LGBM_PARAMS)
    m.fit(
        X_tot[tr],
        y_tot[tr],
        eval_set=[(X_tot[va], y_tot[va])],
        callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
    )
    p = m.predict_proba(X_tot[va])[:, 1]
    aucs_tot.append(roc_auc_score(y_tot[va], p))
    briers_tot.append(brier_score_loss(y_tot[va], p))
    print(f"  Fold {fold+1}: AUC={aucs_tot[-1]:.4f}  Brier={briers_tot[-1]:.4f}")

print(f"\n  Mean AUC:   {np.mean(aucs_tot):.4f} ± {np.std(aucs_tot):.4f}")
print(f"  Mean Brier: {np.mean(briers_tot):.4f}")

print("  Fitting final model + calibrating...")
final_tot = lgb.LGBMClassifier(**LGBM_PARAMS)
final_tot.fit(pd.DataFrame(X_tot, columns=TOTALS_FEATURES), y_tot)

cal_tot = CalibratedClassifierCV(final_tot, method="sigmoid", cv=5)
cal_tot.fit(pd.DataFrame(X_tot, columns=TOTALS_FEATURES), y_tot)

totals_bundle = {
    "model": cal_tot,
    "median_total": median_total,
    "features": TOTALS_FEATURES,
}
with open(MODEL_DIR / "lgbm_v2_totals.pkl", "wb") as f:
    pickle.dump(totals_bundle, f)
print("  Saved models/lgbm_v2_totals.pkl")

imps_tot = pd.Series(final_tot.feature_importances_, index=TOTALS_FEATURES).sort_values(
    ascending=False
)
print("\n  Top 10 features (totals):")
for feat, imp in imps_tot.head(10).items():
    print(f"    {feat:<38} {imp}")


config = {
    "ml_features": ML_FEATURES,
    "totals_features": TOTALS_FEATURES,
    "median_total": median_total,
}
with open(MODEL_DIR / "v2_feature_config.pkl", "wb") as f:
    pickle.dump(config, f)


print("\n" + "=" * 50)
print("SUMMARY")
print("=" * 50)
print(f"  Moneyline AUC: {np.mean(aucs):.4f}  (prev: 0.5508)")
print(f"  Totals AUC:    {np.mean(aucs_tot):.4f}  (prev: 0.5428)")
delta_ml = np.mean(aucs) - 0.5508
delta_tot = np.mean(aucs_tot) - 0.5428
print(f"  Moneyline Δ:   {delta_ml:+.4f}")
print(f"  Totals Δ:      {delta_tot:+.4f}")
if np.mean(aucs_tot) > 0.57:
    print("  Totals model has meaningful edge — deploy v2")
elif np.mean(aucs_tot) > 0.54:
    print("  Totals model improved but still marginal — continue adding features")
else:
    print("  Totals model not improved — check feature coverage")
print("\nTraining complete.")
