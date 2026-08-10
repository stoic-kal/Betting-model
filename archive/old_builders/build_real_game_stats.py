import pandas as pd
from datetime import datetime, timedelta

print("⏳ Building real team stats from 2026 games...\n")

games = pd.read_csv("data/games_with_all_features.csv")
games["date"] = pd.to_datetime(games["date"])


games_2026 = games[games["date"].dt.year == 2026].copy()

print(f"Found {len(games_2026)} games in 2026 so far\n")


team_stats = {}

for team in games_2026["home_team"].unique():
    home_games = games_2026[games_2026["home_team"] == team]
    away_games = games_2026[games_2026["away_team"] == team]

    if len(home_games) > 0:
        home_runs = home_games["home_runs"].mean()
        home_allowed = home_games["away_runs"].mean()
    else:
        home_runs = 4.34
        home_allowed = 4.42

    if len(away_games) > 0:
        away_runs = away_games["away_runs"].mean()
        away_allowed = away_games["home_runs"].mean()
    else:
        away_runs = 4.34
        away_allowed = 4.42

    team_stats[team] = {
        "home_runs": home_runs,
        "home_allowed": home_allowed,
        "away_runs": away_runs,
        "away_allowed": away_allowed,
    }


import json

with open("data/team_stats_2026.json", "w") as f:
    json.dump(team_stats, f, indent=2)

print("Team stats saved to data/team_stats_2026.json")
print("\nSample stats:")
for team, stats in list(team_stats.items())[:3]:
    print(f"\n{team}:")
    print(f"  Home: {stats['home_runs']:.2f} runs, {stats['home_allowed']:.2f} allowed")
    print(f"  Away: {stats['away_runs']:.2f} runs, {stats['away_allowed']:.2f} allowed")
