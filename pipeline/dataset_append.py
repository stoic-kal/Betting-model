import json
import math
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.live_features_v2 import compute_v2_features
from pipeline.features_common import ML_FEATURES
from pipeline import feature_store, model_registry, statcast_store
from services import schedule_service, market_snapshot_service
from services.shadow_inference_service import VENUE_IDS

DATASET_PATH = "data/games_v2_features_final.csv"
DATASET_VERSION_PATH = "data/dataset_version.json"
VALIDATION_LOG_PATH = "data/dataset_append_validation_log.jsonl"
FEATURE_PIPELINE_VERSION = "live_features_v2:v1"
MODEL_GENERATION_VERSION = "v2"

METADATA_COLUMNS = [
    "date", "game_pk", "home_team", "away_team", "home_runs", "away_runs", "total_runs", "home_win",
    "home_sp_name", "away_sp_name",
]

VERSION_COLUMNS = [
    "feature_schema_version", "feature_pipeline_version", "dataset_version",
    "model_generation_version", "creation_timestamp", "degraded_features",
    "odds_home_ml", "odds_away_ml", "odds_total_line", "odds_over_odds", "odds_under_odds",
]


EXHIBITION_GAME_TYPES = statcast_store.EXCLUDED_GAME_TYPES


def _matchup_key(row):
    return f"{row['date']}|{row['home_team']}|{row['away_team']}"


def _game_index_lookups():
    index = statcast_store.load_game_index()
    by_game_pk = {int(r.game_pk): r for r in index.itertuples()}
    by_matchup = {
        f"{r.game_date}|{r.home_team}|{r.away_team}": int(r.game_pk)
        for r in index.itertuples()
    }
    return by_game_pk, by_matchup


def _starter_match_score(row, truth):
    if truth is None:
        return None
    return int(row.get("home_sp_name") == truth.home_sp_name) + int(row.get("away_sp_name") == truth.away_sp_name)


def resolve_dataset(df):
    by_game_pk, by_matchup = _game_index_lookups()
    frame = df.reset_index(drop=True).copy()
    original_game_pks = (frame["game_pk"].copy() if "game_pk" in frame.columns
                         else pd.Series([pd.NA] * len(frame), index=frame.index))

    resolved_pks = []
    for _, row in frame.iterrows():
        game_pk = row.get("game_pk")
        if pd.isna(game_pk):
            game_pk = by_matchup.get(_matchup_key(row))
        resolved_pks.append(int(game_pk) if game_pk is not None and not pd.isna(game_pk) else None)
    recovered_game_pks = sum(
        1 for original, resolved in zip(original_game_pks, resolved_pks)
        if pd.isna(original) and resolved is not None
    )
    frame["game_pk"] = [pk if pk is not None else pd.NA for pk in resolved_pks]

    keys = [
        str(pk) if pk is not None else _matchup_key(row)
        for pk, (_, row) in zip(resolved_pks, frame.iterrows())
    ]
    frame["_dedup_key"] = keys

    keep_positions = []
    duplicate_groups = 0
    duplicate_rows_removed = 0
    resolved_by_statcast = 0
    unresolved_groups = []
    for key, group in frame.groupby("_dedup_key", sort=False):
        if len(group) == 1:
            keep_positions.append(group.index[0])
            continue
        duplicate_groups += 1
        duplicate_rows_removed += len(group) - 1
        game_pk = group["game_pk"].iloc[0]
        truth = by_game_pk.get(int(game_pk)) if not pd.isna(game_pk) else None
        scores = [_starter_match_score(row, truth) for _, row in group.iterrows()]
        best = max((s for s in scores if s is not None), default=None)
        winners = [idx for idx, s in zip(group.index, scores) if s is not None and s == best]
        if best == 2 and len(winners) == 1:
            keep_positions.append(winners[0])
            resolved_by_statcast += 1
        else:
            keep_positions.append(group.index[0])
            unresolved_groups.append(key)

    frame = frame.loc[sorted(keep_positions)]

    game_types = [
        by_game_pk[int(pk)].game_type if not pd.isna(pk) and int(pk) in by_game_pk else None
        for pk in frame["game_pk"]
    ]
    exhibition_mask = pd.Series([gt in EXHIBITION_GAME_TYPES for gt in game_types], index=frame.index)
    exhibition_rows_removed = int(exhibition_mask.sum())
    unknown_game_type_rows = int(sum(1 for gt in game_types if gt is None))
    frame = frame[~exhibition_mask]

    frame = frame.drop(columns=["_dedup_key"])
    frame = frame.sort_values("date", kind="mergesort").reset_index(drop=True)

    report = {
        "rows_in": int(len(df)),
        "rows_out": int(len(frame)),
        "duplicate_groups": duplicate_groups,
        "duplicate_rows_removed": duplicate_rows_removed,
        "duplicates_resolved_by_statcast_starters": resolved_by_statcast,
        "duplicate_groups_unresolved": len(unresolved_groups),
        "unresolved_keys": unresolved_groups,
        "recovered_game_pks": recovered_game_pks,
        "exhibition_rows_removed": exhibition_rows_removed,
        "rows_with_unknown_game_type": unknown_game_type_rows,
    }
    return frame, report


def clean_dataset_file(path=DATASET_PATH):
    df = pd.read_csv(path, dtype={"date": str, "home_team": str, "away_team": str})
    cleaned, report = resolve_dataset(df)
    cleaned.to_csv(path, index=False)
    version_state = load_dataset_version()
    save_dataset_version({
        "version": version_state["version"] + 1,
        "row_count": len(cleaned),
        "last_updated": datetime.utcnow().isoformat(),
        "dataset_hash": model_registry.hash_dataset(path),
        "resolution_report": report,
    })
    return report


def load_dataset_version():
    if not Path(DATASET_VERSION_PATH).exists():
        return {"version": 0, "row_count": 0, "last_updated": None}
    with open(DATASET_VERSION_PATH) as f:
        return json.load(f)


def save_dataset_version(version_state):
    with open(DATASET_VERSION_PATH, "w") as f:
        json.dump(version_state, f, indent=2, default=str)


def _normalize_game_pk(value):
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_existing_identities(df):
    """Return canonical MLB ids plus matchup fallbacks for legacy rows.

    A date/team matchup is not a safe primary key because MLB doubleheaders have
    the same date, home team, and away team.  Use ``game_pk`` whenever it is
    available and reserve the matchup key only for historical rows whose id
    could not be recovered.
    """
    game_pks = set()
    legacy_matchups = set()
    for _, row in df.iterrows():
        game_pk = _normalize_game_pk(row.get("game_pk"))
        if game_pk is not None:
            game_pks.add(game_pk)
        else:
            legacy_matchups.add((str(row["date"]), str(row["home_team"]), str(row["away_team"])))
    return game_pks, legacy_matchups


def extract_closing_odds(away_full, home_full):
    movement = market_snapshot_service.movement_for_matchup(away_full, home_full)
    snapshots = movement.get("snapshots", [])
    latest = {}
    for row in snapshots:
        key = (row["market"], row["outcome"])
        latest[key] = row
    home_ml = None
    away_ml = None
    total_line = None
    over_odds = None
    under_odds = None
    for (market, outcome), row in latest.items():
        outcome_lower = outcome.lower()
        if market in ("h2h", "moneyline"):
            if outcome_lower == home_full.lower():
                home_ml = row["price"]
            elif outcome_lower == away_full.lower():
                away_ml = row["price"]
        elif market == "totals":
            if outcome_lower == "over":
                over_odds = row["price"]
                total_line = row["point"] if row["point"] is not None else total_line
            elif outcome_lower == "under":
                under_odds = row["price"]
                total_line = row["point"] if row["point"] is not None else total_line
    return {
        "odds_home_ml": home_ml, "odds_away_ml": away_ml,
        "odds_total_line": total_line, "odds_over_odds": over_odds, "odds_under_odds": under_odds,
    }


def validate_row_strict(features):
    invalid = []
    for key in ML_FEATURES:
        value = features.get(key)
        if value is None:
            invalid.append(key)
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            invalid.append(key)
            continue
        if math.isnan(v) or math.isinf(v):
            invalid.append(key)
    return invalid


def compute_row_for_game(game, date_str):
    home_abbr = game.get("home_abbr")
    away_abbr = game.get("away_abbr")
    home_team_id = game.get("home_team_id")
    away_team_id = game.get("away_team_id")
    home_sp_id = game.get("home_sp_id")
    away_sp_id = game.get("away_sp_id")
    game_pk = game.get("game_pk")
    venue_id = VENUE_IDS.get(home_abbr)
    home_runs = game.get("home_score")
    away_runs = game.get("away_score")

    if not home_sp_id or not away_sp_id:
        return None, "missing_starting_pitcher_id"
    if not home_team_id or not away_team_id or not venue_id:
        return None, "missing_team_or_venue_id"
    if home_runs is None or away_runs is None:
        return None, "missing_final_score"
    try:
        home_runs = int(home_runs)
        away_runs = int(away_runs)
    except (TypeError, ValueError):
        return None, "non_numeric_score"
    if home_runs < 0 or away_runs < 0:
        return None, "impossible_negative_score"

    try:
        game_dt = datetime.strptime(game["game_date_utc"], "%Y-%m-%dT%H:%M:%SZ")
    except (KeyError, ValueError):
        return None, "missing_or_invalid_game_datetime"

    result = compute_v2_features(
        home_team=home_abbr, away_team=away_abbr,
        home_team_id=home_team_id, away_team_id=away_team_id,
        home_sp_id=home_sp_id, away_sp_id=away_sp_id,
        venue_id=venue_id, game_datetime=game_dt, game_pk=game_pk,
    )

    invalid = validate_row_strict(result["features"])
    if invalid:
        return None, f"unresolved_invalid_features:{invalid}"

    row = dict(result["features"])
    row.update({
        "date": date_str,
        "game_pk": game_pk,
        "home_team": home_abbr,
        "away_team": away_abbr,
        "home_runs": home_runs,
        "away_runs": away_runs,
        "total_runs": home_runs + away_runs,
        "home_win": int(home_runs > away_runs),
        "home_sp_name": game.get("home_sp_name"),
        "away_sp_name": game.get("away_sp_name"),
        "feature_schema_version": result["schema_version"],
        "feature_pipeline_version": FEATURE_PIPELINE_VERSION,
        "model_generation_version": MODEL_GENERATION_VERSION,
        "creation_timestamp": datetime.utcnow().isoformat(),
        "degraded_features": json.dumps(result["degraded"]),
        "context_features": json.dumps(result.get("context_features", {})),
        "context_provenance": json.dumps(result.get("context_provenance", {})),
        "field_provenance": json.dumps(result.get("field_provenance", {})),
    })
    row.update(extract_closing_odds(game.get("away", ""), game.get("home", "")))
    return row, None


def log_rejections(rejections):
    if not rejections:
        return
    Path(VALIDATION_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(VALIDATION_LOG_PATH, "a") as f:
        for record in rejections:
            f.write(json.dumps(record, default=str) + "\n")


def append_new_games(end_date=None):
    df_existing = pd.read_csv(DATASET_PATH, dtype={"date": str, "home_team": str, "away_team": str})
    existing_game_pks, legacy_matchups = load_existing_identities(df_existing)
    start_date = datetime.strptime(df_existing["date"].max(), "%Y-%m-%d").date()
    end_date = end_date or (date.today() - timedelta(days=1))

    new_rows = []
    rejections = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        try:
            games = schedule_service.get_today_games(date_str, include_odds=False)
        except Exception as exc:
            rejections.append({"date": date_str, "reason": f"schedule_fetch_failed:{exc}"})
            current += timedelta(days=1)
            continue
        for game in games:
            if game.get("game_state") != "Final":
                continue
            home_abbr = game.get("home_abbr")
            away_abbr = game.get("away_abbr")
            game_pk = _normalize_game_pk(game.get("game_pk"))
            matchup_key = (date_str, home_abbr, away_abbr)
            if ((game_pk is not None and game_pk in existing_game_pks) or
                    (game_pk is None and matchup_key in legacy_matchups)):
                continue
            row, reason = compute_row_for_game(game, date_str)
            if row is None:
                rejections.append({"date": date_str, "home": home_abbr, "away": away_abbr, "reason": reason})
                continue
            new_rows.append(row)
            if game_pk is not None:
                existing_game_pks.add(game_pk)
            else:
                legacy_matchups.add(matchup_key)
        current += timedelta(days=1)

    log_rejections(rejections)

    if not new_rows:
        return {"appended": 0, "rejected": len(rejections), "dataset_version": load_dataset_version()["version"]}

    version_state = load_dataset_version()
    new_version = version_state["version"] + 1
    for row in new_rows:
        row["dataset_version"] = new_version

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([df_existing, new_df], ignore_index=True, sort=False)
    combined, resolution_report = resolve_dataset(combined)
    combined.to_csv(DATASET_PATH, index=False)

    save_dataset_version({
        "resolution_report": resolution_report,
        "version": new_version,
        "row_count": len(combined),
        "last_updated": datetime.utcnow().isoformat(),
        "rows_appended_this_run": len(new_rows),
        "dataset_hash": model_registry.hash_dataset(DATASET_PATH),
    })

    return {"appended": len(new_rows), "rejected": len(rejections), "dataset_version": new_version}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        report = clean_dataset_file()
        print(json.dumps(report, indent=2, default=str))
        return
    result = append_new_games()
    print(f"appended={result['appended']} rejected={result['rejected']} dataset_version={result['dataset_version']}")


if __name__ == "__main__":
    main()
