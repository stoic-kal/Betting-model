import sqlite3
import threading
import time

import requests

from config import ODDS_API_KEY, now_et

DB_PATH = "database/picks.db"
DEFAULT_TTL = 600
FORCE_DEDUP_SECONDS = 30
_lock = threading.Lock()
_cache = {"at": 0.0, "games": [], "stage": None}


def _log_call(stage, response, games, error=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS api_call_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, called_at TEXT, service TEXT,
          stage TEXT, status_code INTEGER, games INTEGER, requests_remaining TEXT,
          requests_used TEXT, request_cost TEXT, error TEXT)""")
        headers = response.headers if response is not None else {}
        conn.execute(
"""INSERT INTO api_call_log(called_at,service,stage,status_code,games,
          requests_remaining,requests_used,request_cost,error) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                now_et().isoformat(timespec="seconds"),
"odds",
                stage,
                response.status_code if response is not None else None,
                len(games or []),
                headers.get("x-requests-remaining"),
                headers.get("x-requests-used"),
                headers.get("x-requests-last"),
                str(error) if error else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def fetch_odds_games(stage="current", force=False, max_age_seconds=DEFAULT_TTL):

    with _lock:
        now = time.monotonic()
        age = now - _cache["at"]
        allowed_age = FORCE_DEDUP_SECONDS if force else max_age_seconds
        usable = _cache["games"] and age < allowed_age
        if usable:

            from services.market_snapshot_service import record_market_snapshot

            record_market_snapshot(_cache["games"], stage)
            return _cache["games"]
        try:
            response = requests.get(
"https://api.theoddsapi.com/odds/",
                headers={"x-api-key": ODDS_API_KEY},
                params={
"sport_key": "baseball_mlb",
"markets": "h2h,totals",
"oddsFormat": "decimal",
                },
                timeout=12,
            )
            response.raise_for_status()
            games = response.json().get("data", [])
            _cache.update({"at": time.monotonic(), "games": games, "stage": stage})
            from services.market_snapshot_service import record_market_snapshot

            record_market_snapshot(games, stage)
            _log_call(stage, response, games)
            return games
        except Exception as exc:
            _log_call(stage, locals().get("response"), [], exc)
            if _cache["games"] and age < 1800:
                return _cache["games"]
            raise


def cache_status():
    age = time.monotonic() - _cache["at"] if _cache["at"] else None
    return {
"cached_games": len(_cache["games"]),
"age_seconds": round(age, 1) if age is not None else None,
"stage": _cache["stage"],
    }
