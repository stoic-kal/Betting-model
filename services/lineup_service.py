from datetime import date, datetime, timedelta

import requests

from services.game_context_service import TEAM_IDS

STATS_API = "https://statsapi.mlb.com/api/v1"

_CACHE: dict = {}
_CACHE_DATE = None


def _cache_get(key):
    global _CACHE, _CACHE_DATE
    today = date.today().isoformat()
    if _CACHE_DATE != today:
        _CACHE_DATE, _CACHE = today, {}
    return _CACHE.get(key)


def _cache_set(key, value):
    _CACHE[key] = value
    return value


def _extract_lineup_from_boxscore(box, side):
    team = box.get("teams", {}).get(side, {})
    order_ids = team.get("battingOrder", [])
    players = team.get("players", {})
    lineup = []
    for pid in order_ids:
        player = players.get(f"ID{pid}", {})
        batting_order = player.get("battingOrder")
        if batting_order is None:
            continue
        if not str(batting_order).endswith("00"):
            continue
        lineup.append({
            "player_id": pid,
            "name": player.get("person", {}).get("fullName", str(pid)),
            "batting_order": int(batting_order),
        })
    lineup.sort(key=lambda p: p["batting_order"])
    return lineup


def validate_lineup_completeness(lineup):
    if len(lineup) != 9:
        return False
    ids = [p["player_id"] for p in lineup]
    if len(set(ids)) != len(ids):
        return False
    return True


def _fetch_boxscore(game_pk):
    key = ("boxscore", game_pk)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(f"{STATS_API}/game/{game_pk}/boxscore", timeout=8)
        r.raise_for_status()
        box = r.json()
    except Exception as exc:
        print(f"  Lineup boxscore fetch error (game_pk={game_pk}): {exc}")
        box = None
    return _cache_set(key, box)


def _most_recent_completed_game_pk(team_abbr, before_date=None, exclude_game_pk=None):
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return None
    end = before_date or date.today()
    start = end - timedelta(days=10)
    try:
        r = requests.get(
            f"{STATS_API}/schedule",
            params={
                "sportId": 1,
                "teamId": team_id,
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
            },
            timeout=8,
        )
        r.raise_for_status()
        schedule = r.json()
    except Exception as exc:
        print(f"  Lineup schedule fetch error ({team_abbr}): {exc}")
        return None
    completed = [
        g
        for d in schedule.get("dates", [])
        for g in d.get("games", [])
        if g.get("status", {}).get("codedGameState") == "F"
        and (exclude_game_pk is None or g.get("gamePk") != exclude_game_pk)
    ]
    if not completed:
        return None
    return completed[-1]["gamePk"]


def _side_for_team(box, team_abbr):
    team_id = TEAM_IDS.get(team_abbr)
    if team_id is None:
        return None
    for side in ("home", "away"):
        if box.get("teams", {}).get(side, {}).get("team", {}).get("id") == team_id:
            return side
    return None


def get_lineup(game_pk, team_side, team_abbr=None, reference_date=None):
    fetch_time = datetime.utcnow().isoformat() + "Z"
    result = {
        "status": "UNKNOWN",
        "lineup": [],
        "confirmed_at": None,
        "fetch_time": fetch_time,
        "missing_player_count": 9,
        "source": None,
    }

    box = _fetch_boxscore(game_pk)
    if box is not None:
        lineup = _extract_lineup_from_boxscore(box, team_side)
        if validate_lineup_completeness(lineup):
            return {
                "status": "CONFIRMED",
                "lineup": lineup,
                "confirmed_at": fetch_time,
                "fetch_time": fetch_time,
                "missing_player_count": 0,
                "source": f"MLB boxscore battingOrder (game_pk={game_pk})",
            }
        result["missing_player_count"] = max(0, 9 - len(lineup))

    if not team_abbr:
        return result

    prior_game_pk = _most_recent_completed_game_pk(
        team_abbr, before_date=reference_date, exclude_game_pk=game_pk
    )
    if prior_game_pk is None:
        return result
    prior_box = _fetch_boxscore(prior_game_pk)
    if prior_box is None:
        return result
    prior_side = _side_for_team(prior_box, team_abbr)
    if prior_side is None:
        return result
    projected = _extract_lineup_from_boxscore(prior_box, prior_side)
    if not validate_lineup_completeness(projected):
        return result

    return {
        "status": "PROJECTED",
        "lineup": projected,
        "confirmed_at": None,
        "fetch_time": fetch_time,
        "missing_player_count": 0,
        "source": f"most recent completed game boxscore (game_pk={prior_game_pk})",
    }
