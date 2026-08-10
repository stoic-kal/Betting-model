import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from services.game_context_service import TEAM_IDS

_CACHE = {}


def _expected_pitcher_row(pitcher_id):
    key = ("expected_leaderboard", date.today().year, date.today().isoformat())
    if key not in _CACHE:
        try:
            from pybaseball import statcast_pitcher_expected_stats

            frame = statcast_pitcher_expected_stats(date.today().year, 1)
            _CACHE[key] = {int(row["player_id"]): row for _, row in frame.iterrows()}
        except Exception as exc:
            print(f"  Savant expected-stats leaderboard unavailable: {exc}")
            _CACHE[key] = {}
    return _CACHE[key].get(int(pitcher_id))


def pitcher_statcast_profile(pitcher_id, days=60):
    fallback = {
        "available": False,
        "source": "Baseball Savant Statcast",
        "xera": None,
        "xera_proxy": None,
        "xera_is_proxy": False,
        "era": None,
        "xba_allowed": None,
        "xwoba_allowed": None,
        "xslg_allowed": None,
        "avg_velocity": None,
        "pitch_mix": [],
        "sample_pitches": 0,
    }
    if not pitcher_id:
        return fallback
    key = ("statcast", pitcher_id, date.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]
    try:
        from pybaseball import statcast_pitcher

        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=days)
        frame = statcast_pitcher(start.isoformat(), end.isoformat(), int(pitcher_id))
        if frame is None or frame.empty:
            _CACHE[key] = fallback
            return fallback

        def mean_col(name):
            values = frame[name].dropna().astype(float) if name in frame else []
            return float(values.mean()) if len(values) else None

        xwoba = mean_col("estimated_woba_using_speedangle")
        xba = mean_col("estimated_ba_using_speedangle")
        xslg = mean_col("estimated_slg_using_speedangle")
        velo = mean_col("release_speed")
        counts = Counter(str(v) for v in frame.get("pitch_type", []).dropna())
        total = sum(counts.values()) or 1
        mix = [
            {"pitch": pitch, "pct": round(count / total * 100, 1)}
            for pitch, count in counts.most_common(5)
        ]
        hand_values = frame["p_throws"].dropna().astype(str) if "p_throws" in frame else []
        pitcher_hand = Counter(hand_values).most_common(1)[0][0] if len(hand_values) else None
        expected = _expected_pitcher_row(pitcher_id)
        official_xera = (
            float(expected["xera"])
            if expected is not None and not math.isnan(float(expected["xera"]))
            else None
        )
        xera_proxy = max(1.5, min(7.5, 4.20 + ((xwoba or 0.320) - 0.320) * 25))
        if expected is not None:
            xba = float(expected["est_ba"])
            xwoba = float(expected["est_woba"])
            xslg = float(expected["est_slg"])
        result = {
            "available": True,
            "source": "Baseball Savant season expected stats + 60-day pitch data",
            "xera": round(official_xera, 2) if official_xera is not None else None,
            "xera_proxy": round(official_xera if official_xera is not None else xera_proxy, 2),
            "xera_is_proxy": official_xera is None,
            "era": round(float(expected["era"]), 2) if expected is not None else None,
            "xba_allowed": round(xba, 3) if xba is not None else None,
            "xwoba_allowed": round(xwoba, 3) if xwoba is not None else None,
            "xslg_allowed": round(xslg, 3) if xslg is not None else None,
            "avg_velocity": round(velo, 1) if velo is not None else None,
            "pitch_mix": mix,
            "sample_pitches": int(len(frame)),
        }
        result["pitcher_hand"] = pitcher_hand
    except Exception as exc:
        result = {**fallback, "error": str(exc)}
    _CACHE[key] = result
    return result


def _bullpen_fetch_once(team_abbr, team_id, days):

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days + 2)
    schedule = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={
            "sportId": 1,
            "teamId": team_id,
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        },
        timeout=10,
    ).json()
    recent = [
        g
        for d in schedule.get("dates", [])
        for g in d.get("games", [])
        if g.get("status", {}).get("codedGameState") == "F"
    ][-days:]
    usage = defaultdict(
        lambda: {
            "player_id": None,
            "name": "",
            "pitches": 0,
            "days_used": 0,
            "last_game_pitches": 0,
            "season_era": None,
            "season_whip": None,
        }
    )
    for index, game in enumerate(reversed(recent)):
        box = requests.get(
            f"https://statsapi.mlb.com/api/v1/game/{game['gamePk']}/boxscore", timeout=8
        ).json()
        side = "home" if game["teams"]["home"]["team"]["id"] == team_id else "away"
        team = box.get("teams", {}).get(side, {})
        pitcher_ids = team.get("pitchers", [])
        for pid in pitcher_ids[1:]:
            player = team.get("players", {}).get(f"ID{pid}", {})
            pitches = int(
                player.get("stats", {}).get("pitching", {}).get("numberOfPitches", 0) or 0
            )
            if not pitches:
                continue
            u = usage[pid]
            u["player_id"] = pid
            u["name"] = player.get("person", {}).get("fullName", str(pid))
            u["pitches"] += pitches
            u["days_used"] += 1
            season = player.get("seasonStats", {}).get("pitching", {})
            try:
                u["season_era"] = float(season.get("era"))
            except (TypeError, ValueError):
                pass
            try:
                u["season_whip"] = float(season.get("whip"))
            except (TypeError, ValueError):
                pass
            if index == 0:
                u["last_game_pitches"] = pitches
    relievers = []
    for u in usage.values():
        status = (
            "unavailable"
            if u["last_game_pitches"] >= 35 or u["pitches"] >= 55 or u["days_used"] >= 3
            else ("taxed" if u["last_game_pitches"] >= 20 or u["pitches"] >= 35 else "available")
        )
        relievers.append({**u, "status": status})
    available_quality = [
        u["season_era"]
        for u in relievers
        if u["status"] == "available" and u.get("season_era") is not None
    ]
    return {
        "available": True,
        "source": "MLB boxscores (last 3 completed games)",
        "total_pitches": sum(u["pitches"] for u in relievers),
        "unavailable_count": sum(u["status"] == "unavailable" for u in relievers),
        "taxed_count": sum(u["status"] == "taxed" for u in relievers),
        "available_recent_era": (
            round(sum(available_quality) / len(available_quality), 2) if available_quality else None
        ),
        "available_quality_count": len(available_quality),
        "relievers": sorted(relievers, key=lambda u: u["pitches"], reverse=True),
        "bullpen_fetch_status": "SUCCESS",
        "bullpen_data_source": "MLB boxscores (last 3 completed games)",
    }


BULLPEN_RETRY_ATTEMPTS = 2
BULLPEN_RETRY_BASE_DELAY = 1.0


def bullpen_availability(team_abbr, days=3):

    fallback = {
        "available": False,
        "source": "MLB boxscores",
        "total_pitches": 0,
        "unavailable_count": 0,
        "taxed_count": 0,
        "relievers": [],
        "bullpen_fetch_status": "UNKNOWN",
        "bullpen_data_source": None,
    }
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return {**fallback, "bullpen_fetch_status": "FALLBACK"}

    key = ("bullpen", team_abbr, date.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]

    last_exc, last_status = None, "UNKNOWN"
    for attempt in range(BULLPEN_RETRY_ATTEMPTS):
        try:
            result = _bullpen_fetch_once(team_abbr, team_id, days)
            _CACHE[key] = result
            return result
        except requests.exceptions.Timeout as exc:
            last_exc, last_status = exc, "TIMEOUT"
        except Exception as exc:
            last_exc, last_status = exc, "API_ERROR"
        if attempt < BULLPEN_RETRY_ATTEMPTS - 1:
            delay = BULLPEN_RETRY_BASE_DELAY * (2**attempt)
            print(
                f"  Bullpen fetch failed ({team_abbr}, attempt {attempt+1}/{BULLPEN_RETRY_ATTEMPTS}, {last_status}): {last_exc} — retrying in {delay:.1f}s"
            )
            time.sleep(delay)

    print(
        f"  Bullpen fetch FAILED ({team_abbr}) after {BULLPEN_RETRY_ATTEMPTS} attempts ({last_status}): {last_exc}"
    )
    result = {
        **fallback,
        "error": str(last_exc),
        "bullpen_fetch_status": last_status,
        "bullpen_data_source": "fallback_default",
    }

    return result


def handedness_lineup_proxy(context, away_pitcher_hand=None, home_pitcher_hand=None):

    def side(left_bats, right_bats, opposing_hand):
        known = left_bats + right_bats
        if not known or opposing_hand not in ("L", "R"):
            return {"available": False, "adjustment": 0.0}
        opposite = right_bats if opposing_hand == "L" else left_bats
        rate = opposite / known
        return {
            "available": True,
            "opposite_hand_rate": round(rate, 3),
            "adjustment": round(max(-0.015, min(0.015, (rate - 0.55) * 0.06)), 4),
            "source": "Confirmed lineup handedness composition proxy",
        }

    return {
        "home_vs_away_sp": side(
            context.get("home_left_bats", 0), context.get("home_right_bats", 0), away_pitcher_hand
        ),
        "away_vs_home_sp": side(
            context.get("away_left_bats", 0), context.get("away_right_bats", 0), home_pitcher_hand
        ),
        "is_proxy": True,
    }


def game_day_context(game_pk):
    fallback = {
        "available": False,
        "series_description": None,
        "series_game_number": None,
        "games_in_series": None,
        "double_header": None,
        "day_night": None,
        "roof_status": "unknown",
    }
    if not game_pk:
        return fallback
    key = ("game_day", game_pk, date.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]
    try:
        feed = requests.get(
            f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live", timeout=8
        ).json()
        gd = feed.get("gameData", {})
        game = gd.get("game", {})
        weather = gd.get("weather", {})
        venue = gd.get("venue", {})
        dt = gd.get("datetime", {})
        schedule = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "gamePk": game_pk},
            timeout=8,
        ).json()
        scheduled = next((g for d in schedule.get("dates", []) for g in d.get("games", [])), {})
        result = {
            "available": bool(scheduled or game or weather),
            "series_description": scheduled.get("seriesDescription"),
            "series_game_number": scheduled.get("seriesGameNumber"),
            "games_in_series": scheduled.get("gamesInSeries"),
            "double_header": scheduled.get("doubleHeader") or game.get("doubleHeader"),
            "day_night": scheduled.get("dayNight") or dt.get("dayNight"),
            "roof_status": weather.get("condition") or venue.get("roofType") or "unknown",
            "venue_id": venue.get("id") or scheduled.get("venue", {}).get("id"),
        }
    except Exception as exc:
        result = {**fallback, "error": str(exc)}
    _CACHE[key] = result
    return result


def _venue_info(venue_id):
    if not venue_id:
        return {}
    key = ("venue", venue_id)
    if key in _CACHE:
        return _CACHE[key]
    try:
        venue = (
            requests.get(f"https://statsapi.mlb.com/api/v1/venues/{venue_id}", timeout=8)
            .json()
            .get("venues", [{}])[0]
        )
        loc = venue.get("location", {})
        coords = loc.get("defaultCoordinates", {})
        tz = venue.get("timeZone", {}).get("id")
        result = {"lat": coords.get("latitude"), "lon": coords.get("longitude"), "timezone": tz}
    except Exception:
        result = {}
    _CACHE[key] = result
    return result


def team_travel_context(team_abbr, current_venue_id):
    team_id = TEAM_IDS.get(team_abbr)
    fallback = {"available": False, "miles": 0, "timezone_delta": 0}
    if not team_id or not current_venue_id:
        return fallback
    key = ("travel", team_abbr, current_venue_id, date.today().isoformat())
    if key in _CACHE:
        return _CACHE[key]
    try:
        start = date.today() - timedelta(days=7)
        schedule = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "teamId": team_id,
                "startDate": start.isoformat(),
                "endDate": (date.today() - timedelta(days=1)).isoformat(),
            },
            timeout=8,
        ).json()
        games = [
            g
            for d in schedule.get("dates", [])
            for g in d.get("games", [])
            if g.get("status", {}).get("codedGameState") == "F"
        ]
        prior_id = games[-1].get("venue", {}).get("id") if games else current_venue_id
        old = _venue_info(prior_id)
        new = _venue_info(current_venue_id)
        if None in (old.get("lat"), old.get("lon"), new.get("lat"), new.get("lon")):
            raise ValueError("coordinates unavailable")
        lat1, lon1, lat2, lon2 = map(math.radians, [old["lat"], old["lon"], new["lat"], new["lon"]])
        a = (
            math.sin((lat2 - lat1) / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        )
        miles = 3958.8 * 2 * math.asin(math.sqrt(a))
        now = datetime.now()
        old_off = (
            ZoneInfo(old["timezone"]).utcoffset(now).total_seconds() / 3600
            if old.get("timezone")
            else 0
        )
        new_off = (
            ZoneInfo(new["timezone"]).utcoffset(now).total_seconds() / 3600
            if new.get("timezone")
            else 0
        )
        result = {
            "available": True,
            "miles": round(miles),
            "timezone_delta": round(abs(new_off - old_off), 1),
            "from_venue_id": prior_id,
            "to_venue_id": current_venue_id,
        }
    except Exception as exc:
        result = {**fallback, "error": str(exc)}
    _CACHE[key] = result
    return result


def get_advanced_context(
    away_abbr,
    home_abbr,
    away_sp_id=None,
    home_sp_id=None,
    away_sp_hand=None,
    home_sp_hand=None,
    base_context=None,
    game_pk=None,
):
    base_context = base_context or {}
    home_profile = pitcher_statcast_profile(home_sp_id)
    away_profile = pitcher_statcast_profile(away_sp_id)
    away_hand = away_sp_hand or away_profile.get("pitcher_hand")
    home_hand = home_sp_hand or home_profile.get("pitcher_hand")
    day = game_day_context(game_pk)
    return {
        "home_pitcher_statcast": home_profile,
        "away_pitcher_statcast": away_profile,
        "home_bullpen": bullpen_availability(home_abbr),
        "away_bullpen": bullpen_availability(away_abbr),
        "lineup_handedness": handedness_lineup_proxy(base_context, away_hand, home_hand),
        "game_day": day,
        "home_travel": team_travel_context(home_abbr, day.get("venue_id")),
        "away_travel": team_travel_context(away_abbr, day.get("venue_id")),
    }
