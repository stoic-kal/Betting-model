import requests
import pandas as pd
import numpy as np
from datetime import datetime
from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY

print("⏳ Building +EV detection engine...\n")


url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/events"
params = {"apiKey": API_KEY, "markets": "h2h", "oddsFormat": "decimal"}

try:
    response = requests.get(url, params=params)
    games = response.json()["events"] if response.status_code == 200 else []
    print(f"Fetched {len(games)} games from TheOddsAPI\n")

    print("Calculating fair odds across all bookmakers:\n")

    ev_data = []

    for game in games[:3]:
        matchup = f"{game['away_team']} @ {game['home_team']}"

        all_home_odds = []
        all_away_odds = []

        for bookmaker in game.get("bookmakers", []):
            for market in bookmaker["markets"]:
                if market["key"] == "h2h":
                    for outcome in market["outcomes"]:
                        if outcome["name"] == game["home_team"]:
                            all_home_odds.append(outcome["price"])
                        else:
                            all_away_odds.append(outcome["price"])

        if all_home_odds and all_away_odds:

            home_probs = [1 / odd for odd in all_home_odds]
            away_probs = [1 / odd for odd in all_away_odds]

            fair_home_prob = np.mean(home_probs)
            fair_away_prob = np.mean(away_probs)

            fair_home_odds = 1 / fair_home_prob
            fair_away_odds = 1 / fair_away_prob

            print(f"{matchup}:")
            print(f"  Fair HOME odds: {fair_home_odds:.2f} ({fair_home_prob*100:.1f}%)")
            print(f"  Fair AWAY odds: {fair_away_odds:.2f} ({fair_away_prob*100:.1f}%)")
            print(f"  DK HOME: {all_home_odds[0]:.2f} (implied {1/all_home_odds[0]*100:.1f}%)")
            print(f"  FD HOME: {all_home_odds[1]:.2f if len(all_home_odds) > 1 else 'N/A'}")
            print()

except Exception as e:
    print(f"Error: {e}")
