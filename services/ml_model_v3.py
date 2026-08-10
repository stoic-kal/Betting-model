from datetime import date, datetime, timedelta

import numpy as np
import requests
from scipy.special import expit
from scipy.special import logit as scipy_logit

BETA_FIP = 0.22
BETA_RSG = 0.18
BETA_FORM = 0.35
BETA_BP = 0.15
BETA_WPCT = 0.28
BETA_LINEUP = 1.00
BETA_REST = 0.05
BETA_FATIGUE = 0.06
BETA_DEFENSE = 0.10
BETA_XERA = 0.08
BETA_PLATOON = 0.50
BETA_TRAVEL = 0.03


MODEL_SHRINK = 0.45


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

LEAGUE_AVG_FIP = 3.90
LEAGUE_AVG_RSG = 4.60
LEAGUE_AVG_WPCT = 0.500


_cache_date: str = ""
_ml_cache: dict = {}


def _maybe_clear_cache():
    global _cache_date, _ml_cache
    today = date.today().isoformat()
    if today != _cache_date:
        _ml_cache = {}
        _cache_date = today


def _fetch_pitcher_fip(pitcher_id) -> float:

    if pitcher_id is None:
        return LEAGUE_AVG_FIP
    _maybe_clear_cache()
    ck = f"fip_{pitcher_id}"
    if ck in _ml_cache:
        return _ml_cache[ck]
    try:
        r = requests.get(
            f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats",
            params={"stats": "season", "season": datetime.now().year, "group": "pitching"},
            timeout=8,
        )
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            _ml_cache[ck] = LEAGUE_AVG_FIP
            return LEAGUE_AVG_FIP
        s = splits[0].get("stat", {})
        ip = float(s.get("inningsPitched", 0) or 0)
        if ip < 5:
            _ml_cache[ck] = LEAGUE_AVG_FIP
            return LEAGUE_AVG_FIP
        hr = float(s.get("homeRunsAllowed", 0) or 0)
        bb = float(s.get("baseOnBalls", 0) or 0)
        so = float(s.get("strikeOuts", 0) or 0)
        fip = float(np.clip((13 * hr + 3 * bb - 2 * so) / max(ip, 0.1) + 3.10, 2.0, 6.5))
        print(f"    [ML] FIP ({pitcher_id}): {fip:.2f} ({ip:.0f}IP)")
    except Exception as e:
        print(f"     [ML] FIP error ({pitcher_id}): {e}")
        fip = LEAGUE_AVG_FIP
    _ml_cache[ck] = fip
    return fip


def _fetch_team_season_wpct(team_abbr: str) -> float:

    _maybe_clear_cache()
    ck = f"wpct_{team_abbr}"
    if ck in _ml_cache:
        return _ml_cache[ck]
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return LEAGUE_AVG_WPCT
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

        rs = requests.get(
            "https://statsapi.mlb.com/api/v1/standings",
            params={
                "leagueId": "103,104",
                "season": datetime.now().year,
                "standingsTypes": "regularSeason",
            },
            timeout=8,
        )
        for div in rs.json().get("records", []):
            for team_rec in div.get("teamRecords", []):
                if team_rec.get("team", {}).get("id") == team_id:
                    wins = float(team_rec.get("wins", 0) or 0)
                    losses = float(team_rec.get("losses", 0) or 0)
                    total = wins + losses
                    if total < 5:
                        _ml_cache[ck] = LEAGUE_AVG_WPCT
                        return LEAGUE_AVG_WPCT
                    wpct = float(np.clip(wins / total, 0.2, 0.8))
                    print(
                        f"    [ML] Season W% ({team_abbr}): {wpct:.3f} ({int(wins)}-{int(losses)})"
                    )
                    _ml_cache[ck] = wpct
                    return wpct
    except Exception as e:
        print(f"     [ML] Season W% error ({team_abbr}): {e}")
    _ml_cache[ck] = LEAGUE_AVG_WPCT
    return LEAGUE_AVG_WPCT


def _fetch_team_l10_wl(team_abbr: str, venue: str = "all") -> float:

    _maybe_clear_cache()
    ck = f"l10wl_{team_abbr}_{venue}"
    if ck in _ml_cache:
        return _ml_cache[ck]
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return 0.500
    try:
        today = date.today()
        lookback = 35 if venue != "all" else 22
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
        results = []
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

                team_score = int(home_score) if is_home else int(away_score)
                opp_score = int(away_score) if is_home else int(home_score)
                results.append(1 if team_score > opp_score else 0)

        recent = results[-10:]
        if len(recent) < 5:
            _ml_cache[ck] = 0.500
            return 0.500
        wl = float(np.clip(np.mean(recent), 0.1, 0.9))
        print(f"    [ML] L10 W% ({team_abbr} {venue}): {wl:.3f} over {len(recent)} games")
        _ml_cache[ck] = wl
        return wl
    except Exception as e:
        print(f"     [ML] L10 W% error ({team_abbr}): {e}")
        _ml_cache[ck] = 0.500
        return 0.500


def _fetch_team_venue_rsg(team_abbr: str, venue: str) -> float:

    _maybe_clear_cache()
    ck = f"rsg_{team_abbr}_{venue}"
    if ck in _ml_cache:
        return _ml_cache[ck]
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return LEAGUE_AVG_RSG
    try:
        today = date.today()
        start_dt = (today - timedelta(days=35)).strftime("%Y-%m-%d")
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
                if g.get("status", {}).get("codedGameState", "") != "F":
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

        if len(runs) < 5:
            _ml_cache[ck] = LEAGUE_AVG_RSG
            return LEAGUE_AVG_RSG
        rsg = float(np.clip(np.mean(runs[-10:]), 2.0, 8.0))
        print(f"    [ML] RS/G ({team_abbr} {venue}): {rsg:.2f} over {min(len(runs), 10)} games")
        _ml_cache[ck] = rsg
        return rsg
    except Exception as e:
        print(f"     [ML] RS/G error ({team_abbr}): {e}")
        _ml_cache[ck] = LEAGUE_AVG_RSG
        return LEAGUE_AVG_RSG


def _fetch_team_bullpen_era(team_abbr: str) -> float:

    _maybe_clear_cache()
    ck = f"bpera_{team_abbr}"
    if ck in _ml_cache:
        return _ml_cache[ck]
    LEAGUE_AVG_BP_ERA = 4.20
    team_id = TEAM_IDS.get(team_abbr)
    if not team_id:
        return LEAGUE_AVG_BP_ERA
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
            _ml_cache[ck] = LEAGUE_AVG_BP_ERA
            return LEAGUE_AVG_BP_ERA
        team_era = float(splits[0].get("stat", {}).get("era", 0) or 0)
        if team_era < 0.5 or team_era > 8.0:
            _ml_cache[ck] = LEAGUE_AVG_BP_ERA
            return LEAGUE_AVG_BP_ERA

        LEAGUE_SP_ERA = LEAGUE_AVG_FIP
        SP_FRAC, BP_FRAC = 5.5 / 9, 3.5 / 9
        bp_era = float(np.clip((team_era - SP_FRAC * LEAGUE_SP_ERA) / BP_FRAC, 2.5, 6.5))
        print(f"    [ML] BP ERA ({team_abbr}): {bp_era:.2f}")
        _ml_cache[ck] = bp_era
        return bp_era
    except Exception as e:
        print(f"     [ML] BP ERA error ({team_abbr}): {e}")
        _ml_cache[ck] = LEAGUE_AVG_BP_ERA
        return LEAGUE_AVG_BP_ERA


def compute_ml_prob(
    away_abbr: str,
    home_abbr: str,
    away_sp_id,
    home_sp_id,
    mkt_home: float,
    mkt_away: float,
    game_pk=None,
) -> dict:

    print(f"\n  ML model v3.3: {away_abbr} @ {home_abbr} | mkt_home={mkt_home:.3f}")

    home_fip = _fetch_pitcher_fip(home_sp_id)
    away_fip = _fetch_pitcher_fip(away_sp_id)

    fip_adv = float(np.clip(away_fip - home_fip, -3.0, 3.0))

    home_rsg = _fetch_team_venue_rsg(home_abbr, venue="home")
    away_rsg = _fetch_team_venue_rsg(away_abbr, venue="away")
    rsg_adv = float(np.clip(home_rsg - away_rsg, -3.0, 3.0))

    home_l10 = _fetch_team_l10_wl(home_abbr, venue="home")
    away_l10 = _fetch_team_l10_wl(away_abbr, venue="away")
    form_adv = float(np.clip(home_l10 - away_l10, -0.8, 0.8))

    home_bp_era = _fetch_team_bullpen_era(home_abbr)
    away_bp_era = _fetch_team_bullpen_era(away_abbr)

    bp_adv = float(np.clip(away_bp_era - home_bp_era, -3.0, 3.0))

    home_wpct = _fetch_team_season_wpct(home_abbr)
    away_wpct = _fetch_team_season_wpct(away_abbr)
    wpct_adv = float(np.clip(home_wpct - away_wpct, -0.4, 0.4))

    from services.game_context_service import get_game_context

    context = get_game_context(away_abbr, home_abbr, game_pk, away_sp_id, home_sp_id)
    lineup_adv = context["lineup_ops_adv"] if context["context_complete"] else 0.0
    rest_adv = float(np.clip(context["rest_adv"], -2, 2))
    fatigue_adv = float(np.clip(context["bullpen_fatigue_adv"], -2, 2))
    defense_adv = float(np.clip(context["defense_adv"], -1, 1))
    advanced = context.get("advanced", {})
    home_sc = advanced.get("home_pitcher_statcast", {})
    away_sc = advanced.get("away_pitcher_statcast", {})
    xera_adv = 0.0
    if home_sc.get("xera_proxy") is not None and away_sc.get("xera_proxy") is not None:
        xera_adv = float(np.clip(away_sc["xera_proxy"] - home_sc["xera_proxy"], -2.0, 2.0))
    platoon = advanced.get("lineup_handedness", {})
    home_platoon = platoon.get("home_vs_away_sp", {}).get("adjustment", 0) or 0
    away_platoon = platoon.get("away_vs_home_sp", {}).get("adjustment", 0) or 0
    platoon_adv = float(np.clip(home_platoon - away_platoon, -0.03, 0.03))
    travel_adv = float(np.clip(context.get("travel_timezone_adv", 0), -3, 3))

    mkt_home_c = float(np.clip(mkt_home, 0.05, 0.95))
    logit_market = scipy_logit(mkt_home_c)

    logit_model = (
        logit_market
        + BETA_FIP * fip_adv
        + BETA_RSG * rsg_adv
        + BETA_FORM * form_adv
        + BETA_BP * bp_adv
        + BETA_WPCT * wpct_adv
        + BETA_LINEUP * lineup_adv
        + BETA_REST * rest_adv
        + BETA_FATIGUE * fatigue_adv
        + BETA_DEFENSE * defense_adv
        + BETA_XERA * xera_adv
        + BETA_PLATOON * platoon_adv
        + BETA_TRAVEL * travel_adv
    )

    raw_model_home = float(expit(logit_model))

    model_home = (1 - MODEL_SHRINK) * raw_model_home + MODEL_SHRINK * mkt_home_c
    model_home = float(np.clip(model_home, 0.05, 0.95))

    def _squash_high_probability(probability):

        if probability <= 0.625:
            return probability
        if probability <= 0.65:
            return 0.625 + (probability - 0.625) * 0.40
        if probability <= 0.70:
            return 0.635 + (probability - 0.65) * 0.20
        return 0.645

    if model_home >= 0.5:
        model_home = _squash_high_probability(model_home)
    else:
        model_home = 1.0 - _squash_high_probability(1.0 - model_home)

    from services.model_learning_service import apply_active_calibration

    model_home = apply_active_calibration("moneyline", model_home, mkt_home_c)

    model_away = 1.0 - model_home

    logit_delta = logit_model - logit_market
    print(
        f"    logit: market={logit_market:.3f}, adj={logit_delta:+.3f} → model_home={model_home:.3f}"
    )
    print(
        f"    features: fip_adv={fip_adv:+.2f}, rsg_adv={rsg_adv:+.2f}, "
        f"form_adv={form_adv:+.3f}, bp_adv={bp_adv:+.2f}, wpct_adv={wpct_adv:+.3f}"
    )

    return {
        "model_home": round(model_home, 4),
        "model_away": round(model_away, 4),
        "logit_market": round(logit_market, 3),
        "logit_delta": round(logit_delta, 3),
        "features": {
            "home_fip": round(home_fip, 2),
            "away_fip": round(away_fip, 2),
            "fip_adv": round(fip_adv, 2),
            "home_rsg": round(home_rsg, 2),
            "away_rsg": round(away_rsg, 2),
            "rsg_adv": round(rsg_adv, 2),
            "home_l10_wl": round(home_l10, 3),
            "away_l10_wl": round(away_l10, 3),
            "form_adv": round(form_adv, 3),
            "home_bp_era": round(home_bp_era, 2),
            "away_bp_era": round(away_bp_era, 2),
            "bp_adv": round(bp_adv, 2),
            "home_wpct": round(home_wpct, 3),
            "away_wpct": round(away_wpct, 3),
            "wpct_adv": round(wpct_adv, 3),
            "xera_proxy_adv": round(xera_adv, 3),
            "platoon_proxy_adv": round(platoon_adv, 4),
            "travel_timezone_adv": round(travel_adv, 2),
            **context,
        },
    }
