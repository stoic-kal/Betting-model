from datetime import datetime, timedelta

import pandas as pd

print("⏳ Loading historical games...")
games = pd.read_csv("data/games_engineered_features.csv")
games["date"] = pd.to_datetime(games["date"])


def get_team_recent_stats(team_name, reference_date, days_back=30):

    cutoff = reference_date - timedelta(days=days_back)

    team_games = games[
        ((games["home_team"] == team_name) | (games["away_team"] == team_name))
        & (games["date"] >= cutoff)
        & (games["date"] < reference_date)
    ]

    if len(team_games) == 0:

        season_games = games[(games["home_team"] == team_name) | (games["away_team"] == team_name)]
        if len(season_games) > 0:
            return {
"wr": season_games["home_win"].mean(),
"avg_runs": season_games["total_runs"].mean(),
            }
        else:
            return {"wr": 0.5, "avg_runs": 8.5}

    return {
"wr": team_games["home_win"].mean(),
"avg_runs": team_games["total_runs"].mean(),
    }


def get_features_for_game(home_team, away_team, game_date):

    game_date = pd.to_datetime(game_date)

    home_stats = get_team_recent_stats(home_team, game_date, days_back=30)
    away_stats = get_team_recent_stats(away_team, game_date, days_back=30)

    return {
"home_wr": home_stats["wr"],
"away_wr": away_stats["wr"],
"home_avg_runs": home_stats["avg_runs"],
"away_avg_runs": away_stats["avg_runs"],
    }


if __name__ == "__main__":

    today = datetime.now()

    test_game = get_features_for_game("Boston Red Sox", "Los Angeles Dodgers", today)
    print(f"\nTest: Boston Red Sox vs LA Dodgers")
    print(f"Home WR: {test_game['home_wr']:.1%}")
    print(f"Away WR: {test_game['away_wr']:.1%}")
    print(f"Avg runs (home): {test_game['home_avg_runs']:.1f}")
    print(f"Avg runs (away): {test_game['away_avg_runs']:.1f}")
