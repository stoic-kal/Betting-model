import requests


class ProbablePitchersFetcher:

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"

    def get_game_pitcher(self, game_id):

        try:
            url = f"{self.base_url}/game/{game_id}"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                data = resp.json()

                home_pitcher = data.get("gameData", {}).get("probablePitchers", {}).get("home", {})
                away_pitcher = data.get("gameData", {}).get("probablePitchers", {}).get("away", {})

                return {
                    "home_pitcher": home_pitcher.get("person", {}).get("fullName", "TBA"),
                    "away_pitcher": away_pitcher.get("person", {}).get("fullName", "TBA"),
                    "home_pitcher_id": home_pitcher.get("person", {}).get("id"),
                    "away_pitcher_id": away_pitcher.get("person", {}).get("id"),
                }
            return None
        except:
            return None

    def get_team_schedule(self, team_id, date):

        try:
            url = f"{self.base_url}/teams/{team_id}/schedule"
            params = {"date": date}
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                games = data.get("games", [])

                if games:
                    game = games[0]
                    home_pitcher = game.get("teams", {}).get("home", {}).get("probablePitcher", {})
                    away_pitcher = game.get("teams", {}).get("away", {}).get("probablePitcher", {})

                    return {
                        "pitcher_name": home_pitcher.get("person", {}).get("fullName", "TBA"),
                        "pitcher_id": home_pitcher.get("person", {}).get("id"),
                    }
            return {"pitcher_name": "TBA", "pitcher_id": None}
        except:
            return {"pitcher_name": "TBA", "pitcher_id": None}


if __name__ == "__main__":
    fetcher = ProbablePitchersFetcher()

    print("Fetching probable pitchers...\n")
    result = fetcher.get_team_schedule(147, "2026-07-31")
    print(result)
