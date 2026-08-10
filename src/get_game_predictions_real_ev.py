import sys

sys.path.insert(0, "src")
import pickle
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY


with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model_ml = pickle.load(f)
with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)
with open("models/poisson_home_runs.pkl", "rb") as f:
    model_home_runs = pickle.load(f)
with open("models/poisson_away_runs.pkl", "rb") as f:
    model_away_runs = pickle.load(f)


games = pd.read_csv("data/games_engineered_features.csv")
games["date"] = pd.to_datetime(games["date"])


def get_team_avg_features(team_name):

    team_games = games[(games["home_team"] == team_name) | (games["away_team"] == team_name)]

    if len(team_games) == 0:

        return {
"wr": 0.5,
"avg_fastball_velo": 87.69,
"avg_pitches": 630.58,
"avg_exit_velo": 87.50,
"avg_launch_angle": 15.68,
        }

    return {
"wr": team_games["home_wr"].mean(),
"avg_fastball_velo": team_games["league_avg_fastball_velo"].mean(),
"avg_pitches": team_games["league_avg_pitches_per_game"].mean(),
"avg_exit_velo": team_games["league_exit_velo"].mean(),
"avg_launch_angle": team_games["league_launch_angle"].mean(),
    }


def get_predictions_for_games():
    url = "https://api.theoddsapi.com/odds/"
    headers = {"x-api-key": API_KEY}
    params = {"sport_key": "baseball_mlb", "markets": "h2h,totals", "oddsFormat": "decimal"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        games_data = response.json().get("data", [])
    except:
        return []

    if not games_data:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    predictions = []

    for game in games_data:
        try:
            home_team = game["home_team"]
            away_team = game["away_team"]
            matchup = f"{away_team} @ {home_team}"

            home_stats = get_team_avg_features(home_team)
            away_stats = get_team_avg_features(away_team)

            X = np.array(
                [
                    [
                        home_stats["wr"],
                        away_stats["wr"],
                        home_stats["avg_fastball_velo"],
                        home_stats["avg_pitches"],
                        home_stats["avg_exit_velo"],
                        home_stats["avg_launch_angle"],
                        248320,
                        8.5,
                    ]
                ],
                dtype=np.float32,
            )

            home_odds_list = []
            away_odds_list = []
            totals_by_line = {}

            for book in game.get("books", []):
                market = book.get("market")

                if market == "h2h":
                    for outcome in book.get("outcomes", []):
                        price = outcome.get("price")
                        if price is not None:
                            if outcome.get("name") == home_team:
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

            if home_odds_list and away_odds_list:
                raw_prob = model_ml.predict(X)[0]
                model_prob = calibrator.predict_proba([[raw_prob]])[0, 1]
                fair_home = np.mean(home_odds_list)
                fair_away = np.mean(away_odds_list)
                home_ev = (model_prob * fair_home) - 1
                away_ev = ((1 - model_prob) * fair_away) - 1

                if home_ev > away_ev and home_ev > 0.01:
                    predictions.append(
                        {
"date": today,
"game_id": game["event_id"],
"matchup": matchup,
"ml_prob": model_prob,
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
"game_id": game["event_id"],
"matchup": matchup,
"ml_prob": 1 - model_prob,
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

            home_runs = float(model_home_runs.predict(X)[0])
            away_runs = float(model_away_runs.predict(X)[0])
            total_runs = home_runs + away_runs

            for line, odds in totals_by_line.items():
                if odds["over"] and odds["under"]:
                    fair_over = np.mean(odds["over"])
                    fair_under = np.mean(odds["under"])

                    over_prob = 1.0 - poisson.cdf(int(line), total_runs)
                    under_prob = 1.0 - over_prob

                    over_ev = (over_prob * fair_over) - 1
                    under_ev = (under_prob * fair_under) - 1

                    if over_ev > under_ev and over_ev > 0.01:
                        predictions.append(
                            {
"date": today,
"game_id": game["event_id"],
"matchup": matchup,
"ml_prob": None,
"ml_home_odds": None,
"ml_away_odds": None,
"line": line,
"over_odds": fair_over,
"under_odds": fair_under,
"expected_runs": total_runs,
"totals_prob": over_prob,
"ev_pct": over_ev * 100,
                            }
                        )
                    elif under_ev > 0.01:
                        predictions.append(
                            {
"date": today,
"game_id": game["event_id"],
"matchup": matchup,
"ml_prob": None,
"ml_home_odds": None,
"ml_away_odds": None,
"line": line,
"over_odds": fair_over,
"under_odds": fair_under,
"expected_runs": total_runs,
"totals_prob": under_prob,
"ev_pct": under_ev * 100,
                            }
                        )

        except Exception as e:
            continue

    return predictions
