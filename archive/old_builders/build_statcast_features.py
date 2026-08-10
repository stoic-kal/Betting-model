import pandas as pd
import numpy as np

print("⏳ Loading StatCast data...")
df = pd.read_csv("data/statcast_raw.csv")

print(f"Loaded {len(df)} rows")

df["year"] = pd.to_datetime(df["game_date"]).dt.year

print(f"Calculating batter stats...")
batter_stats = (
    df.groupby(["batter", "year"])
    .agg(
        {
            "launch_speed": ["mean", "count"],
            "launch_angle": "mean",
        }
    )
    .reset_index()
)

batter_stats.columns = ["batter_id", "year", "avg_exit_velo", "at_bats", "avg_launch_angle"]
print(f"{len(batter_stats)} batter-years")
batter_stats.to_csv("data/batter_advanced_stats.csv", index=False)

print(f"Calculating pitcher stats...")
pitcher_stats = (
    df.groupby(["pitcher", "year"])
    .agg(
        {
            "release_speed": "mean",
            "pitch_type": "count",
            "game_date": "nunique",
        }
    )
    .reset_index()
)

pitcher_stats.columns = ["pitcher_id", "year", "avg_fastball_velo", "pitches_thrown", "games"]
print(f"{len(pitcher_stats)} pitcher-years")
pitcher_stats.to_csv("data/pitcher_advanced_stats.csv", index=False)

print("\nBoth stats saved!")
