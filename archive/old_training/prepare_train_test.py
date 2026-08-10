import pandas as pd
import numpy as np

print("⏳ Preparing train/test split...\n")

games = pd.read_csv("data/games_engineered_features.csv")
games["date"] = pd.to_datetime(games["date"])

print(f"Total games: {len(games)}")
print(f"Date range: {games['date'].min()} to {games['date'].max()}")


train = games[games["date"] < "2026-01-01"].copy()
test = games[games["date"] >= "2026-01-01"].copy()

print(f"\nTraining set: {len(train)} games (2024-2025)")
print(f"Test set: {len(test)} games (2026)")


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

X_train = train[feature_cols].fillna(train[feature_cols].mean())
y_train = train["home_win"].values

X_test = test[feature_cols].fillna(test[feature_cols].mean())
y_test = test["home_win"].values

print(f"\nFeature matrix:")
print(f"   X_train: {X_train.shape}")
print(f"   X_test: {X_test.shape}")


X_train.to_csv("data/X_train.csv", index=False)
y_train_df = pd.DataFrame({"home_win": y_train})
y_train_df.to_csv("data/y_train.csv", index=False)

X_test.to_csv("data/X_test.csv", index=False)
y_test_df = pd.DataFrame({"home_win": y_test})
y_test_df.to_csv("data/y_test.csv", index=False)

print("\nSaved train/test data")
