import sys

sys.path.insert(0, "src")
import math
import sqlite3

import pandas as pd


def _safe(val):

    if val is None:
        return None
    try:
        if math.isnan(float(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return val


UNIT_SIZE = 20


def get_results(date_filter=None):

    conn = sqlite3.connect("database/picks.db")

    if date_filter:
        picks_df = pd.read_sql(
"SELECT * FROM picks WHERE ev > 0.1 AND status IN ('pending','won','lost','push') AND date = ? ORDER BY pick_type DESC, created_at DESC",
            conn,
            params=[date_filter],
        )
    else:
        picks_df = pd.read_sql(
"SELECT * FROM picks WHERE ev > 0.1 AND status IN ('pending','won','lost','push') ORDER BY date DESC, created_at DESC",
            conn,
        )

    conn.close()

    results = []
    for idx, pick in picks_df.iterrows():

        if pick["status"] == "won":
            units_won = (pick["odds"] - 1) * UNIT_SIZE
            roi_pct = (pick["odds"] - 1) * 100
        elif pick["status"] == "lost":
            units_won = -UNIT_SIZE
            roi_pct = -100
        elif pick["status"] == "push":
            units_won = 0
            roi_pct = 0
        else:
            units_won = 0
            roi_pct = 0

        results.append(
            {
"date": pick["date"],
"matchup": pick["matchup"],
"pick_type": pick["pick_type"],
"pick": pick["pick"],
"model_prob": f"{pick['model_prob']*100:.1f}%",
"odds": f"{pick['odds']:.3f}",
"closing_odds": _safe(pick["closing_odds"]),
"clv": _safe(pick["clv"]),
"ev": f"{pick['ev']:.1f}%",
"kelly_units": _safe(pick["kelly_units"]) if "kelly_units" in pick.index else None,
"status": pick["status"],
"units": f"{units_won:+.0f}" if pick["status"] != "pending" else "-",
"roi": f"{roi_pct:+.1f}%" if pick["status"] != "pending" else "-",
            }
        )

    return {"status": "success", "results": results, "total": len(results)}
