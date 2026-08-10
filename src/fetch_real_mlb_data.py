from datetime import datetime, timedelta

import requests


def get_mlb_teams():

    url = "https://statsapi.mlb.com/api/v1/teams"
    resp = requests.get(url)
    teams = resp.json()["teams"]

    team_map = {}
    for team in teams:
        team_map[team["name"]] = {
            "id": team["id"],
            "abbreviation": team["teamName"],
            "name": team["name"],
        }

    return team_map


def get_team_stats(team_id, season=2026):

    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}"
    params = {"season": season}

    resp = requests.get(url, params=params)
    data = resp.json()

    if "teams" in data and len(data["teams"]) > 0:
        team = data["teams"][0]
        return team
    return None


def get_games_by_date(start_date, end_date):

    url = "https://statsapi.mlb.com/api/v1/schedule"
    params = {"startDate": start_date, "endDate": end_date, "sportId": 1}

    resp = requests.get(url, params=params)
    games = resp.json()["dates"]

    all_games = []
    for date_obj in games:
        for game in date_obj["games"]:
            all_games.append(
                {
                    "game_id": game["gamePk"],
                    "date": date_obj["date"],
                    "home_team": game["teams"]["home"]["team"]["name"],
                    "away_team": game["teams"]["away"]["team"]["name"],
                    "status": game["status"]["abstractGameState"],
                }
            )

    return all_games


def get_game_box_score(game_id):

    url = f"https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"

    resp = requests.get(url)
    data = resp.json()

    if "teams" in data:
        home_runs = data["teams"]["home"]["teamStats"]["batting"].get("runs", 0)
        away_runs = data["teams"]["away"]["teamStats"]["batting"].get("runs", 0)

        return {
            "home_runs": home_runs,
            "away_runs": away_runs,
            "winner": "home" if home_runs > away_runs else "away",
        }

    return None


if __name__ == "__main__":
    print("Testing MLB Stats API...")

    teams = get_mlb_teams()
    print(f"Loaded {len(teams)} teams")

    today = datetime.now().strftime("%Y-%m-%d")
    week_later = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    games = get_games_by_date(today, week_later)
    print(f"Found {len(games)} games this week")

    if games:
        print(f"   Sample: {games[0]}")
