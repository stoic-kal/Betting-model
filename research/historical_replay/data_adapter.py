import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .isolation import require_approved_dataset
from .feature_transforms import apply_transforms


LABELS = {"home_win", "over", "push", "home_runs", "away_runs", "home_runs_allowed",
          "away_runs_allowed", "total_runs"}
IDENTITY = {"canonical_game_id", "game_date", "home_team", "away_team", "venue_name",
            "doubleheader_number", "feature_as_of", "point_in_time_policy"}
POSTGAME_PATTERNS = ("actual_", "final_", "result", "won", "profit", "closing_result")


@dataclass
class ReplayDataset:
    frame: pd.DataFrame
    features: list
    sha256: str
    schema_version: str
    path: str
    feature_provenance: dict
    exclusions: dict


def _provenance_for_feature(name):
    market_tokens=("moneyline","market_","price_decimal","closing_total","total_market_vig")
    shifted_tokens=("_5g","_10g","_30g","win_rate","rest_days","form_edge","bp_er_14g","accel_")
    if any(token in name for token in market_tokens):
        return "closing_market_snapshot"
    if any(token in name for token in shifted_tokens):
        return "shifted_completed_game_history"
    if name.startswith("research_"):
        return "research_transform_of_point_in_time_inputs"
    return None


def _exclude_ambiguous_same_day_games(frame):
    appearances=pd.concat([
        frame[["canonical_game_id","game_date","home_team"]].rename(columns={"home_team":"team"}),
        frame[["canonical_game_id","game_date","away_team"]].rename(columns={"away_team":"team"}),
    ],ignore_index=True)
    counts=appearances.groupby(["team","game_date"]).canonical_game_id.transform("nunique")
    ambiguous=set(appearances.loc[counts>1,"canonical_game_id"])
    clean=frame[~frame.canonical_game_id.isin(ambiguous)].copy()
    check=pd.concat([
        clean[["canonical_game_id","game_date","home_team"]].rename(columns={"home_team":"team"}),
        clean[["canonical_game_id","game_date","away_team"]].rename(columns={"away_team":"team"}),
    ])
    if check.duplicated(["team","game_date"]).any():
        raise AssertionError("Ambiguous same-day team games remain after exclusion")
    return clean,{"ambiguous_same_day_games":len(ambiguous),"policy":"excluded because completion order is unavailable"}


def _hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_dataset(path, target, include_features=None, exclude_features=None, feature_transforms=None):
    source = require_approved_dataset(path)
    frame = pd.read_csv(source, low_memory=False)
    required = {"canonical_game_id", "game_date", "feature_as_of", target}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")
    frame["game_date"] = pd.to_datetime(frame.game_date, errors="raise")
    frame["feature_as_of"] = pd.to_datetime(frame.feature_as_of, errors="raise")
    if (frame.feature_as_of > frame.game_date).any():
        bad = frame.loc[frame.feature_as_of > frame.game_date, "canonical_game_id"].head().tolist()
        raise ValueError(f"Future feature timestamps detected: {bad}")
    policies=set(frame.point_in_time_policy.dropna().astype(str)) if "point_in_time_policy" in frame else set()
    if not policies or not all("shift" in policy.lower() for policy in policies):
        raise ValueError("Dataset lacks an explicit shifted point-in-time policy")
    forbidden_families=[c for c in frame.columns if any(token in c.lower() for token in ("lineup","weather","temperature","wind"))]
    if forbidden_families:
        raise ValueError(f"Untimestamped historical lineup/weather fields rejected: {forbidden_families}")
    frame,transformed=apply_transforms(frame,feature_transforms)
    frame,exclusions=_exclude_ambiguous_same_day_games(frame)
    if target == "over":
        frame = frame[~frame.push.fillna(False)].copy()
    frame = frame[frame[target].notna()].copy()
    numeric = list(frame.select_dtypes(include=[np.number, "bool"]).columns)
    features = [c for c in numeric if c not in LABELS | IDENTITY]
    features.extend(c for c in transformed if c not in features)
    # Closing total is known at the closing-price replay instant and is a valid totals input.
    if target == "over" and "closing_total" in frame.columns and "closing_total" not in features:
        features.append("closing_total")
    if target == "home_win" and "closing_total" in features:
        features.remove("closing_total")
    include_features = include_features or []
    if include_features:
        absent = set(include_features) - set(frame.columns)
        if absent:
            raise ValueError(f"Requested features absent: {sorted(absent)}")
        features = list(include_features)
    excluded = set(exclude_features or [])
    features = [c for c in features if c not in excluded]
    unsafe = [c for c in features if c in LABELS or any(c.lower().startswith(p) for p in POSTGAME_PATTERNS)]
    if unsafe:
        raise ValueError(f"Postgame/leaking features rejected: {unsafe}")
    if not features:
        raise ValueError("No usable point-in-time features")
    provenance={name:_provenance_for_feature(name) for name in features}
    missing_provenance=[name for name,value in provenance.items() if value is None]
    if missing_provenance:
        raise ValueError(f"Feature provenance missing: {missing_provenance}")
    frame = frame.sort_values(["game_date", "canonical_game_id"]).reset_index(drop=True)
    schema = hashlib.sha256("\n".join(features).encode()).hexdigest()[:16]
    return ReplayDataset(frame,features,_hash(source),schema,str(source),provenance,exclusions)


def training_rows(dataset, replay_date, window_days=None):
    date = pd.Timestamp(replay_date)
    train = dataset.frame[dataset.frame.game_date < date]
    if window_days:
        train = train[train.game_date >= date - pd.Timedelta(days=window_days)]
    if not (train.game_date < date).all():
        raise AssertionError("Look-ahead detected in training selection")
    return train
