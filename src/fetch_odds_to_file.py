import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


class OddsFetcher:

    def __init__(self):
        self.api_key = os.getenv("ODDS_API_KEY")
        self.base_url = "https://api.theoddsapi.com/odds/"
        self.output_file = "data/all_odds.json"
        Path("data").mkdir(exist_ok=True)

    def fetch_and_save(self):

        print("Fetching odds from TheOddsAPI Pro...\n")

        params = {
            "sport": "baseball_mlb",
            "regions": "us",
            "markets": "moneyline,totals",
            "oddsFormat": "decimal",
        }

        headers = {"x-api-key": self.api_key}

        try:
            resp = requests.get(self.base_url, params=params, headers=headers, timeout=15)

            print(f"Status: {resp.status_code}")

            if resp.status_code == 401:
                print("Invalid API key")
                return False

            if resp.status_code == 429:
                print("Rate limit reached")
                return False

            if resp.status_code == 400:
                print("Bad Request")
                print(f"Response: {resp.json()}")
                return False

            resp.raise_for_status()
            data = resp.json()

            games = []

            for event in data.get("events", []):
                try:
                    game_id = event["id"]
                    date = event["commence_time"][:10]
                    home_team = event["home_team"]
                    away_team = event["away_team"]

                    ml_home = None
                    ml_away = None
                    total_line = 8.5
                    over_odds = 1.90
                    under_odds = 1.90

                    for bookmaker in event.get("bookmakers", []):
                        for market in bookmaker.get("markets", []):
                            if market["key"] == "moneyline":
                                for outcome in market["outcomes"]:
                                    if outcome["name"] == home_team:
                                        ml_home = outcome["price"]
                                    elif outcome["name"] == away_team:
                                        ml_away = outcome["price"]

                            elif market["key"] == "totals":
                                for outcome in market["outcomes"]:
                                    if "Over" in outcome["name"]:
                                        total_line = outcome["point"]
                                        over_odds = outcome["price"]
                                    elif "Under" in outcome["name"]:
                                        under_odds = outcome["price"]

                    game_data = {
                        "game_id": game_id,
                        "date": date,
                        "home_team": home_team,
                        "away_team": away_team,
                        "ml_home_odds": ml_home,
                        "ml_away_odds": ml_away,
                        "total_line": total_line,
                        "over_odds": over_odds,
                        "under_odds": under_odds,
                        "fetched_at": datetime.now().isoformat(),
                    }

                    games.append(game_data)

                except Exception as e:
                    print(f"Error parsing game: {e}")
                    continue

            with open(self.output_file, "w") as f:
                json.dump(games, f, indent=2)

            print(f"Fetched {len(games)} games")
            print(f"Saved to {self.output_file}\n")

            return True

        except Exception as e:
            print(f"Error: {e}")
            return False

    def load_odds(self):

        try:
            with open(self.output_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"File not found: {self.output_file}")
            return []

    def display_odds(self):

        odds = self.load_odds()

        if odds:
            df = pd.DataFrame(odds)
            print(df[["date", "away_team", "home_team", "total_line"]].to_string())
        else:
            print("No odds available")


if __name__ == "__main__":
    fetcher = OddsFetcher()
    if fetcher.fetch_and_save():
        fetcher.display_odds()
