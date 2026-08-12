import gc
import sys
import pandas as pd
import numpy as np
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import feature_store, statcast_store
from pipeline.features_common import (
    FASTBALL_TYPES,
    FEATURE_FALLBACKS,
    FIP_CONSTANT,
    LEAGUE_AVG_TOTAL_RUNS_PRIOR,
    ML_FEATURES,
    STADIUMS,
    feature_suffix,
    wind_out_factor,
)

STATCAST_PATH = "data/statcast_raw.csv"
GAMES_PATH = "data/games_with_results.csv"
OUTPUT_PATH = "data/games_v2_features_corrected.csv"

ROLLING_STARTS = 5
ROLLING_GAMES = 10


def fetch_historical_weather(lat, lon, start, end):
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
    except Exception:
        return pd.DataFrame()


def get_game_weather(home_team, game_date, weather_cache):
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
    return {"temp_f": float(row["temp_f"]), "wind_mph": float(row["wind_mph"]), "wind_out_factor": wof}


def compute_point_in_time_park_factor(games):
    league_by_date = games.sort_values("date").reset_index(drop=True)
    league_by_date["league_running_avg"] = (
        league_by_date["total_runs"].shift(1).expanding().mean().fillna(LEAGUE_AVG_TOTAL_RUNS_PRIOR)
    )

    g = games.sort_values(["home_team", "date"]).reset_index(drop=True)
    g["park_running_avg"] = g.groupby("home_team")["total_runs"].transform(
        lambda x: x.shift(1).expanding().mean()
    )
    g = g.merge(
        league_by_date[["date", "home_team", "away_team", "league_running_avg"]],
        on=["date", "home_team", "away_team"],
        how="left",
    )
    g["park_factor"] = g["park_running_avg"].fillna(g["league_running_avg"])
    return g[["date", "home_team", "away_team", "park_factor"]]


CONTEXT_INPUT_PATH = "data/games_v2_features_final.csv"
CONTEXT_OUTPUT_PATH = "data/games_v2_features_context.csv"


def _starter_lookup():
    log = pd.read_csv(statcast_store.PITCHER_GAME_LOG, parse_dates=["game_date"])
    starters = log[log["is_starter"]]
    return {
        (int(row.game_pk), row.team): int(row.pitcher)
        for row in starters.itertuples()
    }


def _pitcher_hand_lookup():
    hands = {}
    for chunk in pd.read_csv(STATCAST_PATH, usecols=["pitcher", "p_throws"], chunksize=300000, low_memory=False):
        for pitcher, hand in chunk.drop_duplicates().itertuples(index=False):
            hands.setdefault(int(pitcher), hand)
    return hands


def build_context_dataset(input_path=CONTEXT_INPUT_PATH, output_path=CONTEXT_OUTPUT_PATH):
    df = pd.read_csv(input_path, parse_dates=["date"])
    starters = _starter_lookup()
    hands = _pitcher_hand_lookup()
    context_features = feature_store.get_context_feature_list()

    rows = []
    real_counts = {name: 0 for name in context_features}
    for i, row in enumerate(df.itertuples(index=False), start=1):
        game_pk = getattr(row, "game_pk")
        if pd.isna(game_pk):
            rows.append({})
            continue
        game_pk = int(game_pk)
        as_of = pd.Timestamp(row.date).date()
        home_sp = starters.get((game_pk, row.home_team))
        away_sp = starters.get((game_pk, row.away_team))
        features, provenance = feature_store.build_context_features(
            game_pk, row.home_team, row.away_team,
            {"bat_woba": row.home_bat_woba, "bat_iso": row.home_bat_iso},
            {"bat_woba": row.away_bat_woba, "bat_iso": row.away_bat_iso},
            as_of=as_of,
            home_sp_id=home_sp, away_sp_id=away_sp,
            home_sp_hand=hands.get(home_sp), away_sp_hand=hands.get(away_sp),
            home_days_rest=row.home_days_rest, away_days_rest=row.away_days_rest,
            wind_out=row.wind_out_factor,
            offline_only=True,
        )
        rows.append(features)
        for name in context_features:
            suffix = feature_suffix(name)
            if name in features and features[name] != FEATURE_FALLBACKS.get(suffix):
                real_counts[name] += 1
        if i % 500 == 0:
            print(f"  context features computed for {i:,}/{len(df):,} games")

    context_df = pd.DataFrame(rows, columns=context_features)
    for name in context_features:
        context_df[name] = pd.to_numeric(context_df[name], errors="coerce").fillna(
            FEATURE_FALLBACKS.get(feature_suffix(name), 0.0)
        )
    out = pd.concat([df.reset_index(drop=True), context_df], axis=1)
    out.to_csv(output_path, index=False)

    print(f"\nwrote {len(out):,} rows -> {output_path}")
    print("non-fallback (real computed value) coverage by context feature:")
    for name in context_features:
        print(f"    {name:<55} {real_counts[name] / len(df):.3f}")
    return out, real_counts


def main():
    print("Loading StatCast data...")
    statcast_cols = [
        "game_pk", "game_date", "home_team", "away_team", "pitcher", "batter", "player_name",
        "inning", "inning_topbot", "pitch_number", "pitch_type", "release_speed", "events",
        "launch_speed", "woba_value", "estimated_woba_using_speedangle", "p_throws",
    ]
    dtype_map = {
        "game_pk": "int32",
        "home_team": "category",
        "away_team": "category",
        "pitcher": "int32",
        "batter": "int32",
        "player_name": "category",
        "inning": "int8",
        "inning_topbot": "category",
        "pitch_number": "int8",
        "pitch_type": "category",
        "release_speed": "float32",
        "events": "category",
        "launch_speed": "float32",
        "woba_value": "float32",
        "estimated_woba_using_speedangle": "float32",
        "p_throws": "category",
    }
    print("Streaming statcast in chunks (memory-safe) and computing partial aggregates...")
    inn1_chunks = []
    pitcher_partials = []
    bat_partials = []
    chunk_n = 0
    for chunk in pd.read_csv(STATCAST_PATH, usecols=statcast_cols, dtype=dtype_map, chunksize=300000, low_memory=False):
        chunk["game_date"] = pd.to_datetime(chunk["game_date"])
        chunk_n += 1

        inn1_chunks.append(chunk[chunk["inning"] == 1].copy())

        terminal = chunk[chunk["events"].notna()]
        batted = chunk[chunk["launch_speed"].notna()]
        fastballs = chunk[chunk["pitch_type"].isin(FASTBALL_TYPES)]
        xwoba_rows = chunk[chunk["estimated_woba_using_speedangle"].notna()]

        p = terminal.groupby(["game_pk", "pitcher"]).size().rename("bf").reset_index()
        p = p.merge(terminal[terminal["events"] == "strikeout"].groupby(["game_pk", "pitcher"]).size().rename("k").reset_index(), on=["game_pk", "pitcher"], how="left")
        p = p.merge(terminal[terminal["events"].isin(["walk", "intent_walk", "hit_by_pitch"])].groupby(["game_pk", "pitcher"]).size().rename("bb").reset_index(), on=["game_pk", "pitcher"], how="left")
        p = p.merge(terminal[terminal["events"] == "home_run"].groupby(["game_pk", "pitcher"]).size().rename("hr").reset_index(), on=["game_pk", "pitcher"], how="left")
        velo = fastballs.groupby(["game_pk", "pitcher"])["release_speed"].agg(["sum", "count"]).rename(columns={"sum": "velo_sum", "count": "velo_n"}).reset_index()
        p = p.merge(velo, on=["game_pk", "pitcher"], how="left")
        p = p.merge(batted[batted["launch_speed"] >= 95].groupby(["game_pk", "pitcher"]).size().rename("hard").reset_index(), on=["game_pk", "pitcher"], how="left")
        p = p.merge(batted.groupby(["game_pk", "pitcher"]).size().rename("bip").reset_index(), on=["game_pk", "pitcher"], how="left")
        xw = xwoba_rows.groupby(["game_pk", "pitcher"])["estimated_woba_using_speedangle"].agg(["sum", "count"]).rename(columns={"sum": "xwoba_sum", "count": "xwoba_n"}).reset_index()
        p = p.merge(xw, on=["game_pk", "pitcher"], how="left")
        pitcher_partials.append(p.fillna(0))

        bat_team = np.where(chunk["inning_topbot"] == "Top", chunk["away_team"], chunk["home_team"])
        bchunk = chunk.assign(bat_team=bat_team)
        bterm = bchunk[bchunk["events"].notna()]
        bbatted = bchunk[bchunk["launch_speed"].notna()]
        bwoba = bchunk[bchunk["woba_value"].notna()]
        b = bterm.groupby(["game_pk", "bat_team"]).size().rename("bat_bf").reset_index()
        b = b.merge(bterm[bterm["events"] == "strikeout"].groupby(["game_pk", "bat_team"]).size().rename("bat_k").reset_index(), on=["game_pk", "bat_team"], how="left")
        b = b.merge(bterm[bterm["events"] == "home_run"].groupby(["game_pk", "bat_team"]).size().rename("bat_hr").reset_index(), on=["game_pk", "bat_team"], how="left")
        b = b.merge(bbatted[bbatted["launch_speed"] >= 95].groupby(["game_pk", "bat_team"]).size().rename("bat_hard").reset_index(), on=["game_pk", "bat_team"], how="left")
        b = b.merge(bbatted.groupby(["game_pk", "bat_team"]).size().rename("bat_bip").reset_index(), on=["game_pk", "bat_team"], how="left")
        wsum = bwoba.groupby(["game_pk", "bat_team"])["woba_value"].agg(["sum", "count"]).rename(columns={"sum": "woba_sum", "count": "woba_n"}).reset_index()
        b = b.merge(wsum, on=["game_pk", "bat_team"], how="left")
        bat_partials.append(b.fillna(0))

        if chunk_n % 5 == 0:
            print(f"  processed {chunk_n} chunks")

    print(f"  processed {chunk_n} chunks total")

    inn1 = pd.concat(inn1_chunks, ignore_index=True)
    del inn1_chunks
    gc.collect()
    print(f"  {inn1['game_pk'].nunique():,} games seen")

    print("Identifying starters...")
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

    game_meta = inn1.groupby("game_pk")[["game_date", "home_team", "away_team"]].first().reset_index()
    del inn1
    gc.collect()

    print("Combining per-pitcher-per-game partial aggregates...")
    pg = pd.concat(pitcher_partials, ignore_index=True)
    del pitcher_partials
    gc.collect()
    pg = pg.groupby(["game_pk", "pitcher"], as_index=False).sum()
    pg = pg.merge(game_meta, on="game_pk", how="left")

    pg["k_rate"] = pg["k"] / pg["bf"].clip(lower=1)
    pg["bb_rate"] = pg["bb"] / pg["bf"].clip(lower=1)
    pg["hr_rate"] = pg["hr"] / pg["bf"].clip(lower=1)
    pg["hard_hit_pct"] = pg["hard"] / pg["bip"].clip(lower=1)
    pg["fb_velo"] = pg["velo_sum"] / pg["velo_n"].replace(0, np.nan)
    pg["xwoba_against"] = pg["xwoba_sum"] / pg["xwoba_n"].replace(0, np.nan)
    pg["ip_est"] = pg["bf"] / 4.3
    pg["fip"] = (13 * pg["hr"] + 3 * pg["bb"] - 2 * pg["k"]) / pg["ip_est"].clip(lower=0.3) + FIP_CONSTANT
    pg["fip"] = pg["fip"].clip(lower=0.0, upper=15.0)
    pg["game_date"] = pd.to_datetime(pg["game_date"])
    pg = pg.sort_values(["pitcher", "game_date"]).reset_index(drop=True)
    print(f"  {len(pg):,} pitcher-game records")

    print("Combining team-batting partial aggregates...")
    tbg_raw = pd.concat(bat_partials, ignore_index=True)
    del bat_partials
    gc.collect()
    tbg_raw = tbg_raw.groupby(["game_pk", "bat_team"], as_index=False).sum()

    print("Computing rolling pitcher stats (point-in-time, shift(1) before rolling)...")
    pitcher_cols = ["k_rate", "bb_rate", "hr_rate", "hard_hit_pct", "fb_velo", "xwoba_against", "fip"]

    def rolling_prior(grp, n=ROLLING_STARTS):
        return grp[pitcher_cols].shift(1).rolling(n, min_periods=1).mean()

    rolled = pg.groupby("pitcher", group_keys=False).apply(rolling_prior).add_prefix("roll_")
    pg_rolled = pd.concat([pg[["game_pk", "pitcher", "game_date"]], rolled], axis=1)
    pg_rolled["days_rest"] = (
        pg.groupby("pitcher")["game_date"].transform(lambda x: x.diff().dt.days).clip(upper=30).fillna(5)
    )
    for col in pg_rolled.columns:
        if col.startswith("roll_"):
            pg_rolled[col] = pg_rolled[col].fillna(pg_rolled[col].median())
    print("  Done")

    print("Finalizing team batting stats (point-in-time)...")
    tbg = tbg_raw
    tbg["bat_k_rate"] = tbg["bat_k"] / tbg["bat_bf"].clip(lower=1)
    tbg["bat_hard_hit_pct"] = tbg["bat_hard"] / tbg["bat_bip"].clip(lower=1)
    tbg["bat_iso"] = tbg["bat_hr"] / tbg["bat_bf"].clip(lower=1)
    tbg["bat_woba"] = tbg["woba_sum"] / tbg["woba_n"].replace(0, np.nan)
    tbg = tbg.merge(game_meta[["game_pk", "game_date"]], on="game_pk", how="left")
    tbg["game_date"] = pd.to_datetime(tbg["game_date"])
    tbg = tbg.sort_values(["bat_team", "game_date"]).reset_index(drop=True)

    bat_cols = ["bat_k_rate", "bat_hard_hit_pct", "bat_iso", "bat_woba"]

    def rolling_bat(grp, n=ROLLING_GAMES):
        return grp[bat_cols].shift(1).rolling(n, min_periods=1).mean()

    bat_rolled = tbg.groupby("bat_team", group_keys=False).apply(rolling_bat).add_prefix("roll_")
    tbg_rolled = pd.concat([tbg[["game_pk", "bat_team", "game_date"]], bat_rolled], axis=1)
    for col in bat_rolled.columns:
        tbg_rolled[col] = tbg_rolled[col].fillna(tbg_rolled[col].median())
    print(f"  {len(tbg_rolled):,} team-game batting records")

    print("Computing team form (point-in-time)...")
    games = pd.read_csv(GAMES_PATH, parse_dates=["date"])
    games = games.sort_values("date").reset_index(drop=True)

    def team_form(gdf, n=ROLLING_GAMES):
        records = []
        for _, row in gdf.iterrows():
            records.append({"date": row["date"], "team": row["home_team"], "win": int(row["home_win"]), "rs": row["home_runs"], "ra": row["away_runs"]})
            records.append({"date": row["date"], "team": row["away_team"], "win": 1 - int(row["home_win"]), "rs": row["away_runs"], "ra": row["home_runs"]})
        tf = pd.DataFrame(records).sort_values(["team", "date"]).reset_index(drop=True)
        for col, src in [("L10_wr", "win"), ("L10_rs", "rs"), ("L10_ra", "ra")]:
            tf[col] = tf.groupby("team")[src].transform(lambda x: x.shift(1).rolling(n, min_periods=1).mean())
        return tf[["date", "team", "L10_wr", "L10_rs", "L10_ra"]]

    form = team_form(games)

    print("Computing point-in-time park factor (LEAKAGE FIX: was full-dataset average, now trailing expanding mean)...")
    park_factor_pit = compute_point_in_time_park_factor(games)

    print("Fetching historical weather...")
    date_min = games["date"].min().strftime("%Y-%m-%d")
    date_max = games["date"].max().strftime("%Y-%m-%d")
    weather_cache = {}
    for team in games["home_team"].unique():
        meta = STADIUMS.get(team)
        if not meta or meta["dome"] == 1:
            continue
        wdf = fetch_historical_weather(meta["lat"], meta["lon"], date_min, date_max)
        if not wdf.empty:
            weather_cache[team] = wdf
            print(f"  {team}: {len(wdf)} hourly records")
        else:
            print(f"  {team}: weather fetch failed, using fallback")

    print("Joining all features...")

    def pitcher_feats(starters_df, pg_rolled_df, side):
        sp_id_col = f"{side}_sp_id"
        sp_hand = f"{side}_sp_hand"
        merged = starters_df[["game_pk", "game_date", sp_id_col, sp_hand]].merge(
            pg_rolled_df.rename(columns={"pitcher": sp_id_col}), on=["game_pk", sp_id_col], how="left"
        )
        merged[f"{side}_is_lefty"] = (merged[sp_hand] == "L").astype(float)
        rename = {f"roll_{c}": f"{side}_{c}" for c in pitcher_cols}
        rename["days_rest"] = f"{side}_days_rest"
        merged = merged.rename(columns=rename)
        keep = ["game_pk", f"{side}_is_lefty", f"{side}_days_rest"] + [f"{side}_{c}" for c in pitcher_cols]
        return merged[[c for c in keep if c in merged.columns]]

    home_pf = pitcher_feats(starters, pg_rolled, "home")
    away_pf = pitcher_feats(starters, pg_rolled, "away")
    all_feats = starters.merge(home_pf, on="game_pk", how="left").merge(away_pf, on="game_pk", how="left")

    games["date_str"] = games["date"].dt.strftime("%Y-%m-%d")
    all_feats["date_str"] = all_feats["game_date"].dt.strftime("%Y-%m-%d")
    merged = games.merge(all_feats, on=["date_str", "home_team", "away_team"], how="left")

    home_bat = tbg_rolled[tbg_rolled["bat_team"].isin(games["home_team"].unique())].rename(
        columns={"bat_team": "home_team", "game_pk": "game_pk_bat", "game_date": "game_date_bat",
                 "roll_bat_k_rate": "home_bat_k_rate", "roll_bat_hard_hit_pct": "home_bat_hard_hit_pct",
                 "roll_bat_iso": "home_bat_iso", "roll_bat_woba": "home_bat_woba"}
    )
    away_bat = tbg_rolled.copy().rename(
        columns={"bat_team": "away_team", "game_pk": "game_pk_bat", "game_date": "game_date_bat",
                 "roll_bat_k_rate": "away_bat_k_rate", "roll_bat_hard_hit_pct": "away_bat_hard_hit_pct",
                 "roll_bat_iso": "away_bat_iso", "roll_bat_woba": "away_bat_woba"}
    )
    home_bat_by_game = home_bat[["game_pk_bat", "home_team", "home_bat_k_rate", "home_bat_hard_hit_pct", "home_bat_iso", "home_bat_woba"]].rename(columns={"game_pk_bat": "game_pk"})
    away_bat_by_game = away_bat[["game_pk_bat", "away_team", "away_bat_k_rate", "away_bat_hard_hit_pct", "away_bat_iso", "away_bat_woba"]].rename(columns={"game_pk_bat": "game_pk"})
    merged = merged.merge(home_bat_by_game, on=["game_pk", "home_team"], how="left")
    merged = merged.merge(away_bat_by_game, on=["game_pk", "away_team"], how="left")

    merged = merged.merge(
        form.rename(columns={"team": "home_team", "L10_wr": "home_L10_wr", "L10_rs": "home_L10_rs", "L10_ra": "home_L10_ra"}),
        on=["date", "home_team"], how="left",
    )
    merged = merged.merge(
        form.rename(columns={"team": "away_team", "L10_wr": "away_L10_wr", "L10_rs": "away_L10_rs", "L10_ra": "away_L10_ra"}),
        on=["date", "away_team"], how="left",
    )

    merged = merged.merge(park_factor_pit, on=["date", "home_team", "away_team"], how="left")

    merged["is_dome"] = merged["home_team"].map({t: m["dome"] for t, m in STADIUMS.items()}).fillna(0)
    merged["is_coors"] = (merged["home_team"] == "COL").astype(float)

    print("Attaching weather...")
    weather_rows = [get_game_weather(row["home_team"], row["date"], weather_cache) for _, row in merged.iterrows()]
    wdf = pd.DataFrame(weather_rows)
    merged["temp_f"] = wdf["temp_f"].values
    merged["wind_mph"] = wdf["wind_mph"].values
    merged["wind_out_factor"] = wdf["wind_out_factor"].values

    ml_features = ML_FEATURES

    for col in ml_features:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce")
            merged[col] = merged[col].fillna(merged[col].median())
        else:
            merged[col] = 0.0

    output_cols = ["date", "game_pk", "home_team", "away_team", "home_runs", "away_runs", "total_runs", "home_win",
                    "home_sp_name", "away_sp_name"] + ml_features
    output_cols = [c for c in output_cols if c in merged.columns]
    final = merged[output_cols].dropna(subset=["home_win"])
    Path("data").mkdir(exist_ok=True)
    final.to_csv(OUTPUT_PATH, index=False)

    coverage = final[ml_features].notna().mean().round(3)
    print(f"\nDone. {len(final):,} games -> {OUTPUT_PATH}")
    print(f"  Features: {len(ml_features)}")
    for col, cov in coverage.items():
        flag = "" if cov >= 0.85 else "  low coverage"
        print(f"    {col:<35} {cov:.3f}{flag}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "context":
        build_context_dataset()
    else:
        main()
