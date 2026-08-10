import pandas as pd
import numpy as np

print("⏳ Adding pitcher features...\n")

games = pd.read_csv("data/games_with_team_features.csv")
pitcher_stats = pd.read_csv("data/pitcher_advanced_stats.csv")

print(f"Merging pitcher stats...\n")


pitcher_by_team = (
    pitcher_stats.groupby(["pitcher_id"])
    .agg(
        {
            "avg_fastball_velo": "mean",
            "pitches_thrown": "mean",
        }
    )
    .reset_index()
)


pitcher_agg = (
    pitcher_stats.groupby(["year"])
    .agg(
        {
            "avg_fastball_velo": "mean",
            "pitches_thrown": "mean",
        }
    )
    .reset_index()
)

games["year"] = pd.to_datetime(games["date"]).dt.year


games = games.merge(
    pitcher_agg[["year", "avg_fastball_velo", "pitches_thrown"]], on="year", how="left"
)

games.rename(
    columns={
        "avg_fastball_velo": "league_avg_fastball_velo",
        "pitches_thrown": "league_avg_pitches_per_game",
    },
    inplace=True,
)

games.to_csv("data/games_with_all_features.csv", index=False)

print(f"Added pitcher features to {len(games)} games")
print("\nFinal feature set:")
print(games.columns.tolist())
print(f"\nSample:\n{games.head()}")
