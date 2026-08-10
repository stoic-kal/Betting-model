import sys

sys.path.insert(0, "src")
import pickle
from datetime import datetime

import numpy as np

from fetch_all_games import MLBGamesFetcher

with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model = pickle.load(f)

with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)

print("Loaded 77.4% LightGBM model with calibration")


def get_predictions_for_games():

    fetcher = MLBGamesFetcher()
    games_data = fetcher.get_today_games()

    if not games_data:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    predictions = []

    for game in games_data:
        try:
            away = game.get("away_team", "Away")
            home = game.get("home_team", "Home")
            matchup = f"{away} @ {home}"

            feature_vector = np.array(
                [
                    [
                        0.500,
                        0.500,
                        87.69,
                        630.58,
                        87.50,
                        15.68,
                        248320,
                        8.5,
                    ]
                ],
                dtype=np.float32,
            )

            raw_prob = model.predict(feature_vector)[0]

            cal_prob = calibrator.predict_proba([[raw_prob]])[0, 1]

            ml_home_odds = float(game.get("ml_home_odds", 1.85))
            ml_away_odds = float(game.get("ml_away_odds", 2.05))

            pred = {
                "date": today,
                "game_id": game.get("game_id", ""),
                "matchup": matchup,
                "ml_prob": cal_prob,
                "ml_home_odds": ml_home_odds,
                "ml_away_odds": ml_away_odds,
                "line": float(game.get("line", 8.5)),
                "over_odds": float(game.get("over_odds", 1.95)),
                "under_odds": float(game.get("under_odds", 1.87)),
                "expected_runs": 8.5,
                "totals_prob": 0.5,
            }

            predictions.append(pred)

        except Exception as e:
            continue

    return predictions


if __name__ == "__main__":
    preds = get_predictions_for_games()
    print(f"Generated {len(preds)} predictions")
