import requests
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")

print("⏳ Fetching real game odds from TheOddsAPI...\n")

url = "https://api.theoddsapi.com/odds/"
headers = {"x-api-key": API_KEY}
params = {"sport_key": "baseball_mlb", "markets": "h2h,totals", "oddsFormat": "decimal"}

try:
    response = requests.get(url, headers=headers, params=params, timeout=10)

    print(f"Status: {response.status_code}")

    if response.status_code != 200:
        print(f"Error: {response.text}")
    else:
        data = response.json()
        print(f"Fetched data\n")
        print(f"Response keys: {data.keys()}")
        print(f"\nFirst 500 chars:\n{str(data)[:500]}")

except Exception as e:
    print(f"Error: {e}")
