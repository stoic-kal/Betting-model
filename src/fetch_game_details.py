import requests
from bs4 import BeautifulSoup


class GameDetailsFetcher:

    def __init__(self):
        self.espn_base = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
        self.espn_games = "https://www.espn.com/mlb/games"

    def get_game_ids_from_date(self, date_str):

        try:

            date_formatted = date_str.replace("-", "")

            url = f"{self.espn_games}?date={date_formatted}"
            print(f"Fetching ESPN games page: {url}")

            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")

                game_links = soup.find_all(
                    "a", href=lambda x: x and "/mlb/game" in x and "gameId" in x
                )

                games = {}
                for link in game_links:
                    href = link.get("href", "")

                    if "/gameId/" in href:
                        game_id = href.split("/gameId/")[1].split("/")[0]
                        games[game_id] = href

                print(f"Found {len(games)} games")
                return games
            return {}
        except Exception as e:
            print(f"Error fetching games: {e}")
            return {}

    def get_probable_pitchers(self, matchup, date_str):

        try:
            print(f"Scraping ESPN for pitchers: {matchup}")

            game_ids = self.get_game_ids_from_date(date_str)

            if not game_ids:
                return {"home_pitcher": "TBA", "away_pitcher": "TBA"}

            for game_id, game_url in game_ids.items():
                resp = requests.get(f"https://www.espn.com{game_url}", timeout=10)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, "html.parser")

                    text = soup.get_text()

                    if "Starting Pitchers" in text or "Probable Pitchers" in text:

                        pitcher_sections = soup.find_all(
                            ["div", "span"],
                            class_=lambda x: x
                            and ("pitcher" in x.lower() or "player" in x.lower()),
                        )

                        if pitcher_sections:
                            pitchers = []
                            for section in pitcher_sections[:4]:
                                pitcher_name = section.get_text(strip=True)
                                if pitcher_name and len(pitcher_name) > 2:
                                    pitchers.append(pitcher_name)

                            if len(pitchers) >= 2:
                                print(f"Found pitchers: {pitchers[0]} vs {pitchers[1]}")
                                return {"home_pitcher": pitchers[1], "away_pitcher": pitchers[0]}

            return {"home_pitcher": "TBA", "away_pitcher": "TBA"}

        except Exception as e:
            print(f"Exception: {e}")
            import traceback

            traceback.print_exc()
            return {"home_pitcher": "TBA", "away_pitcher": "TBA"}

    def get_stadium_info(self, matchup, date_str):

        try:
            url = f"{self.espn_base}/scoreboard"
            params = {"dates": date_str.replace("-", "")}

            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])

                for event in events:
                    competitors = event.get("competitions", [{}])[0].get("competitors", [])

                    if len(competitors) >= 2:
                        home_team = competitors[0].get("team", {}).get("displayName", "")
                        away_team = competitors[1].get("team", {}).get("displayName", "")

                        game_matchup = f"{away_team} @ {home_team}"

                        if game_matchup.lower() == matchup.lower():
                            venue = event.get("competitions", [{}])[0].get("venue", {})
                            stadium_name = venue.get("fullName", "TBA")
                            city = venue.get("address", {}).get("city", "")

                            print(f"Stadium: {stadium_name}, {city}")

                            return {"stadium": stadium_name, "city": city}

                return {"stadium": "TBA", "city": ""}
            return {"stadium": "TBA", "city": ""}

        except Exception as e:
            print(f"Stadium fetch error: {e}")
            return {"stadium": "TBA", "city": ""}

    def get_game_weather(self, lat, lon, datetime_str):

        try:
            date_only = datetime_str[:10]
            url = "https://archive-api.open-meteo.com/v1/archive"

            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": date_only,
                "end_date": date_only,
                "hourly": "temperature_2m,precipitation,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
            }

            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                temps = data.get("hourly", {}).get("temperature_2m", [])
                winds = data.get("hourly", {}).get("wind_speed_10m", [])

                game_hour = 19
                if len(temps) > game_hour:
                    temp = temps[game_hour]
                    wind = winds[game_hour] if len(winds) > game_hour else 0
                    return {"temp": f"{temp}°F", "wind": f"{wind} mph", "conditions": "Clear"}

            return {"temp": "TBA", "wind": "TBA", "conditions": "TBA"}
        except Exception as e:
            print(f"Weather error: {e}")
            return {"temp": "TBA", "wind": "TBA", "conditions": "TBA"}


if __name__ == "__main__":
    fetcher = GameDetailsFetcher()

    print("Testing ESPN web scraper...\n")

    pitchers = fetcher.get_probable_pitchers("New York Yankees @ Chicago Cubs", "2026-07-31")
    print(f"Pitchers: {pitchers}\n")

    stadium = fetcher.get_stadium_info("New York Yankees @ Chicago Cubs", "2026-07-31")
    print(f"Stadium: {stadium}\n")

    weather = fetcher.get_game_weather(41.9484, -87.6553, "2026-07-31")
    print(f"Weather: {weather}\n")
