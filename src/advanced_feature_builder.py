import pandas as pd

from fetch_pitcher_stats import PitcherStatsCalculator


class AdvancedFeatureBuilder:

    def __init__(self, games_df):
        self.games_df = games_df
        self.team_stats = self._calculate_all_stats()
        self.pitcher_calc = PitcherStatsCalculator()

    def _calculate_all_stats(self):

        team_stats = {}

        for team in pd.concat([self.games_df["home_team"], self.games_df["away_team"]]).unique():
            home_games = self.games_df[self.games_df["home_team"] == team]
            away_games = self.games_df[self.games_df["away_team"] == team]
            all_games = pd.concat([home_games, away_games])

            if len(all_games) == 0:
                continue

            home_wins = (home_games["home_runs"] > home_games["away_runs"]).sum()
            away_wins = (away_games["away_runs"] > away_games["home_runs"]).sum()

            recent_10 = all_games.tail(10)
            recent_wins = (
                recent_10[recent_10["home_team"] == team]["home_runs"]
                > recent_10[recent_10["home_team"] == team]["away_runs"]
            ).sum() + (
                recent_10[recent_10["away_team"] == team]["away_runs"]
                > recent_10[recent_10["away_team"] == team]["home_runs"]
            ).sum()

            home_runs_scored = home_games["home_runs"].tolist()
            away_runs_scored = away_games["away_runs"].tolist()
            all_runs_scored = home_runs_scored + away_runs_scored

            if len(all_runs_scored) > 1:
                consistency = pd.Series(all_runs_scored).std()
            else:
                consistency = 0

            team_stats[team] = {
"games_played": len(all_games),
"total_wins": home_wins + away_wins,
"total_losses": len(all_games) - (home_wins + away_wins),
"win_pct": (home_wins + away_wins) / len(all_games),
"home_win_pct": home_wins / len(home_games) if len(home_games) > 0 else 0.5,
"away_win_pct": away_wins / len(away_games) if len(away_games) > 0 else 0.5,
"recent_form_pct": recent_wins / len(recent_10) if len(recent_10) > 0 else 0.5,
"runs_for_pg": (home_games["home_runs"].sum() + away_games["away_runs"].sum())
                / len(all_games),
"home_runs_pg": (
                    home_games["home_runs"].sum() / len(home_games) if len(home_games) > 0 else 5.0
                ),
"away_runs_pg": (
                    away_games["away_runs"].sum() / len(away_games) if len(away_games) > 0 else 5.0
                ),
"runs_allowed_pg": (home_games["away_runs"].sum() + away_games["home_runs"].sum())
                / len(all_games),
"consistency": consistency,
"run_differential": (
                    home_games["home_runs"].sum()
                    + away_games["away_runs"].sum()
                    - home_games["away_runs"].sum()
                    - away_games["home_runs"].sum()
                )
                / len(all_games),
            }

        return team_stats

    def get_h2h_record(self, team1, team2):

        h2h = self.games_df[
            ((self.games_df["home_team"] == team1) & (self.games_df["away_team"] == team2))
            | ((self.games_df["home_team"] == team2) & (self.games_df["away_team"] == team1))
        ]

        if len(h2h) == 0:
            return 0.5

        team1_wins = ((h2h["home_team"] == team1) & (h2h["home_runs"] > h2h["away_runs"])).sum() + (
            (h2h["away_team"] == team1) & (h2h["away_runs"] > h2h["home_runs"])
        ).sum()

        return team1_wins / len(h2h) if len(h2h) > 0 else 0.5

    def build_features(self, home_team, away_team, home_team_id=None, away_team_id=None):

        home_stat = self.team_stats.get(home_team, {})
        away_stat = self.team_stats.get(away_team, {})

        h2h_pct = self.get_h2h_record(home_team, away_team)

        home_pitcher_stats = {}
        away_pitcher_stats = {}

        if home_team_id:
            home_pitcher_stats = self.pitcher_calc.get_team_avg_pitcher_stats(home_team_id)
        if away_team_id:
            away_pitcher_stats = self.pitcher_calc.get_team_avg_pitcher_stats(away_team_id)

        features = {
"home_win_pct_all": home_stat.get("win_pct", 0.5),
"home_win_pct_home": home_stat.get("home_win_pct", 0.5),
"home_recent_form": home_stat.get("recent_form_pct", 0.5),
"home_runs_pg": home_stat.get("runs_for_pg", 5.0),
"home_runs_pg_home": home_stat.get("home_runs_pg", 5.0),
"home_runs_allowed_pg": home_stat.get("runs_allowed_pg", 5.0),
"home_consistency": home_stat.get("consistency", 1.5),
"home_run_diff": home_stat.get("run_differential", 0.0),
"away_win_pct_all": away_stat.get("win_pct", 0.5),
"away_win_pct_away": away_stat.get("away_win_pct", 0.5),
"away_recent_form": away_stat.get("recent_form_pct", 0.5),
"away_runs_pg": away_stat.get("runs_for_pg", 5.0),
"away_runs_pg_away": away_stat.get("away_runs_pg", 5.0),
"away_runs_allowed_pg": away_stat.get("runs_allowed_pg", 5.0),
"away_consistency": away_stat.get("consistency", 1.5),
"away_run_diff": away_stat.get("run_differential", 0.0),
"h2h_home_record": h2h_pct,
"runs_diff": home_stat.get("runs_for_pg", 5.0) - away_stat.get("runs_for_pg", 5.0),
"runs_allowed_diff": away_stat.get("runs_allowed_pg", 5.0)
            - home_stat.get("runs_allowed_pg", 5.0),
"total_expected": home_stat.get("runs_for_pg", 5.0) + away_stat.get("runs_for_pg", 5.0),
"consistency_diff": home_stat.get("consistency", 1.5)
            - away_stat.get("consistency", 1.5),
"form_diff": home_stat.get("recent_form_pct", 0.5)
            - away_stat.get("recent_form_pct", 0.5),
"home_avg_era": home_pitcher_stats.get("avg_era", 4.0),
"home_avg_whip": home_pitcher_stats.get("avg_whip", 1.2),
"home_avg_k": home_pitcher_stats.get("avg_strikeouts", 5.0),
"away_avg_era": away_pitcher_stats.get("avg_era", 4.0),
"away_avg_whip": away_pitcher_stats.get("avg_whip", 1.2),
"away_avg_k": away_pitcher_stats.get("avg_strikeouts", 5.0),
"era_diff": home_pitcher_stats.get("avg_era", 4.0)
            - away_pitcher_stats.get("avg_era", 4.0),
"k_diff": home_pitcher_stats.get("avg_strikeouts", 5.0)
            - away_pitcher_stats.get("avg_strikeouts", 5.0),
        }

        return features
