import logging
import math
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MODEL_VERSION = "k_v1.0"
PROP_TYPE = "strikeouts"
CLASSIFICATION = "Research Only"

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


def _safe_get(url: str, params: dict = {}, timeout: int = 10) -> dict:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("MLB API fetch failed %s: %s", url, e)
        return {}


def _fetch_pitcher_k_stats(player_id: int, n_starts: int = 8) -> dict:

    url = f"{MLB_API_BASE}/people/{player_id}/stats"
    data = _safe_get(
        url,
        {
"stats": "gameLog",
"group": "pitching",
"season": "2025",
"limit": str(n_starts),
        },
    )
    splits = (data.get("stats") or [{}])[0].get("splits", [])
    k_list = []
    ip_list = []
    bf_list = []
    for s in splits:
        stat = s.get("stat", {})
        k = stat.get("strikeOuts")
        ip = stat.get("inningsPitched")
        bf = stat.get("battersFaced")
        if k is not None:
            k_list.append(int(k))
        if ip is not None:

            ip_str = str(ip)
            parts = ip_str.split(".")
            dec_ip = int(parts[0]) + (int(parts[1]) / 3.0 if len(parts) > 1 else 0)
            ip_list.append(dec_ip)
        if bf is not None:
            bf_list.append(int(bf))

    if not k_list:
        return {"k_per_9": None, "k_pct": None, "n_starts": 0, "k_list": []}

    total_k = sum(k_list)
    total_ip = sum(ip_list) if ip_list else None
    total_bf = sum(bf_list) if bf_list else None
    k_per_9 = (total_k / total_ip * 9) if (total_ip and total_ip > 0) else None
    k_pct = (total_k / total_bf) if (total_bf and total_bf > 0) else None
    return {
"k_per_9": round(k_per_9, 3) if k_per_9 else None,
"k_pct": round(k_pct, 4) if k_pct else None,
"n_starts": len(k_list),
"k_list": k_list,
"avg_k": round(sum(k_list) / len(k_list), 2),
"std_k": round(
            math.sqrt(
                sum((x - sum(k_list) / len(k_list)) ** 2 for x in k_list) / max(len(k_list) - 1, 1)
            ),
            2,
        ),
    }


def _fetch_opp_lineup_k_rate(opp_abbr: str) -> Optional[float]:

    url = f"{MLB_API_BASE}/teams"
    data = _safe_get(url, {"sportId": "1"})
    teams = data.get("teams", [])
    team_id = None
    for t in teams:
        if t.get("abbreviation", "").upper() == opp_abbr.upper():
            team_id = t.get("id")
            break
    if not team_id:
        return None

    stats_url = f"{MLB_API_BASE}/teams/{team_id}/stats"
    stats_data = _safe_get(stats_url, {"stats": "season", "group": "hitting", "season": "2025"})
    splits = (stats_data.get("stats") or [{}])[0].get("splits", [])
    if splits:
        stat = splits[0].get("stat", {})
        at_bats = stat.get("atBats", 0)
        strikeouts = stat.get("strikeOuts", 0)
        return round(strikeouts / at_bats, 4) if at_bats > 0 else None
    return None


def _discrete_k_dist(avg_k: float, std_k: float, max_k: int = 20) -> dict[int, float]:

    probs = {}
    total = 0.0
    for k in range(0, max_k + 1):

        p = math.exp(-0.5 * ((k - avg_k) / max(std_k, 0.5)) ** 2) / (
            max(std_k, 0.5) * math.sqrt(2 * math.pi)
        )
        probs[k] = p
        total += p
    if total > 0:
        probs = {k: v / total for k, v in probs.items()}
    return probs


def _line_probs_k(dist: dict[int, float], line: float) -> dict:

    prob_over = prob_under = prob_push = 0.0
    for k, p in dist.items():
        if line % 1 == 0:
            if k > line:
                prob_over += p
            elif k < line:
                prob_under += p
            else:
                prob_push += p
        else:
            if k > line:
                prob_over += p
            else:
                prob_under += p
    return {
"prob_over": round(prob_over, 4),
"prob_under": round(prob_under, 4),
"prob_push": round(prob_push, 4),
    }


def analyze_pitcher_strikeouts(
    player_id: int,
    pitcher_name: str,
    opp_abbr: str,
    lines_to_evaluate: Optional[list[float]] = None,
    n_starts: int = 8,
) -> dict:

    warnings = []

    k_stats = _fetch_pitcher_k_stats(player_id, n_starts)
    if k_stats["n_starts"] < 3:
        warnings.append(f'Only {k_stats["n_starts"]} starts found — distribution unreliable')

    avg_k = k_stats.get("avg_k", 5.0) or 5.0
    std_k = k_stats.get("std_k", 2.0) or 2.0

    opp_k_rate = _fetch_opp_lineup_k_rate(opp_abbr)
    if opp_k_rate is not None:

        lineup_adj = (opp_k_rate - 0.22) * 2.5
        avg_k_adj = round(avg_k + lineup_adj, 2)
    else:
        avg_k_adj = avg_k
        warnings.append("Opposing lineup K rate unavailable — using unadjusted avg")

    dist = _discrete_k_dist(avg_k_adj, std_k)

    if not lines_to_evaluate:
        center = round(avg_k_adj * 2) / 2
        lines_to_evaluate = [
            round(center + d, 1) for d in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5) if center + d >= 0
        ]

    line_results = {ln: _line_probs_k(dist, ln) for ln in lines_to_evaluate}

    return {
"player_id": player_id,
"player_name": pitcher_name,
"prop_type": PROP_TYPE,
"model_version": MODEL_VERSION,
"classification": CLASSIFICATION,
"k_stats": k_stats,
"avg_k_raw": avg_k,
"avg_k_adjusted": avg_k_adj,
"std_k": std_k,
"opp_k_rate": opp_k_rate,
"distribution": dist,
"lines": line_results,
"warnings": warnings,
"note": "Research Only — not eligible for recommendations under any circumstances",
    }
