from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import requests

from config import ODDS_API_KEY, today_et

API_KEY = ODDS_API_KEY

TEAM_ABBR = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Oakland Athletics": "ATH",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SD",
    "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH",
    "Athletics": "ATH",
}

ABBR_TO_FULL = {v: k for k, v in TEAM_ABBR.items()}


def _abbr(team_name: str) -> str:

    if team_name in TEAM_ABBR:
        return TEAM_ABBR[team_name]

    mascot = team_name.split()[-1]
    for full, abbr in TEAM_ABBR.items():
        if full.endswith(mascot):
            return abbr
    return team_name[:3].upper()


def _american(decimal_odds: float) -> str:
    if decimal_odds >= 2.0:
        v = int(round((decimal_odds - 1) * 100))
        return f"+{v}"
    else:
        v = int(round(-100 / (decimal_odds - 1)))
        return str(v)


def _fetch_odds(stage="current", force=False) -> dict:

    try:
        from services.odds_feed_service import fetch_odds_games

        games = fetch_odds_games(stage, force=force)
    except Exception as e:
        print(f"   TheOddsAPI error: {e}")
        return {}

    result = {}
    for g in games:
        home = g.get("home_team", "")
        away = g.get("away_team", "")
        home_ml, away_ml, totals = [], [], {}

        for book in g.get("books", []):
            mkt = book.get("market")
            if mkt == "h2h":
                for o in book.get("outcomes", []):
                    p = o.get("price")
                    if p:
                        if o.get("name") == home:
                            home_ml.append(float(p))
                        else:
                            away_ml.append(float(p))
            elif mkt == "totals":
                for o in book.get("outcomes", []):
                    pt, p, n = o.get("point"), o.get("price"), o.get("name")
                    if pt and p and n:
                        ln = float(pt)
                        totals.setdefault(ln, {"over": [], "under": []})
                        if n == "Over":
                            totals[ln]["over"].append(float(p))
                        else:
                            totals[ln]["under"].append(float(p))

        main_line = None
        if totals:
            main_line = max(totals, key=lambda l: len(totals[l]["over"]))

        result[frozenset([home.lower(), away.lower()])] = {
            "event_id": g.get("event_id", ""),
            "home_full": home,
            "away_full": away,
            "home_ml_list": home_ml,
            "away_ml_list": away_ml,
            "home_ml_avg": _american(np.mean(home_ml)) if home_ml else "N/A",
            "away_ml_avg": _american(np.mean(away_ml)) if away_ml else "N/A",
            "home_ml_dec": float(np.mean(home_ml)) if home_ml else None,
            "away_ml_dec": float(np.mean(away_ml)) if away_ml else None,
            "total_line": main_line,
            "totals": totals,
        }
    return result


def _fetch_pitcher_stats(player_id: int) -> dict:

    fallback = {"era": None, "whip": None, "k9": None, "fip": None, "ip": None}
    if not player_id:
        return fallback
    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
            params={"stats": "season", "season": datetime.now().year, "group": "pitching"},
            timeout=8,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return fallback
        s = splits[0].get("stat", {})
        ip = float(s.get("inningsPitched", 1) or 1)
        so = float(s.get("strikeOuts", 0) or 0)
        bb = float(s.get("baseOnBalls", 0) or 0)
        hr = float(s.get("homeRunsAllowed", 0) or 0)
        era = float(s.get("era", 0) or 0)
        whip = float(s.get("whip", 0) or 0)
        k9 = float(s.get("strikeoutsPer9Inn", 0) or 0)
        fip = (13 * hr + 3 * bb - 2 * so) / max(ip, 0.1) + 3.10
        return {
            "era": round(era, 2),
            "whip": round(whip, 2),
            "k9": round(k9, 2),
            "fip": round(fip, 2),
            "ip": round(ip, 1),
            "so": int(so),
        }
    except Exception as e:
        print(f"   Pitcher stats error (id={player_id}): {e}")
        return fallback


def get_today_games(date_str: str = None, include_odds: bool = True) -> list:

    if date_str is None:
        date_str = today_et()

    try:
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "date": date_str,
                "hydrate": "probablePitcher,team,linescore",
            },
            timeout=10,
        )
        dates = r.json().get("dates", [])
    except Exception as e:
        print(f"   MLB API error: {e}")
        return []

    raw_games = []
    for date_block in dates:
        for g in date_block.get("games", []):
            home_info = g["teams"]["home"]
            away_info = g["teams"]["away"]
            home_name = home_info["team"].get("name", "")
            away_name = away_info["team"].get("name", "")

            home_wins = home_info.get("leagueRecord", {}).get("wins", "?")
            home_losses = home_info.get("leagueRecord", {}).get("losses", "?")
            away_wins = away_info.get("leagueRecord", {}).get("wins", "?")
            away_losses = away_info.get("leagueRecord", {}).get("losses", "?")

            game_dt = g.get("gameDate", "")
            time_str = ""
            if game_dt:
                try:
                    from datetime import timezone

                    dt = datetime.strptime(game_dt, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=timezone.utc
                    )
                    dt_et = dt.astimezone(ZoneInfo("America/New_York"))
                    time_str = dt_et.strftime("%-I:%M %p ET")
                except Exception:
                    time_str = game_dt[11:16] + " UTC"

            home_sp = home_info.get("probablePitcher", {})
            away_sp = away_info.get("probablePitcher", {})

            home_abbr = _abbr(home_name)
            away_abbr = _abbr(away_name)
            slug = f"{away_abbr}-vs-{home_abbr}"

            raw_games.append(
                {
                    "game_pk": g.get("gamePk"),
                    "slug": slug,
                    "away": away_name,
                    "home": home_name,
                    "away_team_id": away_info.get("team", {}).get("id"),
                    "home_team_id": home_info.get("team", {}).get("id"),
                    "away_abbr": away_abbr,
                    "home_abbr": home_abbr,
                    "away_record": f"{away_wins}-{away_losses}",
                    "home_record": f"{home_wins}-{home_losses}",
                    "venue": g.get("venue", {}).get("name", "TBD"),
                    "time": time_str or "TBD",
                    "status": g.get("status", {}).get("detailedState", ""),
                    "game_state": g.get("status", {}).get("abstractGameState", ""),
                    "away_score": away_info.get("score"),
                    "home_score": home_info.get("score"),
                    "game_date_utc": game_dt,
                    "series_description": g.get("seriesDescription", ""),
                    "series_game_number": g.get("seriesGameNumber"),
                    "games_in_series": g.get("gamesInSeries"),
                    "double_header": g.get("doubleHeader", "N"),
                    "day_night": g.get("dayNight", ""),
                    "away_sp_name": away_sp.get("fullName", "TBD"),
                    "away_sp_id": away_sp.get("id"),
                    "away_sp_hand": away_sp.get("pitchHand", {}).get("code", "?"),
                    "home_sp_name": home_sp.get("fullName", "TBD"),
                    "home_sp_id": home_sp.get("id"),
                    "home_sp_hand": home_sp.get("pitchHand", {}).get("code", "?"),
                    "odds": None,
                }
            )

    odds_map = _fetch_odds() if include_odds else {}
    for game in raw_games:
        key = frozenset([game["home"].lower(), game["away"].lower()])
        if key in odds_map:
            game["odds"] = odds_map[key]
        else:

            for k, v in odds_map.items():
                if (
                    _abbr(v["home_full"]) == game["home_abbr"]
                    and _abbr(v["away_full"]) == game["away_abbr"]
                ):
                    game["odds"] = v
                    break

    return raw_games


def get_live_state(date_str: str = None) -> list:

    date_str = date_str or today_et()
    r = requests.get(
        "https://statsapi.mlb.com/api/v1/schedule",
        params={"sportId": 1, "date": date_str, "hydrate": "linescore"},
        timeout=10,
    )
    r.raise_for_status()
    games = []
    for block in r.json().get("dates", []):
        for game in block.get("games", []):
            away = game["teams"]["away"]
            home = game["teams"]["home"]
            games.append(
                {
                    "game_pk": game.get("gamePk"),
                    "matchup": f"{away['team'].get('name','')} @ {home['team'].get('name','')}",
                    "away_score": away.get("score"),
                    "home_score": home.get("score"),
                    "status": game.get("status", {}).get("detailedState", ""),
                    "game_state": game.get("status", {}).get("abstractGameState", ""),
                    "game_date_utc": game.get("gameDate", ""),
                }
            )
    return games


def get_game_detail(away_abbr: str, home_abbr: str, date_str: str = None) -> dict:

    games = get_today_games(date_str)
    game = next(
        (g for g in games if g["away_abbr"] == away_abbr and g["home_abbr"] == home_abbr), None
    )
    if not game:
        return {}

    game["home_sp_stats"] = _fetch_pitcher_stats(game.get("home_sp_id"))
    game["away_sp_stats"] = _fetch_pitcher_stats(game.get("away_sp_id"))

    return game
