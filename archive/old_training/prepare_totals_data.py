import pandas as pd
import numpy as np

print("⏳ Preparing Poisson totals data...\n")

games = pd.read_csv("data/games_engineered_features.csv")
games["date"] = pd.to_datetime(games["date"])

print(f"Total games: {len(games)}")
print(f"   Home runs: {games['home_runs'].mean():.2f} avg")
print(f"   Away runs: {games['away_runs'].mean():.2f} avg")
print(f"   Total runs: {games['total_runs'].mean():.2f} avg")

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


X_home = games[feature_cols].fillna(games[feature_cols].mean())
y_home = games["home_runs"].values


X_away = games[feature_cols].fillna(games[feature_cols].mean())
y_away = games["away_runs"].values


y_total = games["total_runs"].values

print(f"\nCreated datasets:")
print(f"   X shape: {X_home.shape}")
print(f"   y_home shape: {y_home.shape}")
print(f"   y_away shape: {y_away.shape}")
print(f"   y_total shape: {y_total.shape}")


X_home.to_csv("data/X_totals.csv", index=False)
pd.DataFrame({"home_runs": y_home}).to_csv("data/y_home_runs.csv", index=False)
pd.DataFrame({"away_runs": y_away}).to_csv("data/y_away_runs.csv", index=False)
pd.DataFrame({"total_runs": y_total}).to_csv("data/y_total_runs.csv", index=False)

print(f"\nSaved totals data")
