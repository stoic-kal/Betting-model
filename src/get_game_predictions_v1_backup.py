import sys

sys.path.insert(0, "src")
import warnings
from datetime import datetime

import numpy as np
from scipy.stats import poisson

from fetch_all_games import MLBGamesFetcher

warnings.filterwarnings("ignore")


def calculate_totals_prob(expected_runs, line):

    try:
        over_prob = 1.0 - poisson.cdf(line, expected_runs)
        return np.clip(over_prob, 0.01, 0.99)
    except:
        if expected_runs > line:
            return min(0.75, expected_runs / (line + 1))
        else:
            return max(0.25, expected_runs / (line + 1))


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

            ml_home_odds = float(game.get("ml_home_odds", 1.85))
            ml_away_odds = float(game.get("ml_away_odds", 2.05))
            line = float(game.get("line", 8.5))
            over_odds = float(game.get("over_odds", 1.95))
            under_odds = float(game.get("under_odds", 1.87))

            implied_home_prob = 1.0 / ml_home_odds
            implied_away_prob = 1.0 / ml_away_odds

            total = implied_home_prob + implied_away_prob
            implied_home_prob /= total
            implied_away_prob /= total

            expected_runs = line

            totals_prob = calculate_totals_prob(expected_runs, line)

            pred = {
                "date": today,
                "game_id": game.get("game_id", ""),
                "matchup": matchup,
                "ml_prob": implied_home_prob,
                "ml_home_odds": ml_home_odds,
                "ml_away_odds": ml_away_odds,
                "line": line,
                "over_odds": over_odds,
                "under_odds": under_odds,
                "expected_runs": expected_runs,
                "totals_prob": totals_prob,
            }

            predictions.append(pred)

        except Exception as e:
            continue

    return predictions


if __name__ == "__main__":
    preds = get_predictions_for_games()
    print(f"Generated {len(preds)} predictions with implied odds")
