import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_DEFAULT_SOURCES = ["dk", "parlayapi", "theoddsapi"]
_SOURCES = os.getenv("PROP_ODDS_SOURCES", ",".join(_DEFAULT_SOURCES)).split(",")


def get_pitcher_prop_odds(
    pitcher_name: str,
    prop_types: Optional[list[str]] = None,
    target_date: Optional[str] = None,
    event_id: Optional[str] = None,
    sources: Optional[list[str]] = None,
) -> dict:

    sources = sources or _SOURCES
    prop_types = prop_types or ["outs_recorded", "strikeouts", "hits_allowed", "walks_allowed"]

    for source in sources:
        try:
            result = _fetch_from(source, pitcher_name, prop_types, target_date, event_id)
            if result:
                logger.info("Props for %s found via source=%s", pitcher_name, source)
                return result
        except Exception as e:
            logger.warning("Source %s failed for %s: %s", source, pitcher_name, e)
            continue

    logger.info("No prop odds found for %s from any source", pitcher_name)
    return {}


def get_all_pitcher_props_today(
    target_date: Optional[str] = None,
    sources: Optional[list[str]] = None,
    max_age_hours: float = 2.0,
    force_refresh: bool = False,
) -> dict:

    from datetime import date as _date
    from services.pitcher_prop_db import load_market_cache, save_market_cache, market_cache_age

    target_date = target_date or _date.today().isoformat()
    sources = sources or _SOURCES

    if not force_refresh:
        age = market_cache_age(target_date)
        if age is not None and age <= max_age_hours * 60:
            cached = load_market_cache(target_date, max_age_hours=max_age_hours)
            if cached:
                logger.info(
"Market cache hit for %s: %d pitchers (%.0f min old)",
                    target_date,
                    len(cached),
                    age,
                )
                return cached

    merged: dict = {}
    for source in sources:
        try:
            if source == "dk":
                from services.dk_props_scraper import scrape_all_pitcher_props

                data = scrape_all_pitcher_props(target_date)
            elif source == "parlayapi":
                from services.parlayapi_service import get_all_pitcher_props_cached

                data = get_all_pitcher_props_cached()
            else:
                continue
            if data:
                _merge_into(merged, data)
                logger.info("Live props from %s: %d pitchers", source, len(data))
        except Exception as e:
            logger.warning("Bulk fetch from %s failed: %s", source, e)
            continue

    if merged:
        try:
            saved = save_market_cache(merged, target_date)
            logger.info("Saved %d prop quotes to market cache for %s", saved, target_date)
        except Exception as e:
            logger.warning("Failed to save market cache: %s", e)

    return merged


def _fetch_from(
    source: str,
    pitcher_name: str,
    prop_types: list[str],
    target_date: Optional[str],
    event_id: Optional[str],
) -> dict:
    if source == "dk":
        from services.dk_props_scraper import get_props_for_pitcher_dk

        return get_props_for_pitcher_dk(pitcher_name, prop_types, target_date)

    elif source == "parlayapi":
        from services.parlayapi_service import get_props_for_pitcher

        return get_props_for_pitcher(pitcher_name, prop_types)

    elif source == "theoddsapi":
        if not event_id:
            return {}
        from services.pitcher_prop_quotes_service import get_market_for_player

        result: dict = {}
        for pt in prop_types:
            quotes = get_market_for_player(
                event_id=event_id,
                player_name=pitcher_name,
                prop_type=pt,
            )
            if quotes:
                result[pt] = quotes
        return result

    return {}


def _merge_into(base: dict, new: dict):

    for player, props in new.items():
        if player not in base:
            base[player] = props
            continue
        for prop_type, lines in props.items():
            if prop_type not in base[player]:
                base[player][prop_type] = lines
                continue
            for line, quote in lines.items():
                if line not in base[player][prop_type]:
                    base[player][prop_type][line] = quote
                else:

                    existing = base[player][prop_type][line]
                    ex_over = existing.get("over_dec") or 0
                    ex_under = existing.get("under_dec") or 0
                    nw_over = quote.get("over_dec") or 0
                    nw_under = quote.get("under_dec") or 0
                    if nw_over > ex_over:
                        existing["over_dec"] = nw_over
                        existing["best_over_book"] = quote.get(
"bookmaker", quote.get("best_over_book")
                        )
                    if nw_under > ex_under:
                        existing["under_dec"] = nw_under
                        existing["best_under_book"] = quote.get(
"bookmaker", quote.get("best_under_book")
                        )

                    o, u = _vigfree(existing.get("over_dec"), existing.get("under_dec"))
                    existing["market_prob_over"] = o
                    existing["market_prob_under"] = u


def _vigfree(o: Optional[float], u: Optional[float]):
    if not o or not u or o <= 1 or u <= 1:
        return None, None
    ro, ru = 1 / o, 1 / u
    t = ro + ru
    return round(ro / t, 5), round(ru / t, 5)


def check_sources() -> dict:

    status = {}
    if "dk" in _SOURCES:
        status["dk"] = {"configured": True, "free": True, "note": "DK internal API scraper"}
    if "parlayapi" in _SOURCES:
        from services.parlayapi_service import fetch_credits_remaining, PARLAY_API_KEY

        key_set = bool(PARLAY_API_KEY)
        credits = fetch_credits_remaining() if key_set else None
        status["parlayapi"] = {
"configured": key_set,
"credits_remaining": credits,
"note": "Set PARLAY_API_KEY env var",
        }
    if "theoddsapi" in _SOURCES:
        from services.pitcher_prop_quotes_service import ODDS_API_KEY

        status["theoddsapi"] = {
"configured": bool(ODDS_API_KEY),
"note": "Set ODDS_API_KEY env var",
        }
    return status
