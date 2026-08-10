import sqlite3, json, warnings, os
import pandas as pd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

DB_PATH = Path(__file__).parent.parent / "database" / "picks.db"
FIG_DIR = Path(__file__).parent / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def load_totals(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT game_id, date, matchup, pick_type, pick,
               odds, opening_odds, closing_odds, clv,
               model_prob, ev, kelly_units, status,
               model_version, model_build, forecast_stage,
               recommendation_tier, feature_snapshot,
               created_at, updated_at
        FROM picks
        WHERE pick_type = 'totals'
          AND status IN ('won', 'lost', 'pending')
        ORDER BY date ASC
    """).fetchall()
    conn.close()

    records = []
    for r in rows:
        d = dict(r)
        snap = {}
        try:
            snap = json.loads(d.pop("feature_snapshot") or "{}")
        except Exception:
            d.pop("feature_snapshot", None)

        for k, v in snap.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if not isinstance(vv, (dict, list)):
                        d[f"snap_{k}_{kk}"] = vv
            elif not isinstance(v, list):
                d[f"snap_{k}"] = v

        d["direction"] = "OVER" if "OVER" in str(d.get("pick", "")) else "UNDER"
        d["won"] = 1 if d["status"] == "won" else (0 if d["status"] == "lost" else np.nan)
        d["line"] = _parse_line(d.get("pick", ""))
        d["profit"] = _profit(d)
        d["wagered"] = 20.0

        records.append(d)

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.month
    df["weekday"] = df["date"].dt.day_name()
    df["away_team"], df["home_team"] = zip(*df["matchup"].apply(_split_matchup))

    for col in ["odds", "opening_odds", "closing_odds", "clv", "model_prob", "ev", "kelly_units"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _parse_line(pick_str):
    try:
        return float(str(pick_str).split()[-1])
    except Exception:
        return np.nan


def _split_matchup(m):
    parts = str(m).split(" @ ")
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("?", "?")


def _profit(d):
    if d["status"] == "won":
        return round((float(d.get("odds") or 1) - 1) * 20, 2)
    elif d["status"] == "lost":
        return -20.0
    return 0.0


def load_all_picks(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT game_id, date, pick_type, status, model_version, model_build, feature_snapshot
        FROM picks
    """).fetchall()
    conn.close()

    records = []
    for r in rows:
        d = dict(r)
        try:
            snap = json.loads(d.get("feature_snapshot") or "{}")
        except Exception:
            snap = {}
        d["snap"] = snap
        d["has_snapshot"] = bool(d.get("feature_snapshot"))
        d["schema_version"] = snap.get("schema_version")
        records.append(d)
    return records


def resolved(df):
    return df[df["status"].isin(["won", "lost"])].copy()


def snapped(df):
    snap_cols = [c for c in df.columns if c.startswith("snap_")]
    return df[df[snap_cols].notna().any(axis=1)].copy()


SNAP_NUMERIC = [
    "snap_market_line",
    "snap_expected_total",
    "snap_home_fip",
    "snap_away_fip",
    "snap_home_rsg",
    "snap_away_rsg",
    "snap_lineup_runs_adj",
    "snap_bullpen_workload_adj",
    "snap_defense_runs_adj",
    "snap_park_factor",
    "snap_home_bp_era",
    "snap_away_bp_era",
    "snap_weather_factor",
    "snap_temp_f",
    "snap_ump_runs_adj",
    "snap_contact_quality_runs_adj",
    "snap_context_home_lineup_ops",
    "snap_context_away_lineup_ops",
    "snap_context_home_bullpen_fatigue",
    "snap_context_away_bullpen_fatigue",
    "snap_context_home_fielding_pct",
    "snap_context_away_fielding_pct",
]


import time as _time
import traceback as _traceback


def emit_event(payload: dict):

    print(f"##DIAG_EVENT##{json.dumps(payload, default=str)}")


def run_section(section_id, title, fn, *args, **kwargs):

    emit_event({"type": "start", "section": section_id, "title": title})
    t0 = _time.time()
    try:
        result = fn(*args, **kwargs)
        metrics = result if isinstance(result, dict) else {}
        elapsed = round(_time.time() - t0, 2)
        emit_event(
            {
                "type": "result",
                "section": section_id,
                "title": title,
                "status": "ok",
                "elapsed": elapsed,
                "metrics": metrics,
            }
        )
        return metrics
    except Exception as e:
        elapsed = round(_time.time() - t0, 2)
        print(f"  {section_id} ({title}) FAILED: {e}")
        _traceback.print_exc()
        emit_event(
            {
                "type": "result",
                "section": section_id,
                "title": title,
                "status": "error",
                "elapsed": elapsed,
                "error": str(e),
            }
        )
        return {}


def skip_section(section_id, title, reason):

    print(f"  ⏭ {section_id} ({title}) SKIPPED: {reason}")
    emit_event(
        {
            "type": "result",
            "section": section_id,
            "title": title,
            "status": "skipped",
            "reason": reason,
        }
    )


if __name__ == "__main__":
    df = load_totals()
    print(f"Total rows:    {len(df)}")
    print(f"Resolved:      {len(resolved(df))}")
    print(f"With snapshot: {len(snapped(resolved(df)))}")
    print(f"Columns:       {len(df.columns)}")
    print(
        df[["date", "matchup", "direction", "line", "model_prob", "ev", "status", "won"]]
        .tail(10)
        .to_string()
    )
