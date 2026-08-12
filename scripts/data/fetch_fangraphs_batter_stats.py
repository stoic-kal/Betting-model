import pandas as pd
import requests
from bs4 import BeautifulSoup

print("⏳ Fetching FanGraphs batter stats (2024-2026)...\n")

all_data = []

for year in [2024, 2025, 2026]:
    try:
        url = f"https://www.fangraphs.com/leaders.aspx?pos=all&stats=bat&lg=all&qual=1&type=8&season={year}&month=0&season1={year}&ind=0&team=0%2Cs&rost=0&age=0&filter=&players=0&startdate={year}-01-01&enddate={year}-12-31&sort=18%2Cd"

        print(f"Fetching {year}...")

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            print(f"{year}: Retrieved")
        else:
            print(f"{year}: Status {response.status_code}")

    except Exception as e:
        print(f"{year} error: {str(e)[:50]}")

print("\nNote: FanGraphs requires subscription for full data access")
print("Alternative: Use statcast data directly for feature engineering")
