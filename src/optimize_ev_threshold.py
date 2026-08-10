import pandas as pd

from track_picks import PickTracker


class EVOptimizer:

    def __init__(self):
        self.tracker = PickTracker()

    def analyze_picks_by_ev(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT p.ev, r.won, r.profit_loss
        FROM picks p
        LEFT JOIN results r ON p.id = r.pick_id
        WHERE r.won IS NOT NULL
        ORDER BY p.ev
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) == 0:
            print("No completed picks yet for analysis")
            return None

        df["ev_bucket"] = pd.cut(
            df["ev"],
            bins=[0, 1, 2, 5, 10, 50, 100],
            labels=["0-1%", "1-2%", "2-5%", "5-10%", "10-50%", "50%+"],
        )

        analysis = (
            df.groupby("ev_bucket", observed=True)
            .agg({"won": ["count", "sum", "mean"], "profit_loss": ["sum", "mean"]})
            .round(3)
        )

        return analysis

    def recommend_ev_threshold(self):

        conn = __import__("sqlite3").connect(self.tracker.db_path)

        query = """
        SELECT p.ev, r.profit_loss
        FROM picks p
        LEFT JOIN results r ON p.id = r.pick_id
        WHERE r.profit_loss IS NOT NULL
        ORDER BY p.ev
        """

        df = pd.read_sql(query, conn)
        conn.close()

        if len(df) < 20:
            print("Need at least 20 completed picks for reliable analysis")
            return None

        results = []

        for threshold in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]:
            picks_above = df[df["ev"] >= threshold]

            if len(picks_above) == 0:
                continue

            roi = picks_above["profit_loss"].sum() / len(picks_above) * 100
            win_rate = (picks_above["profit_loss"] > 0).sum() / len(picks_above) * 100

            results.append(
                {
                    "ev_threshold": f"{threshold}%",
                    "picks": len(picks_above),
                    "wins": (picks_above["profit_loss"] > 0).sum(),
                    "win_rate": f"{win_rate:.1f}%",
                    "profit_loss": round(picks_above["profit_loss"].sum(), 2),
                    "roi": f"{roi:.1f}%",
                }
            )

        return pd.DataFrame(results)


if __name__ == "__main__":
    optimizer = EVOptimizer()

    print("Analyzing picks by EV bucket...\n")
    analysis = optimizer.analyze_picks_by_ev()

    if analysis is not None:
        print(analysis)

    print("\n\nEV Threshold Recommendations:\n")
    recs = optimizer.recommend_ev_threshold()

    if recs is not None:
        print(recs.to_string(index=False))
    else:
        print("Not enough completed picks yet for recommendations")
