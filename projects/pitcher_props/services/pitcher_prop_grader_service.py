import logging
from datetime import date
from typing import Optional

import requests

from services.pitcher_prop_db import grade_lock, DB_PATH
import sqlite3

logger = logging.getLogger(__name__)

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


STAT_FIELD_MAP = {
"outs_recorded": "outs",
"strikeouts": "strikeOuts",
"hits_allowed": "hits",
"walks_allowed": "baseOnBalls",
}


def _safe_get(url: str, params: dict = {}, timeout: int = 15) -> dict:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error("MLB API error %s: %s", url, e)
        return {}


def fetch_game_status(game_pk: int) -> dict:

    url = f"{MLB_API_BASE}/game/{game_pk}/linescore"
    data = _safe_get(url)
    if not data:
        return {"status": "Unknown", "game_pk": game_pk}
    status = data.get("currentInning", None)

    sched = _safe_get(f"{MLB_API_BASE}/schedule", {"gamePk": game_pk, "sportId": 1})
    dates = sched.get("dates", [])
    if dates:
        games = dates[0].get("games", [])
        if games:
            s = games[0].get("status", {})
            return {
"status": s.get("abstractGameState", "Unknown"),
"detail": s.get("detailedState", ""),
"game_pk": game_pk,
            }
    return {"status": "Unknown", "game_pk": game_pk}


def fetch_boxscore_pitching(game_pk: int) -> dict:

    url = f"{MLB_API_BASE}/game/{game_pk}/boxscore"
    data = _safe_get(url)
    if not data:
        return {}

    result = {}
    for side in ("home", "away"):
        team_data = data.get("teams", {}).get(side, {})
        pitchers = team_data.get("pitchers", [])
        players = team_data.get("players", {})

        for idx, pid in enumerate(pitchers):
            key = f"ID{pid}"
            pobj = players.get(key, {})
            stats = pobj.get("stats", {}).get("pitching", {})
            info = pobj.get("person", {})
            result[pid] = {
"player_id": pid,
"player_name": info.get("fullName", ""),
"outs": stats.get("outs"),
"strikeOuts": stats.get("strikeOuts"),
"hits": stats.get("hits"),
"baseOnBalls": stats.get("baseOnBalls"),
"started": idx == 0,
"side": side,
"batting_order_idx": idx,
            }
    return result


def determine_result_status(
    result_value: int,
    line: float,
    direction: str,
    pitcher_started: bool,
    pitcher_found: bool,
) -> tuple[str, Optional[str]]:

    if not pitcher_found:
        return "void", "Pitcher did not pitch (DNP)"

    if not pitcher_started:
        return "void", "Locked pitcher was not the starter"

    if line % 1 == 0 and result_value == int(line):
        return "push", None

    if direction == "Over":
        return ("won" if result_value > line else "lost"), None
    else:
        return ("won" if result_value < line else "lost"), None


def grade_game(game_pk: int, db_path: str = DB_PATH) -> dict:

    status_info = fetch_game_status(game_pk)
    if status_info.get("status", "").lower() != "final":
        return {
"game_pk": game_pk,
"status": status_info.get("status"),
"graded": [],
"skipped": "Game not final",
        }

    boxscore = fetch_boxscore_pitching(game_pk)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
"""SELECT id, player_id, player_name, prop_type, line, pick_direction
           FROM pitcher_prop_official_locks
           WHERE game_pk=? AND result_status='pending'""",
        (game_pk,),
    ).fetchall()
    conn.close()

    graded = []
    for lock_id, player_id, player_name, prop_type, line, direction in rows:
        stat_field = STAT_FIELD_MAP.get(prop_type)
        if not stat_field:
            logger.warning("Unknown prop_type %s for lock %d", prop_type, lock_id)
            continue

        pitcher_data = boxscore.get(player_id)
        if pitcher_data is None:

            for pid, pd in boxscore.items():
                if player_name.lower() in pd.get("player_name", "").lower():
                    pitcher_data = pd
                    break

        pitcher_found = pitcher_data is not None
        pitcher_started = pitcher_data.get("started", False) if pitcher_found else False

        if pitcher_found:
            raw_val = pitcher_data.get(stat_field)
            result_value = int(raw_val) if raw_val is not None else None
        else:
            result_value = None

        if result_value is None and pitcher_found:

            grade_lock(
                lock_id,
                0,
"review",
                void_reason=f"{stat_field} not found in boxscore",
                source="auto",
            )
            graded.append({"lock_id": lock_id, "status": "review"})
            continue

        result_status, void_reason = determine_result_status(
            result_value=result_value or 0,
            line=line,
            direction=direction,
            pitcher_started=pitcher_started,
            pitcher_found=pitcher_found,
        )

        grade_lock(
            lock_id=lock_id,
            result_value=result_value or 0,
            result_status=result_status,
            void_reason=void_reason,
            source="auto",
            path=db_path,
        )
        graded.append(
            {
"lock_id": lock_id,
"player_name": player_name,
"prop_type": prop_type,
"line": line,
"direction": direction,
"result_value": result_value,
"result_status": result_status,
"void_reason": void_reason,
            }
        )
        logger.info(
"Graded lock %d: %s %s %.1f %s → %s=%s (%s)",
            lock_id,
            player_name,
            prop_type,
            line,
            direction,
            stat_field,
            result_value,
            result_status,
        )

    return {
"game_pk": game_pk,
"status": "Final",
"graded": graded,
"count": len(graded),
    }


def grade_all_pending(db_path: str = DB_PATH) -> list[dict]:

    conn = sqlite3.connect(db_path)
    game_pks = [
        row[0] for row in conn.execute("""SELECT DISTINCT game_pk FROM pitcher_prop_official_locks
               WHERE result_status='pending' AND game_pk IS NOT NULL""").fetchall()
    ]
    conn.close()

    results = []
    for gp in game_pks:
        r = grade_game(gp, db_path)
        results.append(r)
    return results
