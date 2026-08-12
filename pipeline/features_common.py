import numpy as np

FIP_CONSTANT = 3.10
LEAGUE_AVG_TOTAL_RUNS_PRIOR = 8.5
LEAGUE_AVG_FIP = 3.90
LEAGUE_AVG_K_RATE = 0.225
LEAGUE_AVG_BB_RATE = 0.085
LEAGUE_AVG_HR_RATE = 0.030
LEAGUE_AVG_HARD_HIT_PCT = 0.38
LEAGUE_AVG_FB_VELO = 93.5
LEAGUE_AVG_XWOBA_AGAINST = 0.315
LEAGUE_AVG_BAT_ISO = 0.150
LEAGUE_AVG_BAT_WOBA = 0.315
LEAGUE_AVG_L10_RS = 4.5
LEAGUE_AVG_L10_RA = 4.5
LEAGUE_AVG_L10_WR = 0.5
FASTBALL_TYPES = {"FF", "SI", "FC"}

STADIUMS = {
    "ARI": {"lat": 33.446, "lon": -112.067, "dome": 0.5, "cf_deg": 0},
    "ATH": {"lat": 37.752, "lon": -122.201, "dome": 0, "cf_deg": 225},
    "ATL": {"lat": 33.891, "lon": -84.468, "dome": 0, "cf_deg": 35},
    "BAL": {"lat": 39.284, "lon": -76.622, "dome": 0, "cf_deg": 80},
    "BOS": {"lat": 42.347, "lon": -71.097, "dome": 0, "cf_deg": 95},
    "CHC": {"lat": 41.948, "lon": -87.656, "dome": 0, "cf_deg": 95},
    "CIN": {"lat": 39.097, "lon": -84.507, "dome": 0, "cf_deg": 10},
    "CLE": {"lat": 41.496, "lon": -81.685, "dome": 0, "cf_deg": 55},
    "COL": {"lat": 39.756, "lon": -104.994, "dome": 0, "cf_deg": 35},
    "CWS": {"lat": 41.830, "lon": -87.634, "dome": 0, "cf_deg": 55},
    "DET": {"lat": 42.339, "lon": -83.049, "dome": 0, "cf_deg": 30},
    "HOU": {"lat": 29.757, "lon": -95.356, "dome": 0.5, "cf_deg": 15},
    "KC": {"lat": 39.051, "lon": -94.480, "dome": 0, "cf_deg": 45},
    "LAA": {"lat": 33.800, "lon": -117.883, "dome": 0, "cf_deg": 45},
    "LAD": {"lat": 34.074, "lon": -118.240, "dome": 0, "cf_deg": 45},
    "MIA": {"lat": 25.778, "lon": -80.220, "dome": 0.5, "cf_deg": 90},
    "MIL": {"lat": 43.029, "lon": -87.971, "dome": 0.5, "cf_deg": 340},
    "MIN": {"lat": 44.982, "lon": -93.278, "dome": 0, "cf_deg": 5},
    "NYM": {"lat": 40.757, "lon": -73.846, "dome": 0, "cf_deg": 50},
    "NYY": {"lat": 40.829, "lon": -73.926, "dome": 0, "cf_deg": 35},
    "PHI": {"lat": 39.906, "lon": -75.167, "dome": 0, "cf_deg": 45},
    "PIT": {"lat": 40.447, "lon": -80.006, "dome": 0, "cf_deg": 320},
    "SD": {"lat": 32.707, "lon": -117.157, "dome": 0, "cf_deg": 315},
    "SEA": {"lat": 47.591, "lon": -122.332, "dome": 0.5, "cf_deg": 350},
    "SF": {"lat": 37.778, "lon": -122.389, "dome": 0, "cf_deg": 90},
    "STL": {"lat": 38.623, "lon": -90.193, "dome": 0, "cf_deg": 35},
    "TB": {"lat": 27.768, "lon": -82.653, "dome": 1, "cf_deg": 0},
    "TEX": {"lat": 32.751, "lon": -97.083, "dome": 0.5, "cf_deg": 45},
    "TOR": {"lat": 43.641, "lon": -79.389, "dome": 0.5, "cf_deg": 35},
    "WSH": {"lat": 38.873, "lon": -77.008, "dome": 0, "cf_deg": 35},
}

ML_FEATURES = [
    "home_k_rate", "home_bb_rate", "home_hr_rate", "home_hard_hit_pct", "home_fb_velo",
    "home_xwoba_against", "home_fip", "home_is_lefty", "home_days_rest",
    "away_k_rate", "away_bb_rate", "away_hr_rate", "away_hard_hit_pct", "away_fb_velo",
    "away_xwoba_against", "away_fip", "away_is_lefty", "away_days_rest",
    "home_bat_k_rate", "home_bat_hard_hit_pct", "home_bat_iso", "home_bat_woba",
    "away_bat_k_rate", "away_bat_hard_hit_pct", "away_bat_iso", "away_bat_woba",
    "home_L10_wr", "home_L10_rs", "home_L10_ra", "away_L10_wr", "away_L10_rs", "away_L10_ra",
    "park_factor", "is_dome", "is_coors", "temp_f", "wind_mph", "wind_out_factor",
]

TOTALS_FEATURES = [f for f in ML_FEATURES if f not in ("home_is_lefty", "away_is_lefty", "home_L10_wr", "away_L10_wr")]

LINEUP_STRENGTH_FEATURES = [
    "home_lineup_woba", "home_lineup_iso", "home_lineup_ops", "home_lineup_xrc_proxy",
    "home_lineup_lr_balance", "home_lineup_quality",
    "away_lineup_woba", "away_lineup_iso", "away_lineup_ops", "away_lineup_xrc_proxy",
    "away_lineup_lr_balance", "away_lineup_quality",
]

PLATOON_MATCHUP_FEATURES = [
    "home_lineup_woba_vs_pitcher_hand", "home_lineup_iso_vs_pitcher_hand",
    "home_lineup_k_rate_vs_pitcher_hand", "home_lineup_bb_rate_vs_pitcher_hand",
    "home_lineup_hard_hit_vs_pitcher_hand",
    "away_lineup_woba_vs_pitcher_hand", "away_lineup_iso_vs_pitcher_hand",
    "away_lineup_k_rate_vs_pitcher_hand", "away_lineup_bb_rate_vs_pitcher_hand",
    "away_lineup_hard_hit_vs_pitcher_hand",
]

LINEUP_HANDEDNESS_INTERACTION_FEATURES = [
    "home_lineup_strength_vs_pitcher_hand", "home_platoon_advantage_score",
    "away_lineup_strength_vs_pitcher_hand", "away_platoon_advantage_score",
]

BULLPEN_FATIGUE_FEATURES = [
    "home_bullpen_appearances_3d", "home_bullpen_pitches_3d", "home_bullpen_bf_3d", "home_bullpen_high_lev_ip_3d",
    "home_bullpen_appearances_5d", "home_bullpen_pitches_5d", "home_bullpen_bf_5d", "home_bullpen_high_lev_ip_5d",
    "home_bullpen_appearances_7d", "home_bullpen_pitches_7d", "home_bullpen_bf_7d", "home_bullpen_high_lev_ip_7d",
    "home_bullpen_fatigue_score", "home_bullpen_availability_score",
    "away_bullpen_appearances_3d", "away_bullpen_pitches_3d", "away_bullpen_bf_3d", "away_bullpen_high_lev_ip_3d",
    "away_bullpen_appearances_5d", "away_bullpen_pitches_5d", "away_bullpen_bf_5d", "away_bullpen_high_lev_ip_5d",
    "away_bullpen_appearances_7d", "away_bullpen_pitches_7d", "away_bullpen_bf_7d", "away_bullpen_high_lev_ip_7d",
    "away_bullpen_fatigue_score", "away_bullpen_availability_score",
]

BULLPEN_QUALITY_FEATURES = [
    "home_bullpen_era_7d", "home_bullpen_era_14d", "home_bullpen_era_30d", "home_bullpen_era_season",
    "home_bullpen_fip_7d", "home_bullpen_fip_14d", "home_bullpen_fip_30d", "home_bullpen_fip_season",
    "home_bullpen_whip_7d", "home_bullpen_whip_14d", "home_bullpen_whip_30d", "home_bullpen_whip_season",
    "home_bullpen_k_rate_7d", "home_bullpen_k_rate_14d", "home_bullpen_k_rate_30d", "home_bullpen_k_rate_season",
    "home_bullpen_bb_rate_7d", "home_bullpen_bb_rate_14d", "home_bullpen_bb_rate_30d", "home_bullpen_bb_rate_season",
    "home_bullpen_hr_rate_7d", "home_bullpen_hr_rate_14d", "home_bullpen_hr_rate_30d", "home_bullpen_hr_rate_season",
    "away_bullpen_era_7d", "away_bullpen_era_14d", "away_bullpen_era_30d", "away_bullpen_era_season",
    "away_bullpen_fip_7d", "away_bullpen_fip_14d", "away_bullpen_fip_30d", "away_bullpen_fip_season",
    "away_bullpen_whip_7d", "away_bullpen_whip_14d", "away_bullpen_whip_30d", "away_bullpen_whip_season",
    "away_bullpen_k_rate_7d", "away_bullpen_k_rate_14d", "away_bullpen_k_rate_30d", "away_bullpen_k_rate_season",
    "away_bullpen_bb_rate_7d", "away_bullpen_bb_rate_14d", "away_bullpen_bb_rate_30d", "away_bullpen_bb_rate_season",
    "away_bullpen_hr_rate_7d", "away_bullpen_hr_rate_14d", "away_bullpen_hr_rate_30d", "away_bullpen_hr_rate_season",
    "home_bullpen_xfip_7d", "home_bullpen_xfip_14d", "home_bullpen_xfip_30d", "home_bullpen_xfip_season",
    "away_bullpen_xfip_7d", "away_bullpen_xfip_14d", "away_bullpen_xfip_30d", "away_bullpen_xfip_season",
]

PHASE3_INTERACTION_FEATURES = [
    "home_fb_rate_x_wind_out", "away_fb_rate_x_wind_out",
    "home_bullpen_fatigue_x_sp_innings_remaining_x_rest", "away_bullpen_fatigue_x_sp_innings_remaining_x_rest",
    "wind_park_directional_factor",
    "home_pitch_mix_x_lineup_matchup", "away_pitch_mix_x_lineup_matchup",
]

CONTEXT_FEATURES = (
    LINEUP_STRENGTH_FEATURES
    + PLATOON_MATCHUP_FEATURES
    + LINEUP_HANDEDNESS_INTERACTION_FEATURES
    + BULLPEN_FATIGUE_FEATURES
    + BULLPEN_QUALITY_FEATURES
    + PHASE3_INTERACTION_FEATURES
)

STATCAST_REAL_CONTEXT_FEATURES = (
    [f"{side}_bullpen_{stat}_{window}"
     for side in ("home", "away")
     for stat in ("era", "fip", "xfip", "whip")
     for window in ("30d", "season")]
    + [f"{side}_bullpen_{stat}_season"
       for side in ("home", "away")
       for stat in ("k_rate", "bb_rate", "hr_rate")]
    + [f"{side}_bullpen_{stat}" for side in ("home", "away")
       for stat in ("fatigue_score", "availability_score", "pitches_7d")]
    + PLATOON_MATCHUP_FEATURES
    + LINEUP_HANDEDNESS_INTERACTION_FEATURES
    + ["home_fb_rate_x_wind_out", "away_fb_rate_x_wind_out",
       "home_bullpen_fatigue_x_sp_innings_remaining_x_rest", "away_bullpen_fatigue_x_sp_innings_remaining_x_rest",
       "home_pitch_mix_x_lineup_matchup", "away_pitch_mix_x_lineup_matchup"]
)

ML_FEATURES_EXPANDED = ML_FEATURES + STATCAST_REAL_CONTEXT_FEATURES
TOTALS_FEATURES_EXPANDED = TOTALS_FEATURES + STATCAST_REAL_CONTEXT_FEATURES

FEATURE_SCHEMA_VERSION = "v2.3"

FEATURE_BOUNDS = {
    "k_rate": (0.0, 1.0),
    "bb_rate": (0.0, 1.0),
    "hr_rate": (0.0, 1.0),
    "hard_hit_pct": (0.0, 1.0),
    "fb_velo": (75.0, 105.0),
    "xwoba_against": (0.0, 0.8),
    "fip": (0.0, 15.0),
    "is_lefty": (0.0, 1.0),
    "days_rest": (0.0, 30.0),
    "bat_k_rate": (0.0, 1.0),
    "bat_hard_hit_pct": (0.0, 1.0),
    "bat_iso": (0.0, 1.0),
    "bat_woba": (0.0, 0.8),
    "L10_wr": (0.0, 1.0),
    "L10_rs": (0.0, 20.0),
    "L10_ra": (0.0, 20.0),
    "park_factor": (2.0, 20.0),
    "is_dome": (0.0, 1.0),
    "is_coors": (0.0, 1.0),
    "temp_f": (-20.0, 130.0),
    "wind_mph": (0.0, 60.0),
    "wind_out_factor": (-1.0, 1.0),
}


MAX_BULLPEN_APPEARANCES_PER_DAY = 10.0
MAX_BULLPEN_PITCHES_PER_DAY = 130.0
MAX_BULLPEN_BF_PER_DAY = 50.0
MAX_BULLPEN_HIGH_LEV_IP_PER_DAY = 5.0

for _days in (3, 5, 7):
    _window = f"{_days}d"
    FEATURE_BOUNDS[f"bullpen_appearances_{_window}"] = (0.0, MAX_BULLPEN_APPEARANCES_PER_DAY * _days)
    FEATURE_BOUNDS[f"bullpen_pitches_{_window}"] = (0.0, MAX_BULLPEN_PITCHES_PER_DAY * _days)
    FEATURE_BOUNDS[f"bullpen_bf_{_window}"] = (0.0, MAX_BULLPEN_BF_PER_DAY * _days)
    FEATURE_BOUNDS[f"bullpen_high_lev_ip_{_window}"] = (0.0, MAX_BULLPEN_HIGH_LEV_IP_PER_DAY * _days)

for _window in ("7d", "14d", "30d", "season"):
    FEATURE_BOUNDS[f"bullpen_era_{_window}"] = (0.0, 15.0)
    FEATURE_BOUNDS[f"bullpen_xfip_{_window}"] = (0.0, 15.0)
    FEATURE_BOUNDS[f"bullpen_fip_{_window}"] = (0.0, 15.0)
    FEATURE_BOUNDS[f"bullpen_whip_{_window}"] = (0.0, 5.0)
    FEATURE_BOUNDS[f"bullpen_k_rate_{_window}"] = (0.0, 1.0)
    FEATURE_BOUNDS[f"bullpen_bb_rate_{_window}"] = (0.0, 1.0)
    FEATURE_BOUNDS[f"bullpen_hr_rate_{_window}"] = (0.0, 1.0)

FEATURE_BOUNDS.update({
    "lineup_woba": (0.0, 0.8),
    "lineup_iso": (0.0, 1.0),
    "lineup_ops": (0.0, 2.0),
    "lineup_xrc_proxy": (0.0, 15.0),
    "lineup_lr_balance": (0.0, 1.0),
    "lineup_quality": (0.0, 1.0),
    "lineup_woba_vs_pitcher_hand": (0.0, 0.8),
    "lineup_iso_vs_pitcher_hand": (0.0, 1.0),
    "lineup_k_rate_vs_pitcher_hand": (0.0, 1.0),
    "lineup_bb_rate_vs_pitcher_hand": (0.0, 1.0),
    "lineup_hard_hit_vs_pitcher_hand": (0.0, 1.0),
    "lineup_strength_vs_pitcher_hand": (0.0, 1.0),
    "platoon_advantage_score": (-1.0, 1.0),
    "bullpen_fatigue_score": (0.0, 1.0),
    "bullpen_availability_score": (0.0, 1.0),
    "fb_rate_x_wind_out": (-1.0, 1.0),
    "bullpen_fatigue_x_sp_innings_remaining_x_rest": (-10.0, 10.0),
    "wind_park_directional_factor": (-1.0, 1.0),
    "pitch_mix_x_lineup_matchup": (-1.0, 1.0),
})

def feature_suffix(key):
    return key[5:] if key.startswith("home_") or key.startswith("away_") else key


def validate_features(features):
    invalid = []
    validated = dict(features)
    for key, value in features.items():
        suffix = feature_suffix(key)
        bounds = FEATURE_BOUNDS.get(suffix)
        if bounds is None:
            continue
        low, high = bounds
        try:
            v = float(value)
        except (TypeError, ValueError):
            invalid.append(key)
            validated[key] = FEATURE_FALLBACKS.get(suffix, 0.0)
            continue
        if v < low or v > high or v != v:
            invalid.append(key)
            validated[key] = FEATURE_FALLBACKS.get(suffix, v)
    return validated, invalid

FEATURE_FALLBACKS = {
    "k_rate": LEAGUE_AVG_K_RATE,
    "bb_rate": LEAGUE_AVG_BB_RATE,
    "hr_rate": LEAGUE_AVG_HR_RATE,
    "hard_hit_pct": LEAGUE_AVG_HARD_HIT_PCT,
    "fb_velo": LEAGUE_AVG_FB_VELO,
    "xwoba_against": LEAGUE_AVG_XWOBA_AGAINST,
    "fip": LEAGUE_AVG_FIP,
    "days_rest": 5.0,
    "bat_k_rate": LEAGUE_AVG_K_RATE,
    "bat_hard_hit_pct": LEAGUE_AVG_HARD_HIT_PCT,
    "bat_iso": LEAGUE_AVG_BAT_ISO,
    "bat_woba": LEAGUE_AVG_BAT_WOBA,
    "L10_wr": LEAGUE_AVG_L10_WR,
    "L10_rs": LEAGUE_AVG_L10_RS,
    "L10_ra": LEAGUE_AVG_L10_RA,
    "park_factor": LEAGUE_AVG_TOTAL_RUNS_PRIOR,
    "temp_f": 72.0,
    "wind_mph": 7.0,
    "wind_out_factor": 0.0,
}

FEATURE_FALLBACKS.update({
    "lineup_woba": LEAGUE_AVG_BAT_WOBA,
    "lineup_iso": LEAGUE_AVG_BAT_ISO,
    "lineup_ops": 0.720,
    "lineup_xrc_proxy": 4.5,
    "lineup_lr_balance": 0.5,
    "lineup_quality": 0.5,
    "lineup_woba_vs_pitcher_hand": LEAGUE_AVG_BAT_WOBA,
    "lineup_iso_vs_pitcher_hand": LEAGUE_AVG_BAT_ISO,
    "lineup_k_rate_vs_pitcher_hand": LEAGUE_AVG_K_RATE,
    "lineup_bb_rate_vs_pitcher_hand": LEAGUE_AVG_BB_RATE,
    "lineup_hard_hit_vs_pitcher_hand": LEAGUE_AVG_HARD_HIT_PCT,
    "lineup_strength_vs_pitcher_hand": 0.5,
    "platoon_advantage_score": 0.0,
    "bullpen_fatigue_score": 0.3,
    "bullpen_availability_score": 0.7,
    "fb_rate_x_wind_out": 0.0,
    "bullpen_fatigue_x_sp_innings_remaining_x_rest": 0.0,
    "wind_park_directional_factor": 0.0,
    "pitch_mix_x_lineup_matchup": 0.0,
})
for _window in ("3d", "5d", "7d"):
    FEATURE_FALLBACKS[f"bullpen_appearances_{_window}"] = 0.0
    FEATURE_FALLBACKS[f"bullpen_pitches_{_window}"] = 0.0
    FEATURE_FALLBACKS[f"bullpen_bf_{_window}"] = 0.0
    FEATURE_FALLBACKS[f"bullpen_high_lev_ip_{_window}"] = 0.0
for _window in ("7d", "14d", "30d", "season"):
    FEATURE_FALLBACKS[f"bullpen_era_{_window}"] = LEAGUE_AVG_FIP
    FEATURE_FALLBACKS[f"bullpen_xfip_{_window}"] = LEAGUE_AVG_FIP
    FEATURE_FALLBACKS[f"bullpen_fip_{_window}"] = LEAGUE_AVG_FIP
    FEATURE_FALLBACKS[f"bullpen_whip_{_window}"] = 1.30
    FEATURE_FALLBACKS[f"bullpen_k_rate_{_window}"] = LEAGUE_AVG_K_RATE
    FEATURE_FALLBACKS[f"bullpen_bb_rate_{_window}"] = LEAGUE_AVG_BB_RATE
    FEATURE_FALLBACKS[f"bullpen_hr_rate_{_window}"] = LEAGUE_AVG_HR_RATE


def wind_out_factor(wind_dir_deg, cf_dir_deg):
    diff = abs((wind_dir_deg - cf_dir_deg + 180) % 360 - 180)
    return float(np.cos(np.radians(diff)))


def pitcher_rate_stats(bf, k, bb, hr, hard, bip, velo_sum, velo_n, xwoba_sum, xwoba_n):
    bf_safe = max(bf, 1)
    bip_safe = max(bip, 1)
    ip_est = max(bf / 4.3, 0.3)
    fip = (13 * hr + 3 * bb - 2 * k) / ip_est + FIP_CONSTANT
    return {
        "k_rate": k / bf_safe,
        "bb_rate": bb / bf_safe,
        "hr_rate": hr / bf_safe,
        "hard_hit_pct": hard / bip_safe,
        "fb_velo": (velo_sum / velo_n) if velo_n > 0 else None,
        "xwoba_against": (xwoba_sum / xwoba_n) if xwoba_n > 0 else None,
        "fip": min(max(fip, 0.0), 15.0),
    }


def team_bat_rate_stats(bf, k, hr, hard, bip, woba_sum, woba_n):
    return {
        "bat_k_rate": (k / bf) if bf > 0 else None,
        "bat_hard_hit_pct": (hard / bip) if bip > 0 else None,
        "bat_iso": (hr / bf) if bf > 0 else None,
        "bat_woba": (woba_sum / woba_n) if woba_n > 0 else None,
    }


def is_dome(team_abbr):
    meta = STADIUMS.get(team_abbr)
    return meta["dome"] == 1 if meta else False


def is_coors(team_abbr):
    return team_abbr == "COL"
