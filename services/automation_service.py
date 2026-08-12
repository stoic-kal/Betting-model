import json
import sqlite3
from datetime import datetime, timezone

from config import now_et, today_et
from services.schedule_service import get_live_state

DB_PATH = "database/picks.db"


CLV_WINDOW_MINUTES = 20


def _claim(key, retry_after_seconds):
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("""CREATE TABLE IF NOT EXISTS automation_state (
        task_key TEXT PRIMARY KEY, claimed_at TEXT NOT NULL, completed_at TEXT,
        status TEXT NOT NULL, detail TEXT)""")
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT claimed_at,status FROM automation_state WHERE task_key=?", (key,)
    ).fetchone()
    if row:
        try:
            age = (now - datetime.fromisoformat(row[0])).total_seconds()
        except ValueError:
            age = 0
        if row[1] == "complete" or age < retry_after_seconds:
            conn.rollback()
            conn.close()
            return False
        conn.execute(
            'UPDATE automation_state SET claimed_at=?,status="running",detail=NULL WHERE task_key=?',
            (now.isoformat(), key),
        )
    else:
        conn.execute(
            'INSERT INTO automation_state(task_key,claimed_at,status) VALUES (?,? ,"running")',
            (key, now.isoformat()),
        )
    conn.commit()
    conn.close()
    return True


def _finish(key, status, detail):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE automation_state SET completed_at=?,status=?,detail=? WHERE task_key=?",
        (datetime.now(timezone.utc).isoformat(), status, json.dumps(detail, default=str), key),
    )
    conn.commit()
    conn.close()


def run_automation_tick(date_str=None, live_games=None):

    date_str = date_str or today_et()
    games = live_games if live_games is not None else get_live_state(date_str)
    report = {"date": date_str, "results_updated": 0, "clv_captured": 0}

    stage_by_hour = {9: "overnight", 12: "morning", 15: "afternoon"}
    local_now = now_et()
    stage = stage_by_hour.get(local_now.hour) if local_now.minute <= 10 else None
    if date_str == today_et() and stage:
        snapshot_key = f"market:{date_str}:{stage}"
        if _claim(snapshot_key, 600):
            try:
                from services.schedule_service import _fetch_odds

                markets = _fetch_odds(stage, force=True)
                snapshot_status = "complete" if markets else "error"
                _finish(snapshot_key, snapshot_status, {"games": len(markets)})
                report["market_snapshot"] = stage if markets else None
            except Exception as exc:
                _finish(snapshot_key, "error", {"error": str(exc)})

    now = datetime.now(timezone.utc)
    due_by_stage = {"lineup_lock": []}
    for game in games:
        try:
            start = datetime.fromisoformat(game["game_date_utc"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        minutes = (start - now).total_seconds() / 60
        if game.get("game_state") != "Preview":
            continue

        if 2 <= minutes <= 240:
            due_by_stage["lineup_lock"].append(game)
    for forecast_stage, due_games in due_by_stage.items():
        claimed = []
        for game in due_games:
            key = f"forecast:{date_str}:{game['game_pk']}:{forecast_stage}"
            if not _claim(key, 300):
                continue
            try:
                from services.game_context_service import get_lineup_status

                readiness = get_lineup_status(game["game_pk"], force=True)
            except Exception as exc:
                readiness = {"confirmed": False, "error": str(exc)}
            if not readiness.get("confirmed"):
                _finish(key, "waiting", readiness)
                continue
            claimed.append((key, game))
        if not claimed:
            continue
        from services.pick_service import generate_picks

        recorded = 0

        for key, game in claimed:
            try:
                result = generate_picks(forecast_stage, [game["game_pk"]])
                complete_pair = (
                    result.get("status") == "success"
                    and result.get("moneyline_count") == 1
                    and result.get("totals_count") == 1
                    and result.get("recorded_count") == 2
                )
                status = "complete" if complete_pair else "error"
                _finish(key, status, {"game_pk": game["game_pk"], **result})
                if complete_pair:
                    recorded += 2
            except Exception as exc:
                _finish(key, "error", {"game_pk": game["game_pk"], "error": str(exc)})
        report[forecast_stage] = recorded

    result_key = f'results:{date_str}:{datetime.now(timezone.utc).strftime("%Y%m%d%H%M")}'
    if _claim(result_key, 90):
        try:
            from src.update_results import ResultsUpdater

            updater = ResultsUpdater()
            updated = updater.update_all_results(date_str) or 0

            import sqlite3 as _sqlite3

            _today = date_str
            conn_s = _sqlite3.connect(updater.db_path)
            prior_dates = [
                r[0]
                for r in conn_s.execute(
                    "SELECT DISTINCT date FROM picks WHERE status='pending' AND date<? ORDER BY date",
                    (_today,),
                ).fetchall()
            ]
            conn_s.close()
            for pd in prior_dates:
                updated += updater.update_all_results(pd) or 0
            report["results_updated"] = updated
            _finish(result_key, "complete", {"updated": updated})

            try:
                from services.report_dispatch_service import maybe_send_daily_report

                maybe_send_daily_report(date_str)
                for pd in prior_dates:
                    maybe_send_daily_report(pd)
            except Exception as exc:
                print(f"  Daily Model Report dispatch failed: {exc}")
        except Exception as exc:
            _finish(result_key, "error", {"error": str(exc)})

    if local_now.hour >= 3:
        learning_key = f"learning:{date_str}"
        if _claim(learning_key, 3600):
            try:
                from services.model_learning_service import run_learning_cycle

                learning = run_learning_cycle()
                report["learning"] = learning
                _finish(learning_key, "complete", learning)
            except Exception as exc:
                _finish(learning_key, "error", {"error": str(exc)})

    due = []
    for game in games:
        try:
            start = datetime.fromisoformat(game["game_date_utc"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        minutes = (start - now).total_seconds() / 60
        if -2 <= minutes <= CLV_WINDOW_MINUTES and game["game_state"] != "Final":
            key = f"clv:{date_str}:{game['game_pk']}"
            if _claim(key, 300):
                due.append((key, game["matchup"]))
    if due:
        try:
            from services.clv_service import capture_clv

            result = capture_clv(date_str, [matchup for _, matchup in due])
            report["clv_captured"] = result.get("captured", 0)
            conn = sqlite3.connect(DB_PATH)
            for key, matchup in due:
                remaining = conn.execute(
                    """SELECT COUNT(*) FROM picks
                    WHERE date=? AND matchup=? AND closing_odds IS NULL""",
                    (date_str, matchup),
                ).fetchone()[0]
                status = "complete" if remaining == 0 else "error"
                _finish(key, status, {"matchup": matchup, "remaining": remaining, **result})
            conn.close()
        except Exception as exc:
            for key, matchup in due:
                _finish(key, "error", {"matchup": matchup, "error": str(exc)})

    conn = sqlite3.connect(DB_PATH)
    pending_dates = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT date FROM picks WHERE closing_odds IS NULL AND status IN ('won','lost')"
        ).fetchall()
    ]
    conn.close()
    for d in pending_dates:
        backfill_key = f"clv_backfill:{d}"
        if _claim(backfill_key, 3600):
            try:
                from services.clv_service import backfill_missing_clv

                backfill = backfill_missing_clv(d)
                if d == date_str:
                    report["clv_backfilled"] = backfill.get("backfilled", 0)

                _finish(backfill_key, "ok", backfill)
            except Exception as exc:
                _finish(backfill_key, "error", {"error": str(exc)})

    return report
