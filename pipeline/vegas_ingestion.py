"""Ingest the Christopher Treasure 2012-2021 MLB closing-lines dataset."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.data_platform import (american_to_decimal, begin_run, connect, finish_run,
                                    normalize_team, register_source_game, sha256_file, stable_hash)

SOURCE = "kaggle_mlb_vegas"


def _load_joined(path):
    path = Path(path)
    mlb_path = path if path.name == "oddsDataMLB.csv" else path.with_name("oddsDataMLB.csv")
    raw_path = path if path.name == "oddsData.csv" else path.with_name("oddsData.csv")
    mlb = pd.read_csv(mlb_path, dtype={"date": str, "team": str, "opponent": str})
    raw = pd.read_csv(raw_path, dtype={"date": str, "at": str, "team": str})
    # Exact market columns disambiguate most repeated team/date rows. cumcount
    # makes the remaining equal-priced doubleheader rows deterministic.
    left_keys = ["date", "team", "moneyLine", "total", "overOdds", "underOdds"]
    right_keys = ["date", "team", "line", "total", "overOdds", "underOdds"]
    mlb["_occ"] = mlb.groupby(left_keys, dropna=False).cumcount()
    raw["_occ"] = raw.groupby(right_keys, dropna=False).cumcount()
    joined = mlb.merge(raw[right_keys + ["_occ", "at", "gameNumber"]],
                       left_on=left_keys + ["_occ"], right_on=right_keys + ["_occ"],
                       how="left", suffixes=("", "_raw"), validate="one_to_one")
    return joined


def _pair_games(frame):
    frame = frame.copy()
    frame["team_norm"] = frame["team"].map(normalize_team)
    frame["opponent_norm"] = frame["opponent"].map(normalize_team)
    frame["pair"] = frame.apply(lambda r: "|".join(sorted((r.team_norm, r.opponent_norm))), axis=1)
    counts = frame.groupby(["date", "pair"], dropna=False)["gameNumber"].nunique(dropna=True)
    for (date, pair, number), group in frame.groupby(["date", "pair", "gameNumber"], dropna=False, sort=True):
        valid = (len(group) == 2 and group["at"].notna().all() and
                 set(group["at"].astype(str).str.upper()) == {"H", "V"} and
                 set(group["team_norm"]) == set(group["opponent_norm"]))
        if not valid:
            yield None, {"date": str(date), "pair": pair,
                         "gameNumber": None if pd.isna(number) else int(number),
                         "rows": group.to_dict("records")}
            continue
        home = group[group["at"].str.upper() == "H"].iloc[0]
        away = group[group["at"].str.upper() == "V"].iloc[0]
        canonical_number = int(number) if counts.loc[(date, pair)] > 1 else 0
        yield (str(date), canonical_number, home, away), None


def ingest(path, db_path=None):
    path = Path(path)
    conn = connect(db_path) if db_path else connect()
    mlb_path = path if path.name == "oddsDataMLB.csv" else path.with_name("oddsDataMLB.csv")
    raw_path = path if path.name == "oddsData.csv" else path.with_name("oddsData.csv")
    digest = stable_hash({"mlb": sha256_file(mlb_path), "raw": sha256_file(raw_path)})
    run_id = begin_run(conn, SOURCE, "2012-2021:v1", digest)
    frame = _load_joined(path)
    inserted = quarantined = 0
    try:
        with conn:
            for paired, bad in _pair_games(frame):
                if bad:
                    source_id = f"{bad['date']}:{bad['gameNumber']}"
                    conn.execute("INSERT OR REPLACE INTO identity_quarantine VALUES (?,?,?,?,?)",
                                 (SOURCE, source_id, "expected_exactly_one_home_and_away_row", json.dumps(bad, default=str), run_id))
                    quarantined += 1
                    continue
                date, number, home, away = paired
                source_id = f"{date}:{normalize_team(away.team)}:{normalize_team(home.team)}:{number}"
                canonical_id = register_source_game(conn, SOURCE, source_id, date, home.team, away.team, number,
                                                    venue_name=None, game_type="R", confidence="date_teams_doubleheader")
                outcomes = [
                    ("h2h", normalize_team(home.team), home.moneyLine, None),
                    ("h2h", normalize_team(away.team), away.moneyLine, None),
                    ("totals", "Over", home.overOdds, home.total),
                    ("totals", "Under", home.underOdds, home.total),
                ]
                for market, outcome, price, point in outcomes:
                    if pd.isna(price) or (point is not None and pd.isna(point)):
                        continue
                    payload = {"source_event_id": source_id, "market": market, "outcome": outcome,
                               "price": float(price), "point": None if point is None else float(point)}
                    row_hash = stable_hash({"source": SOURCE, **payload})
                    conn.execute("""INSERT OR IGNORE INTO historical_market_snapshots
                      (source,source_event_id,canonical_game_id,bookmaker,market,outcome,price_american,
                       price_decimal,point,is_closing,ingestion_run_id,row_sha256,raw_json)
                      VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                      (SOURCE, source_id, canonical_id, "vegas_consensus", market, outcome, float(price),
                       american_to_decimal(price), payload["point"], run_id, row_hash, json.dumps(payload, sort_keys=True)))
                    inserted += conn.execute("SELECT changes()").fetchone()[0]
        report = {"source_rows": len(frame), "candidate_games": len(frame) // 2, "market_rows_inserted": inserted,
                  "quarantined_games": quarantined, "source_sha256": digest}
        finish_run(conn, run_id, "complete" if not quarantined else "complete_with_quarantine", inserted, report)
        return report
    except Exception as exc:
        finish_run(conn, run_id, "failed", inserted, {"error": str(exc)})
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/external/vegas/oddsData.csv")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    print(json.dumps(ingest(args.path, args.db), indent=2))


if __name__ == "__main__":
    main()
