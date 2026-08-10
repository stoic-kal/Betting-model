import pandas as pd
import requests


class WeatherFetcher:

    def __init__(self):

        self.weather_url = "https://archive-api.open-meteo.com/v1/archive"

    def get_game_weather(self, latitude, longitude, date):

        try:
            params = {
"latitude": latitude,
"longitude": longitude,
"start_date": date,
"end_date": date,
"hourly": "temperature_2m,wind_speed_10m",
"temperature_unit": "fahrenheit",
            }

            resp = requests.get(self.weather_url, params=params)
            data = resp.json()

            if "hourly" not in data:
                return self._default_weather()

            temps = data["hourly"]["temperature_2m"]
            winds = data["hourly"]["wind_speed_10m"]

            afternoon_temps = temps[12:18] if len(temps) > 18 else temps
            afternoon_winds = winds[12:18] if len(winds) > 18 else winds

            return {
"temperature": (
                    sum(afternoon_temps) / len(afternoon_temps) if afternoon_temps else 70
                ),
"wind_speed": sum(afternoon_winds) / len(afternoon_winds) if afternoon_winds else 5,
"is_hot": (
                    (sum(afternoon_temps) / len(afternoon_temps)) > 80 if afternoon_temps else False
                ),
"is_windy": (
                    (sum(afternoon_winds) / len(afternoon_winds)) > 12 if afternoon_winds else False
                ),
            }

        except:
            return self._default_weather()

    def _default_weather(self):

        return {
"temperature": 70,
"wind_speed": 5,
"is_hot": False,
"is_windy": False,
        }


class InjuryFetcher:

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"

    def get_team_injuries(self, team_id):

        try:
            url = f"{self.base_url}/teams/{team_id}?hydrate=roster"
            resp = requests.get(url)

            team_data = resp.json()["teams"][0]

            injuries = []
            for player in team_data.get("roster", []):
                status = player.get("status", {}).get("code", "")
                if status in ["IL", "IL60", "IL10", "BEREAVEMENT"]:
                    position = player.get("position", {}).get("code", "")
                    injuries.append(
                        {
"name": player["person"]["fullName"],
"position": position,
"status": status,
                        }
                    )

            return {
"injured_count": len(injuries),
"has_key_injuries": len(injuries) > 2,
"injuries": injuries,
            }

        except:
            return {"injured_count": 0, "has_key_injuries": False, "injuries": []}


class RestDaysCalculator:

    def __init__(self, games_df):
        self.games_df = games_df

    def get_rest_days(self, team, game_date):

        try:

            team_games = self.games_df[
                ((self.games_df["home_team"] == team) | (self.games_df["away_team"] == team))
                & (self.games_df["date"] < game_date)
            ].sort_values("date")

            if len(team_games) == 0:
                return 5

            last_game_date = team_games.iloc[-1]["date"]
            rest_days = (pd.Timestamp(game_date) - pd.Timestamp(last_game_date)).days

            return rest_days

        except:
            return 1
