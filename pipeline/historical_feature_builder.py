"""Build a versioned, point-in-time historical feature table from the warehouse."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.data_platform import connect, sha256_file, stable_hash, utc_now

DEFAULT_OUTPUT = "data/platform/historical_features.csv"


def _json_number(raw, key):
    try:
        value = json.loads(raw or "{}").get(key)
        return np.nan if value is None else float(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return np.nan


def _team_history(conn):
    rows = pd.read_sql_query("""SELECT rowid,canonical_game_id,team,opponent,game_date,
      source_quality,batting_json,pitching_json FROM team_game_history""", conn)
    priority = {"evt": 3, "box": 2, "ded": 1}
    rows["priority"] = rows.source_quality.map(priority).fillna(0)
    rows = rows.sort_values(["canonical_game_id","team","priority","rowid"], ascending=[True,True,False,True])
    rows = rows.drop_duplicates(["canonical_game_id","team"], keep="first")
    rows["runs"] = rows.batting_json.map(lambda x: _json_number(x, "B_R"))
    rows["runs_allowed"] = rows.pitching_json.map(lambda x: _json_number(x, "P_R"))
    rows["hits"] = rows.batting_json.map(lambda x: _json_number(x, "B_H"))
    rows["walks"] = rows.batting_json.map(lambda x: _json_number(x, "B_BB"))
    rows["strikeouts"] = rows.batting_json.map(lambda x: _json_number(x, "B_SO"))
    rows["plate_appearances"] = rows.batting_json.map(lambda x: _json_number(x, "B_PA"))
    rows["bullpen_runs"] = rows.pitching_json.map(lambda x: _json_number(x, "P_R"))
    rows["date"] = pd.to_datetime(rows.game_date)
    rows = rows.sort_values(["team","date","canonical_game_id"])
    for window in (5, 10, 30):
        for column in ("runs", "runs_allowed", "hits", "walks", "strikeouts"):
            rows[f"{column}_{window}g"] = rows.groupby("team")[column].transform(
                lambda values: values.shift(1).rolling(window, min_periods=max(3, window // 3)).mean())
    rows["win"] = (rows.runs > rows.runs_allowed).astype(float)
    rows["win_rate_10g"] = rows.groupby("team")["win"].transform(
        lambda values: values.shift(1).rolling(10, min_periods=3).mean())
    rows["days_since_game"] = rows.groupby("team")["date"].diff().dt.days
    rows["rest_days"] = rows["days_since_game"].clip(0, 10)
    return rows


def _markets(conn):
    rows = pd.read_sql_query("""SELECT canonical_game_id,market,outcome,price_american,
      price_decimal,point FROM historical_market_snapshots WHERE is_closing=1""", conn)
    rows = rows.drop_duplicates(["canonical_game_id","market","outcome","point"])
    return rows


def build(output=DEFAULT_OUTPUT, db_path=None):
    conn = connect(db_path) if db_path else connect()
    games = pd.read_sql_query("""SELECT canonical_game_id,game_date,home_team,away_team,
      doubleheader_number,venue_name FROM canonical_games WHERE canonical_game_id IN
      (SELECT canonical_game_id FROM historical_market_snapshots WHERE is_closing=1)""", conn)
    history = _team_history(conn)
    markets = _markets(conn)

    feature_cols = [c for c in history.columns if c.endswith("g") or c in ("win_rate_10g","rest_days")]
    current_cols = ["canonical_game_id","team","runs","runs_allowed"]
    home = history[current_cols + feature_cols].rename(columns={
        "team":"home_team", "runs":"home_runs", "runs_allowed":"home_runs_allowed",
        **{c:f"home_{c}" for c in feature_cols}})
    away = history[current_cols + feature_cols].rename(columns={
        "team":"away_team", "runs":"away_runs", "runs_allowed":"away_runs_allowed",
        **{c:f"away_{c}" for c in feature_cols}})
    frame = games.merge(home, on=["canonical_game_id","home_team"], how="left")
    frame = frame.merge(away, on=["canonical_game_id","away_team"], how="left")

    h2h = markets[markets.market == "h2h"].copy()
    h2h["implied"] = 1 / h2h.price_decimal
    home_price = h2h.merge(games[["canonical_game_id","home_team"]], left_on=["canonical_game_id","outcome"],
                           right_on=["canonical_game_id","home_team"], how="inner")
    away_price = h2h.merge(games[["canonical_game_id","away_team"]], left_on=["canonical_game_id","outcome"],
                           right_on=["canonical_game_id","away_team"], how="inner")
    home_price = home_price[["canonical_game_id","price_american","price_decimal","implied"]].rename(
        columns={c:f"home_moneyline_{c}" for c in ("price_american","price_decimal","implied")})
    away_price = away_price[["canonical_game_id","price_american","price_decimal","implied"]].rename(
        columns={c:f"away_moneyline_{c}" for c in ("price_american","price_decimal","implied")})
    frame = frame.merge(home_price,on="canonical_game_id",how="left").merge(away_price,on="canonical_game_id",how="left")
    denom = frame.home_moneyline_implied + frame.away_moneyline_implied
    frame["market_home_probability"] = frame.home_moneyline_implied / denom
    frame["market_vig"] = denom - 1

    totals = markets[markets.market == "totals"]
    over = totals[totals.outcome.str.lower() == "over"][["canonical_game_id","point","price_decimal"]].rename(
        columns={"point":"closing_total","price_decimal":"over_price_decimal"})
    under = totals[totals.outcome.str.lower() == "under"][["canonical_game_id","price_decimal"]].rename(
        columns={"price_decimal":"under_price_decimal"})
    frame = frame.merge(over,on="canonical_game_id",how="left").merge(under,on="canonical_game_id",how="left")
    over_imp, under_imp = 1/frame.over_price_decimal, 1/frame.under_price_decimal
    frame["market_over_probability"] = over_imp / (over_imp + under_imp)
    frame["total_market_vig"] = over_imp + under_imp - 1
    frame["home_form_edge"] = frame.home_win_rate_10g - frame.away_win_rate_10g
    frame["run_form_edge"] = ((frame.home_runs_10g - frame.home_runs_allowed_10g) -
                              (frame.away_runs_10g - frame.away_runs_allowed_10g))
    frame["market_x_form_edge"] = (frame.market_home_probability - .5) * frame.home_form_edge
    frame["total_runs"] = frame.home_runs + frame.away_runs
    frame["home_win"] = (frame.home_runs > frame.away_runs).where(frame.home_runs.notna() & frame.away_runs.notna())
    frame["over"] = (frame.total_runs > frame.closing_total).where(frame.total_runs.notna() & frame.closing_total.notna())
    frame["push"] = (frame.total_runs == frame.closing_total).where(frame.total_runs.notna() & frame.closing_total.notna())
    frame["feature_as_of"] = frame.game_date
    frame["point_in_time_policy"] = "all rolling statistics shifted one completed game; closing market is target-time market input"
    frame = frame.sort_values(["game_date","canonical_game_id"]).reset_index(drop=True)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output,index=False)
    digest = sha256_file(output)
    version = stable_hash({"sha":digest,"policy":"shift-1-game-v1"})[:16]
    conn.execute("INSERT OR REPLACE INTO dataset_manifests VALUES (?,?,?,?,?,?)",
                 ("historical_features",version,utc_now(),len(frame),digest,
                  json.dumps({"builder":"historical_feature_builder:v1","output":str(output)},sort_keys=True)))
    conn.commit(); conn.close()
    return {"rows":len(frame),"columns":len(frame.columns),"version":version,"sha256":digest,
            "label_coverage":int(frame.home_win.notna().sum()),"totals_coverage":int((frame.over.notna() & ~frame.push.fillna(False)).sum())}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",default=DEFAULT_OUTPUT); parser.add_argument("--db",default=None)
    args=parser.parse_args(); print(json.dumps(build(args.output,args.db),indent=2))


if __name__ == "__main__": main()
