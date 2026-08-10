import sys

import pandas as pd

sys.path.insert(0, "src")

from advanced_feature_builder import AdvancedFeatureBuilder
from calculate_team_stats import TeamStatsCalculator
from models_advanced import AdvancedMLBBettingModel


class Backtester:

    def __init__(self):
        self.model = AdvancedMLBBettingModel.load("models/advanced_model.pkl")
        calc = TeamStatsCalculator()
        self.games_df = pd.DataFrame(calc.get_full_season_games())
        self.builder = AdvancedFeatureBuilder(self.games_df)

    def backtest_by_ev_threshold(self, thresholds=[0.005, 0.01, 0.02, 0.05, 0.10]):

        print("Running backtest on 1,645 real 2026 games...\n")

        results = []

        for threshold in thresholds:
            picks = self._generate_picks(threshold)

            ml_picks = [p for p in picks if p["type"] == "moneyline"]
            tot_picks = [p for p in picks if p["type"] == "totals"]

            stats = self._calculate_stats(picks)

            results.append(
                {
                    "ev_threshold": f"{threshold*100:.1f}%",
                    "ml_picks": len(ml_picks),
                    "tot_picks": len(tot_picks),
                    "total_picks": len(picks),
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "win_rate": f"{stats['win_rate']:.1f}%",
                    "profit_loss": f"${stats['profit_loss']:.2f}",
                    "roi": f"{stats['roi']:.1f}%",
                    "avg_ev": f"{stats['avg_ev']:.2f}%",
                }
            )

        return pd.DataFrame(results)

    def _generate_picks(self, ev_threshold):

        picks = []

        for idx, game in self.games_df.iterrows():
            home_team = game["home_team"]
            away_team = game["away_team"]

            if home_team not in self.builder.team_stats or away_team not in self.builder.team_stats:
                continue

            features = self.builder.build_features(home_team, away_team)
            feature_df = pd.DataFrame([features])
            feature_scaled = self.model.scaler.transform(feature_df)

            ml_prob = self.model.moneyline_model.predict_proba(feature_scaled)[0][1]
            totals_prob = self.model.totals_model.predict_proba(feature_scaled)[0][1]

            ml_odds = 1.85
            ml_ev = (ml_prob * ml_odds) - 1

            if ml_ev > ev_threshold:
                home_won = 1 if game["home_runs"] > game["away_runs"] else 0
                profit = (ml_odds - 1) if home_won else -1

                picks.append(
                    {
                        "type": "moneyline",
                        "game": f"{away_team} @ {home_team}",
                        "pick": "HOME",
                        "prob": ml_prob,
                        "odds": ml_odds,
                        "ev": ml_ev,
                        "won": home_won,
                        "profit_loss": profit,
                    }
                )

            line = 8.5
            over_odds = 1.90
            under_odds = 1.90

            total_runs = game["home_runs"] + game["away_runs"]

            over_ev = (totals_prob * over_odds) - 1
            if over_ev > ev_threshold:
                over_won = 1 if total_runs > line else 0
                profit = (over_odds - 1) if over_won else -1

                picks.append(
                    {
                        "type": "totals",
                        "game": f"{away_team} @ {home_team}",
                        "pick": f"OVER {line}",
                        "prob": totals_prob,
                        "odds": over_odds,
                        "ev": over_ev,
                        "won": over_won,
                        "profit_loss": profit,
                    }
                )

        return picks

    def _calculate_stats(self, picks):

        if len(picks) == 0:
            return {"wins": 0, "losses": 0, "win_rate": 0, "profit_loss": 0, "roi": 0, "avg_ev": 0}

        df = pd.DataFrame(picks)
        wins = (df["won"] == 1).sum()
        losses = (df["won"] == 0).sum()
        total_profit = df["profit_loss"].sum()

        return {
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": (wins / len(picks) * 100) if len(picks) > 0 else 0,
            "profit_loss": total_profit,
            "roi": (total_profit / len(picks) * 100) if len(picks) > 0 else 0,
            "avg_ev": df["ev"].mean() * 100,
        }

    def backtest_by_pick_type(self):

        print("Analyzing Moneyline vs Totals performance...\n")

        picks = self._generate_picks(0.005)

        ml_picks = [p for p in picks if p["type"] == "moneyline"]
        tot_picks = [p for p in picks if p["type"] == "totals"]

        ml_stats = self._calculate_stats(ml_picks)
        tot_stats = self._calculate_stats(tot_picks)

        return pd.DataFrame(
            [
                {
                    "pick_type": "Moneyline",
                    "picks": len(ml_picks),
                    "wins": ml_stats["wins"],
                    "win_rate": f"{ml_stats['win_rate']:.1f}%",
                    "profit_loss": f"${ml_stats['profit_loss']:.2f}",
                    "roi": f"{ml_stats['roi']:.1f}%",
                },
                {
                    "pick_type": "Totals",
                    "picks": len(tot_picks),
                    "wins": tot_stats["wins"],
                    "win_rate": f"{tot_stats['win_rate']:.1f}%",
                    "profit_loss": f"${tot_stats['profit_loss']:.2f}",
                    "roi": f"{tot_stats['roi']:.1f}%",
                },
            ]
        )


if __name__ == "__main__":
    bt = Backtester()

    print("=" * 80)
    print("BACKTEST RESULTS: EV THRESHOLD ANALYSIS")
    print("=" * 80)
    print()

    threshold_results = bt.backtest_by_ev_threshold([0.005, 0.01, 0.02, 0.05, 0.10])
    print(threshold_results.to_string(index=False))

    print("\n" + "=" * 80)
    print("BACKTEST RESULTS: MONEYLINE VS TOTALS")
    print("=" * 80)
    print()

    type_results = bt.backtest_by_pick_type()
    print(type_results.to_string(index=False))
