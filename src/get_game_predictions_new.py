import sys

sys.path.insert(0, "src")
import pickle

import numpy as np

from fetch_all_games import MLBGamesFetcher

try:
    with open("models/lightgbm_ml_model.pkl", "rb") as f:
        ml_model_data = pickle.load(f)
    with open("models/poisson_totals_model.pkl", "rb") as f:
        totals_model_data = pickle.load(f)

    ml_model = ml_model_data["model"]
    ml_scaler = ml_model_data["scaler"]

    totals_home_model = totals_model_data["home_model"]
    totals_away_model = totals_model_data["away_model"]
    totals_scaler = totals_model_data["scaler"]

    ENSEMBLE_LOADED = True
    print("Loaded Ensemble Models")
except:
    ENSEMBLE_LOADED = False
    print("Ensemble models not found - using fallback predictions")


def get_predictions_for_games():

    fetcher = MLBGamesFetcher()
    games = fetcher.fetch_games()

    if not games:
        print("No games found")
        return []

    predictions = []

    for game in games:
        try:
            matchup = f"{game.get('away_team', 'Away')} @ {game.get('home_team', 'Home')}"

            model_prob = np.random.uniform(0.45, 0.55)
            odds = np.random.uniform(1.5, 2.5)
            ev = (model_prob * odds - 1) * 100

            feature_vector = np.array([[model_prob, odds, ev]], dtype=np.float32)

            if ENSEMBLE_LOADED:
                ml_probs = ml_model.predict(ml_scaler.transform(feature_vector))[0]
                home_runs = totals_home_model.predict(totals_scaler.transform(feature_vector))[0]
                away_runs = totals_away_model.predict(totals_scaler.transform(feature_vector))[0]
                total_runs = home_runs + away_runs
            else:
                ml_probs = model_prob
                total_runs = 8.5

            ml_home_odds = 1.85 if ml_probs > 0.5 else 2.05
            ml_away_odds = 2.05 if ml_probs > 0.5 else 1.85

            pred = {
                "game_id": game.get("game_id", ""),
                "matchup": matchup,
                "ml_prob": ml_probs,
                "ml_home_odds": ml_home_odds,
                "ml_away_odds": ml_away_odds,
                "line": 8.5,
                "over_odds": 1.95,
                "under_odds": 1.87,
                "expected_runs": total_runs,
                "totals_prob": 0.5,
            }

            predictions.append(pred)

        except Exception as e:
            print(f"Error on {game.get('matchup', 'unknown')}: {e}")
            continue

    return predictions


if __name__ == "__main__":
    preds = get_predictions_for_games()
    print(f"\nGenerated {len(preds)} predictions")
