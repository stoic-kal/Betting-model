import pandas as pd
import numpy as np
from datetime import datetime

print("⏳ Building game-level features...\n")


statcast = pd.read_csv("data/statcast_raw.csv")
batter_stats = pd.read_csv("data/batter_advanced_stats.csv")
pitcher_stats = pd.read_csv("data/pitcher_advanced_stats.csv")

print(f"Loaded all data")


statcast["game_date"] = pd.to_datetime(statcast["game_date"])
statcast["year"] = statcast["game_date"].dt.year


games = (
    statcast.groupby(["game_date", "home_team", "away_team"])
    .agg(
        {
            "home_score": "first",
            "away_score": "first",
        }
    )
    .reset_index()
)

games.columns = ["date", "home_team", "away_team", "home_runs", "away_runs"]
games["total_runs"] = games["home_runs"] + games["away_runs"]
games["home_win"] = (games["home_runs"] > games["away_runs"]).astype(int)

print(f"Created {len(games)} game records")


games.to_csv("data/games_with_results.csv", index=False)
print("Saved to data/games_with_results.csv")

print("\nSample games:")
print(games.head())
