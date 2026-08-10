import pandas as pd
import requests


class PitcherStatsCalculator:

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"

    def get_team_roster(self, team_id):

        try:
            url = f"{self.base_url}/teams/{team_id}?hydrate=roster"
            resp = requests.get(url)
            roster = resp.json()["roster"]

            pitchers = {}
            for player in roster:
                if player.get("position", {}).get("code") in ["P", "RP", "SP"]:
                    pitchers[player["person"]["id"]] = {
                        "name": player["person"]["fullName"],
                        "position": player.get("position", {}).get("code"),
                    }

            return pitchers
        except:
            return {}

    def get_pitcher_stats(self, pitcher_id):

        try:
            url = f"{self.base_url}/people/{pitcher_id}"
            params = {"hydrate": "stats(type=season)"}

            resp = requests.get(url, params=params)
            data = resp.json()["people"][0]

            pitching_stats = {}

            if "stats" in data:
                for stat_group in data["stats"]:
                    if stat_group["type"]["displayName"] == "season" and stat_group.get("stats"):
                        stats = stat_group["stats"]
                        pitching_stats = {
                            "era": float(stats.get("era", 0.0)) or 0.0,
                            "whip": float(stats.get("whip", 0.0)) or 0.0,
                            "wins": int(stats.get("wins", 0)),
                            "losses": int(stats.get("losses", 0)),
                            "innings_pitched": float(stats.get("inningsPitched", 0)) or 0.0,
                            "strikeouts": int(stats.get("strikeOuts", 0)),
                            "walks": int(stats.get("baseOnBalls", 0)),
                            "earned_runs": int(stats.get("earnedRuns", 0)),
                            "games_started": int(stats.get("gamesStarted", 0)),
                        }

            return pitching_stats if pitching_stats else self._default_stats()

        except:
            return self._default_stats()

    def _default_stats(self):

        return {
            "era": 4.0,
            "whip": 1.2,
            "wins": 0,
            "losses": 0,
            "innings_pitched": 0,
            "strikeouts": 0,
            "walks": 0,
            "earned_runs": 0,
            "games_started": 0,
        }

    def get_team_avg_pitcher_stats(self, team_id):

        roster = self.get_team_roster(team_id)
        all_stats = []

        for pitcher_id in roster.keys():
            stats = self.get_pitcher_stats(pitcher_id)
            all_stats.append(stats)

        if not all_stats:
            return self._default_stats()

        df = pd.DataFrame(all_stats)

        return {
            "avg_era": float(df["era"].mean()),
            "avg_whip": float(df["whip"].mean()),
            "total_wins": int(df["wins"].sum()),
            "total_strikeouts": int(df["strikeouts"].sum()),
            "avg_strikeouts": float(df["strikeouts"].mean()),
        }


if __name__ == "__main__":
    calc = PitcherStatsCalculator()

    print("Fetching Yankees pitcher stats...\n")
    stats = calc.get_team_avg_pitcher_stats(147)

    print("Pitcher Stats:")
    for key, val in stats.items():
        print(f"  {key}: {val}")
