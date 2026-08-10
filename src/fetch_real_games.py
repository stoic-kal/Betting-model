import os

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


def fetch_mlb_games_with_lines():

    api_key = os.getenv("ODDS_API_KEY")

    if not api_key:
        print("Error: ODDS_API_KEY not found in .env file")
        return pd.DataFrame()

    try:
        url = "https://api.theoddsapi.com/odds/"

        headers = {"x-api-key": api_key}

        params = {
            "sport_key": "baseball_mlb",
            "regions": "us",
            "markets": "totals",
            "oddsFormat": "decimal",
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"API Error: {response.status_code}")
            print(f"Response: {response.text}")
            return pd.DataFrame()

        data = response.json()
        games = []

        if "data" not in data:
            print("No games found in API response")
            return pd.DataFrame()

        for event in data["data"]:

            away_team = event["away_team"].split()[-1][:3].upper()
            home_team = event["home_team"].split()[-1][:3].upper()

            for book in event["books"]:
                if book["market"] == "totals":
                    over = None
                    under = None
                    total_line = None

                    for outcome in book["outcomes"]:
                        if outcome["name"] == "Over":
                            over = outcome["price"]
                            total_line = outcome.get("point")
                        elif outcome["name"] == "Under":
                            under = outcome["price"]

                    if total_line and over and under:
                        games.append(
                            {
                                "game_id": event["event_id"],
                                "date": event["start_time"],
                                "away_team": away_team,
                                "home_team": home_team,
                                "total_line": total_line,
                                "sportsbook": book["book"],
                                "over_odds": over,
                                "under_odds": under,
                            }
                        )

        df = pd.DataFrame(games)
        print(f"Found {len(df)} total lines across all books")
        return df

    except Exception as e:
        print(f"Error fetching games: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame()


if __name__ == "__main__":
    games = fetch_mlb_games_with_lines()
    if len(games) > 0:
        print(f"\nFound {len(games)} games")
        print(games.head())
    else:
        print("No games found")
