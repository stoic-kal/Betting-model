from pybaseball import statcast
import pandas as pd

print("⏳ Fetching StatCast data (2024-2026)...\n")

all_data = []


try:
    print("Downloading 2024...")
    data = statcast(start_dt="2024-03-01", end_dt="2024-11-30")
    print(f"2024: {len(data)} rows")
    all_data.append(data)
except Exception as e:
    print(f"2024 error: {e}")


try:
    print("Downloading 2025...")
    data = statcast(start_dt="2025-03-01", end_dt="2025-11-30")
    print(f"2025: {len(data)} rows")
    all_data.append(data)
except Exception as e:
    print(f"2025 error: {e}")


try:
    print("Downloading 2026...")
    data = statcast(start_dt="2026-03-01", end_dt="2026-08-02")
    print(f"2026: {len(data)} rows")
    all_data.append(data)
except Exception as e:
    print(f"2026 error: {e}")

if all_data:
    combined = pd.concat(all_data, ignore_index=True)
    print(f"\nTotal: {len(combined)} rows")
    combined.to_csv("data/statcast_raw.csv", index=False)
    print("Saved to data/statcast_raw.csv")
else:
    print("No data downloaded")
