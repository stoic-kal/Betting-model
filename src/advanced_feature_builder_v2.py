import pandas as pd

from fetch_pitcher_stats import PitcherStatsCalculator
from fetch_weather_data import InjuryFetcher, RestDaysCalculator, WeatherFetcher


class AdvancedFeatureBuilderV2:

    def __init__(self, games_df):
        self.games_df = games_df
        self.team_stats = self._calculate_all_stats()
        self.pitcher_calc = PitcherStatsCalculator()
        self.weather_fetcher = WeatherFetcher()
        self.injury_fetcher = InjuryFetcher()
        self.rest_calc = RestDaysCalculator(games_df)

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

            team_stats[team] = {
"win_pct": (home_wins + away_wins) / len(all_games),
"runs_for_pg": (home_games["home_runs"].sum() + away_games["away_runs"].sum())
                / len(all_games),
"runs_allowed_pg": (home_games["away_runs"].sum() + away_games["home_runs"].sum())
                / len(all_games),
            }

        return team_stats

    def build_features(
        self,
        home_team,
        away_team,
        home_team_id,
        away_team_id,
        game_date,
        home_lat=None,
        home_lon=None,
    ):

        home_stat = self.team_stats.get(home_team, {})
        away_stat = self.team_stats.get(away_team, {})

        weather = {}
        if home_lat and home_lon:
            weather = self.weather_fetcher.get_game_weather(home_lat, home_lon, game_date)
        else:
            weather = self.weather_fetcher._default_weather()

        home_injuries = self.injury_fetcher.get_team_injuries(home_team_id)
        away_injuries = self.injury_fetcher.get_team_injuries(away_team_id)

        home_rest = self.rest_calc.get_rest_days(home_team, game_date)
        away_rest = self.rest_calc.get_rest_days(away_team, game_date)

        features = {
"home_win_pct": home_stat.get("win_pct", 0.5),
"away_win_pct": away_stat.get("win_pct", 0.5),
"home_runs_pg": home_stat.get("runs_for_pg", 5.0),
"away_runs_pg": away_stat.get("runs_for_pg", 5.0),
"home_runs_allowed": home_stat.get("runs_allowed_pg", 5.0),
"away_runs_allowed": away_stat.get("runs_allowed_pg", 5.0),
"runs_diff": home_stat.get("runs_for_pg", 5.0) - away_stat.get("runs_for_pg", 5.0),
"win_pct_diff": home_stat.get("win_pct", 0.5) - away_stat.get("win_pct", 0.5),
"total_expected": home_stat.get("runs_for_pg", 5.0) + away_stat.get("runs_for_pg", 5.0),
"home_avg_era": 4.0,
"home_avg_whip": 1.2,
"away_avg_era": 4.0,
"away_avg_whip": 1.2,
"era_diff": 0.0,
"whip_diff": 0.0,
"temperature": weather["temperature"],
"wind_speed": weather["wind_speed"],
"is_hot": 1.0 if weather["is_hot"] else 0.0,
"is_windy": 1.0 if weather["is_windy"] else 0.0,
"home_injured_count": home_injuries["injured_count"],
"away_injured_count": away_injuries["injured_count"],
"home_has_key_injuries": 1.0 if home_injuries["has_key_injuries"] else 0.0,
"away_has_key_injuries": 1.0 if away_injuries["has_key_injuries"] else 0.0,
"home_rest_days": min(home_rest, 7),
"away_rest_days": min(away_rest, 7),
"home_is_rested": 1.0 if home_rest >= 2 else 0.0,
"away_is_rested": 1.0 if away_rest >= 2 else 0.0,
        }

        return features
