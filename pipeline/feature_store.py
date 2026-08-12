import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from generate_game_card import TEAM_ABBR
from services.market_snapshot_service import DB_PATH as MARKET_DB_PATH

ABBR_TO_FULL = {abbr: full for full, abbr in TEAM_ABBR.items()}

from pipeline.field_provenance import ProvenanceRecorder
from pipeline.features_common import (
    BULLPEN_FATIGUE_FEATURES,
    BULLPEN_QUALITY_FEATURES,
    CONTEXT_FEATURES,
    FEATURE_BOUNDS,
    FEATURE_FALLBACKS,
    FEATURE_SCHEMA_VERSION,
    LEAGUE_AVG_BAT_ISO,
    LEAGUE_AVG_BAT_WOBA,
    LEAGUE_AVG_BB_RATE,
    LEAGUE_AVG_FIP,
    LEAGUE_AVG_HR_RATE,
    LEAGUE_AVG_K_RATE,
    LINEUP_HANDEDNESS_INTERACTION_FEATURES,
    LINEUP_STRENGTH_FEATURES,
    PHASE3_INTERACTION_FEATURES,
    PLATOON_MATCHUP_FEATURES,
    ML_FEATURES,
    ML_FEATURES_EXPANDED,
    TOTALS_FEATURES,
    TOTALS_FEATURES_EXPANDED,
    feature_suffix,
    validate_features,
)

FEATURE_DESCRIPTIONS = {
    "k_rate": "starting pitcher strikeout rate over trailing appearances",
    "bb_rate": "starting pitcher walk rate over trailing appearances",
    "hr_rate": "starting pitcher home run rate over trailing appearances",
    "hard_hit_pct": "starting pitcher hard-hit rate allowed (exit velo >= 95mph)",
    "fb_velo": "starting pitcher average fastball velocity",
    "xwoba_against": "starting pitcher expected wOBA allowed",
    "fip": "starting pitcher fielding independent pitching",
    "is_lefty": "starting pitcher throws left-handed",
    "days_rest": "starting pitcher days of rest since last appearance",
    "bat_k_rate": "team strikeout rate over trailing games",
    "bat_hard_hit_pct": "team hard-hit rate over trailing games",
    "bat_iso": "team isolated power over trailing games",
    "bat_woba": "team wOBA over trailing games",
    "L10_wr": "team win rate over last 10 games",
    "L10_rs": "team runs scored per game over last 10 games",
    "L10_ra": "team runs allowed per game over last 10 games",
    "park_factor": "point-in-time trailing park run environment factor",
    "is_dome": "game played in a dome or retractable roof venue",
    "is_coors": "game played at Coors Field",
    "temp_f": "forecasted game-time temperature in Fahrenheit",
    "wind_mph": "forecasted wind speed in mph",
    "wind_out_factor": "wind alignment with outfield carry direction (-1 to 1)",
    "lineup_woba": "confirmed/projected lineup weighted wOBA",
    "lineup_iso": "confirmed/projected lineup weighted isolated power",
    "lineup_ops": "confirmed/projected lineup weighted OPS",
    "lineup_xrc_proxy": "lineup expected-runs-created proxy from weighted wOBA/OPS",
    "lineup_lr_balance": "lineup left/right batter balance ratio",
    "lineup_quality": "lineup completeness-weighted average projected batter quality (0-1)",
    "lineup_woba_vs_pitcher_hand": "lineup weighted wOBA vs opposing starter's throwing hand",
    "lineup_iso_vs_pitcher_hand": "lineup weighted ISO vs opposing starter's throwing hand",
    "lineup_k_rate_vs_pitcher_hand": "lineup weighted strikeout rate vs opposing starter's throwing hand",
    "lineup_bb_rate_vs_pitcher_hand": "lineup weighted walk rate vs opposing starter's throwing hand",
    "lineup_hard_hit_vs_pitcher_hand": "lineup weighted hard-hit rate vs opposing starter's throwing hand",
    "lineup_strength_vs_pitcher_hand": "lineup strength x opposing pitcher handedness interaction score",
    "platoon_advantage_score": "net platoon advantage score for lineup vs opposing starter",
    "bullpen_appearances_3d": "bullpen appearances in trailing 3 days",
    "bullpen_appearances_5d": "bullpen appearances in trailing 5 days",
    "bullpen_appearances_7d": "bullpen appearances in trailing 7 days",
    "bullpen_pitches_3d": "bullpen pitches thrown in trailing 3 days",
    "bullpen_pitches_5d": "bullpen pitches thrown in trailing 5 days",
    "bullpen_pitches_7d": "bullpen pitches thrown in trailing 7 days",
    "bullpen_bf_3d": "bullpen batters faced in trailing 3 days",
    "bullpen_bf_5d": "bullpen batters faced in trailing 5 days",
    "bullpen_bf_7d": "bullpen batters faced in trailing 7 days",
    "bullpen_high_lev_ip_3d": "bullpen high-leverage innings in trailing 3 days",
    "bullpen_high_lev_ip_5d": "bullpen high-leverage innings in trailing 5 days",
    "bullpen_high_lev_ip_7d": "bullpen high-leverage innings in trailing 7 days",
    "bullpen_fatigue_score": "aggregate bullpen fatigue score across trailing windows (0-1)",
    "bullpen_availability_score": "aggregate bullpen availability score across trailing windows (0-1)",
    "bullpen_era_7d": "bullpen ERA, trailing 7 days",
    "bullpen_era_14d": "bullpen ERA, trailing 14 days",
    "bullpen_era_30d": "bullpen ERA, trailing 30 days",
    "bullpen_era_season": "bullpen ERA, season to date",
    "bullpen_fip_7d": "bullpen FIP, trailing 7 days",
    "bullpen_fip_14d": "bullpen FIP, trailing 14 days",
    "bullpen_fip_30d": "bullpen FIP, trailing 30 days",
    "bullpen_fip_season": "bullpen FIP, season to date",
    "bullpen_whip_7d": "bullpen WHIP, trailing 7 days",
    "bullpen_whip_14d": "bullpen WHIP, trailing 14 days",
    "bullpen_whip_30d": "bullpen WHIP, trailing 30 days",
    "bullpen_whip_season": "bullpen WHIP, season to date",
    "bullpen_k_rate_7d": "bullpen strikeout rate, trailing 7 days",
    "bullpen_k_rate_14d": "bullpen strikeout rate, trailing 14 days",
    "bullpen_k_rate_30d": "bullpen strikeout rate, trailing 30 days",
    "bullpen_k_rate_season": "bullpen strikeout rate, season to date",
    "bullpen_bb_rate_7d": "bullpen walk rate, trailing 7 days",
    "bullpen_bb_rate_14d": "bullpen walk rate, trailing 14 days",
    "bullpen_bb_rate_30d": "bullpen walk rate, trailing 30 days",
    "bullpen_bb_rate_season": "bullpen walk rate, season to date",
    "bullpen_hr_rate_7d": "bullpen home run rate, trailing 7 days",
    "bullpen_hr_rate_14d": "bullpen home run rate, trailing 14 days",
    "bullpen_hr_rate_30d": "bullpen home run rate, trailing 30 days",
    "bullpen_hr_rate_season": "bullpen home run rate, season to date",
    "bullpen_xfip_7d": "bullpen xFIP using the statcast-derived league HR/FB rate, trailing 7 days",
    "bullpen_xfip_14d": "bullpen xFIP using the statcast-derived league HR/FB rate, trailing 14 days",
    "bullpen_xfip_30d": "bullpen xFIP using the statcast-derived league HR/FB rate, trailing 30 days",
    "bullpen_xfip_season": "bullpen xFIP using the statcast-derived league HR/FB rate, season to date",
    "fb_rate_x_wind_out": "starter flyball-rate proxy x wind-out factor interaction",
    "bullpen_fatigue_x_sp_innings_remaining_x_rest": "bullpen fatigue x starter projected innings remaining x days rest interaction",
    "wind_park_directional_factor": "per-park LF/CF/RF orientation and HR-distance profile x wind vector (directional, replaces scalar wind_out_factor)",
    "pitch_mix_x_lineup_matchup": "starter pitch-type usage/velocity x lineup performance vs those pitch types",
}

TARGETS = {
    "moneyline": {
        "features": ML_FEATURES,
        "label_column": "home_win",
        "model_type": "classification",
    },
    "totals": {
        "features": TOTALS_FEATURES,
        "label_column": "total_runs",
        "model_type": "classification_with_derived_threshold",
    },
    "moneyline_v23": {
        "features": ML_FEATURES_EXPANDED,
        "label_column": "home_win",
        "model_type": "classification",
    },
    "totals_v23": {
        "features": TOTALS_FEATURES_EXPANDED,
        "label_column": "total_runs",
        "model_type": "classification_with_derived_threshold",
    },
}


RFE_VALIDATED_EXCLUSIONS = {
    "moneyline": [],
    "totals": [],
    "moneyline_v23": [],
    "totals_v23": [],
}


def get_feature_list(target):
    return list(TARGETS[target]["features"])


def get_training_feature_list(target):
    excluded = RFE_VALIDATED_EXCLUSIONS.get(target, [])
    return [f for f in get_feature_list(target) if f not in excluded]


def get_schema_version():
    return FEATURE_SCHEMA_VERSION


def get_validation_rules():
    return dict(FEATURE_BOUNDS)


def get_fallback_rules():
    return dict(FEATURE_FALLBACKS)


def describe_feature(feature_name):
    return FEATURE_DESCRIPTIONS.get(feature_suffix(feature_name), "no description available")


def feature_manifest(target):
    features = get_feature_list(target)
    return [
        {
            "name": name,
            "description": describe_feature(name),
            "bounds": FEATURE_BOUNDS.get(feature_suffix(name)),
            "fallback": FEATURE_FALLBACKS.get(feature_suffix(name)),
        }
        for name in features
    ]


def load_dataset(path):
    df = pd.read_csv(path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    return df


TOTALS_TARGET_SKIP_LOG = "data/totals_target_skip_log.jsonl"


def _load_totals_line_lookup():
    conn = sqlite3.connect(MARKET_DB_PATH)
    rows = conn.execute(
        "SELECT home_team, away_team, commence_time, captured_at, point "
        "FROM market_snapshots WHERE market='totals' AND point IS NOT NULL"
    ).fetchall()
    conn.close()
    lookup = {}
    for home_team, away_team, commence_time, captured_at, point in rows:
        if not commence_time:
            continue
        key = (commence_time[:10], home_team.lower(), away_team.lower())
        existing = lookup.get(key)
        if existing is None or captured_at > existing[0]:
            lookup[key] = (captured_at, float(point))
    return lookup


def get_closing_total_line(date_str, home_abbr, away_abbr, lookup):
    home_full = ABBR_TO_FULL.get(home_abbr)
    away_full = ABBR_TO_FULL.get(away_abbr)
    if not home_full or not away_full:
        return None
    entry = lookup.get((date_str, home_full.lower(), away_full.lower()))
    return entry[1] if entry else None


def build_totals_targets(df):
    lookup = _load_totals_line_lookup()
    labels = []
    skipped = []
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
        line = get_closing_total_line(date_str, row["home_team"], row["away_team"], lookup)
        if line is None:
            labels.append(np.nan)
            skipped.append({
                "date": date_str, "home_team": row["home_team"], "away_team": row["away_team"],
                "reason": "no_closing_total_line_available",
            })
            continue
        if float(row["total_runs"]) == line:
            labels.append(np.nan)
            skipped.append({
                "date": date_str, "home_team": row["home_team"], "away_team": row["away_team"],
                "reason": "push", "line": line,
            })
            continue
        labels.append(1.0 if float(row["total_runs"]) > line else 0.0)
    if skipped:
        Path(TOTALS_TARGET_SKIP_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(TOTALS_TARGET_SKIP_LOG, "w") as f:
            for record in skipped:
                f.write(json.dumps(record, default=str) + "\n")
    return pd.Series(labels, index=df.index), len(skipped)


CONTEXT_FEATURES_SKIP_LOG = "data/context_features_skip_log.jsonl"

_PLATOON_UNAVAILABLE_REASON = (
    "per-batter point-in-time platoon splits unavailable for this game: no lineup could be resolved, "
    "the opposing starter's throwing hand is unknown, or no batter cleared the minimum prior-plate-appearance "
    "sample threshold in the local statcast history"
)

_CONTEXT_SKIP_REASONS = {
    "lineup_woba_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "lineup_iso_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "lineup_k_rate_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "lineup_bb_rate_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "lineup_hard_hit_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "lineup_strength_vs_pitcher_hand": _PLATOON_UNAVAILABLE_REASON,
    "platoon_advantage_score": _PLATOON_UNAVAILABLE_REASON,
    "pitch_mix_x_lineup_matchup": (
        "starter pitch-group usage or lineup wOBA-by-pitch-group unavailable for this game at the required "
        "minimum prior-plate-appearance sample threshold"
    ),
}


def get_statcast_context():
    from pipeline.statcast_store import get_context

    return get_context()


def _log_context_skip(game_key, feature_name, reason, recorder=None, source=None):
    Path(CONTEXT_FEATURES_SKIP_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(CONTEXT_FEATURES_SKIP_LOG, "a") as f:
        f.write(json.dumps({"game": game_key, "feature": feature_name, "reason": reason}, default=str) + "\n")
    if recorder is not None:
        recorder.fallback_applied(
            [feature_name],
            source or "pipeline/feature_store.py:build_context_features",
            reason,
            evidence=f"written to {CONTEXT_FEATURES_SKIP_LOG} for game {game_key}",
        )


def _lineup_strength_from_team_rates(team_bat_stats, lineup_result):
    woba = team_bat_stats.get("bat_woba")
    iso = team_bat_stats.get("bat_iso")
    woba = woba if woba is not None else LEAGUE_AVG_BAT_WOBA
    iso = iso if iso is not None else LEAGUE_AVG_BAT_ISO
    ops_proxy = min(2.0, max(0.0, woba * 2.2 + iso * 0.9))
    xrc_proxy = min(15.0, max(0.0, woba * 20 + iso * 8))
    completeness = 1.0 - (lineup_result.get("missing_player_count", 9) / 9.0)
    quality = max(0.0, min(1.0, 0.5 + (woba - LEAGUE_AVG_BAT_WOBA) * 4)) * max(0.4, completeness)
    return {
        "lineup_woba": round(woba, 4),
        "lineup_iso": round(iso, 4),
        "lineup_ops": round(ops_proxy, 4),
        "lineup_xrc_proxy": round(xrc_proxy, 4),
        "lineup_lr_balance": 0.5,
        "lineup_quality": round(quality, 4),
    }


def _bullpen_window_stats(team_abbr, as_of_dt, windows=(3, 5, 7, 14, 30)):
    from services.advanced_context_service import _bullpen_fetch_once
    from services.game_context_service import TEAM_IDS

    team_id = TEAM_IDS.get(team_abbr)
    result = {}
    if not team_id:
        return result
    for w in windows:
        try:
            snap = _bullpen_fetch_once(team_abbr, team_id, min(w, 30), reference_date=as_of_dt)
        except Exception:
            snap = None
        result[w] = snap
    return result


BULLPEN_FATIGUE_PITCH_LOAD_NORMALIZER = 250.0
BULLPEN_ROSTER_SIZE = 8.0


def _fatigue_scores(prefix, fatigue):
    appearances_3d = fatigue.get(f"{prefix}_bullpen_appearances_3d", 0.0)
    pitches_7d = fatigue.get(f"{prefix}_bullpen_pitches_7d", 0.0)
    fatigue[f"{prefix}_bullpen_fatigue_score"] = round(
        min(1.0, pitches_7d / BULLPEN_FATIGUE_PITCH_LOAD_NORMALIZER), 4
    )
    fatigue[f"{prefix}_bullpen_availability_score"] = round(
        max(0.0, 1.0 - min(1.0, appearances_3d / BULLPEN_ROSTER_SIZE)), 4
    )
    return fatigue


def _fatigue_from_live_snapshots(team_abbr, prefix, as_of):
    snaps = _bullpen_window_stats(team_abbr, as_of, windows=(3, 5, 7))
    if not any(snaps.get(w) for w in (3, 5, 7)):
        return None
    fatigue = {}
    for w in (3, 5, 7):
        snap = snaps.get(w) or {}
        fatigue[f"{prefix}_bullpen_appearances_{w}d"] = float(len(snap.get("relievers", [])))
        fatigue[f"{prefix}_bullpen_pitches_{w}d"] = float(snap.get("total_pitches", 0) or 0)
        fatigue[f"{prefix}_bullpen_bf_{w}d"] = float(snap.get("total_pitches", 0) or 0) / 4.0
        fatigue[f"{prefix}_bullpen_high_lev_ip_{w}d"] = 0.0
    return _fatigue_scores(prefix, fatigue)


def build_bullpen_fatigue_quality(team_abbr, prefix, as_of=None, offline_only=False):
    fatigue = None
    quality = {}
    provenance = {
        "fatigue_source": None,
        "quality_source": None,
        "fallback_used": False,
        "quality_fallback_used": False,
        "as_of": as_of.isoformat() if as_of is not None else None,
    }

    if as_of is not None:
        try:
            statcast = get_statcast_context()
            offline = statcast.bullpen_fatigue(team_abbr, as_of)
            if offline is not None:
                fatigue = _fatigue_scores(prefix, {f"{prefix}_{k}": v for k, v in offline.items()})
                provenance["fatigue_source"] = "local statcast reliever game logs (point-in-time rolling windows)"
            offline_quality = statcast.bullpen_quality(team_abbr, as_of)
            for suffix, value in offline_quality.items():
                quality[f"{prefix}_{suffix}"] = value
            if offline_quality:
                provenance["quality_source"] = "local statcast reliever game logs (point-in-time rolling windows)"
                provenance["league_hr_fb_rate"] = statcast.league_hr_fb_rate()
        except Exception as exc:
            provenance["statcast_error"] = str(exc)

    if fatigue is None and not offline_only:
        try:
            fatigue = _fatigue_from_live_snapshots(team_abbr, prefix, as_of)
            if fatigue is not None:
                provenance["fatigue_source"] = "MLB boxscores (rolling windows)"
        except Exception as exc:
            provenance["fatigue_error"] = str(exc)

    if fatigue is None:
        provenance["fallback_used"] = True
        provenance["fatigue_source"] = "league-average fallback"
        fatigue = {}
        for w in (3, 5, 7):
            for stat in ("appearances", "pitches", "bf", "high_lev_ip"):
                fatigue[f"{prefix}_bullpen_{stat}_{w}d"] = FEATURE_FALLBACKS[f"bullpen_{stat}_{w}d"]
        fatigue[f"{prefix}_bullpen_fatigue_score"] = FEATURE_FALLBACKS["bullpen_fatigue_score"]
        fatigue[f"{prefix}_bullpen_availability_score"] = FEATURE_FALLBACKS["bullpen_availability_score"]

    missing_quality = 0
    for w in ("7d", "14d", "30d", "season"):
        for stat in ("era", "fip", "xfip", "whip", "k_rate", "bb_rate", "hr_rate"):
            key = f"{prefix}_bullpen_{stat}_{w}"
            if key not in quality:
                quality[key] = FEATURE_FALLBACKS[f"bullpen_{stat}_{w}"]
                missing_quality += 1
    if missing_quality:
        provenance["quality_fallback_used"] = True
        provenance["quality_fallback_count"] = missing_quality
        if provenance["quality_source"] is None:
            provenance["quality_source"] = "league-average fallback"
    provenance["era_definition"] = "runs allowed per 9 innings from statcast score deltas; statcast does not distinguish earned from unearned runs"
    return {**fatigue, **quality}, provenance


LINEUP_SIZE = 9

_UNKNOWN_LINEUP = {"status": "UNKNOWN", "lineup": [], "missing_player_count": LINEUP_SIZE}


def _resolve_lineup_ids(statcast, game_pk, team_abbr, lineup_result):
    ids = [p["player_id"] for p in lineup_result.get("lineup", [])]
    if ids:
        return ids, lineup_result.get("status")
    if statcast is None:
        return [], "UNKNOWN"
    offline = statcast.lineup_for_game(game_pk, team_abbr)
    return offline, "STATCAST_ACTUAL" if offline else "UNKNOWN"


def build_platoon_features(statcast, game_pk, prefix, lineup_ids, opposing_hand, as_of):
    if statcast is None or as_of is None or not lineup_ids or opposing_hand not in ("L", "R"):
        return None
    return statcast.lineup_platoon_splits(lineup_ids, opposing_hand, as_of)


def build_context_features(game_pk, home_abbr, away_abbr, home_bat_stats=None, away_bat_stats=None, as_of=None,
                           home_sp_id=None, away_sp_id=None, home_sp_hand=None, away_sp_hand=None,
                           home_days_rest=None, away_days_rest=None, wind_out=None, offline_only=False):
    home_bat_stats = home_bat_stats or {}
    away_bat_stats = away_bat_stats or {}
    provenance = {}
    features = {}
    degraded = 0
    recorder = ProvenanceRecorder(FEATURE_SCHEMA_VERSION)

    provenance["as_of"] = as_of.isoformat() if as_of is not None else None
    if as_of is None:
        _log_context_skip(
            f"{game_pk}",
            "as_of",
            "no reference_date supplied — trailing context windows anchored on the current date; correct for live inference, point-in-time incorrect if this game is historical",
        )

    if offline_only:
        home_lineup = _UNKNOWN_LINEUP
        away_lineup = _UNKNOWN_LINEUP
    else:
        from services.lineup_service import get_lineup

        home_lineup = get_lineup(game_pk, "home", home_abbr, reference_date=as_of)
        away_lineup = get_lineup(game_pk, "away", away_abbr, reference_date=as_of)
    try:
        statcast = get_statcast_context()
    except Exception as exc:
        statcast = None
        provenance["statcast_store_error"] = str(exc)

    lineup_ids = {}
    lineups = {}
    for prefix, abbr, lineup in (("home", home_abbr, home_lineup), ("away", away_abbr, away_lineup)):
        ids, source = _resolve_lineup_ids(statcast, game_pk, abbr, lineup)
        lineup_ids[prefix] = ids
        lineups[prefix] = lineup if lineup["lineup"] else {
            "status": source,
            "lineup": [{"player_id": pid} for pid in ids],
            "missing_player_count": max(0, LINEUP_SIZE - len(ids)),
        }
        provenance[f"{prefix}_lineup_status"] = lineups[prefix]["status"]
        provenance[f"{prefix}_lineup_source"] = source
        if source == "UNKNOWN":
            degraded += len(LINEUP_STRENGTH_FEATURES) // 2

    for prefix, bat_stats in (("home", home_bat_stats), ("away", away_bat_stats)):
        strength = _lineup_strength_from_team_rates(bat_stats, lineups[prefix])
        for name, value in strength.items():
            features[f"{prefix}_{name}"] = value
            recorder.fetch_attempted(
                [f"{prefix}_{name}"],
                "team trailing batting rates via _lineup_strength_from_team_rates",
                evidence=f"lineup status {lineups[prefix]['status']}, "
                         f"{lineups[prefix].get('missing_player_count')} unresolved batters",
            )
        if statcast is not None and lineup_ids[prefix]:
            lr_balance = statcast.lineup_lr_balance(lineup_ids[prefix])
            if lr_balance is not None:
                features[f"{prefix}_lineup_lr_balance"] = lr_balance

    opposing_hand = {"home": away_sp_hand, "away": home_sp_hand}
    opposing_sp = {"home": away_sp_id, "away": home_sp_id}

    for prefix in ("home", "away"):
        splits = build_platoon_features(statcast, game_pk, prefix, lineup_ids[prefix], opposing_hand[prefix], as_of)
        if splits is None:
            for feat in PLATOON_MATCHUP_FEATURES + LINEUP_HANDEDNESS_INTERACTION_FEATURES:
                if not feat.startswith(f"{prefix}_"):
                    continue
                suffix = feature_suffix(feat)
                features[feat] = FEATURE_FALLBACKS[suffix]
                degraded += 1
                _log_context_skip(f"{game_pk}", feat, _CONTEXT_SKIP_REASONS.get(suffix, "not implemented in this pass"),
                                  recorder=recorder,
                                  source="pipeline/statcast_store.py lineup_platoon_splits")
            continue
        provenance[f"{prefix}_platoon_batters_matched"] = splits["batters_matched"]
        for suffix in (
            "lineup_woba_vs_pitcher_hand", "lineup_iso_vs_pitcher_hand", "lineup_k_rate_vs_pitcher_hand",
            "lineup_bb_rate_vs_pitcher_hand", "lineup_hard_hit_vs_pitcher_hand",
            "lineup_strength_vs_pitcher_hand", "platoon_advantage_score",
        ):
            features[f"{prefix}_{suffix}"] = splits[suffix]
            recorder.fetch_attempted(
                [f"{prefix}_{suffix}"],
                "pipeline/statcast_store.py lineup_platoon_splits",
                evidence=f"{splits['batters_matched']} batters matched at the minimum sample threshold",
            )

    for prefix, abbr in (("home", home_abbr), ("away", away_abbr)):
        bullpen_feats, bp_provenance = build_bullpen_fatigue_quality(abbr, prefix, as_of=as_of, offline_only=offline_only)
        features.update(bullpen_feats)
        provenance[f"{prefix}_bullpen"] = bp_provenance
        for name in bullpen_feats:
            if bp_provenance.get("fallback_used") or bp_provenance.get("quality_fallback_used"):
                recorder.fallback_applied(
                    [name], bp_provenance.get("fatigue_source") or "league-average fallback",
                    f"build_bullpen_fatigue_quality reported fatigue_source="
                    f"{bp_provenance.get('fatigue_source')!r}, quality_source="
                    f"{bp_provenance.get('quality_source')!r} for {abbr}",
                )
            else:
                recorder.fetch_attempted(
                    [name], bp_provenance.get("quality_source") or bp_provenance.get("fatigue_source") or
                    "local statcast reliever game logs",
                    evidence=f"as_of {bp_provenance.get('as_of')}",
                )
        if bp_provenance.get("fallback_used"):
            degraded += len(BULLPEN_FATIGUE_FEATURES) // 2

    sp_id = {"home": home_sp_id, "away": away_sp_id}
    days_rest_by_side = {"home": home_days_rest, "away": away_days_rest}

    for side in ("home", "away"):
        feat = f"{side}_fb_rate_x_wind_out"
        fb_rate = None
        if statcast is not None and as_of is not None and sp_id[side] is not None:
            fb_rate = statcast.starter_fb_rate(sp_id[side], as_of)
        if fb_rate is None or wind_out is None:
            features[feat] = FEATURE_FALLBACKS[feature_suffix(feat)]
            degraded += 1
            _log_context_skip(f"{game_pk}", feat,
                              "starter point-in-time flyball rate or wind_out_factor unavailable for this game",
                              recorder=recorder, source="pipeline/statcast_store.py starter_fb_rate")
        else:
            features[feat] = round(max(-1.0, min(1.0, fb_rate * float(wind_out))), 4)
            recorder.fetch_attempted([feat], "pipeline/statcast_store.py starter_fb_rate",
                                     evidence=f"fb_rate={fb_rate}, wind_out={wind_out}")

    for side in ("home", "away"):
        feat = f"{side}_bullpen_fatigue_x_sp_innings_remaining_x_rest"
        fatigue = features.get(f"{side}_bullpen_fatigue_score", FEATURE_FALLBACKS["bullpen_fatigue_score"])
        days_rest = days_rest_by_side[side]
        if days_rest is None:
            days_rest = FEATURE_FALLBACKS["days_rest"]
        sp_innings = None
        if statcast is not None and as_of is not None and sp_id[side] is not None:
            sp_innings = statcast.starter_avg_innings(sp_id[side], as_of)
        if sp_innings is None:
            features[feat] = FEATURE_FALLBACKS[feature_suffix(feat)]
            degraded += 1
            _log_context_skip(f"{game_pk}", feat,
                              "starter point-in-time average innings per start unavailable; interaction would multiply a constant placeholder",
                              recorder=recorder, source="pipeline/statcast_store.py starter_avg_innings")
        else:
            features[feat] = round(fatigue * sp_innings / max(float(days_rest), 1.0), 4)
            recorder.fetch_attempted([feat], "pipeline/statcast_store.py starter_avg_innings",
                                     evidence=f"sp_innings={sp_innings}, days_rest={days_rest}")

    features["wind_park_directional_factor"] = FEATURE_FALLBACKS["wind_park_directional_factor"]
    degraded += 1
    _log_context_skip(f"{game_pk}", "wind_park_directional_factor",
                      "per-park LF/CF/RF orientation and HR-distance profile not yet modeled beyond the existing single-scalar wind_out_factor — kept as a live-only placeholder, wind_out_factor remains the production feature",
                      recorder=recorder, source="not implemented — no producer exists for this field")

    for side in ("home", "away"):
        feat = f"{side}_pitch_mix_x_lineup_matchup"
        score = None
        if statcast is not None and as_of is not None and opposing_sp[side] is not None:
            score = statcast.pitch_mix_lineup_matchup(opposing_sp[side], lineup_ids[side], as_of)
        if score is None:
            features[feat] = FEATURE_FALLBACKS[feature_suffix(feat)]
            degraded += 1
            _log_context_skip(f"{game_pk}", feat, _CONTEXT_SKIP_REASONS["pitch_mix_x_lineup_matchup"],
                              recorder=recorder, source="pipeline/statcast_store.py pitch_mix_lineup_matchup")
        else:
            features[feat] = score
            recorder.fetch_attempted([feat], "pipeline/statcast_store.py pitch_mix_lineup_matchup",
                                     evidence=f"matchup score {score}")

    validated, invalid = validate_features(features)
    recorder.validation_result(features.keys(), invalid)
    provenance["invalid_features"] = invalid
    provenance["degraded_feature_count"] = degraded + len(invalid)
    provenance["field_records"] = recorder.finalize(validated)
    return validated, provenance


def get_context_feature_list():
    return list(CONTEXT_FEATURES)


def row_schema_version(df, index):
    if "feature_schema_version" in df.columns:
        value = df["feature_schema_version"].iloc[index]
        if isinstance(value, str) and value:
            return value
    return FEATURE_SCHEMA_VERSION


def schema_applicable_features(features, schema_version, history=None):
    from pipeline.field_provenance import (
        APPLICABILITY_NOT_APPLICABLE,
        classify_training_field_applicability,
        registry_schema_history,
    )

    history = registry_schema_history() if history is None else history
    applicable = []
    excluded = {}
    for name in features:
        verdict, reason, _ = classify_training_field_applicability(name, schema_version, history)
        if verdict == APPLICABILITY_NOT_APPLICABLE:
            excluded[name] = reason
        else:
            applicable.append(name)
    return applicable, excluded


def build_training_frame(df, target):
    from pipeline.field_provenance import registry_schema_history

    features = get_feature_list(target)
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise ValueError(f"dataset missing required features for target {target}: {missing}")
    X = df[features].copy()
    history = registry_schema_history()
    applicable_cache = {}
    validated_rows = []
    degraded_counts = []
    applicable_counts = []
    schema_exclusions = {}
    for position, (_, row) in enumerate(X.iterrows()):
        schema_version = row_schema_version(df, position)
        if schema_version not in applicable_cache:
            applicable_cache[schema_version] = schema_applicable_features(features, schema_version, history)
        applicable, excluded = applicable_cache[schema_version]
        schema_exclusions.update(excluded)
        validated, invalid = validate_features(row.to_dict())
        validated_rows.append(validated)
        degraded_counts.append(len([name for name in invalid if name in applicable]))
        applicable_counts.append(len(applicable))
    X_validated = pd.DataFrame(validated_rows)[features]
    counts = pd.Series(degraded_counts, name="degraded_feature_count")
    counts.attrs["applicable_feature_counts"] = applicable_counts
    counts.attrs["schema_excluded_features"] = schema_exclusions
    return X_validated, counts
