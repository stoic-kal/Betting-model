"""Stream Retrosplits day-by-day CSVs into canonical immutable history tables."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.data_platform import begin_run, connect, finish_run, normalize_team, register_source_game, sha256_file, stable_hash

SOURCE = "retrosplits"
SOURCE_PRIORITY = {"evt": 3, "box": 2, "ded": 1}


def _bucket(row, prefix):
    return {key: (None if pd.isna(value) else value) for key, value in row.items() if key.startswith(prefix)}


def _identity(row):
    source_id = str(row["game.key"])
    home = source_id[:3]
    alignment = int(row.get("team.alignment", 0))
    team, opponent = normalize_team(row["team.key"]), normalize_team(row["opponent.key"])
    return source_id, (team if alignment == 1 else opponent), (opponent if alignment == 1 else team)


def ingest(path, kind="playing", db_path=None, chunksize=25000):
    path = Path(path)
    conn = connect(db_path) if db_path else connect()
    digest = sha256_file(path)
    run_id = begin_run(conn, SOURCE, f"{path.name}:v1", digest)
    inserted = rows_seen = 0
    table = "player_game_history" if kind == "playing" else "team_game_history"
    try:
        for chunk in pd.read_csv(path, chunksize=chunksize, low_memory=False):
            with conn:
                for record in chunk.to_dict("records"):
                    rows_seen += 1
                    source_id, home, away = _identity(record)
                    date = str(record["game.date"])
                    game_number = int(record.get("game.number", 0) or 0)
                    canonical_id = register_source_game(
                        conn, SOURCE, source_id, date, home, away, game_number,
                        venue_name=str(record.get("site.key") or ""), game_type=str(record.get("season.phase") or ""),
                        resume_date=str(record.get("appear.date") or date), confidence="retrosheet_game_key")
                    quality = str(record.get("game.source") or "unknown")
                    base = {"source": SOURCE, "source_game_id": source_id, "canonical_game_id": canonical_id,
                            "team": normalize_team(record["team.key"]), "opponent": normalize_team(record["opponent.key"]),
                            "game_date": date, "source_quality": quality,
                            "batting_json": json.dumps(_bucket(record, "B_"), sort_keys=True, default=str),
                            "pitching_json": json.dumps(_bucket(record, "P_"), sort_keys=True, default=str),
                            "fielding_json": json.dumps(_bucket(record, "F_"), sort_keys=True, default=str)}
                    if kind == "playing":
                        values = (*base.values(), str(record.get("person.key") or ""),
                                  str(record.get("appear.date") or date))
                        payload = {**base, "source_player_id": values[-2], "appearance_date": values[-1]}
                        row_hash = stable_hash(payload)
                        conn.execute("""INSERT OR IGNORE INTO player_game_history
                          (source,source_game_id,canonical_game_id,team,opponent,game_date,source_quality,
                           batting_json,pitching_json,fielding_json,source_player_id,appearance_date,ingestion_run_id,row_sha256)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*base.values(), values[-2], values[-1], run_id, row_hash))
                    else:
                        row_hash = stable_hash(base)
                        conn.execute("""INSERT OR IGNORE INTO team_game_history
                          (source,source_game_id,canonical_game_id,team,opponent,game_date,source_quality,
                           batting_json,pitching_json,fielding_json,ingestion_run_id,row_sha256)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (*base.values(), run_id, row_hash))
                    inserted += conn.execute("SELECT changes()").fetchone()[0]
        report = {"rows_seen": rows_seen, "rows_inserted": inserted, "kind": kind, "source_sha256": digest}
        finish_run(conn, run_id, "complete", inserted, report)
        return report
    except Exception as exc:
        finish_run(conn, run_id, "failed", inserted, {"error": str(exc), "rows_seen": rows_seen})
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--kind", choices=("playing", "teams"), default="playing")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()
    print(json.dumps(ingest(args.path, args.kind, args.db), indent=2))


if __name__ == "__main__":
    main()
