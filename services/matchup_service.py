"""Read-only service layer for the MLB Matchup Lab.

The web layer calls this module; templates/routes should not calculate baseball
metrics. V1 reads generated JSON artifacts from data/matchup_lab so the Flask
request path never scans the multi-million-row Statcast archive.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "matchup_lab"
SLATE_FILE = DATA_DIR / "slate.json"
STATUS_FILE = DATA_DIR / "update_status.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def get_status() -> dict[str, Any]:
    status = _read_json(STATUS_FILE, {})
    return {
        "status": status.get("status", "not_built"),
        "last_success": status.get("last_success"),
        "latest_game_date": status.get("latest_game_date"),
        "total_rows": status.get("total_rows"),
    }


def get_slate(target_date: str | None = None) -> dict[str, Any]:
    """Return the precomputed matchup slate without inventing missing data."""
    payload = _read_json(SLATE_FILE, {})
    requested = target_date or date.today().isoformat()
    if not payload:
        return {
            "date": requested,
            "games": [],
            "generated_at": None,
            "message": "Matchup profiles have not been built yet.",
        }

    if target_date and payload.get("date") != target_date:
        return {
            "date": target_date,
            "games": [],
            "generated_at": payload.get("generated_at"),
            "message": f"No precomputed Matchup Lab slate for {target_date}.",
        }
    return payload


def get_game(game_pk: int, target_date: str | None = None) -> dict[str, Any] | None:
    slate = get_slate(target_date)
    for game in slate.get("games", []):
        if int(game.get("game_pk", -1)) == int(game_pk):
            return game
    return None
