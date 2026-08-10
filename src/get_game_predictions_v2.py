import sys

sys.path.insert(0, "src")

import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from config import ODDS_API_KEY

API_KEY = ODDS_API_KEY
MIN_BOOKS = 3


ML_MODEL_PATH = "models/lgbm_v2_moneyline.pkl"
TOTALS_MODEL_PATH = "models/lgbm_v2_totals.pkl"
FEATURES_PATH = "data/games_v2_features.csv"


_ml_model = None
_totals_bundle = None
_team_form = None
_park_factors = None


def _load_models():
    global _ml_model, _totals_bundle
    if _ml_model is None:
        if not Path(ML_MODEL_PATH).exists():
            raise FileNotFoundError(
                "v2 model not found. Run: python build_features_v2.py && python train_model_v2.py"
            )
        with open(ML_MODEL_PATH, "rb") as f:
            _ml_model = pickle.load(f)
        with open(TOTALS_MODEL_PATH, "rb") as f:
            _totals_bundle = pickle.load(f)


def _load_context():

    global _team_form, _park_factors
    if _team_form is not None:
        return

    if not Path(FEATURES_PATH).exists():
        _team_form = {}
        _park_factors = {}
        return

    df = pd.read_csv(FEATURES_PATH, parse_dates=["date"])
    df = df.sort_values("date")

    home_last = df.groupby("home_team").last()
    _team_form = {
        team: {
            "home_L10_wr": row.get("home_L10_wr", 0.5),
            "home_L10_runs_scored": row.get("home_L10_runs_scored", 4.5),
            "home_L10_runs_allowed": row.get("home_L10_runs_allowed", 4.5),
        }
        for team, row in home_last.iterrows()
    }

    away_last = df.groupby("away_team").last()
    for team, row in away_last.iterrows():
        if team not in _team_form:
            _team_form[team] = {}
        _team_form[team].update(
            {
                "away_L10_wr": row.get("away_L10_wr", 0.5),
                "away_L10_runs_scored": row.get("away_L10_runs_scored", 4.5),
                "away_L10_runs_allowed": row.get("away_L10_runs_allowed", 4.5),
            }
        )

    _park_factors = df.groupby("home_team")["park_factor"].mean().to_dict()


MLB_TEAM_MAP = {
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
    "Oakland Athletics": "OAK",
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


def fetch_probable_pitchers(date_str: str) -> dict:

    url = "https://statsapi.mlb.com/api/v1/schedule"
    try:
        r = requests.get(
            url,
            params={
                "sportId": 1,
                "date": date_str,
                "hydrate": "probablePitcher,team",
            },
            timeout=10,
        )
        data = r.json()
    except Exception as e:
        print(f"   MLB API error: {e}")
        return {}

    result = {}
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            home_info = g["teams"]["home"]
            away_info = g["teams"]["away"]
            home_abbr = MLB_TEAM_MAP.get(
                home_info["team"].get("name", ""), home_info["team"].get("abbreviation", "")
            )
            away_abbr = MLB_TEAM_MAP.get(
                away_info["team"].get("name", ""), away_info["team"].get("abbreviation", "")
            )
            result[(home_abbr, away_abbr)] = {
                "home_sp_id": home_info.get("probablePitcher", {}).get("id"),
                "home_sp_name": home_info.get("probablePitcher", {}).get("fullName", "TBD"),
                "away_sp_id": away_info.get("probablePitcher", {}).get("id"),
                "away_sp_name": away_info.get("probablePitcher", {}).get("fullName", "TBD"),
            }
    return result


PITCHER_FALLBACK = {
    "k_rate": 0.220,
    "bb_rate": 0.085,
    "fb_velo": 93.5,
    "hard_hit_pct": 0.360,
}

_pg_stats = None


def _load_pitcher_stats():
    global _pg_stats
    if _pg_stats is None:
        p = Path("data/pitcher_game_stats.csv")
        if p.exists():
            _pg_stats = pd.read_csv(p)
        else:
            _pg_stats = pd.DataFrame()
    return _pg_stats


def get_pitcher_features(pitcher_id) -> dict:
    pg = _load_pitcher_stats()
    if pg.empty or pitcher_id is None:
        return PITCHER_FALLBACK.copy()

    rows = pg[pg["pitcher"] == pitcher_id].tail(5)
    if rows.empty:
        return PITCHER_FALLBACK.copy()

    return {
        "k_rate": float(rows["k_rate"].mean()),
        "bb_rate": float(rows["bb_rate"].mean()),
        "fb_velo": (
            float(rows["fb_velo"].mean())
            if rows["fb_velo"].notna().any()
            else PITCHER_FALLBACK["fb_velo"]
        ),
        "hard_hit_pct": float(rows["hard_hit_pct"].mean()),
    }


def _market_probs(odds_a: list, odds_b: list):
    ra = np.mean([1.0 / o for o in odds_a])
    rb = np.mean([1.0 / o for o in odds_b])
    t = ra + rb
    return ra / t, rb / t


BLEND_MODEL = 0.70


def get_predictions_for_games():
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        _load_models()
        _load_context()
        use_v2 = True
        print("  Using LightGBM v2 with per-game pitcher features")
    except FileNotFoundError as e:
        print(f"   {e}")
        print("  → Falling back to market-implied EV detection")
        use_v2 = False

    probable = fetch_probable_pitchers(today) if use_v2 else {}
    print(f"  MLB API: {len(probable)} matchups with probable pitchers")

    default_park = np.mean(list(_park_factors.values())) if _park_factors else 9.0

    try:
        resp = requests.get(
            "https://api.theoddsapi.com/odds/",
            headers={"x-api-key": API_KEY},
            params={"sport_key": "baseball_mlb", "markets": "h2h,totals", "oddsFormat": "decimal"},
            timeout=10,
        )
        games_data = resp.json().get("data", [])
    except Exception as e:
        print(f"  TheOddsAPI error: {e}")
        return []

    predictions = []

    for game in games_data:
        try:
            home_team = game["home_team"]
            away_team = game["away_team"]
            matchup = f"{away_team} @ {home_team}"

            home_odds_list = []
            away_odds_list = []
            totals_by_line: dict = {}

            for book in game.get("books", []):
                mkt = book.get("market")
                if mkt == "h2h":
                    for o in book.get("outcomes", []):
                        p = o.get("price")
                        if p is not None:
                            (
                                home_odds_list if o.get("name") == home_team else away_odds_list
                            ).append(float(p))
                elif mkt == "totals":
                    for o in book.get("outcomes", []):
                        pt, p, n = o.get("point"), o.get("price"), o.get("name")
                        if all(x is not None for x in [pt, p, n]):
                            ln = float(pt)
                            totals_by_line.setdefault(ln, {"over": [], "under": []})
                            if n == "Over":
                                totals_by_line[ln]["over"].append(float(p))
                            elif n == "Under":
                                totals_by_line[ln]["under"].append(float(p))

            if len(home_odds_list) < MIN_BOOKS or len(away_odds_list) < MIN_BOOKS:
                continue

            fair_home = np.mean(home_odds_list)
            fair_away = np.mean(away_odds_list)

            if use_v2:

                sp_info = probable.get((home_team, away_team), {})
                home_sp = get_pitcher_features(sp_info.get("home_sp_id"))
                away_sp = get_pitcher_features(sp_info.get("away_sp_id"))
                sp_label = (
                    f"{sp_info.get('home_sp_name','TBD')} vs "
                    f"{sp_info.get('away_sp_name','TBD')}"
                )

                hf = _team_form.get(home_team, {})
                af = _team_form.get(away_team, {})
                park_f = _park_factors.get(home_team, default_park)

                ml_X = np.array(
                    [
                        [
                            home_sp["k_rate"],
                            home_sp["bb_rate"],
                            home_sp["fb_velo"],
                            home_sp["hard_hit_pct"],
                            away_sp["k_rate"],
                            away_sp["bb_rate"],
                            away_sp["fb_velo"],
                            away_sp["hard_hit_pct"],
                            hf.get("home_L10_wr", 0.5),
                            af.get("away_L10_wr", 0.5),
                            hf.get("home_L10_runs_scored", 4.5),
                            hf.get("home_L10_runs_allowed", 4.5),
                            af.get("away_L10_runs_scored", 4.5),
                            af.get("away_L10_runs_allowed", 4.5),
                            park_f,
                        ]
                    ],
                    dtype=np.float64,
                )

                model_home_p = float(_ml_model.predict_proba(ml_X)[0, 1])
                mkt_home_p, mkt_away_p = _market_probs(home_odds_list, away_odds_list)

                home_prob = BLEND_MODEL * model_home_p + (1 - BLEND_MODEL) * mkt_home_p
                away_prob = 1.0 - home_prob

            else:
                home_prob, away_prob = _market_probs(home_odds_list, away_odds_list)
                sp_label = "market-implied"

            home_ev = (home_prob * fair_home) - 1
            away_ev = (away_prob * fair_away) - 1

            if home_ev > away_ev and home_ev > 0.01:
                predictions.append(
                    {
                        "date": today,
                        "game_id": game.get("event_id"),
                        "matchup": matchup,
                        "ml_prob": round(home_prob, 4),
                        "ml_home_odds": fair_home,
                        "ml_away_odds": fair_away,
                        "line": None,
                        "over_odds": None,
                        "under_odds": None,
                        "expected_runs": None,
                        "totals_prob": None,
                        "ev_pct": round(home_ev * 100, 2),
                        "starters": sp_label,
                    }
                )
            elif away_ev > 0.01:
                predictions.append(
                    {
                        "date": today,
                        "game_id": game.get("event_id"),
                        "matchup": matchup,
                        "ml_prob": round(away_prob, 4),
                        "ml_home_odds": fair_home,
                        "ml_away_odds": fair_away,
                        "line": None,
                        "over_odds": None,
                        "under_odds": None,
                        "expected_runs": None,
                        "totals_prob": None,
                        "ev_pct": round(away_ev * 100, 2),
                        "starters": sp_label,
                    }
                )

            for line, odds in totals_by_line.items():
                if len(odds["over"]) < MIN_BOOKS or len(odds["under"]) < MIN_BOOKS:
                    continue

                fair_over = np.mean(odds["over"])
                fair_under = np.mean(odds["under"])

                if use_v2:
                    tot_X = np.array(
                        [
                            [
                                home_sp["k_rate"],
                                home_sp["bb_rate"],
                                home_sp["fb_velo"],
                                home_sp["hard_hit_pct"],
                                away_sp["k_rate"],
                                away_sp["bb_rate"],
                                away_sp["fb_velo"],
                                away_sp["hard_hit_pct"],
                                hf.get("home_L10_runs_scored", 4.5),
                                hf.get("home_L10_runs_allowed", 4.5),
                                af.get("away_L10_runs_scored", 4.5),
                                af.get("away_L10_runs_allowed", 4.5),
                                park_f,
                            ]
                        ],
                        dtype=np.float64,
                    )

                    model_over_raw = float(_totals_bundle["model"].predict_proba(tot_X)[0, 1])
                    median_total = _totals_bundle["median_total"]

                    line_delta = line - median_total
                    model_over = float(np.clip(model_over_raw - 0.04 * line_delta, 0.30, 0.70))
                    model_under = 1.0 - model_over

                    mkt_over, mkt_under = _market_probs(odds["over"], odds["under"])
                    over_prob = BLEND_MODEL * model_over + (1 - BLEND_MODEL) * mkt_over
                    under_prob = 1.0 - over_prob
                else:
                    over_prob, under_prob = _market_probs(odds["over"], odds["under"])

                over_ev = (over_prob * fair_over) - 1
                under_ev = (under_prob * fair_under) - 1

                if over_ev > under_ev and over_ev > 0.01:
                    predictions.append(
                        {
                            "date": today,
                            "game_id": game.get("event_id"),
                            "matchup": matchup,
                            "ml_prob": None,
                            "ml_home_odds": None,
                            "ml_away_odds": None,
                            "line": line,
                            "over_odds": fair_over,
                            "under_odds": fair_under,
                            "expected_runs": None,
                            "totals_prob": round(over_prob, 4),
                            "ev_pct": round(over_ev * 100, 2),
                            "starters": sp_label,
                        }
                    )
                elif under_ev > 0.01:
                    predictions.append(
                        {
                            "date": today,
                            "game_id": game.get("event_id"),
                            "matchup": matchup,
                            "ml_prob": None,
                            "ml_home_odds": None,
                            "ml_away_odds": None,
                            "line": line,
                            "over_odds": fair_over,
                            "under_odds": fair_under,
                            "expected_runs": None,
                            "totals_prob": round(under_prob, 4),
                            "ev_pct": round(under_ev * 100, 2),
                            "starters": sp_label,
                        }
                    )

        except Exception as e:
            print(f"   Game error: {e}")
            continue

    return predictions
