import warnings

from pybaseball import batting_stats, pitching_stats

warnings.filterwarnings("ignore")


def fetch_mlb_advanced_stats():

    print("Fetching advanced MLB stats...")

    try:

        print("  Fetching pitcher stats...")
        pitchers = pitching_stats(start_season=2023, end_season=2024)

        print("  Fetching batter stats...")
        batters = batting_stats(start_season=2023, end_season=2024)

        print(f"Loaded {len(pitchers)} pitchers")
        print(f"Loaded {len(batters)} batters")

        return pitchers, batters

    except Exception as e:
        print(f"Error fetching stats: {e}")
        return None, None


if __name__ == "__main__":
    pitchers, batters = fetch_mlb_advanced_stats()
    if pitchers is not None:
        print("\nPitcher columns:", pitchers.columns.tolist()[:10])
        print(pitchers.head())
