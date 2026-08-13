from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from services.matchup_slate_service import build_slate

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "matchup_lab"
SLATE_FILE = DATA_DIR / "slate.json"
STATUS_FILE = DATA_DIR / "update_status.json"
PROFILE_STATUS_FILE = DATA_DIR / "profile_status.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def get_status() -> dict[str, Any]:
    collector = _read_json(STATUS_FILE, {})
    profiles = _read_json(PROFILE_STATUS_FILE, {})
    return {
        "status": profiles.get("status") or collector.get("status", "not_built"),
        "last_success": collector.get("last_success"),
        "latest_game_date": profiles.get("latest_game_date") or collector.get("latest_game_date"),
        "total_rows": collector.get("total_rows") or profiles.get("source_rows"),
        "profile_cutoff": profiles.get("cutoff"),
    }


def get_slate(target_date: str | None = None) -> dict[str, Any]:
    requested = target_date or date.today().isoformat()
    cached = _read_json(SLATE_FILE, {})
    if cached.get("date") == requested and cached.get("games"):
        return cached
    try:
        return build_slate(date.fromisoformat(requested))
    except ValueError:
        return {"date": requested, "games": [], "generated_at": None, "message": "Invalid date."}
    except FileNotFoundError as exc:
        return {"date": requested, "games": [], "generated_at": None, "message": f"Matchup profile file missing: {exc.filename}"}
    except Exception as exc:
        return {"date": requested, "games": [], "generated_at": None, "message": f"Could not build Matchup Lab slate: {exc}"}


def get_game(game_pk: int, target_date: str | None = None) -> dict[str, Any] | None:
    slate = get_slate(target_date)
    for game in slate.get("games", []):
        if int(game.get("game_pk", -1)) == int(game_pk):
            return game
    return None
