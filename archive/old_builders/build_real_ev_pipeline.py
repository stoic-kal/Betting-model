import requests
import pandas as pd
import numpy as np
import pickle
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")

print("⏳ Building real +EV detection pipeline...\n")


with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model_ml = pickle.load(f)

with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)


url = "https://api.theoddsapi.com/odds/"
headers = {"x-api-key": API_KEY}
params = {"sport_key": "baseball_mlb", "markets": "h2h", "oddsFormat": "decimal"}

response = requests.get(url, headers=headers, params=params)
games_data = response.json()["data"] if response.status_code == 200 else []

print(f"Fetched {len(games_data)} real games from TheOddsAPI\n")

ev_picks = []

for game in games_data[:5]:
    matchup = f"{game['away_team']} @ {game['home_team']}"

    home_odds_list = []
    away_odds_list = []

    for book in game.get("books", []):
        if book["market"] == "h2h":
            for outcome in book["outcomes"]:
                if outcome["name"] == game["home_team"]:
                    home_odds_list.append(outcome["price"])
                else:
                    away_odds_list.append(outcome["price"])

    if not home_odds_list or not away_odds_list:
        continue

    fair_home_odds = np.mean(home_odds_list)
    fair_away_odds = np.mean(away_odds_list)
    fair_home_prob = 1 / fair_home_odds
    fair_away_prob = 1 / fair_away_odds

    total = fair_home_prob + fair_away_prob
    fair_home_prob_clean = fair_home_prob / total
    fair_away_prob_clean = fair_away_prob / total

    X = np.array([[0.5, 0.5, 87.69, 630.58, 87.50, 15.68, 248320, 8.5]], dtype=np.float32)
    raw_prob = model_ml.predict(X)[0]
    model_prob = calibrator.predict_proba([[raw_prob]])[0, 1]

    home_ev = (model_prob * fair_home_odds) - 1
    away_ev = ((1 - model_prob) * fair_away_odds) - 1

    if home_ev > away_ev and home_ev > 0:
        pick = "HOME"
        ev = home_ev
        odds = fair_home_odds
        prob = model_prob
    elif away_ev > 0:
        pick = "AWAY"
        ev = away_ev
        odds = fair_away_odds
        prob = 1 - model_prob
    else:
        continue

    ev_picks.append(
        {
            "date": game["start_time"][:10],
            "matchup": matchup,
            "pick": pick,
            "model_prob": prob,
            "fair_prob": fair_home_prob_clean if pick == "HOME" else fair_away_prob_clean,
            "fair_odds": odds,
            "ev_pct": ev * 100,
            "books_count": len(game["books"]),
        }
    )

    print(f"{matchup}")
    print(
        f"   Model: {prob:.1%} | Fair: {(fair_home_prob_clean if pick == 'HOME' else fair_away_prob_clean):.1%}"
    )
    print(f"   Pick: {pick} @ {odds:.2f} | EV: +{ev*100:.1f}%\n")

if ev_picks:
    df = pd.DataFrame(ev_picks)
    df.to_csv("data/real_ev_picks.csv", index=False)
    print(f"Logged {len(df)} +EV picks to data/real_ev_picks.csv")
else:
    print("No +EV picks found")
