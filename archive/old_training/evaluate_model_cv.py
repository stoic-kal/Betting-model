import pandas as pd
import numpy as np
import pickle
from sklearn.metrics import accuracy_score, roc_auc_score
import lightgbm as lgb

print("⏳ Loading model and data...\n")

with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model = pickle.load(f)

games = pd.read_csv("data/games_engineered_features.csv")
games["date"] = pd.to_datetime(games["date"])

feature_cols = [
    "home_wr",
    "away_wr",
    "league_avg_fastball_velo",
    "league_avg_pitches_per_game",
    "league_exit_velo",
    "league_launch_angle",
    "league_ab_total",
    "total_runs",
]

print("Testing on different years:\n")

for year in [2024, 2025]:
    year_data = games[games["date"].dt.year == year].copy()

    if len(year_data) == 0:
        continue

    X = year_data[feature_cols].fillna(year_data[feature_cols].mean())
    y = year_data["home_win"].values

    y_pred_proba = model.predict(X)
    y_pred = (y_pred_proba > 0.5).astype(int)

    accuracy = accuracy_score(y, y_pred)
    auc = roc_auc_score(y, y_pred_proba)

    print(f"Year {year} ({len(year_data)} games):")
    print(f"   Accuracy: {accuracy:.1%}")
    print(f"   AUC: {auc:.3f}")
    print()

print("Model evaluation complete!")
