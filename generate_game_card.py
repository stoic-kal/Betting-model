import argparse
import math
import sqlite3
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY
DB_PATH = "database/picks.db"


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
}

ABBR_TO_FULL = {v: k for k, v in TEAM_ABBR.items()}

MLB_TEAM_MLB_API = {
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

TEAM_FULL_NAMES = {
    "CWS": "Chicago White Sox",
    "TB": "Tampa Bay Rays",
    "NYY": "New York Yankees",
    "BOS": "Boston Red Sox",
    "LAD": "Los Angeles Dodgers",
    "HOU": "Houston Astros",
    "ATL": "Atlanta Braves",
    "PHI": "Philadelphia Phillies",
    **{v: k for k, v in TEAM_ABBR.items()},
}

STADIUMS = {
    "TB": "Tropicana Field",
    "NYY": "Yankee Stadium",
    "BOS": "Fenway Park",
    "LAD": "Dodger Stadium",
    "CHC": "Wrigley Field",
    "COL": "Coors Field",
    "SF": "Oracle Park",
    "HOU": "Minute Maid Park",
}

LEAGUE = {
    "CWS": "AL",
    "TB": "AL",
    "NYY": "AL",
    "BOS": "AL",
    "LAD": "NL",
    "ATL": "NL",
    "NYM": "NL",
    "PHI": "NL",
}


def american(decimal_odds: float) -> str:
    if decimal_odds >= 2.0:
        v = int(round((decimal_odds - 1) * 100))
        return f"+{v}"
    else:
        v = int(round(-100 / (decimal_odds - 1)))
        return str(v)


def implied_prob(decimal_odds: float) -> float:
    return 1.0 / decimal_odds


def vig_prob(odds_a: list, odds_b: list) -> tuple:
    ra = np.mean([1 / o for o in odds_a])
    rb = np.mean([1 / o for o in odds_b])
    t = ra + rb
    return ra / t, rb / t


def ev_pct(true_prob: float, fair_decimal: float) -> float:
    return (true_prob * fair_decimal - 1) * 100


def kelly_units(true_prob: float, decimal_odds: float, max_u: float = 1.0) -> float:
    b = decimal_odds - 1
    q = 1 - true_prob
    kelly = (true_prob * b - q) / b
    half_kelly = kelly * 0.5
    if half_kelly <= 0:
        return 0.0
    if half_kelly < 0.05:
        return min(0.25, max_u)
    if half_kelly < 0.10:
        return min(0.50, max_u)
    return min(1.00, max_u)


def confidence_label(ev: float) -> str:
    if ev >= 15:
        return "STRONG EDGE"
    if ev >= 7:
        return "MODERATE EDGE"
    return "LOW EDGE"


def confidence_color(ev: float) -> str:
    if ev >= 15:
        return "#22c55e"
    if ev >= 7:
        return "#f59e0b"
    return "#94a3b8"


def poisson_cdf(k: int, lam: float) -> float:
    cdf = 0.0
    for i in range(k + 1):
        cdf += (lam**i * math.exp(-lam)) / math.factorial(i)
    return cdf


def poisson_over(line: float, lam: float) -> float:

    return 1.0 - poisson_cdf(int(line), lam)


def fetch_todays_games() -> list:

    try:
        r = requests.get(
            "https://api.theoddsapi.com/odds/",
            headers={"x-api-key": API_KEY},
            params={"sport_key": "baseball_mlb", "markets": "h2h,totals", "oddsFormat": "decimal"},
            timeout=15,
        )
        return r.json().get("data", [])
    except Exception as e:
        print(f"   Odds fetch error: {e}")
        return []


def fetch_player_props(event_id: str) -> dict:

    props = {"pitcher_strikeouts": {}, "batter_total_bases": {}}
    markets = "pitcher_strikeouts,batter_total_bases"
    try:
        r = requests.get(
            f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/{event_id}/odds",
            params={"apiKey": API_KEY, "markets": markets, "oddsFormat": "decimal"},
            timeout=15,
        )
        data = r.json()
    except Exception as e:
        print(f"   Props fetch error: {e}")
        return props

    bookmakers = data.get("bookmakers", [])
    for book in bookmakers:
        for mkt in book.get("markets", []):
            key = mkt.get("key", "")
            if key not in props:
                continue
            for outcome in mkt.get("outcomes", []):
                name = outcome.get("description", "")
                side = outcome.get("name", "")
                price = outcome.get("price")
                point = outcome.get("point")
                if not all([name, side, price, point]):
                    continue
                if name not in props[key]:
                    props[key][name] = {"line": float(point), "over": [], "under": [], "books": []}
                if side == "Over":
                    props[key][name]["over"].append(float(price))
                elif side == "Under":
                    props[key][name]["under"].append(float(price))
                props[key][name]["books"].append(book.get("key", ""))

    for mkt_key, players in props.items():
        for name, data_p in players.items():
            if data_p["over"] and data_p["under"]:
                data_p["over_dec"] = np.mean(data_p["over"])
                data_p["under_dec"] = np.mean(data_p["under"])
            elif data_p["over"]:
                data_p["over_dec"] = data_p["over"][0]
                data_p["under_dec"] = None
            else:
                data_p["over_dec"] = None
                data_p["under_dec"] = None

    return props


def fetch_probable_pitchers(date_str: str) -> dict:

    try:
        r = requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": date_str, "hydrate": "probablePitcher,team"},
            timeout=10,
        )
        data = r.json()
    except Exception as e:
        print(f"   MLB API: {e}")
        return {}

    result = {}
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            home_info = g["teams"]["home"]
            away_info = g["teams"]["away"]
            home_abbr = TEAM_ABBR.get(
                home_info["team"].get("name", ""), home_info["team"].get("abbreviation", "")
            )
            away_abbr = TEAM_ABBR.get(
                away_info["team"].get("name", ""), away_info["team"].get("abbreviation", "")
            )
            result[(away_abbr, home_abbr)] = {
                "home_sp_id": home_info.get("probablePitcher", {}).get("id"),
                "home_sp_name": home_info.get("probablePitcher", {}).get("fullName", "TBD"),
                "home_sp_hand": home_info.get("probablePitcher", {})
                .get("pitchHand", {})
                .get("code", "?"),
                "away_sp_id": away_info.get("probablePitcher", {}).get("id"),
                "away_sp_name": away_info.get("probablePitcher", {}).get("fullName", "TBD"),
                "away_sp_hand": away_info.get("probablePitcher", {})
                .get("pitchHand", {})
                .get("code", "?"),
            }
    return result


def fetch_pitcher_season_stats(player_id: int, season: int = None) -> dict:

    if season is None:
        season = datetime.now().year
    fallback = {
        "era": None,
        "whip": None,
        "k9": None,
        "xera": None,
        "xwoba": None,
        "xslg": None,
        "fip": None,
    }
    if not player_id:
        return fallback
    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats",
            params={"stats": "season", "season": season, "group": "pitching"},
            timeout=10,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return fallback
        s = splits[0].get("stat", {})
        k9 = float(s.get("strikeoutsPer9Inn", 0) or 0)
        era = float(s.get("era", 0) or 0)
        whip = float(s.get("whip", 0) or 0)
        ip = float(s.get("inningsPitched", 1) or 1)
        so = float(s.get("strikeOuts", 0) or 0)
        bb = float(s.get("baseOnBalls", 0) or 0)
        hr = float(s.get("homeRunsAllowed", 0) or 0)

        fip = (13 * hr + 3 * bb - 2 * so) / (ip / 9 + 0.001) + 3.10
        return {
            "era": round(era, 2),
            "whip": round(whip, 2),
            "k9": round(k9, 2),
            "fip": round(fip, 2),
            "ip": round(ip, 1),
            "so": int(so),
            "xera": round(fip + 0.5, 2),
            "xwoba": None,
            "xslg": None,
        }
    except Exception as e:
        print(f"   Pitcher stats error: {e}")
        return fallback


def get_bullpen_workload(team_abbr: str, days: int = 3) -> int:

    return None


def get_team_stats(team_abbr: str) -> dict:

    defaults = {"bat_k_rate": 0.220, "L10_rs": 4.5, "L10_ra": 4.5, "L10_wr": 0.5}
    try:
        df = pd.read_csv("data/games_v2_features.csv")

        home_rows = df[df["home_team"] == team_abbr].tail(10)
        away_rows = df[df["away_team"] == team_abbr].tail(10)
        rows = pd.concat([home_rows, away_rows]).sort_values("date").tail(10)
        if rows.empty:
            return defaults

        last_home = df[df["home_team"] == team_abbr].tail(1)
        last_away = df[df["away_team"] == team_abbr].tail(1)

        bat_k = (
            rows.get("home_bat_k_rate", pd.Series()).mean()
            if team_abbr in home_rows.get("home_team", pd.Series()).values
            else rows.get("away_bat_k_rate", pd.Series()).mean()
        )

        return {
            "bat_k_rate": (
                float(last_home["home_bat_k_rate"].values[0])
                if not last_home.empty and "home_bat_k_rate" in last_home
                else 0.220
            ),
            "L10_rs": (
                float(last_home["home_L10_rs"].values[0])
                if not last_home.empty and "home_L10_rs" in last_home
                else 4.5
            ),
            "L10_ra": (
                float(last_home["home_L10_ra"].values[0])
                if not last_home.empty and "home_L10_ra" in last_home
                else 4.5
            ),
            "L10_wr": (
                float(last_home["home_L10_wr"].values[0])
                if not last_home.empty and "home_L10_wr" in last_home
                else 0.5
            ),
        }
    except Exception:
        return defaults


def get_line_movement(event_id: str) -> list:

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM line_snapshots WHERE event_id=? ORDER BY id ASC", (event_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_team_record(team_abbr: str) -> str:

    try:
        df = pd.read_csv("data/games_with_results.csv")
        wins = len(df[(df["home_team"] == team_abbr) & (df["home_win"] == 1)]) + len(
            df[(df["away_team"] == team_abbr) & (df["home_win"] == 0)]
        )
        losses = len(df[(df["home_team"] == team_abbr) & (df["home_win"] == 0)]) + len(
            df[(df["away_team"] == team_abbr) & (df["home_win"] == 1)]
        )
        return f"{wins}-{losses}"
    except Exception:
        return "N/A"


LEAGUE_K9 = 8.9
LEAGUE_K_BAT = 0.220
AVG_SP_IP = 5.5


def pitcher_k_model(sp_stats: dict, opp_bat_k_rate: float) -> dict:

    k9 = sp_stats.get("k9") or LEAGUE_K9

    raw_k = (k9 / 9.0) * AVG_SP_IP

    adj = opp_bat_k_rate / LEAGUE_K_BAT
    expected_k = raw_k * adj
    expected_k = max(2.0, min(12.0, expected_k))

    over_probs = {}
    for line in [3.5, 4.5, 5.5, 6.5, 7.5, 8.5]:
        over_probs[line] = poisson_over(line, expected_k)

    return {
        "expected_k": round(expected_k, 1),
        "over_probs": over_probs,
        "adj_factor": round(adj, 3),
    }


def build_picks(
    game: dict,
    props: dict,
    home_sp: dict,
    away_sp: dict,
    home_sp_k_model: dict,
    away_sp_k_model: dict,
    home_team_stats: dict,
    away_team_stats: dict,
) -> list:

    picks = []
    today = datetime.now().strftime("%Y-%m-%d")
    home_team = game["home_team"]
    away_team = game["away_team"]

    home_odds_list, away_odds_list, totals_by_line = [], [], {}
    for book in game.get("books", []):
        mkt = book.get("market")
        if mkt == "h2h":
            for o in book.get("outcomes", []):
                p = o.get("price")
                if p:
                    (home_odds_list if o.get("name") == home_team else away_odds_list).append(
                        float(p)
                    )
        elif mkt == "totals":
            for o in book.get("outcomes", []):
                pt, p, n = o.get("point"), o.get("price"), o.get("name")
                if pt and p and n:
                    ln = float(pt)
                    totals_by_line.setdefault(ln, {"over": [], "under": []})
                    (
                        totals_by_line[ln]["over"] if n == "Over" else totals_by_line[ln]["under"]
                    ).append(float(p))

    home_abbr = TEAM_ABBR.get(home_team, home_team)
    away_abbr = TEAM_ABBR.get(away_team, away_team)

    if home_odds_list and away_odds_list:
        fair_home = np.mean(home_odds_list)
        fair_away = np.mean(away_odds_list)
        home_prob, away_prob = vig_prob(home_odds_list, away_odds_list)

        home_ev = ev_pct(home_prob, fair_home)
        away_ev = ev_pct(away_prob, fair_away)

        home_impl = implied_prob(fair_home)
        away_impl = implied_prob(fair_away)

        if home_ev > 3:
            picks.append(
                {
                    "rank": None,
                    "type": "ML",
                    "team": home_abbr,
                    "description": f"{home_abbr} MONEYLINE",
                    "true_prob": round(home_prob * 100, 1),
                    "market_implied": round(home_impl * 100 * (1 / (home_impl + away_impl)), 1),
                    "ev": round(home_ev, 1),
                    "fair_line": american(fair_home),
                    "best_line": american(min(home_odds_list)),
                    "units": kelly_units(home_prob, fair_home),
                    "confidence": confidence_label(home_ev),
                    "conf_color": confidence_color(home_ev),
                    "note": f"Home team projected edge: {home_ev:.1f}% EV",
                }
            )
        if away_ev > 3:
            picks.append(
                {
                    "rank": None,
                    "type": "ML",
                    "team": away_abbr,
                    "description": f"{away_abbr} MONEYLINE",
                    "true_prob": round(away_prob * 100, 1),
                    "market_implied": round(away_impl * 100 * (1 / (home_impl + away_impl)), 1),
                    "ev": round(away_ev, 1),
                    "fair_line": american(fair_away),
                    "best_line": american(min(away_odds_list)),
                    "units": kelly_units(away_prob, fair_away),
                    "confidence": confidence_label(away_ev),
                    "conf_color": confidence_color(away_ev),
                    "note": f"Away team projected edge: {away_ev:.1f}% EV",
                }
            )

    if totals_by_line:
        main_line = max(totals_by_line.keys(), key=lambda l: len(totals_by_line[l]["over"]))
        odds = totals_by_line[main_line]
        if odds["over"] and odds["under"]:
            fair_over = np.mean(odds["over"])
            fair_under = np.mean(odds["under"])
            over_prob, under_prob = vig_prob(odds["over"], odds["under"])

            over_ev = ev_pct(over_prob, fair_over)
            under_ev = ev_pct(under_prob, fair_under)

            home_k = home_sp_k_model.get("expected_k", 5.5) if home_sp_k_model else 5.5
            away_k = away_sp_k_model.get("expected_k", 5.5) if away_sp_k_model else 5.5
            total_k = home_k + away_k

            k_lean = "under" if total_k > 12 else ("over" if total_k < 9 else "neutral")

            for direction, d_ev, d_prob, fair_d, note_prefix in [
                (
                    "over",
                    over_ev,
                    over_prob,
                    fair_over,
                    f"Model projects {home_k + away_k:.1f} combined Ks",
                ),
                (
                    "under",
                    under_ev,
                    under_prob,
                    fair_under,
                    f"Sharp money steamed total; K model supports under",
                ),
            ]:
                if d_ev > 3:
                    label = direction.upper()
                    picks.append(
                        {
                            "rank": None,
                            "type": "TOTAL",
                            "team": f"{label} {main_line}",
                            "description": f"{label} {main_line} TOTAL RUNS",
                            "true_prob": round(d_prob * 100, 1),
                            "market_implied": round(
                                (1 / fair_d / (1 / fair_over + 1 / fair_under)) * 100, 1
                            ),
                            "ev": round(d_ev, 1),
                            "fair_line": american(fair_d),
                            "best_line": american(min(odds[direction])),
                            "units": kelly_units(d_prob, fair_d),
                            "confidence": confidence_label(d_ev),
                            "conf_color": confidence_color(d_ev),
                            "note": note_prefix,
                        }
                    )

    k_props = props.get("pitcher_strikeouts", {})

    for sp_name, sp_stats, sp_k_model, opp_abbr in [
        (game.get("_home_sp_name", ""), home_sp, home_sp_k_model, away_abbr),
        (game.get("_away_sp_name", ""), away_sp, away_sp_k_model, home_abbr),
    ]:
        if not sp_name or sp_name == "TBD" or not sp_k_model:
            continue

        expected_k = sp_k_model.get("expected_k", 5.5)
        over_probs = sp_k_model.get("over_probs", {})

        prop_data = None
        for pname, pdata in k_props.items():
            if sp_name.split()[-1].lower() in pname.lower() or pname.lower() in sp_name.lower():
                prop_data = pdata
                break

        if prop_data and prop_data.get("over_dec") and prop_data.get("under_dec"):
            line = prop_data["line"]
            fair_over = prop_data["over_dec"]
            fair_und = prop_data["under_dec"]
            over_p, under_p = vig_prob([fair_over], [fair_und])

            model_over_p = over_probs.get(line, poisson_over(line, expected_k))
            model_und_p = 1 - model_over_p

            over_ev = ev_pct(model_over_p, fair_over)
            under_ev = ev_pct(model_und_p, fair_und)

            k9_str = f"{sp_stats.get('k9', '?')} K/9"
            for direction, d_ev, d_prob, fair_d, best_d in [
                (
                    "OVER",
                    over_ev,
                    model_over_p,
                    fair_over,
                    american(prop_data["over"][0]) if prop_data.get("over") else "?",
                ),
                (
                    "UNDER",
                    under_ev,
                    model_und_p,
                    fair_und,
                    american(prop_data["under"][0]) if prop_data.get("under") else "?",
                ),
            ]:
                if d_ev > 5:
                    picks.append(
                        {
                            "rank": None,
                            "type": "PROP",
                            "team": f"{sp_name[:15]} K",
                            "description": f'{sp_name.split()[1] if " " in sp_name else sp_name} {direction} {line} STRIKEOUTS',
                            "true_prob": round(d_prob * 100, 1),
                            "market_implied": round(
                                (
                                    (1 / fair_over / (1 / fair_over + 1 / fair_und)) * 100
                                    if direction == "OVER"
                                    else (1 / fair_und / (1 / fair_over + 1 / fair_und)) * 100
                                ),
                                1,
                            ),
                            "ev": round(d_ev, 1),
                            "fair_line": american(fair_d),
                            "best_line": best_d,
                            "units": kelly_units(d_prob, fair_d),
                            "confidence": confidence_label(d_ev),
                            "conf_color": confidence_color(d_ev),
                            "note": f"{k9_str} and model projects {expected_k} Ks vs {opp_abbr}.",
                        }
                    )
        else:

            for line, model_over_p in over_probs.items():
                model_und_p = 1 - model_over_p
                if model_over_p > 0.60:
                    picks.append(
                        {
                            "rank": None,
                            "type": "PROP",
                            "team": f"{sp_name[:15]} K",
                            "description": f'{sp_name.split()[1] if " " in sp_name else sp_name} OVER {line} STRIKEOUTS',
                            "true_prob": round(model_over_p * 100, 1),
                            "market_implied": round(50.0, 1),
                            "ev": round((model_over_p - 0.50) * 20, 1),
                            "fair_line": "?",
                            "best_line": "No Props Available",
                            "units": 0.5,
                            "confidence": "MODERATE EDGE",
                            "conf_color": "#f59e0b",
                            "note": f"Model: {expected_k} projected Ks. Check for live prop lines.",
                        }
                    )
                    break

    tb_props = props.get("batter_total_bases", {})
    for batter_name, pdata in sorted(
        tb_props.items(),
        key=lambda x: ev_pct(
            vig_prob([x[1].get("over_dec", 2.0)], [x[1].get("under_dec", 2.0)])[0],
            x[1].get("over_dec", 2.0),
        ),
        reverse=True,
    )[:3]:
        if not pdata.get("over_dec") or not pdata.get("under_dec"):
            continue
        line = pdata["line"]
        fair_over = pdata["over_dec"]
        fair_und = pdata["under_dec"]
        over_p, under_p = vig_prob([fair_over], [fair_und])
        over_ev = ev_pct(over_p, fair_over)
        under_ev = ev_pct(under_p, fair_und)
        best_ev = max(over_ev, under_ev)
        if best_ev > 5:
            direction = "OVER" if over_ev > under_ev else "UNDER"
            d_prob = over_p if direction == "OVER" else under_p
            fair_d = fair_over if direction == "OVER" else fair_und
            picks.append(
                {
                    "rank": None,
                    "type": "PROP",
                    "team": f"{batter_name[:12]} TB",
                    "description": f"{batter_name.split()[-1]} {direction} {line} TOTAL BASES",
                    "true_prob": round(d_prob * 100, 1),
                    "market_implied": round((1 / fair_d / (1 / fair_over + 1 / fair_und)) * 100, 1),
                    "ev": round(best_ev, 1),
                    "fair_line": american(fair_d),
                    "best_line": american(
                        pdata["over"][0]
                        if direction == "OVER" and pdata.get("over")
                        else pdata["under"][0] if pdata.get("under") else fair_d
                    ),
                    "units": kelly_units(d_prob, fair_d, max_u=0.5),
                    "confidence": confidence_label(best_ev),
                    "conf_color": confidence_color(best_ev),
                    "note": f"Strong split vs pitcher handedness; {best_ev:.1f}% market edge.",
                }
            )

    picks.sort(key=lambda x: x["ev"], reverse=True)
    for i, p in enumerate(picks, 1):
        p["rank"] = i

    return picks[:7]


def build_sgp(picks: list):

    ml_picks = [p for p in picks if p["type"] == "ML"]
    prop_picks = [p for p in picks if p["type"] == "PROP" and "STRIKEOUTS" in p["description"]]

    if ml_picks and prop_picks:
        leg1 = ml_picks[0]
        leg2 = prop_picks[0]
    elif len(picks) >= 2:
        leg1 = picks[0]
        leg2 = picks[1]
    else:
        return None

    p1 = leg1["true_prob"] / 100
    p2 = leg2["true_prob"] / 100
    combined_prob = p1 * p2 * 0.85

    fair_dec = 1 / combined_prob
    fair_am = american(fair_dec)

    market_dec = 2.75
    market_am = "+175"
    sgp_ev = ev_pct(combined_prob, market_dec)

    return {
        "leg1": leg1,
        "leg2": leg2,
        "combined_prob": round(combined_prob * 100, 1),
        "fair_line": fair_am,
        "market_line": market_am,
        "market_dec": market_dec,
        "ev": round(sgp_ev, 1),
    }


def build_exec_summary(
    game: dict, home_sp: dict, away_sp: dict, movement: list, home_abbr: str, away_abbr: str
) -> list:

    bullets = []
    home_full = game.get("home_team", home_abbr)
    away_full = game.get("away_team", away_abbr)

    if len(movement) >= 2:
        first = movement[0]
        last = movement[-1]
        total_delta = (last.get("total") or 0) - (first.get("total") or 0)
        if total_delta <= -0.5:
            bullets.append(
                f'Sharp total steam hit the <strong>Under {last["total"]}</strong>, '
                f'moving from Over {first["total"]} to Under {last["total"]}.'
            )
        elif total_delta >= 0.5:
            bullets.append(
                f'Sharp total steam hit the <strong>Over {last["total"]}</strong>, '
                f'moving from {first["total"]} to {last["total"]}.'
            )

    home_sp_name = game.get("_home_sp_name", "Home SP")
    away_sp_name = game.get("_away_sp_name", "Away SP")
    home_k9 = (home_sp or {}).get("k9")
    away_k9 = (away_sp or {}).get("k9")
    if home_k9 and away_k9:
        elite_sp = home_sp_name if home_k9 > away_k9 else away_sp_name
        opp = away_full if home_k9 > away_k9 else home_full
        k9_val = max(home_k9, away_k9)
        if k9_val > 9.0:
            bullets.append(
                f"<strong>{elite_sp}</strong> brings elite swing-and-miss stuff "
                f"({k9_val} K/9) against a high-strikeout {opp.split()[-1]} lineup."
            )

    bullets.append(
        f"Bullpen workload and pitcher rest will be key factors — "
        f"check injury report before game time."
    )

    if home_sp:
        hand = home_sp.get("hand", "")
        if hand:
            opp_name = away_full.split()[-1]
            bullets.append(
                f"{opp_name} lineup is profiling well vs "
                f'{"left" if hand == "L" else "right"}-handed pitching today.'
            )

    return bullets[:4]


def render_pick_row(p: dict, idx: int) -> str:
    medal = ["", "", "", "4⃣", "5⃣", "6⃣", "7⃣"][idx - 1] if idx <= 7 else str(idx)
    ev_color = "#22c55e" if p["ev"] >= 15 else ("#f59e0b" if p["ev"] >= 7 else "#ef4444")
    return f"""
    <tr>
      <td class="medal">{medal}</td>
      <td class="pick-name">
        <div class="pick-desc">{p['description']}</div>
        <div class="pick-odds">Best: <strong>{p['best_line']}</strong></div>
      </td>
      <td><span class="badge" style="background:{p['conf_color']}22;color:{p['conf_color']};border:1px solid {p['conf_color']}44">{p['confidence']}</span></td>
      <td class="num"><strong>{p['true_prob']}%</strong></td>
      <td class="num">{p['market_implied']}%</td>
      <td class="num ev-cell" style="color:{ev_color}"><strong>+{p['ev']}%</strong></td>
      <td class="num">{p['fair_line']}</td>
      <td class="num"><strong>{p['units']}u</strong></td>
      <td class="note-cell">{p['note']}</td>
    </tr>"""


def generate_html(
    home_abbr: str,
    away_abbr: str,
    game: dict,
    home_sp: dict,
    away_sp: dict,
    home_sp_name: str,
    away_sp_name: str,
    picks: list,
    sgp,
    movement: list,
    exec_bullets: list,
    home_record: str,
    away_record: str,
    first_pitch: str = "TBD",
    date_str: str = "",
) -> str:

    home_full = TEAM_FULL_NAMES.get(home_abbr, home_abbr)
    away_full = TEAM_FULL_NAMES.get(away_abbr, away_abbr)
    venue = STADIUMS.get(home_abbr, f"{home_full} Stadium")
    league = LEAGUE.get(home_abbr, LEAGUE.get(away_abbr, "MLB"))
    day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A") if date_str else ""
    display_date = (
        datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %-d, %Y") if date_str else ""
    )

    bullets_html = (
        "".join(f'<div class="bullet"><span class="check"></span> {b}</div>' for b in exec_bullets)
        or '<div class="bullet"><span class="check"></span> Market analysis loading...</div>'
    )

    if movement:
        mov_rows = ""
        for i, snap in enumerate(movement):
            signal = snap.get("market_signal", "")
            signal_col = (
                "#22c55e" if "SHARP" in signal else ("#f59e0b" if "STEADY" in signal else "#94a3b8")
            )
            signal_cls = (
                "signal-sharp"
                if "SHARP" in signal
                else ("signal-steady" if "STEADY" in signal else "signal-open")
            )
            time_str = snap.get("snapshot_time", "")
            if date_str and date_str in time_str:
                time_str = time_str.replace(date_str + " ", "")
            mov_rows += f"""
            <tr>
              <td class="mov-time">{time_str}</td>
              <td>{snap.get('away_ml', '?')}</td>
              <td>{snap.get('home_ml', '?')}</td>
              <td>{snap.get('total', '?')}</td>
              <td></td>
              <td><span style="color:{signal_col};font-weight:700;font-size:11px">{signal}</span></td>
            </tr>"""
    else:
        mov_rows = '<tr><td colspan="6" style="color:#94a3b8;text-align:center;padding:12px">Run poll_odds.py to build line history</td></tr>'

    def sp_stat(val, label="", good="low"):
        if val is None:
            return '<span style="color:#94a3b8">N/A</span>'
        v = f"{val:.2f}" if isinstance(val, float) else str(val)
        return v

    home_hand_label = home_sp.get("hand", "")
    away_hand_label = away_sp.get("hand", "")
    home_sp_label = f'{home_sp_name} · {"RHP" if home_hand_label == "R" else "LHP" if home_hand_label == "L" else "SP"} - {home_abbr}'
    away_sp_label = f'{away_sp_name} · {"RHP" if away_hand_label == "R" else "LHP" if away_hand_label == "L" else "SP"} - {away_abbr}'

    pitch_rows = ""
    metrics = [
        ("SEASON ERA", "era", home_sp.get("era"), away_sp.get("era")),
        ("WHIP", "whip", home_sp.get("whip"), away_sp.get("whip")),
        ("xERA", "xera", home_sp.get("xera"), away_sp.get("xera")),
        ("K/9", "k9", home_sp.get("k9"), away_sp.get("k9"), "high"),
        ("FIP", "fip", home_sp.get("fip"), away_sp.get("fip")),
    ]
    for row in metrics:
        label, key = row[0], row[1]
        hv, av = row[2], row[3]
        higher_is_better = len(row) > 4 and row[4] == "high"
        if hv is not None and av is not None:
            h_better = hv < av if not higher_is_better else hv > av
            a_better = av < hv if not higher_is_better else av > hv
        else:
            h_better = a_better = False
        hc = 'style="color:#22c55e;font-weight:700"' if h_better else ""
        ac = 'style="color:#22c55e;font-weight:700"' if a_better else ""
        pitch_rows += f'<tr><td {hc}>{sp_stat(hv)}</td><td class="stat-label">{label}</td><td {ac}>{sp_stat(av)}</td></tr>'

    picks_html = ""
    for p in picks:
        picks_html += render_pick_row(p, p["rank"])

    if sgp:
        l1 = sgp["leg1"]
        l2 = sgp["leg2"]
        sgp_ev_col = "#22c55e" if sgp["ev"] > 10 else "#f59e0b"
        sgp_html = f"""
        <div class="sgp-panel">
          <div class="sgp-header">FEATURED 2-LEG SAME GAME PARLAY (SGP)</div>
          <div class="sgp-legs">
            <div class="sgp-leg">
              <div class="leg-label">LEG 1</div>
              <div class="leg-pick">{l1['team']}</div>
              <div class="leg-line">{l1['best_line']}</div>
            </div>
            <div class="sgp-plus">+</div>
            <div class="sgp-leg">
              <div class="leg-label">LEG 2</div>
              <div class="leg-pick">{l2['team']}</div>
              <div class="leg-line">{l2['best_line']}</div>
            </div>
          </div>
          <div class="sgp-stats">
            <div class="sgp-stat"><span class="sgp-stat-label">COMBINED PARLAY ODDS</span><span class="sgp-stat-val gold">{sgp['market_line']}</span></div>
            <div class="sgp-stat"><span class="sgp-stat-label">FAIR WIN PROBABILITY</span><span class="sgp-stat-val">{sgp['combined_prob']}%</span></div>
            <div class="sgp-stat"><span class="sgp-stat-label">FAIR LINE</span><span class="sgp-stat-val">{sgp['fair_line']}</span></div>
            <div class="sgp-stat"><span class="sgp-stat-label">COMBINED PARLAY EV</span><span class="sgp-stat-val" style="color:{sgp_ev_col}">+{sgp['ev']}%</span></div>
          </div>
        </div>"""
    else:
        sgp_html = '<div class="sgp-panel"><div class="sgp-header">SGP analysis pending picks generation</div></div>'

    if picks:
        overall_edge_team = picks[0]["team"].split()[0]
        biggest_edge_desc = picks[0]["description"]
    else:
        overall_edge_team = home_abbr
        biggest_edge_desc = "See picks below"

    top_pick_summary = (
        f'Sharp action focused on <strong>{picks[0]["description"]}</strong> '
        f'and <strong>{picks[1]["description"] if len(picks) > 1 else "value plays"}</strong>.'
        if picks
        else "Generating analysis..."
    )

    away_name_parts = away_full.split()
    home_name_parts = home_full.split()
    away_city = " ".join(away_name_parts[:-1])
    away_mascot = away_name_parts[-1]
    home_city = " ".join(home_name_parts[:-1])
    home_mascot = home_name_parts[-1]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{away_abbr} @ {home_abbr} — Sharp Movement Card</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #060e1a; color: #e2e8f0; font-family: 'Segoe UI', Arial, sans-serif; padding: 16px; }}
  .card {{ background: #0a1628; border: 2px solid #d4af37; border-radius: 12px; max-width: 1200px; margin: 0 auto; overflow: hidden; box-shadow: 0 0 40px rgba(212,175,55,0.15); }}

  /* ── Header ── */
  .header {{ background: linear-gradient(135deg, #060e1a 0%, #0f2040 50%, #060e1a 100%); padding: 24px 32px 16px; text-align: center; border-bottom: 2px solid #d4af3733; position: relative; }}
  .header-logos {{ display: flex; align-items: center; justify-content: center; gap: 24px; }}
  .team-logo {{ width: 72px; height: 72px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 900; letter-spacing: 1px; }}
  .team-logo.away {{ background: #1a1a2e; border: 2px solid #6b7280; color: #e2e8f0; }}
  .team-logo.home {{ background: #1a3a5c; border: 2px solid #d4af37; color: #d4af37; }}
  .header-title {{ flex: 1; }}
  .matchup-line {{ font-size: 13px; color: #94a3b8; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 4px; }}
  .team-names {{ font-size: 28px; font-weight: 900; letter-spacing: 2px; line-height: 1.1; }}
  .team-names .away-name {{ color: #cbd5e1; }}
  .team-names .vs {{ color: #d4af37; font-size: 18px; margin: 0 8px; }}
  .team-names .home-name {{ color: #ffd700; }}
  .subtitle {{ color: #d4af37; font-size: 14px; letter-spacing: 4px; margin-top: 6px; }}
  .header-tags {{ display: flex; gap: 8px; justify-content: center; margin-top: 10px; }}
  .tag {{ background: #1e3a5f; border: 1px solid #3b82f666; color: #93c5fd; font-size: 11px; padding: 3px 10px; border-radius: 12px; letter-spacing: 1px; }}

  /* ── Game info bar ── */
  .game-info {{ display: flex; gap: 0; background: #0d1f38; border-bottom: 1px solid #d4af3722; }}
  .game-info-item {{ flex: 1; padding: 10px 16px; text-align: center; border-right: 1px solid #1e3a5f; }}
  .game-info-item:last-child {{ border-right: none; }}
  .gi-label {{ font-size: 9px; color: #64748b; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 2px; }}
  .gi-value {{ font-size: 13px; font-weight: 700; color: #e2e8f0; }}

  /* ── Main grid ── */
  .main-grid {{ display: grid; grid-template-columns: 1fr 1.4fr 1fr; gap: 0; border-bottom: 1px solid #1e3a5f; }}
  .section {{ padding: 16px; border-right: 1px solid #1e3a5f; }}
  .section:last-child {{ border-right: none; }}
  .section-title {{ font-size: 11px; letter-spacing: 2px; color: #d4af37; text-transform: uppercase; border-bottom: 1px solid #d4af3733; padding-bottom: 6px; margin-bottom: 10px; font-weight: 700; }}

  /* Executive summary */
  .bullet {{ font-size: 12.5px; color: #cbd5e1; margin-bottom: 8px; line-height: 1.4; display: flex; gap: 6px; }}
  .check {{ color: #d4af37; flex-shrink: 0; }}

  /* Line movement */
  .mov-table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  .mov-table th {{ color: #64748b; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 4px 6px; text-align: center; }}
  .mov-table td {{ padding: 5px 6px; text-align: center; color: #cbd5e1; border-top: 1px solid #1e3a5f; }}
  .mov-time {{ color: #94a3b8; font-size: 10.5px; text-align: left !important; }}

  /* Pitching matchup */
  .pitch-header {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
  .pitch-sp {{ font-size: 11px; font-weight: 700; color: #d4af37; text-align: center; }}
  .pitch-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .pitch-table td {{ padding: 5px 8px; border-top: 1px solid #1e3a5f15; text-align: center; }}
  .stat-label {{ color: #64748b; font-size: 10px; letter-spacing: 1px; }}
  .overall-edge {{ text-align: center; margin-top: 10px; padding: 8px; background: #0f2040; border-radius: 6px; border: 1px solid #d4af3744; }}
  .edge-label {{ font-size: 10px; color: #64748b; letter-spacing: 1px; }}
  .edge-team {{ font-size: 20px; font-weight: 900; color: #ffd700; }}

  /* ── Picks section ── */
  .picks-section {{ padding: 20px; }}
  .picks-title {{ text-align: center; font-size: 15px; font-weight: 900; color: #d4af37; letter-spacing: 3px; margin-bottom: 16px; }}
  .picks-table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
  .picks-table th {{ background: #0d1f38; color: #64748b; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; padding: 8px 10px; text-align: left; border-bottom: 1px solid #1e3a5f; }}
  .picks-table th.num {{ text-align: center; }}
  .picks-table td {{ padding: 10px 10px; border-bottom: 1px solid #1e3a5f33; vertical-align: middle; }}
  .picks-table tr:hover td {{ background: #0f2040; }}
  .medal {{ font-size: 20px; text-align: center; width: 36px; }}
  .pick-desc {{ font-weight: 700; color: #e2e8f0; margin-bottom: 2px; }}
  .pick-odds {{ font-size: 11px; color: #94a3b8; }}
  .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; white-space: nowrap; }}
  .num {{ text-align: center; }}
  .ev-cell {{ font-size: 13px; }}
  .note-cell {{ font-size: 11px; color: #94a3b8; max-width: 200px; }}

  /* ── Bottom row ── */
  .bottom-row {{ display: grid; grid-template-columns: 1fr auto; border-top: 1px solid #1e3a5f; }}
  .sharp-action {{ padding: 16px 24px; display: flex; align-items: center; gap: 16px; }}
  .sharp-icons {{ display: flex; gap: 12px; }}
  .sharp-icon {{ text-align: center; }}
  .sharp-icon div {{ font-size: 9px; color: #64748b; letter-spacing: 1px; margin-top: 2px; }}
  .sharp-action-text {{ font-size: 14px; font-weight: 900; color: #d4af37; letter-spacing: 2px; text-transform: uppercase; }}
  .sharp-action-text span {{ color: white; }}

  /* SGP Panel */
  .sgp-panel {{ background: #0d1f38; border-left: 1px solid #d4af3733; padding: 16px 20px; min-width: 280px; }}
  .sgp-header {{ font-size: 11px; font-weight: 900; color: #d4af37; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 12px; text-align: center; }}
  .sgp-legs {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
  .sgp-leg {{ flex: 1; background: #1a3a5c; border-radius: 6px; padding: 10px; text-align: center; border: 1px solid #3b82f655; }}
  .leg-label {{ font-size: 9px; color: #64748b; letter-spacing: 2px; margin-bottom: 4px; }}
  .leg-pick {{ font-size: 13px; font-weight: 900; color: #ffd700; }}
  .leg-line {{ font-size: 11px; color: #94a3b8; margin-top: 2px; }}
  .sgp-plus {{ font-size: 20px; color: #d4af37; font-weight: 900; }}
  .sgp-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }}
  .sgp-stat {{ background: #060e1a; border-radius: 4px; padding: 6px 8px; text-align: center; }}
  .sgp-stat-label {{ display: block; font-size: 9px; color: #64748b; letter-spacing: 1px; margin-bottom: 2px; }}
  .sgp-stat-val {{ font-size: 14px; font-weight: 900; color: #e2e8f0; }}
  .gold {{ color: #ffd700 !important; }}

  @media (max-width: 900px) {{
    .main-grid {{ grid-template-columns: 1fr; }}
    .section {{ border-right: none; border-bottom: 1px solid #1e3a5f; }}
    .bottom-row {{ grid-template-columns: 1fr; }}
    .game-info {{ flex-wrap: wrap; }}
  }}
</style>
</head>
<body>
<div class="card">

  <!-- Header -->
  <div class="header">
    <div class="header-logos">
      <div class="team-logo away">{away_abbr}</div>
      <div class="header-title">
        <div class="matchup-line">Sharp Movement & Best Bets</div>
        <div class="team-names">
          <span class="away-name">{away_city.upper()} {away_mascot.upper()}</span>
          <span class="vs">AT</span>
          <span class="home-name">{home_city.upper()} {home_mascot.upper()}</span>
        </div>
        <div class="subtitle">SHARP MOVEMENT &amp; BEST BETS </div>
        <div class="header-tags">
          <span class="tag">{league} {day_name.upper()} MATCHUP</span>
          <span class="tag">DATA-DRIVEN CARD</span>
        </div>
      </div>
      <div class="team-logo home">{home_abbr}</div>
    </div>
  </div>

  <!-- Game info bar -->
  <div class="game-info">
    <div class="game-info-item">
      <div class="gi-label">Date</div>
      <div class="gi-value">{display_date}</div>
    </div>
    <div class="game-info-item">
      <div class="gi-label">First Pitch</div>
      <div class="gi-value">⏰ {first_pitch}</div>
    </div>
    <div class="game-info-item">
      <div class="gi-label">Venue</div>
      <div class="gi-value">{venue}</div>
    </div>
    <div class="game-info-item">
      <div class="gi-label">Records</div>
      <div class="gi-value">{away_abbr} ({away_record}) @ {home_abbr} ({home_record})</div>
    </div>
  </div>

  <!-- Main 3-column grid -->
  <div class="main-grid">

    <!-- Executive Summary -->
    <div class="section">
      <div class="section-title">Executive Summary</div>
      {bullets_html}
    </div>

    <!-- Line Movement -->
    <div class="section">
      <div class="section-title">Historical Line Movement</div>
      <table class="mov-table">
        <thead>
          <tr>
            <th style="text-align:left">TIME</th>
            <th>{away_abbr} ML</th>
            <th>{home_abbr} ML</th>
            <th>TOTAL</th>
            <th>SPREAD</th>
            <th>SIGNAL</th>
          </tr>
        </thead>
        <tbody>{mov_rows}</tbody>
      </table>
    </div>

    <!-- Pitching Matchup -->
    <div class="section">
      <div class="section-title">Pitching Matchup</div>
      <div class="pitch-header">
        <div class="pitch-sp" style="flex:1">{home_sp_label}</div>
        <div class="pitch-sp" style="flex:1;color:#cbd5e1">{away_sp_label}</div>
      </div>
      <table class="pitch-table">
        <thead><tr>
          <th style="color:#d4af37">{home_abbr}</th>
          <th class="stat-label">METRIC</th>
          <th style="color:#94a3b8">{away_abbr}</th>
        </tr></thead>
        <tbody>{pitch_rows}</tbody>
      </table>
      <div class="overall-edge">
        <div class="edge-label">OVERALL EDGE</div>
        <div class="edge-team">{overall_edge_team}</div>
        <div style="font-size:10px;color:#94a3b8;margin-top:2px">{biggest_edge_desc[:40]}</div>
      </div>
    </div>
  </div>

  <!-- Picks section -->
  <div class="picks-section">
    <div class="picks-title">TOP RECOMMENDED PLAYS </div>
    <table class="picks-table">
      <thead>
        <tr>
          <th></th>
          <th>PICK</th>
          <th>CONFIDENCE</th>
          <th class="num">TRUE PROB</th>
          <th class="num">MKT IMPLIED</th>
          <th class="num">EV</th>
          <th class="num">FAIR LINE</th>
          <th class="num">SIZE</th>
          <th>NOTES</th>
        </tr>
      </thead>
      <tbody>
        {picks_html if picks_html else '<tr><td colspan="9" style="text-align:center;color:#64748b;padding:20px">No picks above threshold today</td></tr>'}
      </tbody>
    </table>
  </div>

  <!-- Bottom row -->
  <div class="bottom-row">
    <div class="sharp-action">
      <div class="sharp-icons">
        <div class="sharp-icon"><div>ADVANCED<br>METRICS</div></div>
        <div class="sharp-icon"><div>SHARP<br>MOVEMENT</div></div>
        <div class="sharp-icon"><div>VALUE<br>FOCUSED</div></div>
      </div>
      <div class="sharp-action-text">{top_pick_summary}</div>
    </div>
    {sgp_html}
  </div>

</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate sharp movement game card")
    parser.add_argument("--away", type=str, help="Away team abbreviation (e.g. CWS)")
    parser.add_argument("--home", type=str, help="Home team abbreviation (e.g. TB)")
    parser.add_argument("--date", type=str, help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    out_dir = Path("results/cards")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nFetching today's games...")
    games = fetch_todays_games()
    if not games:
        print("No games found. Check API key.")
        return

    target_game = None
    for g in games:
        h = TEAM_ABBR.get(g.get("home_team", ""), "")
        a = TEAM_ABBR.get(g.get("away_team", ""), "")
        if args.home and args.away:
            if h == args.home.upper() and a == args.away.upper():
                target_game = g
                break
        else:
            target_game = g
            break

    if not target_game:
        avail = [
            (
                TEAM_ABBR.get(g["away_team"], g["away_team"]),
                TEAM_ABBR.get(g["home_team"], g["home_team"]),
            )
            for g in games
        ]
        print(f"Game not found. Available today: {avail}")
        return

    home_full = target_game["home_team"]
    away_full = target_game["away_team"]
    home_abbr = TEAM_ABBR.get(home_full, home_full)
    away_abbr = TEAM_ABBR.get(away_full, away_full)
    event_id = target_game.get("event_id", "")
    print(f"  Found: {away_full} @ {home_full}  (id: {event_id})")

    home_record = get_team_record(home_abbr)
    away_record = get_team_record(away_abbr)

    print("Fetching probable pitchers...")
    probable = fetch_probable_pitchers(date_str)
    sp_info = probable.get((away_abbr, home_abbr), {})
    home_sp_id = sp_info.get("home_sp_id")
    away_sp_id = sp_info.get("away_sp_id")
    home_sp_name = sp_info.get("home_sp_name", "TBD")
    away_sp_name = sp_info.get("away_sp_name", "TBD")
    home_sp_hand = sp_info.get("home_sp_hand", "?")
    away_sp_hand = sp_info.get("away_sp_hand", "?")
    print(f"  Home: {home_sp_name} | Away: {away_sp_name}")

    print("Fetching pitcher stats...")
    home_sp = fetch_pitcher_season_stats(home_sp_id)
    away_sp = fetch_pitcher_season_stats(away_sp_id)
    home_sp["hand"] = home_sp_hand
    away_sp["hand"] = away_sp_hand
    print(
        f'  {home_sp_name}: ERA={home_sp.get("era")}  K/9={home_sp.get("k9")}  FIP={home_sp.get("fip")}'
    )
    print(
        f'  {away_sp_name}: ERA={away_sp.get("era")}  K/9={away_sp.get("k9")}  FIP={away_sp.get("fip")}'
    )

    home_stats = get_team_stats(home_abbr)
    away_stats = get_team_stats(away_abbr)

    home_sp_k = pitcher_k_model(home_sp, away_stats["bat_k_rate"])
    away_sp_k = pitcher_k_model(away_sp, home_stats["bat_k_rate"])
    print(f'  K model — {home_sp_name}: {home_sp_k["expected_k"]} projected Ks')
    print(f'  K model — {away_sp_name}: {away_sp_k["expected_k"]} projected Ks')

    print("Fetching player props...")
    props = fetch_player_props(event_id)
    n_k_props = len(props.get("pitcher_strikeouts", {}))
    n_tb_props = len(props.get("batter_total_bases", {}))
    print(f"  Pitcher K props: {n_k_props} pitchers | Batter TB props: {n_tb_props} batters")

    target_game["_home_sp_name"] = home_sp_name
    target_game["_away_sp_name"] = away_sp_name

    print("Evaluating picks...")
    picks = build_picks(
        target_game, props, home_sp, away_sp, home_sp_k, away_sp_k, home_stats, away_stats
    )
    print(f"  {len(picks)} picks above threshold")

    sgp = build_sgp(picks)

    movement = get_line_movement(event_id)
    print(f"  {len(movement)} line movement snapshots")

    exec_bullets = build_exec_summary(target_game, home_sp, away_sp, movement, home_abbr, away_abbr)

    first_pitch = sp_info.get("first_pitch", "See MLB.com")

    print("Generating card...")
    html = generate_html(
        home_abbr,
        away_abbr,
        target_game,
        home_sp,
        away_sp,
        home_sp_name,
        away_sp_name,
        picks,
        sgp,
        movement,
        exec_bullets,
        home_record,
        away_record,
        first_pitch=first_pitch,
        date_str=date_str,
    )

    out_path = out_dir / f"{date_str}_{away_abbr}_{home_abbr}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nCard saved to: {out_path}")
    print(f'   Open in browser: open "{out_path}"')


if __name__ == "__main__":
    main()
