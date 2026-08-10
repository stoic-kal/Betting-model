import sys

sys.path.insert(0, "src")
from fetch_game_details import GameDetailsFetcher

game_details_fetcher = GameDetailsFetcher()


def get_game_details(matchup, date_str):

    try:
        print(f"Fetching details for {matchup} on {date_str}")

        pitchers = game_details_fetcher.get_probable_pitchers(matchup, date_str)
        stadium = game_details_fetcher.get_stadium_info(matchup, date_str)
        weather = game_details_fetcher.get_game_weather(40.7580, -73.8855, date_str)

        return {"status": "success", "pitchers": pitchers, "stadium": stadium, "weather": weather}
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}
