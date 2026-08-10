import logging
import math
from typing import Optional

import requests

logger = logging.getLogger(__name__)

MODEL_VERSION = "hits_v1.0"
PROP_TYPE = "hits_allowed"
CLASSIFICATION = "Research Only"

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


PARK_FACTORS: dict[str, float] = {
"COL": 1.18,
"BOS": 1.10,
"CIN": 1.08,
"TEX": 1.06,
"CHC": 1.05,
"MIL": 1.04,
"PHI": 1.03,
"NYY": 1.03,
"HOU": 1.02,
"ATL": 1.01,
"MIN": 1.00,
"DET": 1.00,
"STL": 1.00,
"WSH": 0.99,
"LAD": 0.98,
"SF": 0.97,
"OAK": 0.97,
"SEA": 0.96,
"MIA": 0.95,
"NYM": 0.97,
"CLE": 0.99,
"CWS": 1.00,
"KC": 1.01,
"BAL": 1.02,
"TB": 0.98,
"TOR": 1.00,
"LAA": 0.99,
"SD": 0.97,
"ARI": 1.04,
"PIT": 0.99,
}


def _safe_get(url: str, params: dict = {}, timeout: int = 10) -> dict:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug("MLB API error %s: %s", url, e)
        return {}


def _fetch_hits_allowed_stats(player_id: int, n_starts: int = 8) -> dict:

    url = f"{MLB_API_BASE}/people/{player_id}/stats"
    data = _safe_get(
        url, {"stats": "gameLog", "group": "pitching", "season": "2025", "limit": str(n_starts)}
    )
    splits = (data.get("stats") or [{}])[0].get("splits", [])
    h_list = []
    ip_list = []
    bf_list = []
    for s in splits:
        stat = s.get("stat", {})
        h = stat.get("hits")
        ip = stat.get("inningsPitched")
        bf = stat.get("battersFaced")
        if h is not None:
            h_list.append(int(h))
        if ip is not None:
            parts = str(ip).split(".")
            ip_list.append(int(parts[0]) + (int(parts[1]) / 3.0 if len(parts) > 1 else 0))
        if bf is not None:
            bf_list.append(int(bf))

    if not h_list:
        return {"avg_h": None, "std_h": None, "h_per_9": None, "n_starts": 0, "h_list": []}

    avg_h = sum(h_list) / len(h_list)
    std_h = math.sqrt(sum((x - avg_h) ** 2 for x in h_list) / max(len(h_list) - 1, 1))
    total_ip = sum(ip_list)
    h_per_9 = (sum(h_list) / total_ip * 9) if total_ip > 0 else None
    return {
"avg_h": round(avg_h, 2),
"std_h": round(std_h, 2),
"h_per_9": round(h_per_9, 3) if h_per_9 else None,
"n_starts": len(h_list),
"h_list": h_list,
    }


def _park_factor(team_abbr: str) -> float:

    return PARK_FACTORS.get(team_abbr.upper(), 1.00)


def analyze_pitcher_hits(
    player_id: int,
    pitcher_name: str,
    team_abbr: str,
    opp_abbr: str,
    lines_to_evaluate: Optional[list[float]] = None,
    n_starts: int = 8,
) -> dict:

    warnings = []
    h_stats = _fetch_hits_allowed_stats(player_id, n_starts)
    if h_stats["n_starts"] < 3:
        warnings.append(f'Only {h_stats["n_starts"]} starts — estimate unreliable')

    avg_h = h_stats.get("avg_h") or 6.0
    std_h = h_stats.get("std_h") or 2.0
    pf = _park_factor(team_abbr)

    avg_h_adj = round(avg_h * pf, 2)
    if pf != 1.0:
        warnings.append(f"Park factor adjustment: {team_abbr} PF={pf:.2f}")

    dist: dict[int, float] = {}
    total = 0.0
    max_h = 20
    for h in range(0, max_h + 1):
        p = math.exp(-0.5 * ((h - avg_h_adj) / max(std_h, 0.5)) ** 2) / (
            max(std_h, 0.5) * math.sqrt(2 * math.pi)
        )
        dist[h] = p
        total += p
    if total > 0:
        dist = {h: round(v / total, 5) for h, v in dist.items()}

    if not lines_to_evaluate:
        ctr = round(avg_h_adj * 2) / 2
        lines_to_evaluate = [
            round(ctr + d, 1) for d in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5) if ctr + d >= 0
        ]

    line_results: dict[float, dict] = {}
    for ln in lines_to_evaluate:
        prob_over = prob_under = prob_push = 0.0
        for h, p in dist.items():
            if ln % 1 == 0:
                if h > ln:
                    prob_over += p
                elif h < ln:
                    prob_under += p
                else:
                    prob_push += p
            else:
                if h > ln:
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
"h_stats": h_stats,
"avg_h_raw": avg_h,
"avg_h_adjusted": avg_h_adj,
"std_h": std_h,
"park_factor": pf,
"distribution": dist,
"lines": line_results,
"warnings": warnings,
"note": "Research Only — not eligible for recommendations",
    }
