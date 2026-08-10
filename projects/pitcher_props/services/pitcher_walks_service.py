import logging
import math
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MODEL_VERSION = "bb_v1.0"
PROP_TYPE = "walks_allowed"
CLASSIFICATION = "Research Only"

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


def _safe_get(url: str, params: dict = {}, timeout: int = 10) -> dict:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("MLB API error %s: %s", url, e)
        return {}


def _fetch_walks_stats(player_id: int, n_starts: int = 8) -> dict:

    url = f"{MLB_API_BASE}/people/{player_id}/stats"
    data = _safe_get(
        url, {"stats": "gameLog", "group": "pitching", "season": "2025", "limit": str(n_starts)}
    )
    splits = (data.get("stats") or [{}])[0].get("splits", [])
    bb_list = []
    ip_list = []
    bf_list = []
    for s in splits:
        stat = s.get("stat", {})
        bb = stat.get("baseOnBalls")
        ip = stat.get("inningsPitched")
        bf = stat.get("battersFaced")
        if bb is not None:
            bb_list.append(int(bb))
        if ip is not None:
            parts = str(ip).split(".")
            ip_list.append(int(parts[0]) + (int(parts[1]) / 3.0 if len(parts) > 1 else 0))
        if bf is not None:
            bf_list.append(int(bf))

    if not bb_list:
        return {"avg_bb": None, "std_bb": None, "bb_per_9": None, "n_starts": 0, "bb_list": []}

    avg_bb = sum(bb_list) / len(bb_list)
    std_bb = math.sqrt(sum((x - avg_bb) ** 2 for x in bb_list) / max(len(bb_list) - 1, 1))
    total_ip = sum(ip_list)
    bb_per_9 = (sum(bb_list) / total_ip * 9) if total_ip > 0 else None
    total_bf = sum(bf_list)
    bb_pct = (sum(bb_list) / total_bf) if total_bf > 0 else None
    return {
"avg_bb": round(avg_bb, 2),
"std_bb": round(std_bb, 2),
"bb_per_9": round(bb_per_9, 3) if bb_per_9 else None,
"bb_pct": round(bb_pct, 4) if bb_pct else None,
"n_starts": len(bb_list),
"bb_list": bb_list,
    }


def analyze_pitcher_walks(
    player_id: int,
    pitcher_name: str,
    opp_abbr: str,
    lines_to_evaluate: Optional[list[float]] = None,
    n_starts: int = 8,
) -> dict:

    warnings = []
    bb_stats = _fetch_walks_stats(player_id, n_starts)
    if bb_stats["n_starts"] < 3:
        warnings.append(f'Only {bb_stats["n_starts"]} starts found — estimate unreliable')

    avg_bb = bb_stats.get("avg_bb") or 2.5
    std_bb = bb_stats.get("std_bb") or 1.2

    dist: dict[int, float] = {}
    total = 0.0
    max_bb = 12
    for bb in range(0, max_bb + 1):
        p = math.exp(-0.5 * ((bb - avg_bb) / max(std_bb, 0.5)) ** 2) / (
            max(std_bb, 0.5) * math.sqrt(2 * math.pi)
        )
        dist[bb] = p
        total += p
    if total > 0:
        dist = {bb: round(v / total, 5) for bb, v in dist.items()}

    if not lines_to_evaluate:
        ctr = round(avg_bb * 2) / 2
        lines_to_evaluate = [
            round(ctr + d, 1) for d in (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0) if ctr + d >= 0
        ]

    line_results: dict[float, dict] = {}
    for ln in lines_to_evaluate:
        prob_over = prob_under = prob_push = 0.0
        for bb, p in dist.items():
            if ln % 1 == 0:
                if bb > ln:
                    prob_over += p
                elif bb < ln:
                    prob_under += p
                else:
                    prob_push += p
            else:
                if bb > ln:
                    prob_over += p
                else:
                    prob_under += p
        line_results[float(ln)] = {
"prob_over": round(prob_over, 4),
"prob_under": round(prob_under, 4),
"prob_push": round(prob_push, 4),
        }

    return {
"player_id": player_id,
"player_name": pitcher_name,
"prop_type": PROP_TYPE,
"model_version": MODEL_VERSION,
"classification": CLASSIFICATION,
"bb_stats": bb_stats,
"avg_bb": avg_bb,
"std_bb": std_bb,
"opp_abbr": opp_abbr,
"distribution": dist,
"lines": line_results,
"warnings": warnings,
"note": "Research Only — not eligible for recommendations",
    }
