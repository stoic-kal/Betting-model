import time
import requests
from datetime import datetime, timedelta

from pipeline.features_common import (
    STADIUMS, ML_FEATURES, TOTALS_FEATURES, FEATURE_FALLBACKS, FEATURE_SCHEMA_VERSION,
    LEAGUE_AVG_TOTAL_RUNS_PRIOR, pitcher_rate_stats, team_bat_rate_stats,
    is_dome, is_coors, wind_out_factor, validate_features,
)
from pipeline.field_provenance import ProvenanceRecorder

MLB_API = "https://statsapi.mlb.com/api/v1"
MAX_RETRIES = 2
RETRY_BACKOFF_SECS = 1.5

_PITCHER_SOURCE = "pybaseball.statcast_pitcher point-in-time pitch-level rows"
_GAMELOG_SOURCE = f"{MLB_API}/people/<id>/stats?stats=gameLog&group=pitching"
_PEOPLE_SOURCE = f"{MLB_API}/people/<id> pitchHand.code"
_TEAM_BAT_SOURCE = "pybaseball.statcast point-in-time team pitch-level rows"
_SCHEDULE_SOURCE = f"{MLB_API}/schedule teamId window"
_VENUE_SOURCE = f"{MLB_API}/schedule venueIds window"
_WEATHER_SOURCE = "api.open-meteo.com/v1/forecast hourly"


def _match(fields, suffix):
    return [name for name in fields if name.endswith(suffix)]


def _record_ok(recorder, fields, source, evidence):
    if recorder is not None and fields:
        recorder.fetch_attempted(fields, source, evidence=evidence)


def _record_failure(recorder, fields, source, error):
    if recorder is not None and fields:
        recorder.fetch_failed(fields, source, error)
        recorder.fallback_applied(
            fields, source,
            f"live fetch from {source} did not return usable data, so the documented FEATURE_FALLBACKS value "
            f"was substituted",
        )


def _record_fallback(recorder, fields, source, reason):
    if recorder is not None and fields:
        recorder.fallback_applied(fields, source, reason)

_cache: dict = {}
_cache_date: str = None


def _maybe_clear_cache(as_of_date):
    global _cache, _cache_date
    key = as_of_date.strftime("%Y-%m-%d")
    if _cache_date != key:
        _cache = {}
        _cache_date = key


def _retry_get(url, params=None, timeout=15):
    last_exc = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECS * (attempt + 1))
    raise last_exc


def assert_point_in_time(fetch_end_date, as_of_date):
    if fetch_end_date >= as_of_date:
        raise ValueError(f"point-in-time violation: fetch_end={fetch_end_date} as_of={as_of_date}")


def fetch_pitcher_recent_stats(pitcher_id, as_of_date, degraded, n_starts=5, lookback_days=45, recorder=None, fields=()):
    _maybe_clear_cache(as_of_date)
    ck = ("pitcher", pitcher_id, as_of_date.strftime("%Y-%m-%d"))
    if ck in _cache:
        return _cache[ck]

    end_date = as_of_date - timedelta(days=1)
    start_date = as_of_date - timedelta(days=lookback_days)
    assert_point_in_time(end_date, as_of_date)

    try:
        import pybaseball
        pybaseball.cache.enable()
        df = pybaseball.statcast_pitcher(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), pitcher_id)
        if df is None or df.empty:
            raise ValueError("no statcast rows returned")

        df = df.sort_values("game_date")
        recent_game_pks = df["game_pk"].drop_duplicates().tail(n_starts)
        df = df[df["game_pk"].isin(recent_game_pks)]

        terminal = df[df["events"].notna()]
        batted = df[df["launch_speed"].notna()]
        fastballs = df[df["pitch_type"].isin({"FF", "SI", "FC"})]

        bf = len(terminal)
        k = int((terminal["events"] == "strikeout").sum())
        bb = int(terminal["events"].isin(["walk", "intent_walk", "hit_by_pitch"]).sum())
        hr = int((terminal["events"] == "home_run").sum())
        hard = int((batted["launch_speed"] >= 95).sum())
        bip = len(batted)
        velo_sum = float(fastballs["release_speed"].sum())
        velo_n = int(fastballs["release_speed"].notna().sum())
        xwoba_col = df["estimated_woba_using_speedangle"]
        xwoba_sum = float(xwoba_col.sum())
        xwoba_n = int(xwoba_col.notna().sum())

        stats = pitcher_rate_stats(bf, k, bb, hr, hard, bip, velo_sum, velo_n, xwoba_sum, xwoba_n)
        _record_ok(recorder, fields, _PITCHER_SOURCE,
                   f"{len(recent_game_pks)} statcast start(s) between {start_date.date()} and {end_date.date()}")
        for suffix in ("fb_velo", "xwoba_against"):
            if stats[suffix] is None:
                stats[suffix] = FEATURE_FALLBACKS[suffix]
                degraded.append(suffix)
                _record_fallback(recorder, _match(fields, suffix), _PITCHER_SOURCE,
                                 f"statcast returned no non-null {suffix} rows in the point-in-time window, "
                                 f"FEATURE_FALLBACKS[{suffix!r}] substituted")
        _cache[ck] = stats
        return stats
    except Exception as exc:
        degraded.append("pitcher_rate_stats")
        _record_failure(recorder, fields, _PITCHER_SOURCE, exc)
        fallback = {k: FEATURE_FALLBACKS[k] for k in ("k_rate", "bb_rate", "hr_rate", "hard_hit_pct", "fb_velo", "xwoba_against", "fip")}
        _cache[ck] = fallback
        return fallback


def fetch_pitcher_days_rest(pitcher_id, as_of_date, degraded, recorder=None, fields=()):
    _maybe_clear_cache(as_of_date)
    ck = ("rest", pitcher_id, as_of_date.strftime("%Y-%m-%d"))
    if ck in _cache:
        return _cache[ck]
    try:
        end_date = as_of_date - timedelta(days=1)
        start_date = as_of_date - timedelta(days=30)
        assert_point_in_time(end_date, as_of_date)
        r = _retry_get(
            f"{MLB_API}/people/{pitcher_id}/stats",
            params={"stats": "gameLog", "group": "pitching", "season": as_of_date.year},
        )
        data = r.json()
        splits = data.get("stats", [{}])[0].get("splits", [])
        dates = [datetime.strptime(s["date"], "%Y-%m-%d") for s in splits if "date" in s]
        dates = [d for d in dates if start_date <= d <= end_date]
        if not dates:
            raise ValueError("no recent starts found")
        last_start = max(dates)
        rest = min((as_of_date - last_start).days, 30)
        _record_ok(recorder, fields, _GAMELOG_SOURCE, f"last start {last_start.date()}")
        _cache[ck] = float(rest)
        return float(rest)
    except Exception as exc:
        degraded.append("days_rest")
        _record_failure(recorder, fields, _GAMELOG_SOURCE, exc)
        _cache[ck] = FEATURE_FALLBACKS["days_rest"]
        return FEATURE_FALLBACKS["days_rest"]


def fetch_pitcher_handedness(pitcher_id, degraded, recorder=None, fields=()):
    ck = ("hand", pitcher_id)
    if ck in _cache:
        return _cache[ck]
    try:
        r = _retry_get(f"{MLB_API}/people/{pitcher_id}")
        hand = r.json()["people"][0]["pitchHand"]["code"]
        val = 1.0 if hand == "L" else 0.0
        _record_ok(recorder, fields, _PEOPLE_SOURCE, f"pitchHand.code={hand}")
        _cache[ck] = val
        return val
    except Exception as exc:
        degraded.append("is_lefty")
        _record_failure(recorder, fields, _PEOPLE_SOURCE, exc)
        _cache[ck] = 0.0
        return 0.0


def fetch_team_batting_recent(team_abbr, as_of_date, degraded, n_games=10, lookback_days=25, recorder=None, fields=()):
    _maybe_clear_cache(as_of_date)
    ck = ("bat", team_abbr, as_of_date.strftime("%Y-%m-%d"))
    if ck in _cache:
        return _cache[ck]
    try:
        import pybaseball
        pybaseball.cache.enable()
        end_date = as_of_date - timedelta(days=1)
        start_date = as_of_date - timedelta(days=lookback_days)
        assert_point_in_time(end_date, as_of_date)
        df = pybaseball.statcast(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"), team=team_abbr)
        if df is None or df.empty:
            raise ValueError("no statcast rows returned")

        df = df.sort_values("game_date")
        df["bat_team"] = df.apply(lambda r: r["away_team"] if r["inning_topbot"] == "Top" else r["home_team"], axis=1)
        df = df[df["bat_team"] == team_abbr]
        recent_game_pks = df["game_pk"].drop_duplicates().tail(n_games)
        df = df[df["game_pk"].isin(recent_game_pks)]

        terminal = df[df["events"].notna()]
        batted = df[df["launch_speed"].notna()]
        woba_col = df["woba_value"]

        bf = len(terminal)
        k = int((terminal["events"] == "strikeout").sum())
        hr = int((terminal["events"] == "home_run").sum())
        hard = int((batted["launch_speed"] >= 95).sum())
        bip = len(batted)
        woba_sum = float(woba_col.sum())
        woba_n = int(woba_col.notna().sum())

        stats = team_bat_rate_stats(bf, k, hr, hard, bip, woba_sum, woba_n)
        _record_ok(recorder, fields, _TEAM_BAT_SOURCE,
                   f"{len(recent_game_pks)} game(s) between {start_date.date()} and {end_date.date()}")
        for stat_key in ("bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba"):
            if stats[stat_key] is None:
                stats[stat_key] = FEATURE_FALLBACKS[stat_key]
                degraded.append(stat_key)
                _record_fallback(recorder, _match(fields, stat_key), _TEAM_BAT_SOURCE,
                                 f"statcast returned no rows able to produce {stat_key} in the point-in-time window")
        _cache[ck] = stats
        return stats
    except Exception as exc:
        degraded.append("team_batting")
        _record_failure(recorder, fields, _TEAM_BAT_SOURCE, exc)
        fallback = {k: FEATURE_FALLBACKS[k] for k in ("bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba")}
        _cache[ck] = fallback
        return fallback


def fetch_team_l10_form(team_id, as_of_date, degraded, n_games=10, recorder=None, fields=()):
    _maybe_clear_cache(as_of_date)
    ck = ("form", team_id, as_of_date.strftime("%Y-%m-%d"))
    if ck in _cache:
        return _cache[ck]
    try:
        end_date = as_of_date - timedelta(days=1)
        start_date = as_of_date - timedelta(days=35)
        assert_point_in_time(end_date, as_of_date)
        r = _retry_get(
            f"{MLB_API}/schedule",
            params={
                "teamId": team_id, "sportId": 1,
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
            },
        )
        games = []
        for d in r.json().get("dates", []):
            for g in d.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                home = g["teams"]["home"]
                away = g["teams"]["away"]
                is_home = home["team"]["id"] == team_id
                team_side = home if is_home else away
                opp_side = away if is_home else home
                rs = team_side.get("score")
                ra = opp_side.get("score")
                win = team_side.get("isWinner")
                if rs is None or ra is None or win is None:
                    continue
                games.append({"date": g["gameDate"], "win": bool(win), "rs": rs, "ra": ra})
        games = sorted(games, key=lambda x: x["date"])[-n_games:]
        if not games:
            raise ValueError("no completed games in lookback window")
        wr = sum(1 for g in games if g["win"]) / len(games)
        rs = sum(g["rs"] for g in games) / len(games)
        ra = sum(g["ra"] for g in games) / len(games)
        result = {"L10_wr": wr, "L10_rs": rs, "L10_ra": ra}
        _record_ok(recorder, fields, _SCHEDULE_SOURCE, f"{len(games)} completed game(s) in the lookback window")
        _cache[ck] = result
        return result
    except Exception as exc:
        degraded.append("l10_form")
        _record_failure(recorder, fields, _SCHEDULE_SOURCE, exc)
        fallback = {k: FEATURE_FALLBACKS[k] for k in ("L10_wr", "L10_rs", "L10_ra")}
        _cache[ck] = fallback
        return fallback


def fetch_park_factor(home_team_abbr, venue_id, as_of_date, degraded, n_games=100, lookback_days=730, recorder=None, fields=()):
    _maybe_clear_cache(as_of_date)
    ck = ("park", venue_id, as_of_date.strftime("%Y-%m-%d"))
    if ck in _cache:
        return _cache[ck]
    try:
        end_date = as_of_date - timedelta(days=1)
        start_date = as_of_date - timedelta(days=lookback_days)
        assert_point_in_time(end_date, as_of_date)
        r = _retry_get(
            f"{MLB_API}/schedule",
            params={
                "venueIds": venue_id, "sportId": 1,
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
            },
        )
        totals = []
        for d in r.json().get("dates", []):
            for g in d.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                home_score = g["teams"]["home"].get("score")
                away_score = g["teams"]["away"].get("score")
                if home_score is None or away_score is None:
                    continue
                totals.append(home_score + away_score)
        totals = totals[-n_games:]
        if not totals:
            raise ValueError("no completed games at venue in lookback window")
        pf = sum(totals) / len(totals)
        _record_ok(recorder, fields, _VENUE_SOURCE, f"{len(totals)} completed game(s) at venue {venue_id}")
        _cache[ck] = float(pf)
        return float(pf)
    except Exception as exc:
        degraded.append("park_factor")
        _record_failure(recorder, fields, _VENUE_SOURCE, exc)
        _cache[ck] = LEAGUE_AVG_TOTAL_RUNS_PRIOR
        return LEAGUE_AVG_TOTAL_RUNS_PRIOR


def fetch_weather_forecast(home_team_abbr, game_datetime, degraded, recorder=None, fields=()):
    meta = STADIUMS.get(home_team_abbr)
    if not meta:
        degraded.append("weather")
        _record_fallback(recorder, fields, _WEATHER_SOURCE,
                         f"no STADIUMS entry exists for home team {home_team_abbr!r}, so no coordinates were "
                         f"available to query the forecast API")
        return {"temp_f": FEATURE_FALLBACKS["temp_f"], "wind_mph": FEATURE_FALLBACKS["wind_mph"], "wind_out_factor": FEATURE_FALLBACKS["wind_out_factor"]}
    if meta["dome"] == 1:
        _record_ok(recorder, fields, "pipeline/features_common.py STADIUMS dome flag",
                   f"{home_team_abbr} is a fixed-roof venue, so indoor constants are the correct value, not a fallback")
        return {"temp_f": 72.0, "wind_mph": 0.0, "wind_out_factor": 0.0}
    try:
        r = _retry_get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": meta["lat"], "longitude": meta["lon"],
                "hourly": "temperature_2m,windspeed_10m,winddirection_10m",
                "temperature_unit": "fahrenheit", "windspeed_unit": "mph",
                "timezone": "America/New_York",
                "start_date": game_datetime.strftime("%Y-%m-%d"),
                "end_date": game_datetime.strftime("%Y-%m-%d"),
            },
        )
        data = r.json()["hourly"]
        times = data["time"]
        target_hour = game_datetime.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
        if target_hour not in times:
            raise ValueError("forecast hour not available")
        idx = times.index(target_hour)
        temp_f = float(data["temperature_2m"][idx])
        wind_mph = float(data["windspeed_10m"][idx])
        wind_dir = float(data["winddirection_10m"][idx])
        wof = wind_out_factor(wind_dir, meta["cf_deg"]) * (1 - meta["dome"])
        _record_ok(recorder, fields, _WEATHER_SOURCE, f"forecast hour {target_hour}")
        return {"temp_f": temp_f, "wind_mph": wind_mph, "wind_out_factor": wof}
    except Exception as exc:
        degraded.append("weather")
        _record_failure(recorder, fields, _WEATHER_SOURCE, exc)
        return {"temp_f": FEATURE_FALLBACKS["temp_f"], "wind_mph": FEATURE_FALLBACKS["wind_mph"], "wind_out_factor": FEATURE_FALLBACKS["wind_out_factor"]}


def compute_context_features_for_game(game_pk, home_team, away_team, home_bat, away_bat, as_of=None, **matchup):
    from pipeline.feature_store import build_context_features

    try:
        context_features, context_provenance = build_context_features(
            game_pk, home_team, away_team, home_bat, away_bat, as_of=as_of, **matchup
        )
        return context_features, context_provenance
    except Exception as exc:
        return {}, {"error": str(exc)}


def compute_v2_features(home_team, away_team, home_team_id, away_team_id, home_sp_id, away_sp_id, venue_id, game_datetime, game_pk=None):
    degraded = []
    recorder = ProvenanceRecorder(FEATURE_SCHEMA_VERSION)
    as_of_date = game_datetime.replace(hour=0, minute=0, second=0, microsecond=0)

    def _side_fields(prefix, suffixes):
        return [f"{prefix}_{s}" for s in suffixes if f"{prefix}_{s}" in ML_FEATURES]

    pitcher_suffixes = ("k_rate", "bb_rate", "hr_rate", "hard_hit_pct", "fb_velo", "xwoba_against", "fip")
    bat_suffixes = ("bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba")
    form_suffixes = ("L10_wr", "L10_rs", "L10_ra")

    home_p = fetch_pitcher_recent_stats(home_sp_id, as_of_date, degraded,
                                        recorder=recorder, fields=_side_fields("home", pitcher_suffixes))
    away_p = fetch_pitcher_recent_stats(away_sp_id, as_of_date, degraded,
                                        recorder=recorder, fields=_side_fields("away", pitcher_suffixes))
    home_rest = fetch_pitcher_days_rest(home_sp_id, as_of_date, degraded,
                                        recorder=recorder, fields=["home_days_rest"])
    away_rest = fetch_pitcher_days_rest(away_sp_id, as_of_date, degraded,
                                        recorder=recorder, fields=["away_days_rest"])
    home_lefty = fetch_pitcher_handedness(home_sp_id, degraded, recorder=recorder, fields=["home_is_lefty"])
    away_lefty = fetch_pitcher_handedness(away_sp_id, degraded, recorder=recorder, fields=["away_is_lefty"])
    home_bat = fetch_team_batting_recent(home_team, as_of_date, degraded,
                                         recorder=recorder, fields=_side_fields("home", bat_suffixes))
    away_bat = fetch_team_batting_recent(away_team, as_of_date, degraded,
                                         recorder=recorder, fields=_side_fields("away", bat_suffixes))
    home_form = fetch_team_l10_form(home_team_id, as_of_date, degraded,
                                    recorder=recorder, fields=_side_fields("home", form_suffixes))
    away_form = fetch_team_l10_form(away_team_id, as_of_date, degraded,
                                    recorder=recorder, fields=_side_fields("away", form_suffixes))
    park_factor = fetch_park_factor(home_team, venue_id, as_of_date, degraded,
                                    recorder=recorder, fields=["park_factor"])
    weather = fetch_weather_forecast(home_team, game_datetime, degraded,
                                     recorder=recorder, fields=["temp_f", "wind_mph", "wind_out_factor"])

    features = {
        "home_k_rate": home_p["k_rate"], "home_bb_rate": home_p["bb_rate"], "home_hr_rate": home_p["hr_rate"],
        "home_hard_hit_pct": home_p["hard_hit_pct"], "home_fb_velo": home_p["fb_velo"],
        "home_xwoba_against": home_p["xwoba_against"], "home_fip": home_p["fip"],
        "home_is_lefty": home_lefty, "home_days_rest": home_rest,
        "away_k_rate": away_p["k_rate"], "away_bb_rate": away_p["bb_rate"], "away_hr_rate": away_p["hr_rate"],
        "away_hard_hit_pct": away_p["hard_hit_pct"], "away_fb_velo": away_p["fb_velo"],
        "away_xwoba_against": away_p["xwoba_against"], "away_fip": away_p["fip"],
        "away_is_lefty": away_lefty, "away_days_rest": away_rest,
        "home_bat_k_rate": home_bat["bat_k_rate"], "home_bat_hard_hit_pct": home_bat["bat_hard_hit_pct"],
        "home_bat_iso": home_bat["bat_iso"], "home_bat_woba": home_bat["bat_woba"],
        "away_bat_k_rate": away_bat["bat_k_rate"], "away_bat_hard_hit_pct": away_bat["bat_hard_hit_pct"],
        "away_bat_iso": away_bat["bat_iso"], "away_bat_woba": away_bat["bat_woba"],
        "home_L10_wr": home_form["L10_wr"], "home_L10_rs": home_form["L10_rs"], "home_L10_ra": home_form["L10_ra"],
        "away_L10_wr": away_form["L10_wr"], "away_L10_rs": away_form["L10_rs"], "away_L10_ra": away_form["L10_ra"],
        "park_factor": park_factor, "is_dome": 1.0 if is_dome(home_team) else 0.0,
        "is_coors": 1.0 if is_coors(home_team) else 0.0,
        "temp_f": weather["temp_f"], "wind_mph": weather["wind_mph"], "wind_out_factor": weather["wind_out_factor"],
    }

    assert set(features.keys()) == set(ML_FEATURES), "feature set mismatch vs trained model contract"
    recorder.fetch_attempted(
        ["is_dome", "is_coors"],
        "pipeline/features_common.py STADIUMS table",
        evidence=f"deterministic from home team {home_team}",
    )
    validated, invalid = validate_features(features)
    recorder.validation_result(features.keys(), invalid)
    degraded = degraded + [f"invalid:{k}" for k in invalid if f"invalid:{k}" not in degraded]

    context_features, context_provenance = ({}, {})
    if game_pk is not None:
        context_features, context_provenance = compute_context_features_for_game(
            game_pk, home_team, away_team, home_bat, away_bat, as_of=as_of_date.date(),
            home_sp_id=home_sp_id, away_sp_id=away_sp_id,
            home_sp_hand="L" if home_lefty == 1.0 else "R",
            away_sp_hand="L" if away_lefty == 1.0 else "R",
            home_days_rest=home_rest, away_days_rest=away_rest,
            wind_out=weather["wind_out_factor"],
        )

    return {
        "features": validated,
        "degraded": degraded,
        "schema_version": FEATURE_SCHEMA_VERSION,
        "context_features": context_features,
        "context_provenance": context_provenance,
        "field_provenance": recorder.finalize(validated),
    }
