import sys

sys.path.insert(0, "src")
import pickle
from datetime import datetime

import numpy as np
import requests

from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY
MIN_BOOKS = 3

with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model_ml = pickle.load(f)
with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)


def _market_implied_probs(odds_list_a, odds_list_b):

    raw_a = np.mean([1.0 / o for o in odds_list_a])
    raw_b = np.mean([1.0 / o for o in odds_list_b])
    total = raw_a + raw_b
    return raw_a / total, raw_b / total


def get_predictions_for_games():
    url = "https://api.theoddsapi.com/odds/"
    headers = {"x-api-key": API_KEY}
    params = {"sport_key": "baseball_mlb", "markets": "h2h,totals", "oddsFormat": "decimal"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        games_data = response.json().get("data", [])
    except:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    predictions = []

    for game in games_data:
        try:
            matchup = f"{game['away_team']} @ {game['home_team']}"
            home_odds_list = []
            away_odds_list = []
            totals_by_line = {}

            for book in game.get("books", []):
                market = book.get("market")

                if market == "h2h":
                    for outcome in book.get("outcomes", []):
                        price = outcome.get("price")
                        if price is not None:
                            if outcome.get("name") == game["home_team"]:
                                home_odds_list.append(float(price))
                            else:
                                away_odds_list.append(float(price))

                elif market == "totals":
                    for outcome in book.get("outcomes", []):
                        point = outcome.get("point")
                        price = outcome.get("price")
                        name = outcome.get("name")

                        if all(x is not None for x in [point, price, name]):
                            line = float(point)
                            if line not in totals_by_line:
                                totals_by_line[line] = {"over": [], "under": []}

                            if name == "Over":
                                totals_by_line[line]["over"].append(float(price))
                            elif name == "Under":
                                totals_by_line[line]["under"].append(float(price))

            if len(home_odds_list) >= MIN_BOOKS and len(away_odds_list) >= MIN_BOOKS:
                fair_home = np.mean(home_odds_list)
                fair_away = np.mean(away_odds_list)

                home_prob, away_prob = _market_implied_probs(home_odds_list, away_odds_list)

                home_ev = (home_prob * fair_home) - 1
                away_ev = (away_prob * fair_away) - 1

                if home_ev > away_ev and home_ev > 0.01:
                    predictions.append(
                        {
"date": today,
"game_id": game.get("event_id"),
"matchup": matchup,
"ml_prob": home_prob,
"ml_home_odds": fair_home,
"ml_away_odds": fair_away,
"line": None,
"over_odds": None,
"under_odds": None,
"expected_runs": None,
"totals_prob": None,
"ev_pct": home_ev * 100,
                        }
                    )
                elif away_ev > 0.01:
                    predictions.append(
                        {
"date": today,
"game_id": game.get("event_id"),
"matchup": matchup,
"ml_prob": away_prob,
"ml_home_odds": fair_home,
"ml_away_odds": fair_away,
"line": None,
"over_odds": None,
"under_odds": None,
"expected_runs": None,
"totals_prob": None,
"ev_pct": away_ev * 100,
                        }
                    )

            for line, odds in totals_by_line.items():
                if len(odds["over"]) >= MIN_BOOKS and len(odds["under"]) >= MIN_BOOKS:
                    fair_over = np.mean(odds["over"])
                    fair_under = np.mean(odds["under"])

                    over_prob, under_prob = _market_implied_probs(odds["over"], odds["under"])

                    over_ev = (over_prob * fair_over) - 1
                    under_ev = (under_prob * fair_under) - 1

                    if over_ev > under_ev and over_ev > 0.01:
                        predictions.append(
                            {
"date": today,
"game_id": game.get("event_id"),
"matchup": matchup,
"ml_prob": None,
"ml_home_odds": None,
"ml_away_odds": None,
"line": line,
"over_odds": fair_over,
"under_odds": fair_under,
"expected_runs": None,
"totals_prob": over_prob,
"ev_pct": over_ev * 100,
                            }
                        )
                    elif under_ev > 0.01:
                        predictions.append(
                            {
"date": today,
"game_id": game.get("event_id"),
"matchup": matchup,
"ml_prob": None,
"ml_home_odds": None,
"ml_away_odds": None,
"line": line,
"over_odds": fair_over,
"under_odds": fair_under,
"expected_runs": None,
"totals_prob": under_prob,
"ev_pct": under_ev * 100,
                            }
                        )

        except:
            continue

    return predictions
