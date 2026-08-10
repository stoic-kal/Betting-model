import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests

from services.pitcher_prop_db import save_quotes

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_BASE = "https://api.the-odds-api.com/v4"


PROP_MARKET_MAP = {
"outs_recorded": "pitcher_outs_recorded",
"strikeouts": "pitcher_strikeouts",
"hits_allowed": "pitcher_hits_allowed",
"walks_allowed": "pitcher_walks_allowed",
}


DEFAULT_BOOKS = "draftkings,fanduel,betmgm,caesars,pointsbetus,bovada,betonlineag"


FETCH_DELAY_S = 0.25


def _vigfree_probs(
    over_dec: Optional[float], under_dec: Optional[float]
) -> tuple[Optional[float], Optional[float]]:

    if not over_dec or not under_dec or over_dec <= 1 or under_dec <= 1:
        return None, None
    raw_over = 1.0 / over_dec
    raw_under = 1.0 / under_dec
    total = raw_over + raw_under
    if total <= 0:
        return None, None
    return raw_over / total, raw_under / total


def fetch_event_props(
    event_id: str,
    markets: Optional[list[str]] = None,
    bookmakers: str = DEFAULT_BOOKS,
) -> dict:

    if not ODDS_API_KEY:
        logger.warning("ODDS_API_KEY not set — skipping market fetch")
        return {}

    if markets is None:
        markets = list(PROP_MARKET_MAP.values())

    url = f"{ODDS_BASE}/sports/baseball_mlb/events/{event_id}/odds"
    params = {
"apiKey": ODDS_API_KEY,
"regions": "us",
"markets": ",".join(markets),
"bookmakers": bookmakers,
"oddsFormat": "decimal",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        remaining = resp.headers.get("x-requests-remaining", "?")
        logger.debug(
"OddsAPI event %s — status %d, remaining=%s", event_id, resp.status_code, remaining
        )
        if resp.status_code == 422:
            logger.info("Event %s not found on OddsAPI (422)", event_id)
            return {}
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error("OddsAPI fetch error event %s: %s", event_id, e)
        return {}


def parse_and_store_quotes(
    event_data: dict,
    event_id: str,
    game_pk: Optional[int],
    team: Optional[str],
    opponent: Optional[str],
    stage: str = "lineup_lock",
    is_pregame: bool = True,
) -> dict[str, list[dict]]:

    if not event_data:
        return {}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bookmakers_data = event_data.get("bookmakers", [])
    stored: dict[str, list[dict]] = {}

    for book in bookmakers_data:
        bookmaker = book.get("key", "")
        for market in book.get("markets", []):
            api_market_key = market.get("key", "")

            prop_type = next(
                (k for k, v in PROP_MARKET_MAP.items() if v == api_market_key),
                None,
            )
            if not prop_type:
                continue

            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                desc = outcome.get("description", "")
                point = outcome.get("point")
                price = outcome.get("price")

                if point is None or price is None:
                    continue

                direction = (
                    desc if desc in ("Over", "Under") else name.split()[-1] if name.split() else ""
                )
                player_name = name

                line_key = (player_name, prop_type, float(point))
                quote_key = (player_name, prop_type, float(point), bookmaker)

                if quote_key not in stored.get(prop_type, {}) and prop_type not in stored:
                    stored[prop_type] = []

                stored.setdefault(prop_type, {})

                inner_key = (player_name, float(point), bookmaker)
                stored[prop_type] = stored.get(prop_type, {})

    accum: dict = {}
    player_map: dict = {}

    for book in bookmakers_data:
        bookmaker = book.get("key", "")
        for market in book.get("markets", []):
            api_market_key = market.get("key", "")
            prop_type = next((k for k, v in PROP_MARKET_MAP.items() if v == api_market_key), None)
            if not prop_type:
                continue

            player_lines: dict = {}
            for outcome in market.get("outcomes", []):
                desc = outcome.get("description", "")
                point = outcome.get("point")
                price = outcome.get("price")
                pname = outcome.get("name", "")
                if point is None or price is None:
                    continue
                k = (pname, float(point))
                if k not in player_lines:
                    player_lines[k] = {"over": None, "under": None, "name": pname}
                if desc == "Over":
                    player_lines[k]["over"] = float(price)
                elif desc == "Under":
                    player_lines[k]["under"] = float(price)

            for (pname, line), pdata in player_lines.items():
                key = (pname, prop_type, line, bookmaker)
                accum[key] = {"over": pdata["over"], "under": pdata["under"]}

    all_quotes: list[dict] = []
    for (pname, prop_type, line, bookmaker), sides in accum.items():
        over_dec = sides["over"]
        under_dec = sides["under"]
        mp_over, mp_under = _vigfree_probs(over_dec, under_dec)
        all_quotes.append(
            {
"captured_at": now,
"stage": stage,
"event_id": event_id,
"game_pk": game_pk,
"player_id": None,
"player_name": pname,
"team": team,
"opponent": opponent,
"prop_type": prop_type,
"bookmaker": bookmaker,
"line": line,
"over_odds_dec": over_dec,
"under_odds_dec": under_dec,
"is_pregame": 1 if is_pregame else 0,
"is_live": 0,
"market_prob_over": mp_over,
"market_prob_under": mp_under,
            }
        )

    if all_quotes:
        save_quotes(all_quotes)
        logger.info(
"Stored %d prop quotes for event %s (stage=%s)", len(all_quotes), event_id, stage
        )

    result: dict = {}
    for q in all_quotes:
        pt = q["prop_type"]
        pn = q["player_name"]
        ln = q["line"]
        result.setdefault(pt, {}).setdefault(pn, {})[ln] = {
"line": ln,
"bookmaker": q["bookmaker"],
"over_odds_dec": q["over_odds_dec"],
"under_odds_dec": q["under_odds_dec"],
"market_prob_over": q["market_prob_over"],
"market_prob_under": q["market_prob_under"],
        }
    return result


def get_market_for_player(
    event_id: str,
    player_name: str,
    prop_type: str,
    game_pk: Optional[int] = None,
    team: Optional[str] = None,
    opponent: Optional[str] = None,
    stage: str = "lineup_lock",
) -> dict[float, dict]:

    if not ODDS_API_KEY:
        return {}

    api_market = PROP_MARKET_MAP.get(prop_type)
    if not api_market:
        return {}

    raw = fetch_event_props(event_id, markets=[api_market])
    if not raw:
        return {}

    parsed = parse_and_store_quotes(raw, event_id, game_pk, team, opponent, stage=stage)
    player_data = parsed.get(prop_type, {})

    pname_lower = player_name.lower()
    matched = None
    for pn, lines in player_data.items():
        if pname_lower in pn.lower() or pn.lower() in pname_lower:
            matched = lines
            break
    if matched is None:
        return {}

    return matched


def fetch_all_game_props(
    events: list[dict],
    stage: str = "lineup_lock",
) -> dict[str, dict]:

    results = {}
    for ev in events:
        eid = ev.get("event_id", "")
        game_pk = ev.get("game_pk")
        home = ev.get("home_team")
        away = ev.get("away_team")
        if not eid:
            continue
        raw = fetch_event_props(eid)
        if raw:
            results[eid] = parse_and_store_quotes(raw, eid, game_pk, home, away, stage=stage)
        time.sleep(FETCH_DELAY_S)
    return results
