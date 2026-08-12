import sqlite3
import csv
import os

db_path = os.path.abspath("database/picks.db")

print(f"Database path: {db_path}")
print(f"File exists: {os.path.exists(db_path)}")
print(f"File size: {os.path.getsize(db_path)} bytes")


with open("/Users/kalyaan/Downloads/picks_import.csv", "r") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"CSV rows: {len(rows)}")


conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Connected to database")


cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='picks';")
table_exists = cursor.fetchone()[0]
print(f"Picks table exists: {table_exists > 0}")


inserted = 0
for i, row in enumerate(rows):
    unique_game_id = f"{row['game_id']}_{row['pick'].replace(' ', '_')}"

    try:
        cursor.execute(
            """
            INSERT OR IGNORE INTO picks (game_id, date, matchup, pick_type, pick, odds, model_prob, ev, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                unique_game_id,
                row["date"],
                row["matchup"],
                row["pick_type"],
                row["pick"],
                row["odds"],
                row["model_prob"],
                row["ev"],
                row["status"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        inserted += 1
    except Exception as e:
        print(f"Error on row {i}: {e}")

conn.commit()
print(f"Committed {inserted} rows")


count = cursor.execute("SELECT COUNT(*) FROM picks;").fetchone()[0]
print(f"Database now has {count} picks")

conn.close()
