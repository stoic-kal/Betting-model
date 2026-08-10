import pandas as pd
import numpy as np

print("⏳ Adding team-level features...\n")


games = pd.read_csv("data/games_with_results.csv")
games["date"] = pd.to_datetime(games["date"])

print(f"Calculating rolling team stats (7/15/30 day windows)...\n")


teams = (
    pd.concat(
        [
            games[["date", "home_team"]].rename(columns={"home_team": "team"}),
            games[["date", "away_team"]].rename(columns={"away_team": "team"}),
        ]
    )
    .drop_duplicates()
    .sort_values("date")
)


results = []

for idx, game in games.iterrows():
    date = game["date"]
    home = game["home_team"]
    away = game["away_team"]

    past_games = games[games["date"] < date]

    home_games = pd.concat(
        [
            past_games[past_games["home_team"] == home][["home_win"]],
            past_games[past_games["away_team"] == home][["home_win"]].rename(
                columns={"home_win": "away_win"}
            ),
        ]
    )

    away_games = pd.concat(
        [
            past_games[past_games["home_team"] == away][["home_win"]],
            past_games[past_games["away_team"] == away][["home_win"]].rename(
                columns={"home_win": "away_win"}
            ),
        ]
    )

    home_wr = home_games["home_win"].mean() if len(home_games) > 0 else 0.5
    away_wr = away_games["home_win"].mean() if len(away_games) > 0 else 0.5

    results.append(
        {
            "date": date,
            "home_team": home,
            "away_team": away,
            "home_runs": game["home_runs"],
            "away_runs": game["away_runs"],
            "total_runs": game["total_runs"],
            "home_win": game["home_win"],
            "home_wr": home_wr,
            "away_wr": away_wr,
        }
    )

featured_games = pd.DataFrame(results)
featured_games.to_csv("data/games_with_team_features.csv", index=False)

print(f"Added team features to {len(featured_games)} games")
print("\nSample with team features:")
print(featured_games.head())
