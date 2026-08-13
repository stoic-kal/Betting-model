"""Build reusable Matchup Lab profiles from pitch-level Statcast.

This is intentionally offline: Flask never scans statcast_raw.csv. The output
is compact JSON under data/matchup_lab and can later be joined to today's slate.
No production betting-model files are modified.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "statcast_raw.csv"
OUT = ROOT / "data" / "matchup_lab"

USECOLS = [
    "game_date", "game_pk", "batter", "pitcher", "pitch_type", "pitch_name",
    "stand", "p_throws", "description", "events", "zone", "plate_x", "plate_z",
    "release_speed", "release_spin_rate", "pfx_x", "pfx_z", "launch_speed",
    "launch_angle", "estimated_woba_using_speedangle", "woba_value", "iso_value",
    "launch_speed_angle",
]


def safe_mean(s: pd.Series) -> float | None:
    v = pd.to_numeric(s, errors="coerce").dropna()
    return None if v.empty else round(float(v.mean()), 4)


def pct(n: float, d: float) -> float | None:
    return None if not d else round(100.0 * float(n) / float(d), 2)


def atomic_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, path)


def clean(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    desc = df["description"].fillna("").astype(str)
    events = df["events"].fillna("").astype(str)
    df["swing"] = desc.str.contains("swing|foul", case=False, regex=True)
    df["whiff"] = desc.str.contains("swinging_strike", case=False, regex=False)
    df["bip"] = df["launch_speed"].notna()
    df["hard"] = pd.to_numeric(df["launch_speed"], errors="coerce") >= 95.0
    # Savant launch_speed_angle == 6 is the barrel classification.
    df["barrel"] = pd.to_numeric(df["launch_speed_angle"], errors="coerce") == 6
    df["k"] = events.str.contains("strikeout", case=False, regex=False)
    df["bb"] = events.isin(["walk", "intent_walk"])
    return df


def batter_profiles(df: pd.DataFrame, cutoff: date) -> list[dict]:
    rows = []
    for (batter, pitch_type, throws), g in df.groupby(["batter", "pitch_type", "p_throws"], dropna=False):
        if pd.isna(batter) or pd.isna(pitch_type):
            continue
        bip = int(g["bip"].sum()); swings = int(g["swing"].sum())
        rows.append({
            "batter": int(batter), "pitch_type": str(pitch_type), "p_throws": clean(throws),
            "pitches": int(len(g)), "swings": swings, "whiff_pct": pct(g["whiff"].sum(), swings),
            "bip": bip, "xwoba": safe_mean(g["estimated_woba_using_speedangle"]),
            "woba": safe_mean(g["woba_value"]), "iso": safe_mean(g["iso_value"]),
            "hard_hit_pct": pct(g["hard"].sum(), bip), "barrel_pct": pct(g["barrel"].sum(), bip),
            "avg_exit_velocity": safe_mean(g["launch_speed"]), "avg_launch_angle": safe_mean(g["launch_angle"]),
        })
    return rows


def pitcher_profiles(df: pd.DataFrame) -> list[dict]:
    rows = []
    totals = df.groupby("pitcher").size().to_dict()
    for (pitcher, pitch_type, stand), g in df.groupby(["pitcher", "pitch_type", "stand"], dropna=False):
        if pd.isna(pitcher) or pd.isna(pitch_type):
            continue
        swings = int(g["swing"].sum()); bip = int(g["bip"].sum())
        rows.append({
            "pitcher": int(pitcher), "pitch_type": str(pitch_type), "stand": clean(stand),
            "pitches": int(len(g)), "usage_pct": pct(len(g), totals.get(pitcher, 0)),
            "velocity": safe_mean(g["release_speed"]), "spin": safe_mean(g["release_spin_rate"]),
            "pfx_x": safe_mean(g["pfx_x"]), "pfx_z": safe_mean(g["pfx_z"]),
            "whiff_pct": pct(g["whiff"].sum(), swings), "xwoba_allowed": safe_mean(g["estimated_woba_using_speedangle"]),
            "hard_hit_pct_allowed": pct(g["hard"].sum(), bip), "barrel_pct_allowed": pct(g["barrel"].sum(), bip),
        })
    return rows


def rolling_form(df: pd.DataFrame, cutoff: date) -> list[dict]:
    out = []
    for days in (7, 14, 30):
        start = pd.Timestamp(cutoff - timedelta(days=days))
        w = df[df["game_date"] >= start]
        for batter, g in w.groupby("batter"):
            if pd.isna(batter): continue
            bip = int(g["bip"].sum()); swings = int(g["swing"].sum())
            out.append({"batter": int(batter), "window_days": days, "pitches": int(len(g)),
                        "xwoba": safe_mean(g["estimated_woba_using_speedangle"]),
                        "whiff_pct": pct(g["whiff"].sum(), swings), "hard_hit_pct": pct(g["hard"].sum(), bip),
                        "barrel_pct": pct(g["barrel"].sum(), bip)})
    return out


def zone_profiles(df: pd.DataFrame) -> dict:
    z = df.dropna(subset=["zone"])
    hitters=[]; pitchers=[]
    for (batter, zone), g in z.groupby(["batter", "zone"]):
        if pd.isna(batter): continue
        hitters.append({"batter":int(batter),"zone":int(zone),"pitches":int(len(g)),"xwoba":safe_mean(g["estimated_woba_using_speedangle"])})
    for (pitcher, zone), g in z.groupby(["pitcher", "zone"]):
        if pd.isna(pitcher): continue
        pitchers.append({"pitcher":int(pitcher),"zone":int(zone),"pitches":int(len(g)),"xwoba_allowed":safe_mean(g["estimated_woba_using_speedangle"])})
    return {"hitters":hitters,"pitchers":pitchers}


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--cutoff", type=date.fromisoformat, default=date.today()); ap.add_argument("--lookback-days", type=int, default=730); args=ap.parse_args()
    cutoff=args.cutoff
    print(f"Building Matchup Lab profiles through {cutoff - timedelta(days=1)}")
    df=pd.read_csv(RAW,usecols=lambda c:c in USECOLS,low_memory=False)
    missing=[c for c in USECOLS if c not in df.columns]
    if missing: raise SystemExit(f"statcast_raw.csv missing required columns: {missing}")
    df["game_date"]=pd.to_datetime(df["game_date"],errors="coerce")
    start=pd.Timestamp(cutoff-timedelta(days=args.lookback_days)); end=pd.Timestamp(cutoff)
    df=df[(df.game_date>=start)&(df.game_date<end)].copy()
    df=add_flags(df)
    meta={"cutoff":cutoff.isoformat(),"lookback_days":args.lookback_days,"source_rows":int(len(df)),"latest_game_date":df.game_date.max().date().isoformat() if not df.empty else None}
    print(f"Using {len(df):,} pitches; latest {meta['latest_game_date']}")
    atomic_json(OUT/"batter_pitch_profiles.json",{"meta":meta,"rows":batter_profiles(df,cutoff)})
    atomic_json(OUT/"pitcher_pitch_profiles.json",{"meta":meta,"rows":pitcher_profiles(df)})
    atomic_json(OUT/"rolling_form.json",{"meta":meta,"rows":rolling_form(df,cutoff)})
    atomic_json(OUT/"zone_profiles.json",{"meta":meta,**zone_profiles(df)})
    atomic_json(OUT/"profile_status.json",{"status":"healthy",**meta})
    print(f"Saved Matchup Lab profiles to {OUT}")

if __name__=="__main__": main()
