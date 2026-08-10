import json
import logging
import os
import sqlite3

logger = logging.getLogger(__name__)

DB_PATH = "database/picks.db"
REPORT_HISTORY_PATH = os.path.join("data", "report_history.json")


def _load_history() -> dict:
    try:
        with open(REPORT_HISTORY_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_history(history: dict):
    os.makedirs(os.path.dirname(REPORT_HISTORY_PATH), exist_ok=True)
    with open(REPORT_HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2, sort_keys=True)


def already_sent(date_str: str) -> bool:
    return bool(_load_history().get(date_str))


def mark_sent(date_str: str):
    history = _load_history()
    history[date_str] = True
    _save_history(history)


def _fully_graded(date_str: str) -> bool:

    conn = sqlite3.connect(DB_PATH)
    try:
        total = conn.execute("SELECT COUNT(*) FROM picks WHERE date=?", (date_str,)).fetchone()[0]
        if total == 0:
            return False
        pending = conn.execute(
"SELECT COUNT(*) FROM picks WHERE date=? AND status='pending'", (date_str,)
        ).fetchone()[0]
        return pending == 0
    finally:
        conn.close()


def maybe_send_daily_report(date_str: str):

    try:
        if already_sent(date_str):
            print("Daily report already sent today.")
            print("Skipping.")
            return
        if not _fully_graded(date_str):
            return

        print("=" * 30)
        print("DAILY MODEL REPORT")
        print("=" * 30)
        print("Generating report...")

        from services.daily_report_service import generate_daily_report

        report = generate_daily_report(date_str)

        if report["formatted_report"] == "No graded picks today.":
            print("No graded picks today. Nothing to send.")
            return

        print("Daily report generated.")
        print("Posting to Discord...")

        try:
            from services import discord_service

            ok = discord_service.send_daily_model_summary(report["formatted_report"])
        except Exception as exc:
            ok = False
            print(f"Failed to send Daily Model Report:\n{exc}")

        if ok:
            print("Posted successfully.")
            mark_sent(date_str)
            print("Marked as sent.")
        else:
            print("Failed to send Daily Model Report:\nsend_daily_model_summary() returned False")
    except Exception as exc:

        logger.warning("report_dispatch_service.maybe_send_daily_report failed", exc_info=True)
        print(f"Failed to send Daily Model Report:\n{exc}")
