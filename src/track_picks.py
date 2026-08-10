import os
import sqlite3
from datetime import datetime

import pandas as pd


class PickTracker:

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "database", "picks.db"
            )
        self.db_path = db_path
        self.init_db()

    def init_db(self):

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            matchup TEXT NOT NULL,
            pick_type TEXT NOT NULL,
            pick TEXT NOT NULL,
            odds REAL NOT NULL,
            model_prob REAL NOT NULL,
            ev REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_id INTEGER,
            game_id TEXT,
            actual_result TEXT,
            won INTEGER,
            profit_loss REAL,
            updated_at TEXT,
            FOREIGN KEY(pick_id) REFERENCES picks(id)
        )""")

        conn.commit()
        conn.close()

    def delete_picks_by_date(self, date_str):

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("DELETE FROM picks WHERE date = ?", (date_str,))

        conn.commit()
        deleted_count = c.rowcount
        conn.close()

        return deleted_count

    def log_pick(self, game_id, date, matchup, pick_type, pick, odds, model_prob, ev):

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        now = datetime.now().isoformat()

        try:
            c.execute(
                """INSERT INTO picks 
            (game_id, date, matchup, pick_type, pick, odds, model_prob, ev, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    game_id,
                    date,
                    matchup,
                    pick_type,
                    pick,
                    float(odds),
                    float(model_prob),
                    float(ev),
                    "pending",
                    now,
                    now,
                ),
            )

            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_stats(self):

        conn = sqlite3.connect(self.db_path)

        picks_df = pd.read_sql("SELECT * FROM picks", conn)
        conn.close()

        if len(picks_df) == 0:
            return {
                "total_picks": 0,
                "completed_picks": 0,
                "win_rate": 0.0,
                "wins": 0,
                "losses": 0,
                "total_profit": 0.0,
                "avg_ev": 0.0,
                "roi": 0.0,
                "pending_picks": 0,
            }

        total_picks = len(picks_df)
        completed_picks = len(picks_df[picks_df["status"].isin(["won", "lost"])])
        wins = len(picks_df[picks_df["status"] == "won"])
        losses = len(picks_df[picks_df["status"] == "lost"])
        pending_picks = len(picks_df[picks_df["status"] == "pending"])

        win_rate = (wins / completed_picks) if completed_picks > 0 else 0.0

        won_picks = picks_df[picks_df["status"] == "won"]
        lost_picks = picks_df[picks_df["status"] == "lost"]

        total_profit = 0.0
        if len(won_picks) > 0:
            total_profit += (won_picks["odds"] - 1).sum() * 20
        if len(lost_picks) > 0:
            total_profit -= len(lost_picks) * 20

        roi = (total_profit / (completed_picks * 20)) if completed_picks > 0 else 0.0

        return {
            "total_picks": int(total_picks),
            "completed_picks": int(completed_picks),
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(float(win_rate), 3),
            "total_profit": round(float(total_profit), 2),
            "roi": round(float(roi), 3),
            "avg_ev": 0.0,
            "pending_picks": int(pending_picks),
        }

    def get_recent_picks(self, limit=20):

        conn = sqlite3.connect(self.db_path)

        query = """
        SELECT * FROM picks
        ORDER BY created_at DESC
        LIMIT ?
        """

        df = pd.read_sql(query, conn, params=[limit])
        conn.close()

        return df


if __name__ == "__main__":
    tracker = PickTracker()
    stats = tracker.get_stats()
    print(f"\nStats: {stats}")
