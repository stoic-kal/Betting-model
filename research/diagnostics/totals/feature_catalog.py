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
        required_count_path=("context", "home_available_reliever_quality_count"),
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
        required_count_path=("context", "away_available_reliever_quality_count"),
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
REASON_NOT_APPLICABLE = "Not Applicable (field absent from this writer version)"
REASON_NO_SNAPSHOT = "No Snapshot Payload Persisted"
REASON_INSUFFICIENT_EVIDENCE = "Insufficient Evidence To Determine Root Cause"


def _provenance():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "pipeline" / "field_provenance.py"
    spec = importlib.util.spec_from_file_location("pipeline_field_provenance", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PROVENANCE = _provenance()


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


def field_provenance(record, feature_key, cohorts, skip_index=None):

    meta = FEATURE_CATALOG.get(feature_key, {})
    status_path = meta.get("status_path")
    status_value = _get_path(record.get("snap") or {}, status_path) if status_path else None
    if status_value is None and feature_key.startswith("context_") and "available_recent_reliever_era" in feature_key:
        side = "home" if "context_home_" in feature_key else "away"
        bullpen = _get_path(record.get("snap") or {}, ("context", "advanced", f"{side}_bullpen")) or {}
        if bullpen.get("available"):
            status_value = "SUCCESS"
        elif "timed out" in str(bullpen.get("error", "")).lower():
            status_value = "TIMEOUT"
        elif bullpen.get("error"):
            status_value = "API_ERROR"
    return _PROVENANCE.reconstruct_snapshot_provenance(
        record,
        feature_key,
        _PROVENANCE.snapshot_key_for(feature_key),
        get_feature_value(record, feature_key),
        cohorts,
        meta=meta,
        skip_index=skip_index,
        status_value=status_value,
        status_path=status_path,
    )


def classify_missing_reason(record, feature_key, current_version, cohorts=None, skip_index=None):

    meta = FEATURE_CATALOG.get(feature_key, {})
    if meta.get("applies_to", "totals") == "totals" and record.get("pick_type") != "totals":
        return REASON_MONEYLINE_SNAPSHOT, (
            "this pick is not a totals pick, and the field is only produced by the totals pipeline"
        )

    cohorts = cohorts if cohorts is not None else _PROVENANCE.snapshot_cohorts([record])
    provenance = field_provenance(record, feature_key, cohorts, skip_index=skip_index)

    if provenance.applicability == _PROVENANCE.APPLICABILITY_NOT_APPLICABLE:
        return REASON_NOT_APPLICABLE, provenance.reason_if_missing
    if provenance.snapshot_status == _PROVENANCE.SNAPSHOT_ABSENT:
        return REASON_NO_SNAPSHOT, provenance.reason_if_missing
    if provenance.fetch_status == _PROVENANCE.FETCH_FAILED and provenance.fallback_status == _PROVENANCE.FALLBACK_APPLIED:
        label = (
            REASON_API_TIMEOUT
            if "TIMEOUT" in provenance.reason_if_missing or "API_ERROR" in provenance.reason_if_missing
            else REASON_FALLBACK_USED
        )
        return label, provenance.reason_if_missing
    if provenance.fetch_status == _PROVENANCE.FETCH_NOT_ATTEMPTED and provenance.reason_if_missing:
        return REASON_NOT_COLLECTED, provenance.reason_if_missing
    if provenance.reason_if_missing.startswith("insufficient information"):
        return REASON_INSUFFICIENT_EVIDENCE, provenance.reason_if_missing
    if record.get("schema_version") is None or (current_version is not None
                                                and record.get("schema_version") < current_version):
        return REASON_HISTORICAL_SNAPSHOT, provenance.reason_if_missing
    return REASON_NULL, provenance.reason_if_missing


def compute_feature_health(records, feature_key, current_version):

    meta = FEATURE_CATALOG.get(feature_key, {})
    applies_to = meta.get("applies_to", "totals")
    status_path = meta.get("status_path")

    applicable = [r for r in records if applies_to != "totals" or r.get("pick_type") == "totals"]
    total_n = len(applicable)
    if total_n == 0:
        return None

    cohorts = _PROVENANCE.snapshot_cohorts(applicable)
    skip_index = _PROVENANCE.context_skip_index()

    no_snapshot_rows = [r for r in applicable if not r.get("has_snapshot")]
    snapshot_rows = [r for r in applicable if r.get("has_snapshot")]
    required_count_path = meta.get("required_count_path")
    not_applicable_rows = []
    for r in applicable:
        if not r.get("has_snapshot") or get_feature_value(r, feature_key) is not None:
            continue
        count = _get_path(r.get("snap") or {}, required_count_path) if required_count_path else None
        provenance = field_provenance(r, feature_key, cohorts, skip_index)
        if count == 0 and provenance.fetch_status != _PROVENANCE.FETCH_FAILED:
            not_applicable_rows.append(r)
        elif provenance.applicability == _PROVENANCE.APPLICABILITY_NOT_APPLICABLE:
            not_applicable_rows.append(r)
    scored = [r for r in snapshot_rows if r not in not_applicable_rows]
    scored_n = len(scored)

    current_rows = [r for r in scored if (r.get("schema_version") or 0) >= current_version]
    older_rows = [r for r in scored if r not in current_rows]

    def _present(rows):
        return [r for r in rows if get_feature_value(r, feature_key) is not None]

    missing_pct = round((1 - len(_present(scored)) / scored_n) * 100, 1) if scored_n else 0.0
    missing_pct_unfiltered = round((1 - len(_present(applicable)) / total_n) * 100, 1)
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
    explanations = {}
    for r in scored:
        if get_feature_value(r, feature_key) is None:
            reason, explanation = classify_missing_reason(r, feature_key, current_version, cohorts, skip_index)
            reasons[reason] = reasons.get(reason, 0) + 1
            explanations.setdefault(reason, explanation)

    return {
"key": feature_key,
"label": meta.get("label", feature_key),
"status": meta.get("baseline_status", derived_baseline_status(reasons, missing_pct)),
"missing_pct": missing_pct,
"missing_pct_unfiltered": missing_pct_unfiltered,
"not_applicable_rows": len(not_applicable_rows),
"no_snapshot_rows": len(no_snapshot_rows),
"live_coverage": live_coverage,
"historical_coverage": historical_coverage,
"fallback_rate": fallback_rate,
"default_rate": default_rate,
"source": meta.get("source") or derived_source(applicable, feature_key, cohorts, skip_index),
"pipeline": meta.get("pipeline") or derived_pipeline(feature_key),
"recommendation": meta.get("recommendation", ""),
"priority": meta.get("priority", "Low"),
"reasons": reasons,
"reason_explanations": explanations,
"n": total_n,
"n_scored": scored_n,
"n_current_schema": len(current_rows),
    }


def derived_baseline_status(reasons, missing_pct):

    if not reasons:
        return "Healthy"
    if REASON_API_TIMEOUT in reasons or REASON_FALLBACK_USED in reasons:
        return "Partial"
    if missing_pct >= 50:
        return "Historical Only"
    return "Partial"


def derived_source(records, feature_key, cohorts, skip_index):

    for record in records:
        provenance = field_provenance(record, feature_key, cohorts, skip_index)
        if provenance.snapshot_status == _PROVENANCE.SNAPSHOT_PRESENT:
            return (
                f"no source string is catalogued for this field; observed evidence is that a writer at schema "
                f"version {provenance.schema_version} persists it ({provenance.serialization_status}) — "
                f"see the code locations reported in the pipeline field"
            )
    return _PROVENANCE.insufficient_evidence(
        feature_key,
        ["the FEATURE_CATALOG source field", "every stored feature_snapshot payload in database/picks.db"],
    )


def derived_pipeline(feature_key):

    hits = _PROVENANCE.locate_field_code(feature_key)
    if hits:
        return "produced or referenced at " + ", ".join(hits)
    return _PROVENANCE.insufficient_evidence(
        feature_key, ["a whole-repository source scan for this identifier"]
    )
