import pandas as pd
import numpy as np
import requests
from pathlib import Path
from datetime import timedelta

STATCAST_PATH = "data/statcast_raw.csv"
GAMES_PATH = "data/games_with_results.csv"
OUTPUT_PATH = "data/games_v2_features.csv"

ROLLING_STARTS = 5
ROLLING_GAMES = 10
FIP_CONSTANT = 3.10
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


def wind_out_factor(wind_dir_deg: float, cf_dir_deg: float) -> float:

    diff = abs((wind_dir_deg - cf_dir_deg + 180) % 360 - 180)

    return np.cos(np.radians(diff))


def fetch_historical_weather(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:

    url = "https://archive-api.open-meteo.com/v1/archive"
    try:
        r = requests.get(
            url,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": start,
                "end_date": end,
                "hourly": "temperature_2m,windspeed_10m,winddirection_10m",
                "temperature_unit": "fahrenheit",
                "windspeed_unit": "mph",
                "timezone": "America/New_York",
            },
            timeout=30,
        )
        data = r.json()
        times = data["hourly"]["time"]
        temp_f = data["hourly"]["temperature_2m"]
        wind_mph = data["hourly"]["windspeed_10m"]
        wind_dir = data["hourly"]["winddirection_10m"]
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime(times),
                "temp_f": temp_f,
                "wind_mph": wind_mph,
                "wind_dir": wind_dir,
            }
        )
        return df.set_index("datetime")
    except Exception as e:
        return pd.DataFrame()


def get_game_weather(home_team: str, game_date: pd.Timestamp, weather_cache: dict) -> dict:

    fallback = {"temp_f": 72.0, "wind_mph": 7.0, "wind_out_factor": 0.0}
    meta = STADIUMS.get(home_team)
    if not meta:
        return fallback

    if meta["dome"] == 1:
        return {"temp_f": 72.0, "wind_mph": 0.0, "wind_out_factor": 0.0}

    wdf = weather_cache.get(home_team)
    if wdf is None or wdf.empty:
        return fallback

    target = pd.Timestamp(game_date.date()) + pd.Timedelta(hours=19)
    if target not in wdf.index:

        idx = wdf.index.get_indexer([target], method="nearest")[0]
        if idx < 0:
            return fallback
        row = wdf.iloc[idx]
    else:
        row = wdf.loc[target]

    wof = wind_out_factor(float(row["wind_dir"]), meta["cf_deg"])

    wof *= 1 - meta["dome"]

    return {
        "temp_f": float(row["temp_f"]),
        "wind_mph": float(row["wind_mph"]),
        "wind_out_factor": wof,
    }


print("Loading StatCast data...")
STATCAST_COLS = [
    "game_pk",
    "game_date",
    "home_team",
    "away_team",
    "pitcher",
    "batter",
    "player_name",
    "inning",
    "inning_topbot",
    "pitch_number",
    "pitch_type",
    "release_speed",
    "events",
    "launch_speed",
    "woba_value",
    "estimated_woba_using_speedangle",
    "p_throws",
]
sc = pd.read_csv(STATCAST_PATH, usecols=STATCAST_COLS, low_memory=False)
sc["game_date"] = pd.to_datetime(sc["game_date"])
print(f"  {len(sc):,} pitches, {sc['game_pk'].nunique():,} games")


print("Identifying starters...")
inn1 = sc[sc["inning"] == 1].copy()

home_sp = (
    inn1[inn1["inning_topbot"] == "Top"]
    .sort_values("pitch_number")
    .groupby("game_pk")
    .agg(
        game_date=("game_date", "first"),
        home_team=("home_team", "first"),
        away_team=("away_team", "first"),
        home_sp_id=("pitcher", "first"),
        home_sp_name=("player_name", "first"),
        home_sp_hand=("p_throws", "first"),
    )
    .reset_index()
)
away_sp = (
    inn1[inn1["inning_topbot"] == "Bot"]
    .sort_values("pitch_number")
    .groupby("game_pk")
    .agg(
        away_sp_id=("pitcher", "first"),
        away_sp_name=("player_name", "first"),
        away_sp_hand=("p_throws", "first"),
    )
    .reset_index()
)
starters = home_sp.merge(away_sp, on="game_pk", how="inner")
print(f"  {len(starters):,} games with starters identified")


print("Computing per-pitcher-per-game stats...")

terminal = sc[sc["events"].notna()].copy()
batted = sc[sc["launch_speed"].notna()].copy()
fastballs = sc[sc["pitch_type"].isin(FASTBALL_TYPES)].copy()


bf = terminal.groupby(["game_pk", "pitcher"]).size().rename("bf").reset_index()


k = (
    terminal[terminal["events"] == "strikeout"]
    .groupby(["game_pk", "pitcher"])
    .size()
    .rename("k")
    .reset_index()
)


bb = (
    terminal[terminal["events"].isin(["walk", "intent_walk", "hit_by_pitch"])]
    .groupby(["game_pk", "pitcher"])
    .size()
    .rename("bb")
    .reset_index()
)


hr = (
    terminal[terminal["events"] == "home_run"]
    .groupby(["game_pk", "pitcher"])
    .size()
    .rename("hr")
    .reset_index()
)


fb_velo = (
    fastballs.groupby(["game_pk", "pitcher"])["release_speed"]
    .mean()
    .rename("fb_velo")
    .reset_index()
)


hard = (
    batted[batted["launch_speed"] >= 95]
    .groupby(["game_pk", "pitcher"])
    .size()
    .rename("hard")
    .reset_index()
)
n_bip = batted.groupby(["game_pk", "pitcher"]).size().rename("bip").reset_index()


xwoba = (
    sc[sc["estimated_woba_using_speedangle"].notna()]
    .groupby(["game_pk", "pitcher"])["estimated_woba_using_speedangle"]
    .mean()
    .rename("xwoba_against")
    .reset_index()
)


game_meta = sc.groupby("game_pk")[["game_date", "home_team", "away_team"]].first().reset_index()


pg = (
    bf.merge(k, on=["game_pk", "pitcher"], how="left")
    .merge(bb, on=["game_pk", "pitcher"], how="left")
    .merge(hr, on=["game_pk", "pitcher"], how="left")
    .merge(fb_velo, on=["game_pk", "pitcher"], how="left")
    .merge(hard, on=["game_pk", "pitcher"], how="left")
    .merge(n_bip, on=["game_pk", "pitcher"], how="left")
    .merge(xwoba, on=["game_pk", "pitcher"], how="left")
    .merge(game_meta, on="game_pk", how="left")
    .fillna({"k": 0, "bb": 0, "hr": 0, "hard": 0, "bip": 0})
)


pg["k_rate"] = pg["k"] / pg["bf"].clip(lower=1)
pg["bb_rate"] = pg["bb"] / pg["bf"].clip(lower=1)
pg["hr_rate"] = pg["hr"] / pg["bf"].clip(lower=1)
pg["hard_hit_pct"] = pg["hard"] / pg["bip"].clip(lower=1)


pg["ip_est"] = pg["bf"] / 4.3
pg["fip"] = (13 * pg["hr"] + 3 * pg["bb"] - 2 * pg["k"]) / pg["ip_est"].clip(
    lower=0.3
) + FIP_CONSTANT
pg["fip"] = pg["fip"].clip(lower=0.0, upper=15.0)

pg["game_date"] = pd.to_datetime(pg["game_date"])
pg = pg.sort_values(["pitcher", "game_date"]).reset_index(drop=True)
print(f"  {len(pg):,} pitcher-game records")


print("Computing rolling pitcher stats...")
PITCHER_COLS = ["k_rate", "bb_rate", "hr_rate", "hard_hit_pct", "fb_velo", "xwoba_against", "fip"]


def rolling_prior(grp, n=ROLLING_STARTS):
    return grp[PITCHER_COLS].shift(1).rolling(n, min_periods=1).mean()


rolled = pg.groupby("pitcher", group_keys=False).apply(rolling_prior).add_prefix("roll_")
pg_rolled = pd.concat([pg[["game_pk", "pitcher", "game_date"]], rolled], axis=1)


pg_rolled["days_rest"] = (
    pg.groupby("pitcher")["game_date"]
    .transform(lambda x: x.diff().dt.days)
    .clip(upper=30)
    .fillna(5)
)


for col in pg_rolled.columns:
    if col.startswith("roll_"):
        pg_rolled[col] = pg_rolled[col].fillna(pg_rolled[col].median())

print("  Done")


print("Computing bullpen stats...")

starter_ids = set(starters["home_sp_id"]).union(set(starters["away_sp_id"]))


starters_by_game = (
    inn1.groupby(["game_pk", "pitcher"])
    .size()
    .reset_index()[["game_pk", "pitcher"]]
    .assign(is_starter=True)
)

pg_with_role = pg.merge(starters_by_game, on=["game_pk", "pitcher"], how="left")
pg_with_role["is_starter"] = pg_with_role["is_starter"].fillna(False)
bp = pg_with_role[~pg_with_role["is_starter"]].copy()


bp = bp.merge(game_meta, on="game_pk", how="left")


games = pd.read_csv(GAMES_PATH, parse_dates=["date"])
games = games.sort_values("date").reset_index(drop=True)


print("  Using team form as bullpen proxy (sufficient for v2)")


print("Computing team batting stats...")


bat_terminal = sc[sc["events"].notna()].copy()
bat_woba = sc[sc["woba_value"].notna()].copy()
bat_batted = sc[sc["launch_speed"].notna()].copy()


def team_bat_stats_per_game(sc_df):
    sc_df = sc_df.copy()
    sc_df["bat_team"] = np.where(
        sc_df["inning_topbot"] == "Top", sc_df["away_team"], sc_df["home_team"]
    )
    return sc_df


bat_terminal = team_bat_stats_per_game(bat_terminal)
bat_woba = team_bat_stats_per_game(bat_woba)
bat_batted = team_bat_stats_per_game(bat_batted)


bat_bf = bat_terminal.groupby(["game_pk", "bat_team"]).size().rename("bat_bf").reset_index()


bat_k = (
    bat_terminal[bat_terminal["events"] == "strikeout"]
    .groupby(["game_pk", "bat_team"])
    .size()
    .rename("bat_k")
    .reset_index()
)


bat_bb = (
    bat_terminal[bat_terminal["events"].isin(["walk", "intent_walk"])]
    .groupby(["game_pk", "bat_team"])
    .size()
    .rename("bat_bb")
    .reset_index()
)


bat_hr = (
    bat_terminal[bat_terminal["events"] == "home_run"]
    .groupby(["game_pk", "bat_team"])
    .size()
    .rename("bat_hr")
    .reset_index()
)


bat_hard = (
    bat_batted[bat_batted["launch_speed"] >= 95]
    .groupby(["game_pk", "bat_team"])
    .size()
    .rename("bat_hard")
    .reset_index()
)
bat_bip = bat_batted.groupby(["game_pk", "bat_team"]).size().rename("bat_bip").reset_index()


bat_woba_stat = (
    bat_woba.groupby(["game_pk", "bat_team"])["woba_value"].mean().rename("bat_woba").reset_index()
)

tbg = (
    bat_bf.merge(bat_k, on=["game_pk", "bat_team"], how="left")
    .merge(bat_bb, on=["game_pk", "bat_team"], how="left")
    .merge(bat_hr, on=["game_pk", "bat_team"], how="left")
    .merge(bat_hard, on=["game_pk", "bat_team"], how="left")
    .merge(bat_bip, on=["game_pk", "bat_team"], how="left")
    .merge(bat_woba_stat, on=["game_pk", "bat_team"], how="left")
    .fillna(0)
)

tbg["bat_k_rate"] = tbg["bat_k"] / tbg["bat_bf"].clip(lower=1)
tbg["bat_hard_hit_pct"] = tbg["bat_hard"] / tbg["bat_bip"].clip(lower=1)
tbg["bat_iso"] = tbg["bat_hr"] / tbg["bat_bf"].clip(lower=1)

tbg = tbg.merge(game_meta[["game_pk", "game_date"]], on="game_pk", how="left")
tbg["game_date"] = pd.to_datetime(tbg["game_date"])
tbg = tbg.sort_values(["bat_team", "game_date"]).reset_index(drop=True)


BAT_COLS = ["bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba"]


def rolling_bat(grp, n=ROLLING_GAMES):
    return grp[BAT_COLS].shift(1).rolling(n, min_periods=1).mean()


bat_rolled = tbg.groupby("bat_team", group_keys=False).apply(rolling_bat).add_prefix("roll_")
tbg_rolled = pd.concat([tbg[["game_pk", "bat_team", "game_date"]], bat_rolled], axis=1)
for col in bat_rolled.columns:
    tbg_rolled[col] = tbg_rolled[col].fillna(tbg_rolled[col].median())

print(f"  {len(tbg_rolled):,} team-game batting records")


print("Computing team form...")


def team_form(gdf, n=ROLLING_GAMES):
    records = []
    for _, row in gdf.iterrows():
        records.append(
            {
                "date": row["date"],
                "team": row["home_team"],
                "win": int(row["home_win"]),
                "rs": row["home_runs"],
                "ra": row["away_runs"],
            }
        )
        records.append(
            {
                "date": row["date"],
                "team": row["away_team"],
                "win": 1 - int(row["home_win"]),
                "rs": row["away_runs"],
                "ra": row["home_runs"],
            }
        )
    tf = pd.DataFrame(records).sort_values(["team", "date"]).reset_index(drop=True)
    for col, src in [("L10_wr", "win"), ("L10_rs", "rs"), ("L10_ra", "ra")]:
        tf[col] = tf.groupby("team")[src].transform(
            lambda x: x.shift(1).rolling(n, min_periods=1).mean()
        )
    return tf[["date", "team", "L10_wr", "L10_rs", "L10_ra"]]


form = team_form(games)
park_factor = games.groupby("home_team")["total_runs"].mean().rename("park_factor").reset_index()
park_factor.columns = ["home_team", "park_factor"]
print("  Done")


print("Fetching historical weather (may take ~1-2 min)...")
date_min = games["date"].min().strftime("%Y-%m-%d")
date_max = games["date"].max().strftime("%Y-%m-%d")

weather_cache = {}
teams_in_games = games["home_team"].unique()
for team in teams_in_games:
    meta = STADIUMS.get(team)
    if not meta or meta["dome"] == 1:
        continue
    wdf = fetch_historical_weather(meta["lat"], meta["lon"], date_min, date_max)
    if not wdf.empty:
        weather_cache[team] = wdf
        print(f"  {team}: {len(wdf)} hourly records")
    else:
        print(f"   {team}: weather fetch failed, using fallback")


print("Joining all features...")


def pitcher_feats(starters_df, pg_rolled_df, side):
    sp_id_col = f"{side}_sp_id"
    sp_hand = f"{side}_sp_hand"
    merged = starters_df[["game_pk", "game_date", sp_id_col, sp_hand]].merge(
        pg_rolled_df.rename(columns={"pitcher": sp_id_col}), on=["game_pk", sp_id_col], how="left"
    )
    merged[f"{side}_is_lefty"] = (merged[sp_hand] == "L").astype(float)
    rename = {f"roll_{c}": f"{side}_{c}" for c in PITCHER_COLS}
    rename["days_rest"] = f"{side}_days_rest"
    merged = merged.rename(columns=rename)
    keep = ["game_pk", f"{side}_is_lefty", f"{side}_days_rest"] + [
        f"{side}_{c}" for c in PITCHER_COLS
    ]
    return merged[[c for c in keep if c in merged.columns]]


home_pf = pitcher_feats(starters, pg_rolled, "home")
away_pf = pitcher_feats(starters, pg_rolled, "away")

all_feats = starters.merge(home_pf, on="game_pk", how="left").merge(
    away_pf, on="game_pk", how="left"
)


games["date_str"] = games["date"].dt.strftime("%Y-%m-%d")
all_feats["date_str"] = all_feats["game_date"].dt.strftime("%Y-%m-%d")

merged = games.merge(all_feats, on=["date_str", "home_team", "away_team"], how="left")


home_bat = tbg_rolled[tbg_rolled["bat_team"].isin(games["home_team"].unique())].rename(
    columns={
        "bat_team": "home_team",
        "game_pk": "game_pk_bat",
        "game_date": "game_date_bat",
        "roll_bat_k_rate": "home_bat_k_rate",
        "roll_bat_hard_hit_pct": "home_bat_hard_hit_pct",
        "roll_bat_iso": "home_bat_iso",
        "roll_bat_woba": "home_bat_woba",
    }
)

away_bat = tbg_rolled.copy().rename(
    columns={
        "bat_team": "away_team",
        "game_pk": "game_pk_bat",
        "game_date": "game_date_bat",
        "roll_bat_k_rate": "away_bat_k_rate",
        "roll_bat_hard_hit_pct": "away_bat_hard_hit_pct",
        "roll_bat_iso": "away_bat_iso",
        "roll_bat_woba": "away_bat_woba",
    }
)


home_bat_by_game = home_bat[
    [
        "game_pk_bat",
        "home_team",
        "home_bat_k_rate",
        "home_bat_hard_hit_pct",
        "home_bat_iso",
        "home_bat_woba",
    ]
].rename(columns={"game_pk_bat": "game_pk"})
away_bat_by_game = away_bat[
    [
        "game_pk_bat",
        "away_team",
        "away_bat_k_rate",
        "away_bat_hard_hit_pct",
        "away_bat_iso",
        "away_bat_woba",
    ]
].rename(columns={"game_pk_bat": "game_pk"})

merged = merged.merge(home_bat_by_game, on=["game_pk", "home_team"], how="left")
merged = merged.merge(away_bat_by_game, on=["game_pk", "away_team"], how="left")


merged = merged.merge(
    form.rename(
        columns={
            "team": "home_team",
            "date": "date",
            "L10_wr": "home_L10_wr",
            "L10_rs": "home_L10_rs",
            "L10_ra": "home_L10_ra",
        }
    ),
    on=["date", "home_team"],
    how="left",
)


merged = merged.merge(
    form.rename(
        columns={
            "team": "away_team",
            "date": "date",
            "L10_wr": "away_L10_wr",
            "L10_rs": "away_L10_rs",
            "L10_ra": "away_L10_ra",
        }
    ),
    on=["date", "away_team"],
    how="left",
)


merged = merged.merge(park_factor, on="home_team", how="left")


merged["is_dome"] = merged["home_team"].map({t: m["dome"] for t, m in STADIUMS.items()}).fillna(0)


merged["is_coors"] = (merged["home_team"] == "COL").astype(float)


print("Attaching weather...")
weather_rows = []
for _, row in merged.iterrows():
    w = get_game_weather(row["home_team"], row["date"], weather_cache)
    weather_rows.append(w)
wdf = pd.DataFrame(weather_rows)
merged["temp_f"] = wdf["temp_f"].values
merged["wind_mph"] = wdf["wind_mph"].values
merged["wind_out_factor"] = wdf["wind_out_factor"].values


ML_FEATURES = [
    "home_k_rate",
    "home_bb_rate",
    "home_hr_rate",
    "home_hard_hit_pct",
    "home_fb_velo",
    "home_xwoba_against",
    "home_fip",
    "home_is_lefty",
    "home_days_rest",
    "away_k_rate",
    "away_bb_rate",
    "away_hr_rate",
    "away_hard_hit_pct",
    "away_fb_velo",
    "away_xwoba_against",
    "away_fip",
    "away_is_lefty",
    "away_days_rest",
    "home_bat_k_rate",
    "home_bat_hard_hit_pct",
    "home_bat_iso",
    "home_bat_woba",
    "away_bat_k_rate",
    "away_bat_hard_hit_pct",
    "away_bat_iso",
    "away_bat_woba",
    "home_L10_wr",
    "home_L10_rs",
    "home_L10_ra",
    "away_L10_wr",
    "away_L10_rs",
    "away_L10_ra",
    "park_factor",
    "is_dome",
    "is_coors",
    "temp_f",
    "wind_mph",
    "wind_out_factor",
]


for col in ML_FEATURES:
    if col in merged.columns:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
        merged[col] = merged[col].fillna(merged[col].median())
    else:
        merged[col] = 0.0

output_cols = [
    "date",
    "home_team",
    "away_team",
    "home_runs",
    "away_runs",
    "total_runs",
    "home_win",
    "home_sp_name",
    "away_sp_name",
] + ML_FEATURES
output_cols = [c for c in output_cols if c in merged.columns]

final = merged[output_cols].dropna(subset=["home_win"])
Path("data").mkdir(exist_ok=True)
final.to_csv(OUTPUT_PATH, index=False)

coverage = final[ML_FEATURES].notna().mean().round(3)
print(f"\nDone. {len(final):,} games → {OUTPUT_PATH}")
print(f"   Features: {len(ML_FEATURES)}")
print("\n   Coverage:")
for col, cov in coverage.items():
    flag = "" if cov >= 0.85 else "   low coverage"
    print(f"     {col:<35} {cov:.3f}{flag}")

print("\nRun next: python train_model_v2.py")
