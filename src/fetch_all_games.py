from datetime import datetime

import requests


class MLBGamesFetcher:

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"

    def get_games_by_date(self, date_str):

        try:
            url = f"{self.base_url}/schedule"
            params = {"sportId": 1, "date": date_str}

            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code != 200:
                print(f"Error: {resp.status_code}")
                return []

            data = resp.json()

            dates = data.get("dates", [])
            if not dates:
                return []

            games = dates[0].get("games", [])

            games_list = []

            for game in games:
                try:
                    home_team = (
                        game.get("teams", {}).get("home", {}).get("team", {}).get("name", "Unknown")
                    )
                    away_team = (
                        game.get("teams", {}).get("away", {}).get("team", {}).get("name", "Unknown")
                    )

                    game_data = {
                        "game_id": game.get("gamePk"),
                        "date": date_str,
                        "home_team": home_team,
                        "away_team": away_team,
                        "start_time": game.get("gameDateTime"),
                        "status": game.get("status"),
                    }
                    games_list.append(game_data)
                except Exception as e:
                    print(f"Error parsing game: {e}")
                    continue

            return games_list

        except Exception as e:
            print(f"Error fetching from MLB Stats API: {e}")
            import traceback

            traceback.print_exc()
            return []

    def get_today_games(self):

        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_games_by_date(today)


if __name__ == "__main__":
    fetcher = MLBGamesFetcher()

    print("Fetching ALL MLB games from MLB Stats API...\n")
    games = fetcher.get_today_games()

    print(f"Found {len(games)} total games:\n")
    for game in games:
        print(f"{game['away_team']} @ {game['home_team']}")
