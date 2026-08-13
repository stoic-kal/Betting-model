from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "matchup_lab"
PROFILE_FILES = {
    "batter": DATA_DIR / "batter_pitch_profiles.json",
    "pitcher": DATA_DIR / "pitcher_pitch_profiles.json",
    "form": DATA_DIR / "rolling_form.json",
    "zones": DATA_DIR / "zone_profiles.json",
}
SLATE_FILE = DATA_DIR / "slate.json"
MLB_API = "https://statsapi.mlb.com/api/v1"


def _load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"), allow_nan=False)
    os.replace(tmp, path)


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{MLB_API}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Jingleez-Matchup-Lab/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _mean(values: list[float | None], weights: list[float] | None = None) -> float | None:
    pairs = [(float(v), float(weights[i]) if weights else 1.0) for i, v in enumerate(values) if v is not None and math.isfinite(float(v))]
    if not pairs:
        return None
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total else None


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scale(value: float | None, center: float, spread: float, reverse: bool = False) -> float | None:
    if value is None or spread <= 0:
        return None
    z = (float(value) - center) / spread
    if reverse:
        z = -z
    return round(_clamp(50.0 + 15.0 * z), 1)


def _index(rows: list[dict], key: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for row in rows:
        value = row.get(key)
        if value is not None:
            out.setdefault(int(value), []).append(row)
    return out


def _league_centers(batter_rows: list[dict]) -> dict[str, tuple[float, float]]:
    metrics = ["xwoba", "iso", "whiff_pct", "barrel_pct", "hard_hit_pct"]
    result = {}
    for metric in metrics:
        values = [float(r[metric]) for r in batter_rows if r.get(metric) is not None and r.get("pitches", 0) >= 25]
        if not values:
            result[metric] = (0.0, 1.0)
            continue
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        result[metric] = (mean, math.sqrt(variance) or 1.0)
    return result


def _pitch_match(batter_rows: list[dict], pitcher_rows: list[dict]) -> tuple[float | None, int]:
    batter_by_pitch = {r.get("pitch_type"): r for r in batter_rows}
    weighted = []
    total_weight = 0.0
    sample = 0
    for p in pitcher_rows:
        b = batter_by_pitch.get(p.get("pitch_type"))
        if not b:
            continue
        usage = float(p.get("usage_pct") or 0.0)
        bx = b.get("xwoba")
        px = p.get("xwoba_allowed")
        if bx is None and px is None:
            continue
        expected = _mean([bx, px])
        if expected is None:
            continue
        weighted.append(expected * usage)
        total_weight += usage
        sample += int(b.get("pitches") or 0)
    return ((sum(weighted) / total_weight) if total_weight else None, sample)


def _zone_match(batter_zones: list[dict], pitcher_zones: list[dict]) -> float | None:
    bz = {int(r["zone"]): r for r in batter_zones if r.get("zone") is not None}
    weighted = 0.0
    weight = 0.0
    total_pitcher = sum(int(r.get("pitches") or 0) for r in pitcher_zones)
    if not total_pitcher:
        return None
    for p in pitcher_zones:
        b = bz.get(int(p["zone"]))
        if not b:
            continue
        x = _mean([b.get("xwoba"), p.get("xwoba_allowed")])
        if x is None:
            continue
        w = int(p.get("pitches") or 0) / total_pitcher
        weighted += x * w
        weight += w
    return weighted / weight if weight else None


def _aggregate_batter(rows: list[dict]) -> dict[str, float | None]:
    weights = [max(1, int(r.get("pitches") or 0)) for r in rows]
    return {metric: _mean([r.get(metric) for r in rows], weights) for metric in ["xwoba", "iso", "whiff_pct", "barrel_pct", "hard_hit_pct", "avg_exit_velocity", "avg_launch_angle"]}


def _player_name(person: dict[str, Any] | None) -> str:
    return (person or {}).get("fullName") or "Unknown"


def _probable(game: dict[str, Any], side: str) -> dict[str, Any] | None:
    return game.get("teams", {}).get(side, {}).get("probablePitcher")


def _boxscore(game_pk: int) -> dict[str, Any]:
    return _get(f"/game/{game_pk}/boxscore")


def _lineup(box: dict[str, Any], side: str) -> list[dict[str, Any]]:
    team = box.get("teams", {}).get(side, {})
    order = team.get("battingOrder") or []
    players = team.get("players") or {}
    result = []
    for position, player_id in enumerate(order, 1):
        player = players.get(f"ID{player_id}", {})
        person = player.get("person", {})
        result.append({"id": int(player_id), "name": _player_name(person), "batting_order": position, "stand": (person.get("batSide") or {}).get("code")})
    return result


def build_slate(target_date: date) -> dict[str, Any]:
    batter_payload = _load(PROFILE_FILES["batter"])
    pitcher_payload = _load(PROFILE_FILES["pitcher"])
    form_payload = _load(PROFILE_FILES["form"])
    zone_payload = _load(PROFILE_FILES["zones"])
    batter_rows = batter_payload.get("rows", [])
    pitcher_rows = pitcher_payload.get("rows", [])
    batter_idx = _index(batter_rows, "batter")
    pitcher_idx = _index(pitcher_rows, "pitcher")
    form_idx = _index(form_payload.get("rows", []), "batter")
    batter_zone_idx = _index(zone_payload.get("hitters", []), "batter")
    pitcher_zone_idx = _index(zone_payload.get("pitchers", []), "pitcher")
    centers = _league_centers(batter_rows)
    schedule = _get("/schedule", {"sportId": 1, "date": target_date.isoformat(), "hydrate": "probablePitcher,team"})
    games = []
    for day in schedule.get("dates", []):
        for game in day.get("games", []):
            game_pk = int(game["gamePk"])
            away = game["teams"]["away"]["team"]
            home = game["teams"]["home"]["team"]
            away_pitcher = _probable(game, "away")
            home_pitcher = _probable(game, "home")
            try:
                box = _boxscore(game_pk)
            except Exception:
                box = {}
            away_lineup = _lineup(box, "away")
            home_lineup = _lineup(box, "home")

            def pitcher_info(person: dict[str, Any] | None) -> dict[str, Any]:
                if not person:
                    return {"id": None, "name": "TBD", "summary": "Probable starter not announced"}
                pid = int(person["id"])
                rows = pitcher_idx.get(pid, [])
                pitches = sum(int(r.get("pitches") or 0) for r in rows)
                return {"id": pid, "name": _player_name(person), "summary": f"{pitches:,} profiled pitches" if pitches else "No pitcher profile"}

            def hitter_cards(lineup: list[dict], opposing_pitcher: dict[str, Any] | None) -> list[dict]:
                pid = int(opposing_pitcher["id"]) if opposing_pitcher and opposing_pitcher.get("id") else None
                p_rows_all = pitcher_idx.get(pid, []) if pid else []
                p_zones = pitcher_zone_idx.get(pid, []) if pid else []
                cards = []
                for hitter in lineup:
                    bid = hitter["id"]
                    b_rows_all = batter_idx.get(bid, [])
                    hand = hitter.get("stand")
                    throws = None
                    if p_rows_all:
                        throws = next((r.get("stand") for r in []), None)
                    b_rows = b_rows_all
                    p_rows = [r for r in p_rows_all if not hand or r.get("stand") in (hand, None)] or p_rows_all
                    agg = _aggregate_batter(b_rows)
                    pitch_x, sample = _pitch_match(b_rows, p_rows)
                    zone_x = _zone_match(batter_zone_idx.get(bid, []), p_zones)
                    recent = next((r for r in form_idx.get(bid, []) if int(r.get("window_days", 0)) == 30), None)
                    x_center, x_spread = centers["xwoba"]
                    pit = _scale(pitch_x, x_center, x_spread)
                    zone = _scale(zone_x, x_center, x_spread)
                    form = _scale((recent or {}).get("xwoba"), x_center, x_spread)
                    platoon_x = _mean([r.get("xwoba") for r in b_rows if r.get("p_throws") == throws]) if throws else agg.get("xwoba")
                    platoon = _scale(platoon_x, x_center, x_spread)
                    components = [v for v in [pit, zone, form, platoon] if v is not None]
                    match = round(_mean(components) or 50.0, 1)
                    cards.append({
                        "id": bid, "name": hitter["name"], "stand": hand, "batting_order": hitter["batting_order"],
                        "match": match, "pitch_mix": pit, "zone": zone, "platoon": platoon, "form": form,
                        "xwoba": agg.get("xwoba"), "iso": agg.get("iso"), "whiff_pct": agg.get("whiff_pct"),
                        "barrel_pct": agg.get("barrel_pct"), "hard_hit_pct": agg.get("hard_hit_pct"),
                        "avg_exit_velocity": agg.get("avg_exit_velocity"), "avg_launch_angle": agg.get("avg_launch_angle"),
                        "sample_pitches": sample,
                    })
                return cards

            games.append({
                "game_pk": game_pk,
                "game_date": target_date.isoformat(),
                "game_time": game.get("gameDate"),
                "status": game.get("status", {}).get("detailedState"),
                "venue": (game.get("venue") or {}).get("name"),
                "away_team": away.get("abbreviation") or away.get("name"),
                "home_team": home.get("abbreviation") or home.get("name"),
                "away_team_name": away.get("name"),
                "home_team_name": home.get("name"),
                "away_pitcher": pitcher_info(away_pitcher),
                "home_pitcher": pitcher_info(home_pitcher),
                "away_hitters": hitter_cards(away_lineup, home_pitcher),
                "home_hitters": hitter_cards(home_lineup, away_pitcher),
            })
    payload = {
        "date": target_date.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_cutoff": batter_payload.get("meta", {}).get("cutoff"),
        "games": games,
        "message": None if games else f"No MLB games found for {target_date.isoformat()}.",
    }
    _write(SLATE_FILE, payload)
    return payload
