from __future__ import annotations

import statistics
from datetime import date
from typing import Optional

import requests

_CACHE: dict = {}
_CACHE_DATE: Optional[str] = None


def _cache_get(key):
    global _CACHE, _CACHE_DATE
    today = date.today().isoformat()
    if _CACHE_DATE != today:
        _CACHE_DATE, _CACHE = today, {}
    return _CACHE.get(key)


def _cache_set(key, value):
    _CACHE[key] = value
    return value


def ip_to_outs(ip_value: float) -> int:

    ip_str = f"{ip_value:.1f}"
    parts = ip_str.split(".")
    full_innings = int(parts[0])
    extra_outs = int(parts[1]) if len(parts) > 1 else 0

    extra_outs = min(extra_outs, 2)
    return full_innings * 3 + extra_outs


def outs_to_ip(outs: int) -> float:

    full = outs // 3
    remainder = outs % 3
    return float(f"{full}.{remainder}")


def ip_to_decimal(ip_value: float) -> float:

    outs = ip_to_outs(ip_value)
    return outs / 3.0


STATS_API = "https://statsapi.mlb.com/api/v1"
CURRENT_YEAR = date.today().year


def _fetch_pitcher_game_log(player_id: int, n_starts: int = 8) -> list[dict]:

    key = ("game_log", player_id, date.today().isoformat())
    cached = _cache_get(key)
    if cached is not None:
        return cached

    fallback: list[dict] = []
    try:
        r = requests.get(
            f"{STATS_API}/people/{player_id}/stats",
            params={
                "stats": "gameLog",
                "group": "pitching",
                "season": CURRENT_YEAR,
                "gameType": "R",
            },
            timeout=10,
        )
        r.raise_for_status()
        splits = r.json().get("stats", [{}])[0].get("splits", [])
    except Exception as exc:
        print(f"  Workload game log error (player={player_id}): {exc}")
        return _cache_set(key, fallback)

    starts = []
    for split in splits:
        stat = split.get("stat", {})
        ip_raw = stat.get("inningsPitched")
        if ip_raw is None:
            continue
        try:
            ip_val = float(ip_raw)
            pitches = int(stat.get("numberOfPitches", 0) or 0)
            bf = int(stat.get("battersFaced", 0) or 0)
            k = int(stat.get("strikeOuts", 0) or 0)
            bb = int(stat.get("baseOnBalls", 0) or 0)
            h = int(stat.get("hits", 0) or 0)
            game_date = split.get("date", "")
            opponent = (split.get("opponent", {}) or {}).get("name", "")
            is_starter = stat.get("gamesStarted", 0) or 0
        except (TypeError, ValueError):
            continue

        if int(is_starter) < 1 and pitches < 30:
            continue

        starts.append(
            {
                "date": game_date,
                "opponent": opponent,
                "ip_notation": ip_val,
                "outs": ip_to_outs(ip_val),
                "ip_decimal": ip_to_decimal(ip_val),
                "pitches": pitches,
                "bf": bf,
                "k": k,
                "bb": bb,
                "h": h,
            }
        )

    starts.sort(key=lambda x: x["date"], reverse=True)
    result = starts[:n_starts]
    return _cache_set(key, result)


def _fetch_season_stats(player_id: int) -> dict:

    key = ("season_stats", player_id, date.today().isoformat())
    cached = _cache_get(key)
    if cached is not None:
        return cached

    fallback = {
        "era": None,
        "ip": None,
        "gs": None,
        "k": None,
        "bb": None,
        "h": None,
        "avg_ip_per_start": None,
        "avg_pitches_per_start": None,
        "source": "fallback — season stats unavailable",
    }
    try:
        r = requests.get(
            f"{STATS_API}/people/{player_id}/stats",
            params={
                "stats": "season",
                "group": "pitching",
                "season": CURRENT_YEAR,
                "gameType": "R",
            },
            timeout=8,
        )
        r.raise_for_status()
        splits = r.json().get("stats", [{}])[0].get("splits", [])
        if not splits:
            return _cache_set(key, fallback)
        s = splits[0].get("stat", {})

        ip_raw = float(s.get("inningsPitched", 0) or 0)
        gs = int(s.get("gamesStarted", 0) or 0)
        k = int(s.get("strikeOuts", 0) or 0)
        bb = int(s.get("baseOnBalls", 0) or 0)
        h = int(s.get("hits", 0) or 0)
        era = float(s.get("era", 0) or 0)
        pitches_total = int(s.get("numberOfPitches", 0) or 0)

        avg_ip = ip_to_decimal(ip_raw) / max(gs, 1) if gs else None
        avg_pc = pitches_total / gs if gs and pitches_total else None

        result = {
            "era": round(era, 2),
            "ip": ip_raw,
            "gs": gs,
            "k": k,
            "bb": bb,
            "h": h,
            "avg_ip_per_start": round(avg_ip, 3) if avg_ip else None,
            "avg_pitches_per_start": round(avg_pc, 1) if avg_pc else None,
            "source": "MLB Stats API season totals",
        }
        return _cache_set(key, result)
    except Exception as exc:
        print(f"  Season stats error (player={player_id}): {exc}")
        return _cache_set(key, fallback)


def _classify_starter(recent_starts: list[dict], season_stats: dict) -> dict:

    if not recent_starts:
        avg_pitches = season_stats.get("avg_pitches_per_start")
        if avg_pitches is None:
            return {
                "role": "unknown",
                "label": "Unknown (no recent data)",
                "pitch_limit": 85,
                "source": "fallback",
            }
        avg_pitches = avg_pitches
    else:
        avg_pitches = (
            statistics.mean(s["pitches"] for s in recent_starts if s["pitches"] > 0)
            if any(s["pitches"] > 0 for s in recent_starts)
            else (season_stats.get("avg_pitches_per_start") or 85)
        )

    recent_outs = [s["outs"] for s in recent_starts] if recent_starts else []
    avg_outs = statistics.mean(recent_outs) if recent_outs else None

    if recent_starts:
        openers = sum(1 for s in recent_starts[:3] if s["pitches"] < 35 or s["outs"] < 6)
        if openers >= 2:
            return {
                "role": "opener",
                "label": "Opener (short appearance)",
                "pitch_limit": 35,
                "source": "recent start pitch-count pattern",
            }

    if avg_pitches < 75 or (avg_outs is not None and avg_outs < 15):
        return {
            "role": "pitch_limited",
            "label": "Pitch-Limited Starter",
            "pitch_limit": int(avg_pitches + 5),
            "source": "recent average pitch counts",
        }

    if avg_pitches >= 100 or (avg_outs is not None and avg_outs >= 21):
        return {
            "role": "workhorse",
            "label": "Workhorse Starter",
            "pitch_limit": int(min(avg_pitches + 10, 120)),
            "source": "recent average pitch counts",
        }

    return {
        "role": "typical",
        "label": "Typical Starter",
        "pitch_limit": int(avg_pitches + 5),
        "source": "recent average pitch counts",
    }


def _early_removal_prob(
    recent_starts: list[dict],
    season_stats: dict,
    bullpen_available: bool = True,
    opp_lineup_ops: float = 0.720,
) -> float:

    if not recent_starts:

        base = 0.30
    else:
        short_starts = sum(1 for s in recent_starts if s["outs"] < 15)
        base = short_starts / len(recent_starts)

    lineup_adj = max(0, (opp_lineup_ops - 0.720) * 0.5)

    bullpen_adj = -0.05 if not bullpen_available else 0.0

    prob = min(0.95, max(0.02, base + lineup_adj + bullpen_adj))
    return round(prob, 3)


def _outs_distribution(
    expected_outs: float,
    std_outs: float,
    max_outs: int = 27,
) -> dict[int, float]:

    import math as _math

    def _norm_pdf(x, mu, sigma):
        return _math.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * _math.sqrt(2 * _math.pi))

    std_outs = max(std_outs, 1.5)
    raw = {}
    for o in range(0, max_outs + 1):
        raw[o] = _norm_pdf(o, expected_outs, std_outs)

    total = sum(raw.values())
    if total <= 0:

        unif = 1.0 / (max_outs + 1)
        return {o: round(unif, 6) for o in range(max_outs + 1)}

    return {o: round(v / total, 6) for o, v in raw.items()}


def _over_under_push(dist: dict[int, float], line: float) -> dict:

    is_integer = line == int(line)
    line_int = int(line)

    over_prob = 0.0
    under_prob = 0.0
    push_prob = 0.0

    for outs, prob in dist.items():
        if is_integer:
            if outs > line_int:
                over_prob += prob
            elif outs < line_int:
                under_prob += prob
            else:
                push_prob += prob
        else:

            if outs > line:
                over_prob += prob
            else:
                under_prob += prob

    return {
        "over": round(over_prob, 4),
        "under": round(under_prob, 4),
        "push": round(push_prob, 4),
    }


def _data_quality(
    recent_starts: list[dict],
    season_stats: dict,
    lineup_confirmed: bool,
    has_statcast: bool,
) -> dict:

    checks = {}

    n = len(recent_starts)
    checks["recent_starts_5plus"] = n >= 5
    checks["recent_starts_3plus"] = n >= 3
    checks["recent_starts_1plus"] = n >= 1
    start_score = min(n / 5, 1.0) * 0.35

    has_pc = any(s["pitches"] > 0 for s in recent_starts) if recent_starts else False
    checks["pitch_counts_available"] = has_pc
    pc_score = 0.15 if has_pc else 0.0

    has_season = season_stats.get("gs", 0) and season_stats.get("gs", 0) > 0
    checks["season_stats_available"] = bool(has_season)
    season_score = 0.15 if has_season else 0.0

    checks["lineup_confirmed"] = lineup_confirmed
    lineup_score = 0.20 if lineup_confirmed else 0.0

    checks["statcast_available"] = has_statcast
    statcast_score = 0.15 if has_statcast else 0.0

    total = start_score + pc_score + season_score + lineup_score + statcast_score

    return {
        "score": round(total, 3),
        "label": (
            "Excellent"
            if total >= 0.85
            else "Good" if total >= 0.65 else "Fair" if total >= 0.40 else "Poor"
        ),
        "checks": checks,
        "n_recent_starts": n,
    }


def project_pitcher_workload(
    player_id: int,
    pitcher_name: str = "Unknown",
    team_abbr: str = "",
    opp_abbr: str = "",
    opp_lineup_ops: float = 0.720,
    lineup_confirmed: bool = False,
    bullpen_available: bool = True,
    rest_days: int = 4,
    is_injury_return: bool = False,
    injury_return_verified: bool = False,
    game_pk: Optional[int] = None,
) -> dict:

    recent_starts = _fetch_pitcher_game_log(player_id, n_starts=8) if player_id else []
    season_stats = (
        _fetch_season_stats(player_id)
        if player_id
        else {"source": "fallback — no player ID", "gs": None}
    )

    statcast = None
    try:
        from services.advanced_context_service import pitcher_statcast_profile

        statcast = pitcher_statcast_profile(player_id) if player_id else None
    except Exception:
        pass
    has_statcast = bool(statcast and statcast.get("available"))

    role_info = _classify_starter(recent_starts, season_stats)

    injury_note = None
    if is_injury_return:
        if injury_return_verified:
            injury_note = "Injury return — verified; may face pitch limit"

            role_info["pitch_limit"] = min(role_info["pitch_limit"], 75)
            role_info["label"] += " (injury return — verified)"
        else:
            injury_note = "Injury return status not verified from official source — ignored"

    provenance = {}

    if recent_starts:
        recent_outs = [s["outs"] for s in recent_starts]
        recent_pitches = [s["pitches"] for s in recent_starts if s["pitches"] > 0]
        recent_bf = [s["bf"] for s in recent_starts if s["bf"] > 0]

        weights = [0.9**i for i in range(len(recent_outs))]
        w_total = sum(weights)
        exp_outs_raw = sum(o * w / w_total for o, w in zip(recent_outs, weights))

        std_outs = statistics.stdev(recent_outs) if len(recent_outs) >= 2 else 3.0
        exp_pitches = (
            sum(p * w / w_total for p, w in zip(recent_pitches, weights))
            if recent_pitches
            else role_info["pitch_limit"]
        )
        exp_bf = (
            sum(b * w / w_total for b, w in zip(recent_bf, weights))
            if recent_bf
            else exp_outs_raw * 1.25
        )

        provenance["expected_outs"] = f"Weighted average of {len(recent_outs)} recent starts"
        provenance["expected_pitches"] = (
            f"Weighted average of {len(recent_pitches)} starts with pitch counts"
            if recent_pitches
            else "Pitch-limit estimate (no pitch count data)"
        )
        provenance["expected_bf"] = (
            f"Weighted average of {len(recent_bf)} starts with BF data"
            if recent_bf
            else "Estimated from expected outs × 1.25"
        )
    else:

        season_ip_avg = season_stats.get("avg_ip_per_start")
        season_pc_avg = season_stats.get("avg_pitches_per_start")
        season_outs_avg = ip_to_decimal(season_ip_avg) * 3 if season_ip_avg else None

        if season_outs_avg:
            exp_outs_raw = season_outs_avg
            std_outs = 3.5
            provenance["expected_outs"] = "Season IP per start (no recent game log)"
        else:

            exp_outs_raw = 15.0
            std_outs = 4.5
            provenance["expected_outs"] = "League-average fallback (no data available) "

        exp_pitches = season_pc_avg or role_info["pitch_limit"]
        exp_bf = exp_outs_raw * 1.25
        provenance["expected_pitches"] = (
            "Season average" if season_pc_avg else "Pitch-limit estimate "
        )
        provenance["expected_bf"] = "Estimated from expected outs × 1.25 "

    adj_notes = []

    if rest_days >= 6:
        exp_outs_raw += 0.5
        adj_notes.append("Extra rest (+0.5 outs)")
    elif rest_days <= 2:
        exp_outs_raw -= 1.0
        std_outs += 0.5
        adj_notes.append("Short rest (-1.0 outs, +uncertainty)")

    if opp_lineup_ops > 0.760:
        exp_outs_raw -= 1.5
        adj_notes.append(f"Tough lineup OPS={opp_lineup_ops:.3f} (-1.5 outs)")
    elif opp_lineup_ops > 0.730:
        exp_outs_raw -= 0.75
        adj_notes.append(f"Above-avg lineup OPS={opp_lineup_ops:.3f} (-0.75 outs)")
    elif opp_lineup_ops < 0.680:
        exp_outs_raw += 0.75
        adj_notes.append(f"Weak lineup OPS={opp_lineup_ops:.3f} (+0.75 outs)")

    pitches_per_out = exp_pitches / max(exp_outs_raw, 1)
    outs_at_limit = role_info["pitch_limit"] / max(pitches_per_out, 3.5)
    if exp_outs_raw > outs_at_limit:
        exp_outs_raw = min(exp_outs_raw, outs_at_limit)
        adj_notes.append(f'Capped by pitch limit {role_info["pitch_limit"]}')

    exp_outs_raw = min(exp_outs_raw, 27.0)
    exp_outs_raw = max(exp_outs_raw, 0.0)

    exp_outs = round(exp_outs_raw, 2)
    exp_ip = outs_to_ip(round(exp_outs_raw))
    provenance["adjustments"] = adj_notes if adj_notes else ["No adjustments applied"]

    early_removal = _early_removal_prob(
        recent_starts, season_stats, bullpen_available, opp_lineup_ops
    )

    dist = _outs_distribution(exp_outs, std_outs)

    dq = _data_quality(recent_starts, season_stats, lineup_confirmed, has_statcast)

    has_fallback = "" in str(provenance)
    if has_fallback:
        dq["score"] = min(dq["score"], 0.55)
        dq["label"] = min(
            ["Poor", "Fair", dq["label"]], key=["Excellent", "Good", "Fair", "Poor"].index
        )

    return {
        "player_id": player_id,
        "pitcher_name": pitcher_name,
        "team": team_abbr,
        "opponent": opp_abbr,
        "projection_date": date.today().isoformat(),
        "expected_outs": exp_outs,
        "expected_ip": exp_ip,
        "expected_ip_decimal": round(ip_to_decimal(exp_ip), 3),
        "expected_pitches": round(exp_pitches, 1),
        "expected_bf": round(exp_bf, 1),
        "std_outs": round(std_outs, 2),
        "early_removal_prob": early_removal,
        "outs_distribution": dist,
        "starter_role": role_info["role"],
        "starter_label": role_info["label"],
        "pitch_limit": role_info["pitch_limit"],
        "role_source": role_info["source"],
        "recent_starts": recent_starts,
        "season_stats": season_stats,
        "statcast": statcast,
        "lineup_confirmed": lineup_confirmed,
        "injury_note": injury_note,
        "data_quality": dq,
        "provenance": provenance,
        "has_fallback": has_fallback,
    }


def line_probs(workload: dict, line: float) -> dict:

    dist = workload.get("outs_distribution", {})
    if not dist:
        return {"over": None, "under": None, "push": None, "error": "no distribution"}
    return _over_under_push(dist, line)
