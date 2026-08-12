from datetime import date, datetime, timedelta, timezone

import requests

TEAM_IDS = {
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHC": 112,
    "CWS": 145,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "HOU": 117,
    "KC": 118,
    "LAA": 108,
    "LAD": 119,
    "MIA": 146,
    "MIL": 158,
    "MIN": 142,
    "NYM": 121,
    "NYY": 147,
    "ATH": 133,
    "PHI": 143,
    "PIT": 134,
    "SD": 135,
    "SF": 137,
    "SEA": 136,
    "STL": 138,
    "TB": 139,
    "TEX": 140,
    "TOR": 141,
    "WSH": 120,
}

LEAGUE_OPS = 0.720
LEAGUE_FIELDING_PCT = 0.985
_cache = {}
_cache_date = None


def _cached(key, loader, fallback, ttl_seconds=None):
    global _cache_date, _cache
    today = date.today().isoformat()
    if _cache_date != today:
        _cache_date, _cache = today, {}
    cached = _cache.get(key)
    if cached is not None:
        value, stored_at = cached if isinstance(cached, tuple) else (cached, None)
        if ttl_seconds is None or (
            stored_at and (datetime.now(timezone.utc) - stored_at).total_seconds() < ttl_seconds
        ):
            return value
    if cached is None or ttl_seconds is not None:
        try:
            value = loader()
        except Exception as exc:
            print(f"  Context fetch failed ({key}): {exc}")
            value = fallback
        _cache[key] = (value, datetime.now(timezone.utc))
    return _cache[key][0]


def _team_recent_context(team_abbr):
    team_id = TEAM_IDS.get(team_abbr)
    fallback = {"rest_days": 1, "games_last_3": 0, "travel_timezone_delta": 0}
    if not team_id:
        return fallback

    def load():
        today = date.today()
        response = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "teamId": team_id,
                "startDate": (today - timedelta(days=7)).isoformat(),
                "endDate": (today - timedelta(days=1)).isoformat(),
            },
            timeout=8,
        )
        completed = []
        for block in response.json().get("dates", []):
            for game in block.get("games", []):
                if game.get("status", {}).get("codedGameState") == "F":
                    completed.append(game)
        if not completed:
            return fallback
        last_date = datetime.fromisoformat(completed[-1]["officialDate"]).date()
        rest_days = max((today - last_date).days - 1, 0)
        cutoff = today - timedelta(days=3)
        games_last_3 = sum(
            datetime.fromisoformat(g["officialDate"]).date() >= cutoff for g in completed
        )
        return {
            "rest_days": min(rest_days, 3),
            "games_last_3": games_last_3,
            "travel_timezone_delta": 0,
        }

    return _cached(f"recent_{team_abbr}", load, fallback)


def _team_fielding_pct(team_abbr):
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return LEAGUE_FIELDING_PCT

    def load():
        response = requests.get(
            f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats",
            params={
                "stats": "season",
                "season": date.today().year,
                "group": "fielding",
                "gameType": "R",
            },
            timeout=8,
        )
        splits = response.json().get("stats", [{}])[0].get("splits", [])
        value = splits[0].get("stat", {}).get("fielding") if splits else None
        return float(value) if value else LEAGUE_FIELDING_PCT

    return _cached(f"fielding_{team_abbr}", load, LEAGUE_FIELDING_PCT)


def _lineup_context(game_pk, side, force=False):
    fallback = {"confirmed": False, "count": 0, "ops": LEAGUE_OPS, "left_bats": 0, "right_bats": 0}
    if not game_pk:
        return fallback

    def load():

        response = requests.get(
            f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live", timeout=8
        )
        response.raise_for_status()
        payload = response.json()
        team = payload.get("liveData", {}).get("boxscore", {}).get("teams", {}).get(side, {})
        player_directory = payload.get("gameData", {}).get("players", {})
        players = team.get("players", {})
        starters = []
        left, right = 0, 0
        for player in players.values():
            order = player.get("battingOrder")
            if not order or str(order).startswith("0"):
                continue
            starters.append(player)
            person = player.get("person", {})
            person_id = person.get("id")
            full_person = player_directory.get(f"ID{person_id}", {})
            bat_side = full_person.get("batSide", {}).get("code") or person.get("batSide", {}).get(
                "code"
            )
            if bat_side == "L":
                left += 1
            elif bat_side == "R":
                right += 1
        ops_values = []
        for player in starters:
            value = player.get("seasonStats", {}).get("batting", {}).get("ops")
            try:
                ops_values.append(float(value))
            except (TypeError, ValueError):
                pass
        return {
            "confirmed": len(starters) >= 9,
            "count": len(starters),
            "ops": sum(ops_values) / len(ops_values) if ops_values else LEAGUE_OPS,
            "left_bats": left,
            "right_bats": right,
        }

    key = f"lineup_{game_pk}_{side}"
    if force:
        _cache.pop(key, None)

    result = _cached(key, load, fallback, ttl_seconds=120)
    if not result.get("confirmed"):

        stored = _cache.get(key)
        if stored:
            _cache[key] = (stored[0], datetime.now(timezone.utc) - timedelta(seconds=91))
    return result


def get_lineup_status(game_pk, force=False):

    home = _lineup_context(game_pk, "home", force=force)
    away = _lineup_context(game_pk, "away", force=force)
    return {
        "confirmed": home["confirmed"] and away["confirmed"],
        "home_confirmed": home["confirmed"],
        "away_confirmed": away["confirmed"],
        "home_count": home["count"],
        "away_count": away["count"],
    }


def get_game_context(away_abbr, home_abbr, game_pk=None, away_sp_id=None, home_sp_id=None):

    home_recent = _team_recent_context(home_abbr)
    away_recent = _team_recent_context(away_abbr)
    home_lineup = _lineup_context(game_pk, "home")
    away_lineup = _lineup_context(game_pk, "away")
    home_fielding = _team_fielding_pct(home_abbr)
    away_fielding = _team_fielding_pct(away_abbr)

    home_fatigue = home_recent["games_last_3"] - 1
    away_fatigue = away_recent["games_last_3"] - 1
    result = {
        "home_lineup_confirmed": home_lineup["confirmed"],
        "away_lineup_confirmed": away_lineup["confirmed"],
        "home_lineup_count": home_lineup["count"],
        "away_lineup_count": away_lineup["count"],
        "home_lineup_ops": round(home_lineup["ops"], 3),
        "away_lineup_ops": round(away_lineup["ops"], 3),
        "lineup_ops_adv": round(home_lineup["ops"] - away_lineup["ops"], 3),
        "home_left_bats": home_lineup["left_bats"],
        "home_right_bats": home_lineup["right_bats"],
        "away_left_bats": away_lineup["left_bats"],
        "away_right_bats": away_lineup["right_bats"],
        "home_rest_days": home_recent["rest_days"],
        "away_rest_days": away_recent["rest_days"],
        "rest_adv": home_recent["rest_days"] - away_recent["rest_days"],
        "home_games_last_3": home_recent["games_last_3"],
        "away_games_last_3": away_recent["games_last_3"],
        "home_bullpen_fatigue": home_fatigue,
        "away_bullpen_fatigue": away_fatigue,
        "bullpen_fatigue_adv": away_fatigue - home_fatigue,
        "home_fielding_pct": round(home_fielding, 4),
        "away_fielding_pct": round(away_fielding, 4),
        "defense_adv": round((home_fielding - away_fielding) * 100, 3),
        "travel_timezone_adv": 0,
        "travel_context_available": False,
        "context_complete": home_lineup["confirmed"] and away_lineup["confirmed"],
    }
    from services.advanced_context_service import get_advanced_context

    advanced = get_advanced_context(
        away_abbr, home_abbr, away_sp_id, home_sp_id, base_context=result, game_pk=game_pk
    )
    result["advanced"] = advanced
    home_bp = advanced["home_bullpen"]
    away_bp = advanced["away_bullpen"]
    result["home_bullpen_pitches_3d"] = (
        home_bp.get("total_pitches") if home_bp.get("available") else None
    )
    result["away_bullpen_pitches_3d"] = (
        away_bp.get("total_pitches") if away_bp.get("available") else None
    )
    result["home_unavailable_relievers"] = (
        home_bp.get("unavailable_count") if home_bp.get("available") else None
    )
    result["away_unavailable_relievers"] = (
        away_bp.get("unavailable_count") if away_bp.get("available") else None
    )
    result["home_available_recent_reliever_era"] = home_bp.get("available_recent_era")
    result["away_available_recent_reliever_era"] = away_bp.get("available_recent_era")
    result["home_available_reliever_quality_count"] = home_bp.get("available_quality_count", 0)
    result["away_available_reliever_quality_count"] = away_bp.get("available_quality_count", 0)
    result["home_bullpen_fetch_status"] = home_bp.get("bullpen_fetch_status", "UNKNOWN")
    result["away_bullpen_fetch_status"] = away_bp.get("bullpen_fetch_status", "UNKNOWN")
    result["home_bullpen_data_source"] = home_bp.get("bullpen_data_source")
    result["away_bullpen_data_source"] = away_bp.get("bullpen_data_source")
    if home_bp.get("available") and away_bp.get("available"):
        home_burden = home_bp["total_pitches"] / 80 + home_bp["unavailable_count"]
        away_burden = away_bp["total_pitches"] / 80 + away_bp["unavailable_count"]
        result["bullpen_fatigue_adv"] = round(away_burden - home_burden, 3)
        result["home_bullpen_fatigue"] = round(home_burden, 3)
        result["away_bullpen_fatigue"] = round(away_burden, 3)
        result["bullpen_workload_source"] = "MLB reliever pitch counts"
    else:
        result["bullpen_workload_source"] = "games-in-3-days proxy"
    home_travel = advanced.get("home_travel", {})
    away_travel = advanced.get("away_travel", {})
    if home_travel.get("available") and away_travel.get("available"):
        result["travel_context_available"] = True
        result["home_travel_miles"] = home_travel["miles"]
        result["away_travel_miles"] = away_travel["miles"]
        result["travel_timezone_adv"] = round(
            away_travel["timezone_delta"] - home_travel["timezone_delta"], 1
        )
    return result
