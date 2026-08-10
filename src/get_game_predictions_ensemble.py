import sys

sys.path.insert(0, "src")
import pickle
from datetime import datetime

import numpy as np
from scipy.stats import poisson

from fetch_all_games import MLBGamesFetcher

print("⏳ Loading ensemble models...\n")


with open("models/lightgbm_90pct_model.pkl", "rb") as f:
    model_ml = pickle.load(f)

with open("models/calibrator.pkl", "rb") as f:
    calibrator = pickle.load(f)


with open("models/poisson_home_runs.pkl", "rb") as f:
    model_home_runs = pickle.load(f)

with open("models/poisson_away_runs.pkl", "rb") as f:
    model_away_runs = pickle.load(f)

print("Ensemble loaded: LightGBM ML + Poisson Totals\n")


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

            raw_prob = model_ml.predict(feature_vector)[0]
            cal_prob = calibrator.predict_proba([[raw_prob]])[0, 1]

            ml_home_odds = float(game.get("ml_home_odds", 1.85))
            ml_away_odds = float(game.get("ml_away_odds", 2.05))

            home_runs_pred = model_home_runs.predict(feature_vector)[0]
            away_runs_pred = model_away_runs.predict(feature_vector)[0]
            total_runs_pred = home_runs_pred + away_runs_pred

            line = float(game.get("line", 8.5))

            over_prob = 1.0 - poisson.cdf(int(line), total_runs_pred)
            under_prob = 1.0 - over_prob

            over_odds = float(game.get("over_odds", 1.95))
            under_odds = float(game.get("under_odds", 1.87))

            pred = {
                "date": today,
                "game_id": game.get("game_id", ""),
                "matchup": matchup,
                "ml_prob": cal_prob,
                "ml_home_odds": ml_home_odds,
                "ml_away_odds": ml_away_odds,
                "line": line,
                "over_odds": over_odds,
                "under_odds": under_odds,
                "expected_runs": total_runs_pred,
                "totals_prob": over_prob,
            }

            predictions.append(pred)

        except Exception as e:
            continue

    return predictions


if __name__ == "__main__":
    preds = get_predictions_for_games()
    print(f"Generated {len(preds)} predictions (ML + Totals)")
