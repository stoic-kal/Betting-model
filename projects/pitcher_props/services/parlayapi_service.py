import os
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PARLAY_API_KEY = os.getenv("PARLAY_API_KEY", "")
BASE_URL = "https://parlay-api.com/v1"
SPORT_KEY = "baseball_mlb"


PITCHER_MARKETS = [
"player_pitcher_outs",
"player_strikeouts",
"player_hits_allowed",
"player_walks",
"player_earned_runs",
]


MARKET_TO_PROP = {
"player_pitcher_outs": "outs_recorded",
"player_strikeouts": "strikeouts",
"player_hits_allowed": "hits_allowed",
"player_walks": "walks_allowed",
"player_earned_runs": "earned_runs",
}

_HEADERS = lambda: {"X-API-Key": PARLAY_API_KEY}


def _get(path: str, params: dict = {}):
    if not PARLAY_API_KEY:
        logger.warning("PARLAY_API_KEY not set")
        return None
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=_HEADERS(), params=params, timeout=15)
        remaining = r.headers.get("x-requests-remaining", "?")
        used = r.headers.get("x-requests-used", "?")
        logger.debug(
"ParlayAPI %s → %d | remaining=%s used=%s", path, r.status_code, remaining, used
        )
        if r.status_code == 403:
            logger.error("ParlayAPI credit limit exceeded")
            return None
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("ParlayAPI request error: %s", e)
        return None


def fetch_pitcher_props(
    markets: Optional[list[str]] = None,
    bookmakers: Optional[list[str]] = None,
    player: Optional[str] = None,
    event_id: Optional[str] = None,
    max_age_sec: int = 300,
) -> list[dict]:

    params: dict = {
"markets": ",".join(markets or PITCHER_MARKETS),
"maxAgeSec": max_age_sec,
    }
    if bookmakers:
        params["bookmakers"] = ",".join(bookmakers)
    if player:
        params["player"] = player
    if event_id:
        params["eventId"] = event_id

    data = _get(f"/sports/{SPORT_KEY}/props", params)
    if data is None:
        return []
    rows = data if isinstance(data, list) else data.get("results", [])
    logger.info(
"ParlayAPI: fetched %d prop rows (markets=%s)", len(rows), params.get("markets", "all")
    )
    return rows


def normalize_props(raw_rows: list[dict]) -> dict:

    from collections import defaultdict

    accum: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for row in raw_rows:
        player = row.get("player", "")
        mkt_key = row.get("market_key", "")
        prop_type = MARKET_TO_PROP.get(mkt_key)
        line = row.get("line")
        over_am = row.get("over_price")
        under_am = row.get("under_price")
        book = row.get("bookmaker", "")
        age = row.get("age_seconds", 999)

        if not player or not prop_type or line is None:
            continue

        over_dec = _american_to_decimal(over_am) if over_am else None
        under_dec = _american_to_decimal(under_am) if under_am else None

        accum[player][prop_type][float(line)].append(
            {
"over_dec": over_dec,
"under_dec": under_dec,
"bookmaker": book,
"age_seconds": age,
            }
        )

    result: dict = {}
    for player, props in accum.items():
        result[player] = {}
        for prop_type, lines in props.items():
            result[player][prop_type] = {}
            for line, quotes in lines.items():
                best_over = max(
                    (q for q in quotes if q["over_dec"]), key=lambda q: q["over_dec"], default=None
                )
                best_under = max(
                    (q for q in quotes if q["under_dec"]),
                    key=lambda q: q["under_dec"],
                    default=None,
                )

                over_dec = best_over["over_dec"] if best_over else None
                under_dec = best_under["under_dec"] if best_under else None
                mp_over, mp_under = _vigfree(over_dec, under_dec)

                result[player][prop_type][line] = {
"line": line,
"over_dec": over_dec,
"under_dec": under_dec,
"market_prob_over": mp_over,
"market_prob_under": mp_under,
"best_over_book": best_over["bookmaker"] if best_over else None,
"best_under_book": best_under["bookmaker"] if best_under else None,
"n_books": len({q["bookmaker"] for q in quotes}),
"age_seconds": min(q["age_seconds"] for q in quotes),
"source": "parlayapi",
                }
    return result


_bulk_cache: dict = {}
_BULK_CACHE_TTL = 300


def get_all_pitcher_props_cached(markets=None) -> dict:

    import time as _t

    cache_key = ",".join(sorted(markets or PITCHER_MARKETS))
    entry = _bulk_cache.get(cache_key)
    now = _t.time()
    if entry and now - entry[0] < _BULK_CACHE_TTL:
        return entry[1]
    raw = fetch_pitcher_props(markets=markets)
    normalized = normalize_props(raw) if raw else {}
    _bulk_cache[cache_key] = (now, normalized)
    logger.info("ParlayAPI: cache refreshed — %d pitchers found", len(normalized))
    return normalized


def get_props_for_pitcher(
    pitcher_name: str,
    prop_types=None,
) -> dict:

    markets = [k for k, v in MARKET_TO_PROP.items() if v in prop_types] if prop_types else None
    normalized = get_all_pitcher_props_cached(markets)
    name_lower = pitcher_name.lower()
    for pname, props in normalized.items():
        if name_lower in pname.lower() or pname.lower() in name_lower:
            return props
    return {}


def fetch_credits_remaining() -> Optional[int]:

    try:
        r = requests.get(f"{BASE_URL}/sports", headers=_HEADERS(), timeout=10)
        return int(r.headers.get("x-requests-remaining", -1))
    except Exception:
        return None


def _american_to_decimal(american) -> Optional[float]:

    try:
        a = float(american)
        if a >= 100:
            return round(a / 100 + 1, 4)
        elif a < 0:
            return round(100 / abs(a) + 1, 4)
    except (TypeError, ZeroDivisionError):
        pass
    return None


def _vigfree(
    over_dec: Optional[float], under_dec: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    if not over_dec or not under_dec or over_dec <= 1 or under_dec <= 1:
        return None, None
    raw_over = 1 / over_dec
    raw_under = 1 / under_dec
    total = raw_over + raw_under
    if total <= 0:
        return None, None
    return round(raw_over / total, 5), round(raw_under / total, 5)
