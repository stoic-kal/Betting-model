import pandas as pd
import numpy as np

print("⏳ Adding batter exit velocity features...\n")

games = pd.read_csv("data/games_with_all_features.csv")
batter_stats = pd.read_csv("data/batter_advanced_stats.csv")

print(f"Aggregating batter metrics by year and team...\n")


batter_by_year = (
    batter_stats.groupby("year")
    .agg(
        {
            "avg_exit_velo": "mean",
            "avg_launch_angle": "mean",
            "at_bats": "sum",
        }
    )
    .reset_index()
)

games["year"] = pd.to_datetime(games["date"]).dt.year


games = games.merge(batter_by_year, on="year", how="left")

games.rename(
    columns={
        "avg_exit_velo": "league_exit_velo",
        "avg_launch_angle": "league_launch_angle",
        "at_bats": "league_ab_total",
    },
    inplace=True,
)


games["run_diff"] = games["home_runs"] - games["away_runs"]

games.to_csv("data/games_engineered_features.csv", index=False)

print(f"Added batter features to {len(games)} games")
print(f"\nTotal features: {len(games.columns)}")
print(f"Columns:\n{games.columns.tolist()}")
print(f"\nSample:\n{games.head()}")
