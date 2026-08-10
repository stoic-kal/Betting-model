import csv
import io
import logging
import math
import sqlite3
from typing import Optional

from services.pitcher_prop_db import DB_PATH

logger = logging.getLogger(__name__)

_GRADED = ("'won','lost','push'",)


def _conn(path: str = DB_PATH):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def _outcome_binary(result_status: str) -> Optional[float]:

    if result_status == "won":
        return 1.0
    if result_status == "lost":
        return 0.0
    return None


def brier_score(rows: list[sqlite3.Row]) -> Optional[float]:

    total = 0.0
    n = 0
    for r in rows:
        y = _outcome_binary(r["result_status"])
        if y is None:
            continue
        p = r["model_prob"]
        if p is None:
            continue
        total += (p - y) ** 2
        n += 1
    return round(total / n, 5) if n > 0 else None


def mae(rows: list[sqlite3.Row]) -> Optional[float]:

    total = 0.0
    n = 0
    for r in rows:
        ev = r["expected_value_stat"]
        rv = r["result_value"]
        stat = r["result_status"]
        if ev is None or rv is None or stat == "void":
            continue
        total += abs(ev - rv)
        n += 1
    return round(total / n, 3) if n > 0 else None


def expected_calibration_error(rows: list[sqlite3.Row], n_bins: int = 10) -> Optional[float]:

    bins = [[] for _ in range(n_bins)]
    for r in rows:
        y = _outcome_binary(r["result_status"])
        p = r["model_prob"]
        if y is None or p is None:
            continue
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append((p, y))

    total_weighted = 0.0
    n_total = sum(len(b) for b in bins)
    if n_total == 0:
        return None
    for b in bins:
        if not b:
            continue
        avg_p = sum(x[0] for x in b) / len(b)
        avg_y = sum(x[1] for x in b) / len(b)
        total_weighted += (len(b) / n_total) * abs(avg_p - avg_y)
    return round(total_weighted, 5)


def calibration_curve(rows: list[sqlite3.Row], n_bins: int = 10) -> list[dict]:

    bins: list[list] = [[] for _ in range(n_bins)]
    for r in rows:
        y = _outcome_binary(r["result_status"])
        p = r["model_prob"]
        if y is None or p is None:
            continue
        bin_idx = min(int(p * n_bins), n_bins - 1)
        bins[bin_idx].append((p, y))

    curve = []
    for i, b in enumerate(bins):
        if not b:
            continue
        lo = i / n_bins
        hi = (i + 1) / n_bins
        curve.append(
            {
"bin": f"{lo:.1f}-{hi:.1f}",
"avg_predicted": round(sum(x[0] for x in b) / len(b), 4),
"avg_actual": round(sum(x[1] for x in b) / len(b), 4),
"n": len(b),
            }
        )
    return curve


def avg_clv(rows: list[sqlite3.Row]) -> Optional[float]:

    vals = [r["clv_pp"] for r in rows if r["clv_pp"] is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def push_rate(rows: list[sqlite3.Row]) -> Optional[float]:
    resolved = [r for r in rows if r["result_status"] in ("won", "lost", "push")]
    if not resolved:
        return None
    pushes = sum(1 for r in resolved if r["result_status"] == "push")
    return round(pushes / len(resolved), 4)


def get_pitcher_prop_analytics(
    prop_type: Optional[str] = None,
    classification: Optional[str] = None,
    since_date: Optional[str] = None,
    model_version: Optional[str] = None,
    path: str = DB_PATH,
) -> dict:

    conn = _conn(path)
    q = """
        SELECT *
        FROM pitcher_prop_official_locks
        WHERE forecast_stage='lineup_lock'
          AND result_status IN ('won','lost','push','void')
"""
    params: list = []
    if prop_type:
        q += " AND prop_type=?"
        params.append(prop_type)
    if classification:
        q += " AND classification=?"
        params.append(classification)
    if since_date:
        q += " AND lock_date>=?"
        params.append(since_date)
    if model_version:
        q += " AND model_version=?"
        params.append(model_version)
    q += " ORDER BY lock_date"

    rows = conn.execute(q, params).fetchall()
    conn.close()

    all_graded = [r for r in rows if r["result_status"] in ("won", "lost", "push")]
    non_void = [r for r in rows if r["result_status"] != "void"]
    won_rows = [r for r in all_graded if r["result_status"] == "won"]
    lost_rows = [r for r in all_graded if r["result_status"] == "lost"]
    push_rows = [r for r in all_graded if r["result_status"] == "push"]

    n_total = len(rows)
    n_graded = len(all_graded)
    n_won = len(won_rows)
    n_lost = len(lost_rows)
    n_push = len(push_rows)
    n_void = len([r for r in rows if r["result_status"] == "void"])
    win_rate = round(n_won / (n_won + n_lost), 4) if (n_won + n_lost) > 0 else None

    cls_counts: dict = {}
    for r in all_graded:
        cls = r["classification"]
        if cls not in cls_counts:
            cls_counts[cls] = {"n": 0, "won": 0, "lost": 0, "push": 0}
        cls_counts[cls]["n"] += 1
        cls_counts[cls][r["result_status"]] += 1

    pt_counts: dict = {}
    for r in all_graded:
        pt = r["prop_type"]
        if pt not in pt_counts:
            pt_counts[pt] = {"n": 0, "won": 0, "lost": 0, "push": 0}
        pt_counts[pt]["n"] += 1
        pt_counts[pt][r["result_status"]] += 1

    return {
"total": n_total,
"graded": n_graded,
"won": n_won,
"lost": n_lost,
"push": n_push,
"void": n_void,
"win_rate": win_rate,
"brier_score": brier_score(all_graded),
"mae": mae(non_void),
"ece": expected_calibration_error(all_graded),
"calibration": calibration_curve(all_graded),
"avg_clv_pp": avg_clv(all_graded),
"push_rate": push_rate(rows),
"by_classification": cls_counts,
"by_prop_type": pt_counts,
"filters": {
"prop_type": prop_type,
"classification": classification,
"since_date": since_date,
"model_version": model_version,
        },
    }


def export_csv(prop_type: Optional[str] = None, path: str = DB_PATH) -> str:

    conn = _conn(path)
    q = """SELECT lock_date, player_name, team, opponent, prop_type, line,
                  pick_direction, model_prob, market_prob, edge_pp, ev_pct,
                  odds_dec, classification, result_value, result_status,
                  expected_value_stat, data_quality_label, clv_pp, model_version
           FROM pitcher_prop_official_locks
           WHERE result_status IN ('won','lost','push','void')
             AND forecast_stage='lineup_lock'"""
    params = []
    if prop_type:
        q += " AND prop_type=?"
        params.append(prop_type)
    q += " ORDER BY lock_date DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()

    buf = io.StringIO()
    writer = csv.writer(buf)
    if rows:
        writer.writerow(
            [d[0] for d in rows[0].description]
            if hasattr(rows[0], "description")
            else [
"lock_date",
"player_name",
"team",
"opponent",
"prop_type",
"line",
"pick_direction",
"model_prob",
"market_prob",
"edge_pp",
"ev_pct",
"odds_dec",
"classification",
"result_value",
"result_status",
"expected_value_stat",
"data_quality_label",
"clv_pp",
"model_version",
            ]
        )
        for r in rows:
            writer.writerow(list(r))
    return buf.getvalue()
