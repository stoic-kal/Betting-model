import os
import sys

sys.path.insert(0, "src")
import pandas as pd
import requests
from dotenv import load_dotenv

from advanced_feature_builder import AdvancedFeatureBuilder
from calculate_team_stats import TeamStatsCalculator
from fetch_all_games import MLBGamesFetcher
from models_advanced import AdvancedMLBBettingModel
from team_id_mapper import get_team_id

load_dotenv()


def american_to_decimal(american_odds):

    if american_odds > 0:
        return (american_odds / 100) + 1
    else:
        return (100 / abs(american_odds)) + 1


def get_predictions_for_games():

    api_key = os.getenv("ODDS_API_KEY")

    print("Fetching ALL games from MLB Stats API...\n")

    mlb_fetcher = MLBGamesFetcher()
    all_games = mlb_fetcher.get_today_games()

    print(f"Found {len(all_games)} total games\n")

    try:
        url = "https://api.theoddsapi.com/odds/"
        params = {
            "sport_key": "baseball_mlb",
            "regions": "us",
            "markets": "h2h,totals",
            "oddsFormat": "american",
        }
        headers = {"x-api-key": api_key}

        resp = requests.get(url, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "data" in data:
                odds_games = data["data"]
            elif isinstance(data, list):
                odds_games = data
            else:
                odds_games = []
        else:
            odds_games = []

        odds_map = {}
        for game in odds_games:
            key = f"{game.get('away_team')}_{game.get('home_team')}"
            odds_map[key] = game

        print(f"Found odds for {len(odds_games)} games from TheOddsAPI\n")

    except Exception as e:
        print(f" Error fetching odds: {e}")
        odds_map = {}

    calc = TeamStatsCalculator()
    all_games_df = pd.DataFrame(calc.get_full_season_games())
    builder = AdvancedFeatureBuilder(all_games_df)
    model = AdvancedMLBBettingModel.load("models/advanced_model.pkl")

    predictions = []

    for game in all_games:
        try:
            game_id = game.get("game_id")
            date = game.get("date")
            home_team = game.get("home_team")
            away_team = game.get("away_team")

            print(f"Processing: {away_team} @ {home_team}...", end=" ")

            if home_team not in builder.team_stats or away_team not in builder.team_stats:
                print(" Team not in stats")
                continue

            home_team_id = get_team_id(home_team)
            away_team_id = get_team_id(away_team)

            feature_row = builder.build_features(home_team, away_team, home_team_id, away_team_id)
            feature_df = pd.DataFrame([feature_row])
            feature_scaled = model.scaler.transform(feature_df)

            ml_prob = model.moneyline_model.predict_proba(feature_scaled)[0][1]
            totals_prob = model.totals_model.predict_proba(feature_scaled)[0][1]

            ml_home_decimal = 1.85
            ml_away_decimal = 1.85
            total_line = 8.5
            over_decimal = 1.90
            under_decimal = 1.90

            odds_key = f"{away_team}_{home_team}"
            if odds_key in odds_map:
                odds_game = odds_map[odds_key]

                for book in odds_game.get("books", []):
                    market_name = book.get("market", "")

                    if market_name == "h2h":
                        for outcome in book.get("outcomes", []):
                            american = outcome.get("price", 0)
                            decimal = american_to_decimal(american)

                            if outcome["name"] == home_team:
                                ml_home_decimal = decimal
                            elif outcome["name"] == away_team:
                                ml_away_decimal = decimal

                    elif market_name == "totals":
                        for outcome in book.get("outcomes", []):
                            american = outcome.get("price", 0)
                            decimal = american_to_decimal(american)
                            point = outcome.get("point", 8.5)

                            if "Over" in outcome["name"]:
                                total_line = point
                                over_decimal = decimal
                            elif "Under" in outcome["name"]:
                                under_decimal = decimal

            expected_runs = feature_row["total_expected"]

            prediction = {
                "game_id": game_id,
                "date": date,
                "matchup": f"{away_team.split()[-1]} @ {home_team.split()[-1]}",
                "home_team": home_team,
                "away_team": away_team,
                "ml_prob": ml_prob,
                "ml_home_odds": ml_home_decimal,
                "ml_away_odds": ml_away_decimal,
                "totals_prob": totals_prob,
                "expected_runs": expected_runs,
                "line": total_line,
                "over_odds": over_decimal,
                "under_odds": under_decimal,
            }

            predictions.append(prediction)
            print("")

        except Exception as e:
            print(f"{e}")
            continue

    print(f"\nGenerated {len(predictions)} predictions\n")
    return predictions


if __name__ == "__main__":
    predictions = get_predictions_for_games()
    for pred in predictions[:15]:
        print(
            f"{pred['date']} | {pred['matchup']:20} | ML: {pred['ml_prob']:.1%} | Totals: {pred['totals_prob']:.1%}"
        )
