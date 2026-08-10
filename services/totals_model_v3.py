from datetime import date, datetime

import numpy as np
import requests
from scipy.stats import poisson

LEAGUE_AVG_FIP = 3.90
LEAGUE_AVG_RSG = 4.60
SP_FIP_EXPONENT = 0.75


PARK_FACTORS = {
    "COL": 1.22,
    "BOS": 1.08,
    "CIN": 1.07,
    "CHC": 1.06,
    "PHI": 1.05,
    "ARI": 1.04,
    "BAL": 1.03,
    "CWS": 1.02,
    "HOU": 1.02,
    "NYY": 1.02,
    "MIN": 1.00,
    "NYM": 1.00,
    "TOR": 1.00,
    "MIL": 0.99,
    "ATL": 0.99,
    "KC": 0.99,
    "STL": 0.98,
    "TEX": 0.98,
    "WSH": 0.98,
    "LAA": 0.97,
    "DET": 0.97,
    "CLE": 0.97,
    "ATH": 0.97,
    "TB": 0.97,
    "LAD": 0.97,
    "PIT": 0.95,
    "SEA": 0.95,
    "MIA": 0.94,
    "SD": 0.94,
    "SF": 0.93,
}


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


UMPIRE_RUNS_ADJ: dict[str, float] = {
    "CB Bucknor": +0.45,
    "Angel Hernandez": +0.40,
    "Laz Diaz": +0.35,
    "Ron Kulpa": +0.30,
    "Hunter Wendelstedt": +0.25,
    "Vic Carapazza": +0.22,
    "Adrian Johnson": +0.20,
    "Roberto Ortiz": +0.18,
    "Brian Knight": +0.15,
    "Chad Whitson": +0.14,
    "Jeremie Rehak": +0.13,
    "Alex Tosi": +0.12,
    "Pat Hoberg": +0.10,
    "Ryan Additon": +0.10,
    "Chris Guccione": +0.08,
    "Marvin Hudson": +0.07,
    "Jim Reynolds": 0.00,
    "Fieldin Culbreth": 0.00,
    "Jeff Nelson": -0.02,
    "Bill Miller": -0.03,
    "Mike Winters": -0.04,
    "Tom Hallion": -0.05,
    "John Hirschbeck": -0.05,
    "Mark Wegner": -0.06,
    "Alan Porter": -0.07,
    "Phil Cuzzi": -0.08,
    "Greg Gibson": -0.09,
    "Mark Carlson": -0.10,
    "Jim Wolf": -0.12,
    "Ted Barrett": -0.13,
    "James Hoye": -0.15,
    "Stu Scheurwater": -0.16,
    "Dan Bellino": -0.40,
    "Todd Tichenor": -0.30,
    "Ben May": -0.22,
    "Mike Muchlinski": -0.20,
    "David Rackley": -0.18,
    "Nick Mahrley": -0.17,
    "Mike Estabrook": -0.17,
    "Larry Vanover": -0.14,
}


_cache_date: str = ""
_fip_cache: dict = {}
_rsg_cache: dict = {}


def _maybe_clear_cache():

    global _cache_date, _fip_cache, _rsg_cache
    today = date.today().isoformat()
    if today != _cache_date:
        _fip_cache = {}
        _rsg_cache = {}
        _cache_date = today


def _fetch_home_plate_umpire(game_pk) -> tuple[str, float]:

    if not game_pk:
        return ("Unknown", 0.0)

    _maybe_clear_cache()
    cache_key = f"ump_{game_pk}"
    if cache_key in _rsg_cache:
        return _rsg_cache[cache_key]

    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore",
            timeout=8,
        )
        officials = r.json().get("officials", [])
        hp_name = None
        for official in officials:
            role = official.get("officialType", "")
            if "Home Plate" in role or role == "HP":
                hp_name = official.get("official", {}).get("fullName", "")
                break
        if not hp_name:
            _rsg_cache[cache_key] = ("Unknown", 0.0)
            return ("Unknown", 0.0)

        adj = UMPIRE_RUNS_ADJ.get(hp_name, 0.0)
        print(f"     HP Umpire: {hp_name} → runs adj {adj:+.2f}")
        result = (hp_name, adj)
        _rsg_cache[cache_key] = result
        return result

    except Exception as e:
        print(f"     Umpire fetch error (game_pk={game_pk}): {e}")
        _rsg_cache[cache_key] = ("Unknown", 0.0)
        return ("Unknown", 0.0)


def _fetch_pitcher_fip(pitcher_id) -> float:

    _maybe_clear_cache()
    if pitcher_id is None:
        return LEAGUE_AVG_FIP
    if pitcher_id in _fip_cache:
        return _fip_cache[pitcher_id]

    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats",
            params={
                "stats": "season",
                "season": datetime.now().year,
                "group": "pitching",
            },
            timeout=8,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            _fip_cache[pitcher_id] = LEAGUE_AVG_FIP
            return LEAGUE_AVG_FIP
        s = splits[0].get("stat", {})

        ip = _baseball_innings(s.get("inningsPitched", 0))
        hr = float(s.get("homeRunsAllowed", 0) or 0)
        bb = float(s.get("baseOnBalls", 0) or 0)
        so = float(s.get("strikeOuts", 0) or 0)
        if ip < 20:

            _fip_cache[pitcher_id] = LEAGUE_AVG_FIP
            return LEAGUE_AVG_FIP

        fip = (13 * hr + 3 * bb - 2 * so) / max(ip, 0.1) + 3.10
        fip = float(np.clip(fip, 2.00, 6.50))
        print(f"    FIP fetched: pitcher {pitcher_id} → {fip:.2f} ({ip:.0f} IP)")
    except Exception as e:
        print(f"     FIP fetch error (id={pitcher_id}): {e}")
        fip = LEAGUE_AVG_FIP

    _fip_cache[pitcher_id] = fip
    return fip


def _baseball_innings(value):

    text = str(value or "0")
    whole, _, outs = text.partition(".")
    return float(whole or 0) + min(int(outs or 0), 2) / 3


def _fetch_expected_starter_usage(pitcher_id):

    fallback = {
        "available": False,
        "expected_innings": 5.5,
        "expected_bullpen_innings": 3.5,
        "avg_pitches": None,
        "role": "typical",
        "starts_used": 0,
        "source": "5.5-inning fallback",
    }
    if not pitcher_id:
        return fallback
    _maybe_clear_cache()
    key = ("starter_usage", pitcher_id)
    if key in _rsg_cache:
        return _rsg_cache[key]
    try:
        response = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats",
            params={
                "stats": "gameLog",
                "group": "pitching",
                "season": datetime.now().year,
                "gameType": "R",
            },
            timeout=8,
        )
        starts = []
        for split in response.json().get("stats", [{}])[0].get("splits", []):
            stat = split.get("stat", {})
            if int(stat.get("gamesStarted", 0) or 0) < 1:
                continue
            innings = _baseball_innings(stat.get("inningsPitched"))
            pitches = stat.get("numberOfPitches")
            starts.append(
                {
                    "date": split.get("date") or "",
                    "innings": innings,
                    "pitches": float(pitches) if pitches not in (None, "") else None,
                }
            )

        starts = sorted(starts, key=lambda item: item["date"])[-5:]
        if len(starts) < 2:
            _rsg_cache[key] = fallback
            return fallback
        weights = list(range(1, len(starts) + 1))
        expected = sum(s["innings"] * w for s, w in zip(starts, weights)) / sum(weights)
        pitch_values = [s["pitches"] for s in starts if s["pitches"] is not None]
        avg_pitches = sum(pitch_values) / len(pitch_values) if pitch_values else None
        expected = float(np.clip(expected, 1.0, 7.0))
        if expected < 3.0:
            role = "opener"
        elif expected < 4.5 or (avg_pitches is not None and avg_pitches < 72):
            role = "limited"
        elif expected >= 6.2 and (avg_pitches or 0) >= 90:
            role = "workhorse"
        else:
            role = "typical"
        result = {
            "available": True,
            "expected_innings": round(expected, 2),
            "expected_bullpen_innings": round(9 - expected, 2),
            "avg_pitches": round(avg_pitches, 1) if avg_pitches is not None else None,
            "role": role,
            "starts_used": len(starts),
            "source": "MLB last-five-start weighted usage",
        }
    except Exception as exc:
        print(f"     Starter usage fetch error (id={pitcher_id}): {exc}")
        result = fallback
    _rsg_cache[key] = result
    return result


def _fetch_team_l10_rsg(team_abbr: str, venue: str = "all") -> float:

    _maybe_clear_cache()
    cache_key = f"{team_abbr}_l10_{venue}"
    if cache_key in _rsg_cache:
        return _rsg_cache[cache_key]

    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return None

    try:
        from datetime import timedelta

        today = date.today()

        lookback = 40 if venue != "all" else 25
        start_dt = (today - timedelta(days=lookback)).strftime("%Y-%m-%d")
        end_dt = today.strftime("%Y-%m-%d")

        r = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={
                "sportId": 1,
                "teamId": team_id,
                "season": today.year,
                "gameType": "R",
                "startDate": start_dt,
                "endDate": end_dt,
            },
            timeout=10,
        )
        runs = []
        for date_block in r.json().get("dates", []):
            for g in date_block.get("games", []):
                state = g.get("status", {}).get("codedGameState", "")
                if state != "F":
                    continue
                home_id = g["teams"]["home"]["team"].get("id")
                home_score = g["teams"]["home"].get("score")
                away_score = g["teams"]["away"].get("score")
                if home_score is None or away_score is None:
                    continue
                is_home = home_id == team_id

                if venue == "home" and not is_home:
                    continue
                if venue == "away" and is_home:
                    continue
                runs.append(int(home_score) if is_home else int(away_score))

        recent = runs[-10:]
        if len(recent) < 5:
            _rsg_cache[cache_key] = None
            return None

        l10 = float(np.clip(np.mean(recent), 2.0, 8.0))
        print(f"    L10 RS/G ({team_abbr} {venue}): {l10:.2f} over {len(recent)} games")
        _rsg_cache[cache_key] = l10
        return l10

    except Exception as e:
        print(f"     L10 RS/G fetch error ({team_abbr}): {e}")
        _rsg_cache[cache_key] = None
        return None


def _fetch_team_bullpen_era(team_abbr: str) -> float:

    LEAGUE_AVG_BULLPEN_ERA = 4.20
    SP_INNINGS_FRAC = 5.5 / 9.0
    BP_INNINGS_FRAC = 3.5 / 9.0

    _maybe_clear_cache()
    cache_key = f"{team_abbr}_bp_era"
    if cache_key in _rsg_cache:
        return _rsg_cache[cache_key]

    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return LEAGUE_AVG_BULLPEN_ERA

    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats",
            params={
                "stats": "season",
                "season": datetime.now().year,
                "group": "pitching",
                "gameType": "R",
            },
            timeout=8,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            _rsg_cache[cache_key] = LEAGUE_AVG_BULLPEN_ERA
            return LEAGUE_AVG_BULLPEN_ERA
        s = splits[0].get("stat", {})
        team_era = float(s.get("era", 0) or 0)
        if team_era < 0.5 or team_era > 8.0:
            _rsg_cache[cache_key] = LEAGUE_AVG_BULLPEN_ERA
            return LEAGUE_AVG_BULLPEN_ERA

        LEAGUE_SP_ERA = LEAGUE_AVG_FIP
        bp_era = (team_era - SP_INNINGS_FRAC * LEAGUE_SP_ERA) / BP_INNINGS_FRAC
        bp_era = float(np.clip(bp_era, 2.50, 6.50))
        print(f"    Bullpen ERA ({team_abbr}): {bp_era:.2f} (team ERA {team_era:.2f})")
        _rsg_cache[cache_key] = bp_era
        return bp_era

    except Exception as e:
        print(f"     Bullpen ERA fetch error ({team_abbr}): {e}")
        _rsg_cache[cache_key] = LEAGUE_AVG_BULLPEN_ERA
        return LEAGUE_AVG_BULLPEN_ERA


def _fetch_weather(venue_city: str, home_abbr: str, game_pk=None) -> dict:

    if game_pk:
        try:
            game_feed = requests.get(
                f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live",
                timeout=6,
            ).json()
            condition = str(
                game_feed.get("gameData", {}).get("weather", {}).get("condition", "")
            ).lower()
            if any(label in condition for label in ("roof closed", "dome", "indoor")):
                return {
                    "temp_f": 72,
                    "wind_mph": 0,
                    "wind_dir": "roof closed",
                    "dome": True,
                    "roof_status": condition,
                    "weather_factor": 1.0,
                    "weather_source": "dome",
                }
        except Exception as e:
            print(f"     Roof status unavailable ({home_abbr}): {e}")

    _maybe_clear_cache()
    cache_key = f"weather_{home_abbr}"
    if cache_key in _rsg_cache:
        return _rsg_cache[cache_key]

    TEAM_CITIES = {
        "ARI": "Phoenix",
        "ATL": "Atlanta",
        "BAL": "Baltimore",
        "BOS": "Boston",
        "CHC": "Chicago",
        "CWS": "Chicago",
        "CIN": "Cincinnati",
        "CLE": "Cleveland",
        "COL": "Denver",
        "DET": "Detroit",
        "HOU": "Houston",
        "KC": "Kansas+City",
        "LAA": "Anaheim",
        "LAD": "Los+Angeles",
        "MIA": "Miami",
        "MIL": "Milwaukee",
        "MIN": "Minneapolis",
        "NYM": "New+York",
        "NYY": "New+York",
        "ATH": "Oakland",
        "PHI": "Philadelphia",
        "PIT": "Pittsburgh",
        "SD": "San+Diego",
        "SF": "San+Francisco",
        "SEA": "Seattle",
        "STL": "St+Louis",
        "TB": "St+Petersburg",
        "TEX": "Arlington",
        "TOR": "Toronto",
        "WSH": "Washington",
    }
    city = TEAM_CITIES.get(home_abbr, venue_city or "New+York")

    try:
        r = requests.get(
            f"https://wttr.in/{city}",
            params={"format": "j1"},
            timeout=6,
        )
        data = r.json()
        current = data["current_condition"][0]
        temp_f = float(current.get("temp_F", 72))
        wind_mph = float(current.get("windspeedMiles", 5))
        wind_dir = current.get("winddir16Point", "N")

        if temp_f < 45:
            temp_factor = 0.92
        elif temp_f < 55:
            temp_factor = 0.96
        elif temp_f > 85:
            temp_factor = 1.03
        else:
            temp_factor = 1.00

        OUT_DIRS = {"S", "SW", "SSW", "WSW", "SE", "SSE", "ESE"}
        IN_DIRS = {"N", "NW", "NNW", "WNW", "NE", "NNE", "ENE"}
        WIND_GATE_MPH = 8
        if wind_dir in OUT_DIRS and wind_mph >= WIND_GATE_MPH:
            wind_factor = 1.0 + min((wind_mph - WIND_GATE_MPH + 4) / 100, 0.10)
        elif wind_dir in IN_DIRS and wind_mph >= WIND_GATE_MPH:
            wind_factor = 1.0 - min((wind_mph - WIND_GATE_MPH + 4) / 100, 0.08)
        else:
            wind_factor = 1.00

        weather_factor = temp_factor * wind_factor
        result = {
            "temp_f": round(temp_f, 1),
            "wind_mph": round(wind_mph, 1),
            "wind_dir": wind_dir,
            "dome": False,
            "roof_status": "open/outdoor or unconfirmed",
            "weather_factor": round(weather_factor, 4),
            "weather_source": "wttr.in",
        }
        print(
            f"     Weather ({home_abbr}): {temp_f:.0f}°F, wind {wind_mph:.0f}mph {wind_dir} → factor {weather_factor:.3f}"
        )
        _rsg_cache[cache_key] = result
        return result

    except Exception as e:

        reason = str(e)
        print(
            f"     Weather fetch FAILED ({home_abbr}) — using neutral fallback, NOT real data: {reason}"
        )
        result = {
            "temp_f": 72,
            "wind_mph": 5,
            "wind_dir": "calm",
            "dome": False,
            "roof_status": "unknown",
            "weather_factor": 1.0,
            "weather_source": "fallback_default",
            "weather_error": reason,
        }
        _rsg_cache[cache_key] = result
        return result


def _fetch_team_rsg(team_abbr: str, venue: str = "all") -> float:

    _maybe_clear_cache()
    cache_key = f"{team_abbr}_season"
    if cache_key in _rsg_cache:
        season_rsg = _rsg_cache[cache_key]
    else:
        team_id = TEAM_IDS.get(team_abbr)
        if not team_id:
            return LEAGUE_AVG_RSG
        try:
            r = requests.get(
                f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats",
                params={
                    "stats": "season",
                    "season": datetime.now().year,
                    "group": "hitting",
                    "gameType": "R",
                },
                timeout=8,
            )
            splits = r.json().get("stats", [{}])[0].get("splits", [])
            if not splits:
                _rsg_cache[cache_key] = LEAGUE_AVG_RSG
                return LEAGUE_AVG_RSG
            s = splits[0].get("stat", {})
            runs_scored = float(s.get("runs", 0) or 0)
            games_played = float(s.get("gamesPlayed", 1) or 1)
            if games_played < 5:
                _rsg_cache[cache_key] = LEAGUE_AVG_RSG
                return LEAGUE_AVG_RSG
            season_rsg = float(np.clip(runs_scored / games_played, 2.5, 7.5))
            print(f"    Season RS/G ({team_abbr}): {season_rsg:.2f} ({int(games_played)} G)")
        except Exception as e:
            print(f"     RS/G fetch error ({team_abbr}): {e}")
            season_rsg = LEAGUE_AVG_RSG
        _rsg_cache[cache_key] = season_rsg

    l10_venue = _fetch_team_l10_rsg(team_abbr, venue) if venue != "all" else None
    l10_all = _fetch_team_l10_rsg(team_abbr, "all")

    if l10_venue is not None and l10_all is not None:
        blended = 0.50 * season_rsg + 0.30 * l10_venue + 0.20 * l10_all
    elif l10_all is not None:
        blended = 0.60 * season_rsg + 0.40 * l10_all
    else:
        blended = season_rsg

    blended = float(np.clip(blended, 2.5, 7.5))
    print(f"    RS/G ({team_abbr}/{venue}): {blended:.2f}")
    return blended


def kelly_units(
    model_prob: float, decimal_odds: float, kelly_fraction: float = 0.5, max_units: float = 1.0
) -> float:

    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    p = model_prob
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    half_kelly = full_kelly * kelly_fraction
    if half_kelly <= 0:
        return 0.0
    if half_kelly < 0.05:
        return min(0.25, max_units)
    if half_kelly < 0.10:
        return min(0.50, max_units)
    return min(1.00, max_units)


def poisson_side_probs(expected_total: float, line: float) -> tuple[float, float]:

    k = int(np.floor(line))
    over = float(1.0 - poisson.cdf(k, expected_total))
    if float(line).is_integer():
        under = float(poisson.cdf(k - 1, expected_total))
        actionable = over + under
        if actionable > 0:
            over /= actionable
            under /= actionable
    else:
        under = float(poisson.cdf(k, expected_total))
    over = float(np.clip(over, 0.05, 0.95))
    under = float(np.clip(under, 0.05, 0.95))
    total = over + under
    return over / total, under / total


def poisson_over_prob(expected_total: float, line: float) -> float:

    return poisson_side_probs(expected_total, line)[0]


def compute_totals_pick(
    away_abbr: str,
    home_abbr: str,
    away_sp_id,
    home_sp_id,
    market_line: float,
    over_odds_list: list,
    under_odds_list: list,
    n_books: int,
    venue_city: str = "",
    game_pk=None,
) -> dict:

    MIN_BOOKS = 6
    limited_market_warning = (
        f"Only {n_books} books (prefer {MIN_BOOKS}+)" if n_books < MIN_BOOKS else None
    )

    print(f"\n  Totals model v3: {away_abbr} @ {home_abbr} | line={market_line}")

    home_fip = _fetch_pitcher_fip(home_sp_id)
    away_fip = _fetch_pitcher_fip(away_sp_id)

    home_rsg = _fetch_team_rsg(home_abbr, venue="home")
    away_rsg = _fetch_team_rsg(away_abbr, venue="away")

    home_bp_era = _fetch_team_bullpen_era(away_abbr)
    away_bp_era = _fetch_team_bullpen_era(home_abbr)

    weather = _fetch_weather(venue_city, home_abbr, game_pk)
    weather_factor = weather["weather_factor"]

    ump_name, ump_runs_adj = _fetch_home_plate_umpire(game_pk)

    park_f = PARK_FACTORS.get(home_abbr, 1.00)

    from services.game_context_service import LEAGUE_FIELDING_PCT, LEAGUE_OPS, get_game_context

    context = get_game_context(away_abbr, home_abbr, game_pk, away_sp_id, home_sp_id)

    home_starter_usage = _fetch_expected_starter_usage(home_sp_id)
    away_starter_usage = _fetch_expected_starter_usage(away_sp_id)

    LEAGUE_AVG_BP_ERA = 4.20

    def _available_bp_era(team_bp_era, available_recent_era, quality_count):
        if available_recent_era is None or quality_count < 2:
            return team_bp_era
        return float(np.clip(0.55 * team_bp_era + 0.45 * available_recent_era, 2.0, 7.5))

    home_available_bp_era = _available_bp_era(
        home_bp_era,
        context.get("away_available_recent_reliever_era"),
        context.get("away_available_reliever_quality_count", 0),
    )
    away_available_bp_era = _available_bp_era(
        away_bp_era,
        context.get("home_available_recent_reliever_era"),
        context.get("home_available_reliever_quality_count", 0),
    )

    def _pm(sp_fip, bp_era, starter_innings):
        bullpen_innings = 9.0 - starter_innings
        sp_factor = (sp_fip / LEAGUE_AVG_FIP) ** SP_FIP_EXPONENT * (starter_innings / 9)
        bp_factor = (bp_era / LEAGUE_AVG_BP_ERA) * (bullpen_innings / 9)
        return sp_factor + bp_factor

    home_exp = (
        home_rsg
        * park_f
        * _pm(away_fip, home_available_bp_era, away_starter_usage["expected_innings"])
        * weather_factor
    )
    away_exp = (
        away_rsg
        * park_f
        * _pm(home_fip, away_available_bp_era, home_starter_usage["expected_innings"])
        * weather_factor
    )

    lineup_runs_adj = 0.0
    if context["context_complete"]:
        avg_lineup_ops = (context["home_lineup_ops"] + context["away_lineup_ops"]) / 2
        lineup_runs_adj = float(np.clip((avg_lineup_ops - LEAGUE_OPS) * 4.0, -0.6, 0.6))

    BULLPEN_PITCHES_BASELINE = 360

    if context.get("bullpen_workload_source") == "MLB reliever pitch counts":
        total_pitches = (context.get("home_bullpen_pitches_3d") or 0) + (
            context.get("away_bullpen_pitches_3d") or 0
        )
        unavailable = (context.get("home_unavailable_relievers") or 0) + (
            context.get("away_unavailable_relievers") or 0
        )

        pitch_deviation = total_pitches - BULLPEN_PITCHES_BASELINE
        bullpen_workload_adj = float(
            np.clip(pitch_deviation * 0.002 + unavailable * 0.06, -0.35, 0.70)
        )
    else:
        bullpen_workload_adj = float(
            np.clip(
                (context["home_bullpen_fatigue"] + context["away_bullpen_fatigue"]) * 0.12,
                -0.30,
                0.60,
            )
        )
    defense_runs_adj = float(
        np.clip(
            -(
                (context["home_fielding_pct"] + context["away_fielding_pct"])
                - 2 * LEAGUE_FIELDING_PCT
            )
            * 10.0,
            -0.30,
            0.30,
        )
    )
    advanced = context.get("advanced", {})
    home_sc = advanced.get("home_pitcher_statcast", {})
    away_sc = advanced.get("away_pitcher_statcast", {})
    contact_runs_adj = 0.0
    if home_sc.get("xera_proxy") is not None and away_sc.get("xera_proxy") is not None:
        contact_runs_adj = float(
            np.clip(
                ((home_sc["xera_proxy"] - home_fip) + (away_sc["xera_proxy"] - away_fip)) * 0.12,
                -0.45,
                0.45,
            )
        )
    hr_park_factor_proxy = round(1 + (park_f - 1) * 1.4, 3)
    expected_total = (
        home_exp
        + away_exp
        + ump_runs_adj
        + lineup_runs_adj
        + bullpen_workload_adj
        + defense_runs_adj
        + contact_runs_adj
    )

    wind_info = (
        f'{weather["wind_mph"]:.0f}mph {weather["wind_dir"]}' if not weather.get("dome") else "dome"
    )
    print(
        f"    λ={expected_total:.2f} | home_exp={home_exp:.2f} away_exp={away_exp:.2f} "
        f"| FIPs {home_fip:.2f}/{away_fip:.2f} | BPs {home_bp_era:.2f}/{away_bp_era:.2f} "
        f'| park={park_f} | wx={weather_factor:.3f} ({weather["temp_f"]:.0f}°F {wind_info})'
        f"| ump={ump_name} ({ump_runs_adj:+.2f})"
    )

    model_over_prob, model_under_prob = poisson_side_probs(expected_total, market_line)

    PROB_SHRINK = 0.25
    model_over_prob = (1 - PROB_SHRINK) * model_over_prob + PROB_SHRINK * 0.5
    model_under_prob = 1.0 - model_over_prob

    raw_over = np.mean([1.0 / o for o in over_odds_list])
    raw_under = np.mean([1.0 / o for o in under_odds_list])
    tot_vig = raw_over + raw_under
    mkt_over = raw_over / tot_vig
    mkt_under = raw_under / tot_vig

    from services.model_learning_service import apply_active_calibration

    model_over_prob = apply_active_calibration("totals", model_over_prob, mkt_over)
    model_under_prob = 1.0 - model_over_prob

    if model_over_prob >= model_under_prob:
        direction = "over"
        model_prob = model_over_prob
        market_prob = mkt_over
        best_odds = max(over_odds_list)
    else:
        direction = "under"
        model_prob = model_under_prob
        market_prob = mkt_under
        best_odds = max(under_odds_list)

    model_edge = (model_prob - market_prob) * 100

    ev = (model_prob * best_odds - 1) * 100

    if best_odds >= 2.0:
        odds_display = f"+{int(round((best_odds - 1) * 100))}"
    else:
        odds_display = str(int(round(-100 / (best_odds - 1))))

    pick_str = f'{"OVER" if direction == "over" else "UNDER"} {market_line}'

    MIN_PROB = 0.54
    MAX_PROB = 0.74
    MIN_EV = 12.0
    MIN_EDGE = 4.0

    OVER_MIN_PROB = 0.62

    all_prices = [float(x) for x in over_odds_list + under_odds_list]
    market_price_spread = max(all_prices) - min(all_prices) if all_prices else 99.0
    qualification_checklist = {
        "probability_54_to_74": MIN_PROB <= model_prob <= MAX_PROB,
        "ev_at_least_12": ev >= MIN_EV,
        "edge_at_least_4pp": abs(model_edge) >= MIN_EDGE,
        "six_or_more_books": n_books >= MIN_BOOKS,
        "confirmed_lineups": bool(context.get("context_complete")),
        "both_starters_confirmed": bool(home_sp_id and away_sp_id),
        "dynamic_starter_usage": bool(
            home_starter_usage.get("available") and away_starter_usage.get("available")
        ),
        "individual_reliever_availability": context.get("bullpen_workload_source")
        == "MLB reliever pitch counts",
        "available_reliever_quality": (
            context.get("home_available_reliever_quality_count", 0) >= 2
            and context.get("away_available_reliever_quality_count", 0) >= 2
        ),
        "strong_probability_60": model_prob >= 0.60,
        "strong_ev_18": ev >= 18.0,
        "strong_edge_7pp": abs(model_edge) >= 7.0,
        "ten_or_more_books": n_books >= 10,
        "stable_cross_book_prices": market_price_spread <= 0.12,
        "over_min_prob_62": direction != "over" or model_prob >= 0.62,
    }
    qualified = all(
        qualification_checklist[key]
        for key in (
            "probability_54_to_74",
            "ev_at_least_12",
            "edge_at_least_4pp",
            "six_or_more_books",
            "over_min_prob_62",
        )
    )
    strong_lock = qualified and all(
        qualification_checklist[key]
        for key in (
            "confirmed_lineups",
            "both_starters_confirmed",
            "strong_probability_60",
            "dynamic_starter_usage",
            "individual_reliever_availability",
            "available_reliever_quality",
            "strong_ev_18",
            "strong_edge_7pp",
            "ten_or_more_books",
            "stable_cross_book_prices",
        )
    )
    recommendation_tier = (
        "strong_lock" if strong_lock else "qualified_pick" if qualified else "daily_forecast"
    )

    print(
        f"    model {model_prob:.1%} vs mkt {market_prob:.1%} | edge {model_edge:+.1f}pp | EV {ev:.1f}%"
    )

    def _base():
        return {
            "pick": pick_str,
            "direction": direction,
            "model_prob": round(model_prob, 4),
            "market_prob": round(market_prob, 4),
            "model_edge": round(model_edge, 2),
            "best_odds": round(best_odds, 3),
            "best_odds_display": odds_display,
            "ev": round(ev, 2),
            "expected_total": round(expected_total, 2),
            "home_fip": round(home_fip, 2),
            "away_fip": round(away_fip, 2),
            "home_rsg": round(home_rsg, 2),
            "away_rsg": round(away_rsg, 2),
            "park_factor": park_f,
            "hr_park_factor_proxy": hr_park_factor_proxy,
            "home_bp_era": round(home_bp_era, 2),
            "away_bp_era": round(away_bp_era, 2),
            "home_available_bp_era": round(home_available_bp_era, 2),
            "away_available_bp_era": round(away_available_bp_era, 2),
            "home_team_available_bp_era": round(away_available_bp_era, 2),
            "away_team_available_bp_era": round(home_available_bp_era, 2),
            "home_starter_usage": home_starter_usage,
            "away_starter_usage": away_starter_usage,
            "weather_factor": round(weather_factor, 4),
            "temp_f": weather.get("temp_f"),
            "wind_info": wind_info,
            "weather_source": weather.get("weather_source"),
            "weather_error": weather.get("weather_error"),
            "ump_name": ump_name,
            "ump_runs_adj": round(ump_runs_adj, 2),
            "lineup_runs_adj": round(lineup_runs_adj, 2),
            "bullpen_workload_adj": round(bullpen_workload_adj, 2),
            "defense_runs_adj": round(defense_runs_adj, 2),
            "contact_quality_runs_adj": round(contact_runs_adj, 2),
            "context": context,
            "n_books": n_books,
            "recommendation_tier": recommendation_tier,
            "qualification_checklist": qualification_checklist,
            "market_price_spread": round(market_price_spread, 4),
        }

    if limited_market_warning:
        return {**_base(), "skipped": True, "skip_reason": limited_market_warning}
    if model_prob < MIN_PROB:
        return {
            **_base(),
            "skipped": True,
            "skip_reason": f"Model prob {model_prob:.1%} < {MIN_PROB:.0%} minimum",
        }

    if direction == "over" and model_prob < OVER_MIN_PROB:
        return {
            **_base(),
            "skipped": True,
            "skip_reason": (
                f"OVER model prob {model_prob:.1%} < {OVER_MIN_PROB:.0%} "
                "temporary OVER-only floor (pending calibration fix)"
            ),
        }

    if model_prob > MAX_PROB:
        return {
            **_base(),
            "skipped": True,
            "skip_reason": f"Model prob {model_prob:.1%} > {MAX_PROB:.0%} cap (overconfidence zone)",
        }

    if abs(model_edge) < MIN_EDGE:
        return {
            **_base(),
            "skipped": True,
            "skip_reason": f"Edge {model_edge:+.1f}pp < {MIN_EDGE}pp (no meaningful disagreement with market)",
        }

    if ev < MIN_EV:
        return {**_base(), "skipped": True, "skip_reason": f"EV {ev:.1f}% < {MIN_EV}% minimum"}

    print(
        f"    TOTALS PICK: {pick_str} | model {model_prob:.1%} vs mkt {market_prob:.1%} "
        f"| edge {model_edge:+.1f}pp | EV {ev:.1f}% | λ={expected_total:.2f} "
        f"| weather {weather_factor:.3f}"
    )

    return {**_base(), "skipped": False, "skip_reason": None}
