import pandas as pd

from track_picks import PickTracker


class DashboardMetrics:

    def __init__(self):
        self.tracker = PickTracker()

    def get_overall_stats(self):

        return self.tracker.get_stats()

    def get_daily_performance(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT DATE(p.date) as date, 
               COUNT(*) as picks,
               SUM(r.won) as wins,
               SUM(r.profit_loss) as profit
        FROM picks p
        LEFT JOIN results r ON p.id = r.pick_id
        WHERE r.won IS NOT NULL
        GROUP BY DATE(p.date)
        ORDER BY date DESC
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) == 0:
            return pd.DataFrame()

        df["win_rate"] = (df["wins"] / df["picks"] * 100).round(1)
        df["roi"] = (df["profit"] / df["picks"] * 100).round(1)

        return df

    def get_pick_type_performance(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT p.pick_type,
               COUNT(*) as picks,
               SUM(r.won) as wins,
               SUM(r.profit_loss) as profit
        FROM picks p
        LEFT JOIN results r ON p.id = r.pick_id
        WHERE r.won IS NOT NULL
        GROUP BY p.pick_type
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) == 0:
            return pd.DataFrame()

        df["win_rate"] = (df["wins"] / df["picks"] * 100).round(1)
        df["roi"] = (df["profit"] / df["picks"] * 100).round(1)
        df["avg_profit"] = (df["profit"] / df["picks"]).round(2)

        return df

    def get_ev_performance(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT p.ev,
               r.won,
               r.profit_loss
        FROM picks p
        LEFT JOIN results r ON p.id = r.pick_id
        WHERE r.won IS NOT NULL
        ORDER BY p.ev
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) == 0:
            return pd.DataFrame()

        df["ev_bucket"] = pd.cut(
            df["ev"], bins=[0, 1, 2, 5, 10, 100], labels=["0-1%", "1-2%", "2-5%", "5-10%", "10%+"]
        )

        analysis = (
            df.groupby("ev_bucket", observed=True)
            .agg({"won": ["count", "sum", "mean"], "profit_loss": ["sum", "mean"]})
            .round(3)
        )

        return analysis

    def get_win_streak(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT r.won FROM results r
        ORDER BY r.updated_at DESC
        LIMIT 20
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) == 0:
            return {"streak": 0, "type": "none", "details": "No results yet"}

        streak = 0
        streak_type = df.iloc[0]["won"]

        for _, row in df.iterrows():
            if row["won"] == streak_type:
                streak += 1
            else:
                break

        streak_label = "Win" if streak_type == 1 else "Loss"

        return {
            "streak": streak,
            "type": streak_label,
            "details": f"{streak} {streak_label.lower()} streak",
        }


if __name__ == "__main__":
    metrics = DashboardMetrics()

    print("DASHBOARD METRICS\n")

    stats = metrics.get_overall_stats()
    print("Overall Stats:")
    for key, val in stats.items():
        print(f"  {key}: {val}")

    print("\n\nDaily Performance:")
    daily = metrics.get_daily_performance()
    print(daily.to_string())

    print("\n\nPick Type Performance:")
    types = metrics.get_pick_type_performance()
    print(types.to_string())

    print("\n\nWin Streak:")
    streak = metrics.get_win_streak()
    print(streak)
