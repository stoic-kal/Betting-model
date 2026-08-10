from datetime import datetime

import pandas as pd
import requests


class TeamStatsCalculator:

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"

    def get_full_season_games(self):

        start_date = "2026-03-28"
        end_date = datetime.now().strftime("%Y-%m-%d")

        url = f"{self.base_url}/schedule"
        params = {"startDate": start_date, "endDate": end_date, "sportId": 1}

        resp = requests.get(url, params=params)
        all_games = []

        for date_obj in resp.json()["dates"]:
            for game in date_obj["games"]:
                if game["status"]["abstractGameState"] in ["Final", "Completed", "Completed Early"]:
                    try:
                        home_team = game["teams"]["home"]["team"]["name"]
                        away_team = game["teams"]["away"]["team"]["name"]

                        if "All-Star" in home_team or "All-Star" in away_team:
                            continue
                        if "MLB" in home_team or "MLB" in away_team:
                            continue

                        home_runs = game["teams"]["home"].get("score", 0)
                        away_runs = game["teams"]["away"].get("score", 0)

                        all_games.append(
                            {
                                "game_id": game["gamePk"],
                                "date": date_obj["date"],
                                "home_team": home_team,
                                "away_team": away_team,
                                "home_runs": home_runs,
                                "away_runs": away_runs,
                            }
                        )
                    except:
                        continue

        return all_games

    def calculate_team_stats(self, games_df):

        team_stats = {}

        for team in pd.concat([games_df["home_team"], games_df["away_team"]]).unique():
            home_games = games_df[games_df["home_team"] == team]
            away_games = games_df[games_df["away_team"] == team]

            all_games = pd.concat([home_games, away_games])

            if len(all_games) == 0:
                continue

            home_runs_for = home_games["home_runs"].sum()
            away_runs_for = away_games["away_runs"].sum()
            total_runs_for = home_runs_for + away_runs_for

            home_runs_against = home_games["away_runs"].sum()
            away_runs_against = away_games["home_runs"].sum()
            total_runs_against = home_runs_against + away_runs_against

            home_wins = (home_games["home_runs"] > home_games["away_runs"]).sum()
            away_wins = (away_games["away_runs"] > away_games["home_runs"]).sum()
            total_wins = home_wins + away_wins

            team_stats[team] = {
                "games_played": len(all_games),
                "wins": int(total_wins),
                "losses": int(len(all_games) - total_wins),
                "win_pct": float(total_wins / len(all_games)) if len(all_games) > 0 else 0.5,
                "runs_for_pg": (
                    float(total_runs_for / len(all_games)) if len(all_games) > 0 else 5.0
                ),
                "runs_against_pg": (
                    float(total_runs_against / len(all_games)) if len(all_games) > 0 else 5.0
                ),
                "home_runs_pg": (
                    float(home_runs_for / len(home_games)) if len(home_games) > 0 else 5.0
                ),
                "away_runs_pg": (
                    float(away_runs_for / len(away_games)) if len(away_games) > 0 else 5.0
                ),
            }

        return team_stats


if __name__ == "__main__":
    calc = TeamStatsCalculator()
    print("Fetching FULL 2026 regular season games...")
    games = calc.get_full_season_games()

    if games:
        games_df = pd.DataFrame(games)
        print(f"Found {len(games_df)} completed REGULAR SEASON games")

        stats = calc.calculate_team_stats(games_df)
        print(f"Calculated stats for {len(stats)} teams\n")

        for team, team_stat in sorted(
            list(stats.items()), key=lambda x: x[1]["win_pct"], reverse=True
        )[:10]:
            print(f"{team}:")
            print(f"  Record: {team_stat['wins']}-{team_stat['losses']}")
            print(f"  Win %: {team_stat['win_pct']:.1%}")
            print(f"  Runs/Game: {team_stat['runs_for_pg']:.1f}\n")
    else:
        print("No games found")
