import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from .matchup_normalizer import MatchupNormalizer
except ImportError:
    from matchup_normalizer import MatchupNormalizer


FINAL_ABSTRACT_STATE = "Final"


class ResultsUpdater:
    """Grade official picks from authoritative MLB final states.

    Grading and notification enqueueing occur in one SQLite transaction.  Discord
    delivery is deliberately disabled for non-production databases so unit tests,
    diagnostics, and local fixtures can never contact the production channel.
    """

    def __init__(self, db_path="database/picks.db", notifier=None):
        self.db_path = db_path
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.normalizer = MatchupNormalizer()
        production = Path(__file__).resolve().parent.parent / "database" / "picks.db"
        self.is_production_db = Path(db_path).resolve() == production.resolve()
        self.notifier = notifier

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn):
        conn.execute("BEGIN IMMEDIATE")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(picks)")}
        for name, kind in (
            ("game_id", "TEXT"),
            ("odds", "REAL"),
            ("home_score", "INTEGER"),
            ("away_score", "INTEGER"),
            ("actual_total", "INTEGER"),
            ("mlb_game_pk", "INTEGER"),
            ("graded_at", "TEXT"),
            ("grade_source", "TEXT"),
            ("notification_sent", "INTEGER NOT NULL DEFAULT 0"),
            ("notification_sent_at", "TEXT"),
        ):
            if name not in columns:
                conn.execute(f"ALTER TABLE picks ADD COLUMN {name} {kind}")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS notification_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                claimed_at TEXT,
                sent_at TEXT,
                last_error TEXT,
                UNIQUE(pick_id, notification_type),
                FOREIGN KEY(pick_id) REFERENCES picks(id)
            )"""
        )
        conn.commit()

    def extract_line(self, pick_str):
        try:
            parts = pick_str.split()
            if len(parts) >= 2:
                return float(parts[-1])
        except (AttributeError, TypeError, ValueError):
            pass
        return None

    def convert_home_away_to_team(self, matchup, pick_choice):
        if pick_choice not in ("HOME", "AWAY"):
            return self.normalizer.extract_team(pick_choice)
        parts = matchup.split(" @ ")
        if len(parts) != 2:
            return pick_choice
        away_team = self.normalizer.extract_team(parts[0])
        home_team = self.normalizer.extract_team(parts[1])
        return home_team if pick_choice == "HOME" else away_team

    def get_final_scores(self, target_date):
        """Return only games for which MLB explicitly reports abstract state Final."""
        try:
            resp = requests.get(
                f"{self.base_url}/schedule",
                params={"startDate": target_date, "endDate": target_date, "sportId": 1},
                timeout=10,
            )
            resp.raise_for_status()
            final_games = {}
            for date_obj in resp.json().get("dates", []):
                for game in date_obj.get("games", []):
                    status = game.get("status") or {}
                    if status.get("abstractGameState") != FINAL_ABSTRACT_STATE:
                        continue
                    try:
                        home_runs = int(game["teams"]["home"]["score"])
                        away_runs = int(game["teams"]["away"]["score"])
                        home_name = game["teams"]["home"]["team"]["name"]
                        away_name = game["teams"]["away"]["team"]["name"]
                        matchup = self.normalizer.normalize_matchup(f"{away_name} @ {home_name}")
                        game_pk = int(game["gamePk"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    final_games[game_pk] = {
                        "game_pk": game_pk,
                        "matchup": matchup,
                        "mlb_abstract_state": status.get("abstractGameState"),
                        "mlb_detailed_state": status.get("detailedState"),
                        "home_runs": home_runs,
                        "away_runs": away_runs,
                        "total_runs": home_runs + away_runs,
                        "home_won": home_runs > away_runs,
                        "home_team": self.normalizer.extract_team(home_name),
                        "away_team": self.normalizer.extract_team(away_name),
                    }
            return final_games
        except Exception as exc:
            print(f"Error fetching scores: {exc}")
            return {}

    def _select_final(self, row, final_games):
        # Compatibility with test fixtures that use normalized matchup keys.
        games = list(final_games.values())
        if row["mlb_game_pk"] is not None:
            game = final_games.get(int(row["mlb_game_pk"]))
            return game if game and game.get("mlb_abstract_state", FINAL_ABSTRACT_STATE) == FINAL_ABSTRACT_STATE else None
        normalized = self.normalizer.normalize_matchup(row["matchup"])
        candidates = [
            g for g in games
            if g.get("matchup", normalized if len(games) == 1 else None) == normalized
            and g.get("mlb_abstract_state", FINAL_ABSTRACT_STATE) == FINAL_ABSTRACT_STATE
        ]
        # A matchup-only identity is unsafe for doubleheaders.
        return candidates[0] if len(candidates) == 1 else None

    def _grade(self, row, game):
        pick_type = row["pick_type"]
        pick_choice = row["pick"]
        if pick_type == "moneyline":
            actual_pick = self.convert_home_away_to_team(row["matchup"], pick_choice).lower()
            if actual_pick == game["home_team"]:
                return "won" if game["home_won"] else "lost"
            if actual_pick == game["away_team"]:
                return "lost" if game["home_won"] else "won"
            return None
        if pick_type == "totals":
            line = self.extract_line(pick_choice)
            if line is None:
                return None
            total = game["total_runs"]
            if total == line:
                return "push"
            won = total > line if "OVER" in pick_choice.upper() else total < line
            return "won" if won else "lost"
        return None

    def _enqueue_result(self, conn, row, status):
        overall, ml, totals = self._current_records(conn)
        odds = row["odds"]
        profit = (float(odds) - 1) if status == "won" and odds is not None else -1.0 if status == "lost" else 0.0
        payload = {
            "matchup": row["matchup"], "pick": row["pick"],
            "pick_type": row["pick_type"], "status": status,
            "profit_units": profit, "overall_record": overall,
            "moneyline_record": ml, "totals_record": totals,
        }
        key = hashlib.sha256(
            f"result:{row['game_id']}:{row['id']}:{status}".encode()
        ).hexdigest()
        conn.execute(
            """INSERT OR IGNORE INTO notification_outbox
               (pick_id,notification_type,idempotency_key,payload)
               VALUES (?,'result',?,?)""",
            (row["id"], key, json.dumps(payload, sort_keys=True)),
        )

    def update_all_results(self, target_date):
        final_games = self.get_final_scores(target_date)
        if not final_games:
            print(f"Updating results for {target_date}...\nNo final games found")
            return 0
        conn = self._connect()
        self._ensure_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT id,game_id,matchup,pick,pick_type,status,odds,mlb_game_pk
               FROM picks WHERE date=? AND status='pending' ORDER BY id""",
            (target_date,),
        ).fetchall()
        updated = 0
        newly_graded = []
        for row in rows:
            game = self._select_final(row, final_games)
            if not game:
                continue
            status = self._grade(row, game)
            if not status:
                continue
            now = datetime.now(timezone.utc).isoformat()
            changed = conn.execute(
                """UPDATE picks SET status=?,updated_at=?,graded_at=?,grade_source='mlb_stats_api_final',
                          mlb_game_pk=COALESCE(mlb_game_pk,?),home_score=?,away_score=?,actual_total=?
                   WHERE id=? AND status='pending'""",
                (status, now, now, game.get("game_pk"), game["home_runs"],
                 game["away_runs"], game["total_runs"], row["id"]),
            ).rowcount
            if changed != 1:
                continue
            updated += 1
            newly_graded.append((row, status))
        # Build every notification only after the full grading batch is visible
        # inside this transaction, so all messages carry the same complete record.
        for row, status in newly_graded:
            self._enqueue_result(conn, row, status)
        conn.commit()
        conn.close()
        if self.is_production_db:
            self.dispatch_result_notifications()
        print(f"Updated {updated} picks for {target_date}")
        return updated

    def dispatch_result_notifications(self):
        """Atomically claim outbox rows; Discord nonce makes retries idempotent."""
        if not self.is_production_db:
            return 0
        sent = 0
        while True:
            conn = self._connect()
            self._ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """SELECT * FROM notification_outbox
                   WHERE status='pending' OR
                         (status='sending' AND unixepoch(claimed_at) < unixepoch('now','-10 minutes'))
                   ORDER BY id LIMIT 1"""
            ).fetchone()
            if not row:
                conn.commit(); conn.close(); break
            claimed = datetime.now(timezone.utc).isoformat()
            changed = conn.execute(
                """UPDATE notification_outbox SET status='sending',claimed_at=?,attempts=attempts+1
                   WHERE id=? AND (status='pending' OR
                       (status='sending' AND unixepoch(claimed_at) < unixepoch('now','-10 minutes')))""",
                (claimed, row["id"]),
            ).rowcount
            conn.commit(); conn.close()
            if changed != 1:
                continue
            try:
                if self.notifier is None:
                    from services import discord_service
                    ok = discord_service.send_results(
                        json.loads(row["payload"]), idempotency_key=row["idempotency_key"]
                    )
                else:
                    ok = self.notifier(json.loads(row["payload"]), row["idempotency_key"])
                conn = self._connect(); conn.execute("BEGIN IMMEDIATE")
                if ok:
                    now = datetime.now(timezone.utc).isoformat()
                    conn.execute("UPDATE notification_outbox SET status='sent',sent_at=?,last_error=NULL WHERE id=?", (now, row["id"]))
                    conn.execute("UPDATE picks SET notification_sent=1,notification_sent_at=? WHERE id=?", (now, row["pick_id"]))
                    sent += 1
                else:
                    conn.execute("UPDATE notification_outbox SET status='pending',last_error='send returned false' WHERE id=?", (row["id"],))
                conn.commit(); conn.close()
            except Exception as exc:
                conn = self._connect()
                conn.execute("UPDATE notification_outbox SET status='pending',last_error=? WHERE id=?", (str(exc), row["id"]))
                conn.commit(); conn.close()
        return sent

    def _current_records(self, conn):
        def record(pick_type=None):
            query = "SELECT status,COUNT(*) FROM picks WHERE status IN ('won','lost')"
            params = []
            if pick_type:
                query += " AND pick_type=?"; params.append(pick_type)
            query += " GROUP BY status"
            counts = dict(conn.execute(query, params).fetchall())
            return f"{counts.get('won', 0)}-{counts.get('lost', 0)}"
        return record(), record("moneyline"), record("totals")

    def update_pending_results(self, through_date):
        conn = self._connect()
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM picks WHERE status='pending' AND date<=? ORDER BY date",
            (through_date,),
        )]
        conn.close()
        return sum(self.update_all_results(date_str) or 0 for date_str in dates)


if __name__ == "__main__":
    from config import today_et
    ResultsUpdater().update_pending_results(today_et())
