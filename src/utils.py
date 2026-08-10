from pathlib import Path


def create_database():

    import sqlite3

    Path("database").mkdir(exist_ok=True)
    conn = sqlite3.connect("database/picks.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            date DATE,
            game_id TEXT,
            home_team TEXT,
            away_team TEXT,
            model_probability REAL,
            odds REAL,
            ev_percentage REAL,
            pick_side TEXT,
            status TEXT DEFAULT 'PENDING',
            result TEXT,
            profit REAL
        )
    """)

    conn.commit()
    conn.close()
    print("Database created")


if __name__ == "__main__":
    create_database()
