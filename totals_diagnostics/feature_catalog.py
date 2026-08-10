FEATURE_CATALOG = {
"park_factor": dict(
        label="Park Factor",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="Hardcoded PARK_FACTORS table (FanGraphs 2024-2025 actuals)",
        pipeline="services/totals_model_v3.py: compute_totals_pick()",
        recommendation="Historical gap only — deterministic from home team, safe to backfill if ever needed.",
        priority="Low",
    ),
"weather_factor": dict(
        label="Weather Factor",
        applies_to="totals",
        status_path=("weather_source",),
        baseline_status="Partial",
        source="wttr.in (live) with an MLB Stats API dome/roof check",
        pipeline="services/totals_model_v3.py: _fetch_weather()",
        recommendation="Now tagged with weather_source/weather_error (fixed 2026-08-07) — watch the fallback_default rate.",
        priority="Medium",
    ),
"temp_f": dict(
        label="Temperature (F)",
        applies_to="totals",
        status_path=("weather_source",),
        baseline_status="Partial",
        source="wttr.in (live) — shares the weather_factor fetch",
        pipeline="services/totals_model_v3.py: _fetch_weather()",
        recommendation="Same fetch as weather_factor.",
        priority="Low",
    ),
"wind_info": dict(
        label="Wind Info",
        applies_to="totals",
        status_path=("weather_source",),
        baseline_status="Partial",
        source="wttr.in (live) — shares the weather_factor fetch",
        pipeline="services/totals_model_v3.py: _fetch_weather()",
        recommendation="Same fetch as weather_factor.",
        priority="Low",
    ),
"home_bp_era": dict(
        label="Home Bullpen ERA",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API team season stats (back-solved estimate, never returns null)",
        pipeline="services/totals_model_v3.py: _fetch_team_bullpen_era()",
        recommendation="Historical gap only. Methodology is an approximation, not a broken fetch — future upgrade, not a bug.",
        priority="Low",
    ),
"away_bp_era": dict(
        label="Away Bullpen ERA",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API team season stats (back-solved estimate, never returns null)",
        pipeline="services/totals_model_v3.py: _fetch_team_bullpen_era()",
        recommendation="Historical gap only.",
        priority="Low",
    ),
"home_available_bp_era": dict(
        label="Home Available Bullpen ERA",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="Blend of home_bp_era + live reliever-availability data, falls back to team ERA",
        pipeline="services/totals_model_v3.py: _available_bp_era()",
        recommendation="Historical gap only; gracefully degrades to home_bp_era when live data is thin.",
        priority="Low",
    ),
"away_available_bp_era": dict(
        label="Away Available Bullpen ERA",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="Blend of away_bp_era + live reliever-availability data, falls back to team ERA",
        pipeline="services/totals_model_v3.py: _available_bp_era()",
        recommendation="Historical gap only.",
        priority="Low",
    ),
"context_home_available_recent_reliever_era": dict(
        label="Home Reliever ERA (live availability)",
        applies_to="totals",
        status_path=("context", "home_bullpen_fetch_status"),
        baseline_status="Partial",
        source="Live MLB boxscore fetch — last 3 completed games",
        pipeline="services/advanced_context_service.py: bullpen_availability()",
        recommendation="Now retries once with exponential backoff and no longer caches failures for the day (fixed 2026-08-07).",
        priority="Medium",
    ),
"context_away_available_recent_reliever_era": dict(
        label="Away Reliever ERA (live availability)",
        applies_to="totals",
        status_path=("context", "away_bullpen_fetch_status"),
        baseline_status="Partial",
        source="Live MLB boxscore fetch — last 3 completed games",
        pipeline="services/advanced_context_service.py: bullpen_availability()",
        recommendation="Same fix as the home side.",
        priority="Medium",
    ),
"home_starter_usage_expected_innings": dict(
        label="Home Starter Expected Innings",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API per-pitcher game log, last 5 starts (documented fallback: 5.5 innings)",
        pipeline="services/totals_model_v3.py: _fetch_expected_starter_usage()",
        recommendation="Historical gap only; not safely backfillable (needs the historical confirmed starter).",
        priority="Low",
    ),
"away_starter_usage_expected_innings": dict(
        label="Away Starter Expected Innings",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API per-pitcher game log, last 5 starts (documented fallback: 5.5 innings)",
        pipeline="services/totals_model_v3.py: _fetch_expected_starter_usage()",
        recommendation="Historical gap only.",
        priority="Low",
    ),
"home_starter_usage_starts_used": dict(
        label="Home Starter Starts Used",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API per-pitcher game log — len(last 5 starts), correctly capped at 5",
        pipeline="services/totals_model_v3.py: _fetch_expected_starter_usage()",
        recommendation="Not broken — diagnostics false positive. len(last_5_starts) is arithmetically pinned at 5 for any pitcher with 5+ starts this season. Rename to starter_usage_window_size and exclude from constant-feature flags.",
        priority="Low",
    ),
"away_starter_usage_starts_used": dict(
        label="Away Starter Starts Used",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API per-pitcher game log — len(last 5 starts), correctly capped at 5",
        pipeline="services/totals_model_v3.py: _fetch_expected_starter_usage()",
        recommendation="Not broken — same false positive as the home side.",
        priority="Low",
    ),
"ump_name": dict(
        label="Home Plate Umpire",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API boxscore + static UMPIRE_RUNS_ADJ table",
        pipeline="services/totals_model_v3.py: _fetch_home_plate_umpire()",
        recommendation="Historical gap + structurally absent from moneyline picks by design (not a bug unless umpire data should also inform moneyline).",
        priority="Low",
    ),
"ump_runs_adj": dict(
        label="Umpire Runs Adjustment",
        applies_to="totals",
        status_path=None,
        baseline_status="Healthy",
        source="MLB Stats API boxscore + static UMPIRE_RUNS_ADJ table",
        pipeline="services/totals_model_v3.py: _fetch_home_plate_umpire()",
        recommendation="Same as ump_name.",
        priority="Low",
    ),
}


REASON_HISTORICAL_SNAPSHOT = "Historical Snapshot"
REASON_MONEYLINE_SNAPSHOT = "Moneyline Snapshot"
REASON_API_TIMEOUT = "API Timeout"
REASON_FALLBACK_USED = "Fallback Used"
REASON_NOT_COLLECTED = "Feature Not Collected"
REASON_NULL = "Null"
REASON_UNKNOWN = "Unknown"


def _get_path(d, path):
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def current_schema_version(records, default=1):

    versions = [r["schema_version"] for r in records if r.get("schema_version") is not None]
    return max(versions) if versions else default


def get_feature_value(record, feature_key):

    snap = record.get("snap") or {}
    if feature_key.startswith("home_starter_usage_"):
        return _get_path(snap, ("home_starter_usage", feature_key[len("home_starter_usage_") :]))
    if feature_key.startswith("away_starter_usage_"):
        return _get_path(snap, ("away_starter_usage", feature_key[len("away_starter_usage_") :]))
    if feature_key.startswith("context_"):
        return _get_path(snap, ("context", feature_key[len("context_") :]))
    return snap.get(feature_key)


def classify_missing_reason(record, feature_key, current_version):

    meta = FEATURE_CATALOG.get(feature_key, {})
    applies_to = meta.get("applies_to", "totals")
    status_path = meta.get("status_path")

    if applies_to == "totals" and record.get("pick_type") != "totals":
        return REASON_MONEYLINE_SNAPSHOT
    if not record.get("has_snapshot"):
        return REASON_HISTORICAL_SNAPSHOT
    schema_version = record.get("schema_version")
    if schema_version is None or schema_version < current_version:
        return REASON_HISTORICAL_SNAPSHOT

    status_value = _get_path(record.get("snap") or {}, status_path) if status_path else None
    if status_value in ("TIMEOUT", "API_ERROR"):
        return REASON_API_TIMEOUT
    if status_value == "FALLBACK" or status_value == "fallback_default":
        return REASON_FALLBACK_USED
    if status_value is None and status_path is not None:

        return REASON_NOT_COLLECTED
    if status_path is None:
        return REASON_NULL
    return REASON_UNKNOWN


def compute_feature_health(records, feature_key, current_version):

    meta = FEATURE_CATALOG.get(feature_key, {})
    applies_to = meta.get("applies_to", "totals")
    status_path = meta.get("status_path")

    applicable = [r for r in records if applies_to != "totals" or r.get("pick_type") == "totals"]
    total_n = len(applicable)
    if total_n == 0:
        return None

    current_rows = [r for r in applicable if (r.get("schema_version") or 0) >= current_version]
    older_rows = [r for r in applicable if r not in current_rows]

    def _present(rows):
        return [r for r in rows if get_feature_value(r, feature_key) is not None]

    missing_pct = round((1 - len(_present(applicable)) / total_n) * 100, 1)
    live_coverage = (
        round(len(_present(current_rows)) / len(current_rows) * 100, 1) if current_rows else None
    )
    historical_coverage = (
        round(len(_present(older_rows)) / len(older_rows) * 100, 1) if older_rows else None
    )

    fallback_rate = None
    default_rate = None
    if status_path is not None and current_rows:
        present_current = _present(current_rows)
        if present_current:
            statuses = [_get_path(r.get("snap") or {}, status_path) for r in present_current]
            fallback_rate = round(
                sum(s in ("TIMEOUT", "API_ERROR") for s in statuses) / len(statuses) * 100, 1
            )
            default_rate = round(
                sum(s in ("FALLBACK", "fallback_default") for s in statuses) / len(statuses) * 100,
                1,
            )

    reasons = {}
    for r in applicable:
        if get_feature_value(r, feature_key) is None:
            reason = classify_missing_reason(r, feature_key, current_version)
            reasons[reason] = reasons.get(reason, 0) + 1

    return {
"key": feature_key,
"label": meta.get("label", feature_key),
"status": meta.get("baseline_status", "Unknown"),
"missing_pct": missing_pct,
"live_coverage": live_coverage,
"historical_coverage": historical_coverage,
"fallback_rate": fallback_rate,
"default_rate": default_rate,
"source": meta.get("source", "Unknown"),
"pipeline": meta.get("pipeline", "Unknown"),
"recommendation": meta.get("recommendation", ""),
"priority": meta.get("priority", "Low"),
"reasons": reasons,
"n": total_n,
"n_current_schema": len(current_rows),
    }
