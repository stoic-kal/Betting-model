import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = "database/picks.db"


def _ensure_backfill_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_backfill (
            pick_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (pick_id, notification_type)
        )
    """)
    conn.commit()


def _already_sent(conn, pick_id, notification_type) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notification_backfill WHERE pick_id=? AND notification_type=?",
        (pick_id, notification_type),
    ).fetchone()
    return row is not None


def _mark_sent(conn, pick_id, notification_type):
    conn.execute(
        "INSERT OR REPLACE INTO notification_backfill (pick_id, notification_type, sent_at) VALUES (?,?,?)",
        (pick_id, notification_type, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _load_snapshot(raw):
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _market_prob_for_moneyline(matchup, pick, snapshot):

    parts = matchup.split(" @ ")
    home_team = parts[-1] if len(parts) == 2 else None
    if pick == home_team:
        return snapshot.get("market_home")
    return snapshot.get("market_away")


def _build_records(conn):

    from src.update_results import ResultsUpdater

    return ResultsUpdater(db_path=DB_PATH)._current_records(conn)


def _profit_units(status, odds):
    if status == "won":
        return (float(odds) - 1) if odds is not None else None
    if status == "lost":
        return -1.0
    if status == "push":
        return 0.0
    return None


def run(dry_run: bool, limit: int, since: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_backfill_table(conn)

    query = """SELECT id, game_id, date, matchup, pick_type, pick, odds, model_prob,
                      ev, kelly_units, status, model_build, feature_snapshot, created_at
               FROM picks
               WHERE forecast_stage = 'lineup_lock' """
    params = []
    if since:
        query += " AND date >= ?"
        params.append(since)
    query += " ORDER BY created_at ASC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()

    scanned = 0
    skipped = 0
    model_output_sent = 0
    pick_sent = 0
    result_sent = 0
    errors = 0

    try:
        from services import discord_service
    except Exception as e:
        print(f"Could not import discord_service: {e}")
        discord_service = None

    print(
        f'Scanning official (lineup_lock) picks{f" since {since}" if since else ""}'
        f'{f", limit {limit}" if limit else ""}{" [DRY RUN]" if dry_run else ""}...\n'
    )

    for row in rows:
        scanned += 1
        pick_id = row["id"]
        pick_type = row["pick_type"]
        matchup = row["matchup"]
        snapshot = _load_snapshot(row["feature_snapshot"])
        model_version = row["model_build"]

        print(
            f'[{pick_id}] {row["date"]}  {matchup}  {pick_type}  {row["pick"]}  status={row["status"]}'
        )

        if _already_sent(conn, pick_id, "model_output"):
            print("    – Model Output: already sent, skipping")
            skipped += 1
        else:
            try:
                if pick_type == "moneyline":
                    payload = {
                        "pick_type": "moneyline",
                        "matchup": matchup,
                        "prediction": row["pick"],
                        "model_prob": row["model_prob"],
                        "market_prob": _market_prob_for_moneyline(matchup, row["pick"], snapshot),
                        "model_version": model_version,
                    }
                    sender = discord_service.send_moneyline_output if discord_service else None
                else:
                    payload = {
                        "pick_type": "totals",
                        "matchup": matchup,
                        "prediction": row["pick"],
                        "expected_total": snapshot.get("expected_total"),
                        "market_line": snapshot.get("market_line"),
                        "model_prob": row["model_prob"],
                        "kelly_units": row["kelly_units"],
                        "model_version": model_version,
                    }
                    sender = discord_service.send_totals_output if discord_service else None

                if dry_run:
                    print(f"    WOULD SEND: Model Output  {payload}")
                else:
                    ok = sender(payload) if sender else False
                    if ok:
                        _mark_sent(conn, pick_id, "model_output")
                        model_output_sent += 1
                        print("    Model Output sent")
                    else:
                        print(
                            "    Model Output send returned False (not marked sent, will retry next run)"
                        )
            except Exception as e:
                errors += 1
                print(f"    Model Output error: {e}")

        if _already_sent(conn, pick_id, "pick"):
            print("    – Pick: already sent, skipping")
            skipped += 1
        else:
            try:
                payload = {
                    "pick_type": pick_type,
                    "matchup": matchup,
                    "pick": row["pick"],
                    "model_prob": row["model_prob"],
                    "kelly_units": row["kelly_units"],
                    "odds_dec": row["odds"],
                }
                if pick_type == "totals":
                    payload["expected_total"] = snapshot.get("expected_total")
                    payload["market_line"] = snapshot.get("market_line")

                if dry_run:
                    print(f"    WOULD SEND: Pick  {payload}")
                else:
                    ok = discord_service.send_pick(payload) if discord_service else False
                    if ok:
                        _mark_sent(conn, pick_id, "pick")
                        pick_sent += 1
                        print("    Pick sent")
                    else:
                        print(
                            "    Pick send returned False (not marked sent, will retry next run)"
                        )
            except Exception as e:
                errors += 1
                print(f"    Pick error: {e}")

        if row["status"] in ("won", "lost", "push"):
            # Result delivery belongs exclusively to ResultsUpdater's transactional
            # outbox.  A second maintenance-specific sent table cannot coordinate
            # atomically with the live grader and caused duplicate notifications.
            print("    – Result: managed by the production result outbox, skipping")
            skipped += 1
        print()

    conn.close()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Historical picks scanned : {scanned}")
    print(f"Notifications skipped    : {skipped}")
    print(f"Model Outputs sent       : {model_output_sent}")
    print(f"Picks sent               : {pick_sent}")
    print(f"Results sent             : {result_sent}")
    print(f"Errors                   : {errors}")
    if dry_run:
        print("\n(DRY RUN — nothing was actually sent or recorded.)")


def main():
    parser = argparse.ArgumentParser(
        description="One-time backfill of Discord notifications for historical official picks. "
        "Standalone maintenance utility — never run automatically."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print what would be sent without sending anything."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N eligible picks (for testing).",
    )
    parser.add_argument(
        "--since", type=str, default=None, help="Only process picks with date >= YYYY-MM-DD."
    )
    args = parser.parse_args()

    run(dry_run=args.dry_run, limit=args.limit, since=args.since)


if __name__ == "__main__":
    main()
