import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)


DK_BASES = [
"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1",
"https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1",
"https://sportsbook-nash.draftkings.com/api/sportscontent/dkus/v1",
"https://sportsbook-nash.draftkings.com/api/sportscontent/v1",
]
DK_BASE = DK_BASES[0]

DK_LEAGUE_MLB = 84240
DK_TIMEOUT = 15


PITCHER_CATEGORY_NAMES = {"pitcher", "pitching"}


SUBCAT_KEYWORD_MAP = {
"outs recorded": "outs_recorded",
"outs rec": "outs_recorded",
"strikeout": "strikeouts",
"hits allowed": "hits_allowed",
"hits allow": "hits_allowed",
"walks allowed": "walks_allowed",
"earned run": "earned_runs",
"walk": "walks_allowed",
}

_SESSION = requests.Session()
_SESSION.headers.update(
    {
"User-Agent": (
"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
"AppleWebKit/537.36 (KHTML, like Gecko) "
"Chrome/126.0.0.0 Safari/537.36"
        ),
"Accept": "application/json, text/plain, */*",
"Accept-Language": "en-US,en;q=0.9",
"Referer": "https://sportsbook.draftkings.com/",
"Origin": "https://sportsbook.draftkings.com",
    }
)


_working_base: Optional[str] = None
_probe_failed_until: float = 0.0
_PROBE_FAIL_TTL = 300


def _find_working_base() -> Optional[str]:

    import time as _time

    global _working_base, _probe_failed_until

    if _working_base:
        return _working_base
    now = _time.time()
    if now < _probe_failed_until:
        return None

    statuses = []
    for base in DK_BASES:
        try:
            url = f"{base}/leagues/{DK_LEAGUE_MLB}"
            r = _SESSION.get(url, timeout=DK_TIMEOUT)
            try:
                data = r.json()
                top_keys = list(data.keys())[:6] if isinstance(data, dict) else ["<list>"]
            except ValueError:
                data = None
                top_keys = ["<non-JSON>"]
            label = base.replace("https://sportsbook-nash.draftkings.com/api/sportscontent/", "")
            statuses.append(f"{label} → HTTP {r.status_code} keys={top_keys}")
            if r.status_code == 200 and isinstance(data, dict):
                _working_base = base
                logger.info("DK: connected via %s (keys: %s)", base, top_keys)
                return base
        except requests.Timeout:
            statuses.append(f"{base} → TIMEOUT")
        except Exception as e:
            statuses.append(f"{base} → {type(e).__name__}: {e}")

    _probe_failed_until = now + _PROBE_FAIL_TTL
    logger.warning(
"DK: all endpoints failed (retry in %ds):\n  %s", _PROBE_FAIL_TTL, "\n".join(statuses)
    )
    return None


def _get(url: str, params: dict = {}) -> dict:
    try:
        r = _SESSION.get(url, params=params, timeout=DK_TIMEOUT)
        if r.status_code in (403, 404, 451):
            logger.warning("DK blocked/missing: %s → %d", url, r.status_code)
            return {}
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("DK scraper error %s: %s", url, e)
        return {}


def fetch_mlb_events(target_date: Optional[str] = None) -> list[dict]:

    base = _find_working_base()
    if not base:
        return []

    url = f"{base}/leagues/{DK_LEAGUE_MLB}"
    data = _get(url)
    if not data:
        return []

    eg = data.get("eventGroup", {})
    events_raw = (
        data.get("events") or eg.get("events") or data.get("eventGroups", [{}])[0].get("events", [])
        if data.get("eventGroups")
        else None or []
    )

    if not events_raw:
        logger.warning("DK: league response has no events. Top-level keys: %s", list(data.keys()))
        if eg:
            logger.warning("DK: eventGroup keys: %s", list(eg.keys()))

    today = target_date or date.today().isoformat()

    results = []
    for ev in events_raw:
        start = ev.get("startDate") or ev.get("startEventDate") or ev.get("eventDateUtc") or ""

        if today not in start:
            continue
        event_id = ev.get("id") or ev.get("eventId")
        if not event_id:
            continue
        results.append(
            {
"dk_event_id": event_id,
"name": ev.get("name", "") or ev.get("eventName", ""),
"start_time": start,
"home_team": _parse_home(ev),
"away_team": _parse_away(ev),
            }
        )

    logger.info("DK: found %d events for %s", len(results), today)
    return results


def _parse_home(ev: dict) -> str:

    teams = ev.get("teamGroups", []) or []
    home = next((t for t in teams if t.get("isHome")), None)
    if home:
        return home.get("name", "") or home.get("shortName", "")
    name = ev.get("name", "") or ev.get("eventName", "")
    return name.split(" @ ")[-1].strip() if " @ " in name else ""


def _parse_away(ev: dict) -> str:
    teams = ev.get("teamGroups", []) or []
    away = next((t for t in teams if not t.get("isHome")), None)
    if away:
        return away.get("name", "") or away.get("shortName", "")
    name = ev.get("name", "") or ev.get("eventName", "")
    return name.split(" @ ")[0].strip() if " @ " in name else ""


def fetch_event_categories(dk_event_id: int) -> list[dict]:

    base = _find_working_base()
    if not base:
        return []
    url = f"{base}/events/{dk_event_id}"
    data = _get(url)
    if not data:
        return []

    cats = (
        data.get("eventCategories")
        or data.get("offerCategories")
        or data.get("event", {}).get("offerCategories")
        or data.get("event", {}).get("eventCategories")
        or []
    )
    return cats


def find_pitcher_categories(categories: list[dict]) -> list[dict]:

    result = []
    for cat in categories:
        name = (
            cat.get("name", "") or cat.get("offerCategoryName", "") or cat.get("categoryName", "")
        ).lower()
        if any(kw in name for kw in PITCHER_CATEGORY_NAMES):
            result.append(cat)
    return result


def resolve_prop_type(subcat_name: str) -> Optional[str]:

    lower = subcat_name.lower()

    for kw in sorted(SUBCAT_KEYWORD_MAP, key=len, reverse=True):
        if kw in lower:
            return SUBCAT_KEYWORD_MAP[kw]
    return None


def parse_offer(offer: dict, prop_type: str, event_info: dict) -> list[dict]:

    player_name = (
        offer.get("label", "")
        or offer.get("participant", "")
        or offer.get("playerName", "")
        or offer.get("participantName", "")
    ).strip()

    line = offer.get("line") or offer.get("total") or offer.get("handicap")
    try:
        line = float(line) if line is not None else None
    except (TypeError, ValueError):
        line = None

    if not player_name or line is None:
        return []

    over_odds = under_odds = None
    outcomes = offer.get("outcomes", []) or []
    for o in outcomes:
        label = (
            o.get("label", "") or o.get("outcomeType", "") or o.get("participantType", "")
        ).lower()

        price_am = o.get("oddsAmerican") or o.get("americanOdds")
        price_dec = o.get("oddsDecimal") or o.get("decimalOdds")

        is_over = "over" in label or label in ("o", "yes")
        is_under = "under" in label or label in ("u", "no")

        if is_over:
            if price_am is not None:
                try:
                    over_odds = float(str(price_am).replace(",", ""))
                except (TypeError, ValueError):
                    pass
            elif price_dec is not None and over_odds is None:
                try:
                    over_odds = _decimal_to_american(float(price_dec))
                except (TypeError, ValueError):
                    pass

        elif is_under:
            if price_am is not None:
                try:
                    under_odds = float(str(price_am).replace(",", ""))
                except (TypeError, ValueError):
                    pass
            elif price_dec is not None and under_odds is None:
                try:
                    under_odds = _decimal_to_american(float(price_dec))
                except (TypeError, ValueError):
                    pass

    over_dec = _american_to_decimal(over_odds) if over_odds is not None else None
    under_dec = _american_to_decimal(under_odds) if under_odds is not None else None

    if over_dec is None and under_dec is None:
        return []

    mp_over, mp_under = _vigfree(over_dec, under_dec)

    return [
        {
"player_name": player_name,
"prop_type": prop_type,
"line": line,
"over_dec": over_dec,
"under_dec": under_dec,
"over_american": over_odds,
"under_american": under_odds,
"market_prob_over": mp_over,
"market_prob_under": mp_under,
"bookmaker": "draftkings",
"dk_event_id": event_info.get("dk_event_id"),
"home_team": event_info.get("home_team", ""),
"away_team": event_info.get("away_team", ""),
"source": "dk_scraper",
"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    ]


def _extract_offers_from_data(data: dict) -> list[dict]:

    og = data.get("offerGroups", [])
    if og:
        first_group = og[0] if isinstance(og, list) and og else {}
        offers_raw = first_group.get("offers", [])
        if offers_raw:
            if isinstance(offers_raw[0], list):

                return [o for row in offers_raw for o in (row if isinstance(row, list) else [row])]
            return offers_raw

    flat = data.get("offers", [])
    if flat:
        if flat and isinstance(flat[0], list):
            return [o for row in flat for o in row]
        return flat

    subcat = data.get("subcategory", {}) or {}
    return subcat.get("offers", [])


def scrape_event_pitcher_props(event_info: dict) -> list[dict]:

    dk_event_id = event_info.get("dk_event_id")
    if not dk_event_id:
        return []

    base = _find_working_base()
    if not base:
        return []

    cats = fetch_event_categories(dk_event_id)
    pitcher_cats = find_pitcher_categories(cats)

    if not pitcher_cats:

        logger.debug("No pitcher categories found for event %s — scanning all", dk_event_id)
        pitcher_cats = cats

    all_quotes = []

    for cat in pitcher_cats:
        cat_id = cat.get("id") or cat.get("offerCategoryId") or cat.get("categoryId")
        subcats = (
            cat.get("offerSubcategoryDescriptors")
            or cat.get("subcategories")
            or cat.get("subcategoryDescriptors")
            or []
        )

        for subcat in subcats:
            subcat_id = subcat.get("id") or subcat.get("subcategoryId")
            subcat_name = (
                subcat.get("name", "")
                or subcat.get("subcategoryName", "")
                or subcat.get("title", "")
            )
            prop_type = resolve_prop_type(subcat_name)

            if not prop_type:
                continue

            url = f"{base}/events/{dk_event_id}/categories/{cat_id}/subcategories/{subcat_id}"
            data = _get(url)
            if not data:
                continue

            offers = _extract_offers_from_data(data)
            for offer in offers:
                if isinstance(offer, dict):
                    all_quotes.extend(parse_offer(offer, prop_type, event_info))

            time.sleep(0.15)

    logger.debug("DK: event %s → %d prop quotes", dk_event_id, len(all_quotes))
    return all_quotes


def scrape_all_pitcher_props(target_date: Optional[str] = None) -> dict:

    target_date = target_date or date.today().isoformat()
    events = fetch_mlb_events(target_date)

    if not events:
        logger.info("DK scraper: no MLB events found for %s", target_date)
        return {}

    all_quotes: list[dict] = []
    for ev in events:
        quotes = scrape_event_pitcher_props(ev)
        all_quotes.extend(quotes)
        time.sleep(0.25)

    result: dict = {}
    for q in all_quotes:
        player = q["player_name"]
        pt = q["prop_type"]
        line = q["line"]
        result.setdefault(player, {}).setdefault(pt, {})[line] = q

    logger.info(
"DK scraper: %d prop quotes across %d pitchers for %s",
        len(all_quotes),
        len(result),
        target_date,
    )
    return result


def get_props_for_pitcher_dk(
    pitcher_name: str,
    prop_types: Optional[list[str]] = None,
    target_date: Optional[str] = None,
) -> dict:

    all_props = scrape_all_pitcher_props(target_date)
    name_lower = pitcher_name.lower()
    for pname, props in all_props.items():
        if name_lower in pname.lower() or pname.lower() in name_lower:
            if prop_types:
                return {k: v for k, v in props.items() if k in prop_types}
            return props
    return {}


def check_dk_connectivity() -> dict:

    global _working_base
    _working_base = None
    results = []
    for base in DK_BASES:
        try:
            url = f"{base}/leagues/{DK_LEAGUE_MLB}"
            r = _SESSION.get(url, timeout=DK_TIMEOUT)
            try:
                body = r.json()
                top_keys = list(body.keys()) if isinstance(body, dict) else ["<list>"]
            except ValueError:
                body = None
                top_keys = ["<non-JSON>"]
            results.append(
                {
"base": base,
"status": r.status_code,
"top_keys": top_keys,
"reachable": r.status_code == 200 and isinstance(body, dict),
                }
            )
        except Exception as e:
            results.append({"base": base, "status": "error", "error": str(e), "reachable": False})

    working = next((r for r in results if r["reachable"]), None)
    if working:
        _working_base = working["base"]

    event_count = 0
    if working:
        url = f'{working["base"]}/leagues/{DK_LEAGUE_MLB}'
        data = _get(url)
        eg = data.get("eventGroup", {})
        events = (
            data.get("events")
            or eg.get("events")
            or (
                data.get("eventGroups", [{}])[0].get("events", [])
                if data.get("eventGroups")
                else []
            )
        )
        event_count = len(events)

    return {
"reachable": bool(working),
"working_base": working["base"] if working else None,
"event_count": event_count,
"probe_results": results,
    }


def _american_to_decimal(american: float) -> Optional[float]:
    try:
        a = float(american)
        if a >= 100:
            return round(a / 100 + 1, 4)
        elif a < 0:
            return round(100 / abs(a) + 1, 4)
    except (TypeError, ZeroDivisionError):
        pass
    return None


def _decimal_to_american(decimal: float) -> Optional[float]:
    try:
        d = float(decimal)
        if d >= 2.0:
            return round((d - 1) * 100, 1)
        elif 1 < d < 2:
            return round(-100 / (d - 1), 1)
    except (TypeError, ZeroDivisionError):
        pass
    return None


def _vigfree(
    over_dec: Optional[float], under_dec: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    if not over_dec or not under_dec or over_dec <= 1 or under_dec <= 1:
        return None, None
    raw_o = 1 / over_dec
    raw_u = 1 / under_dec
    total = raw_o + raw_u
    if total <= 0:
        return None, None
    return round(raw_o / total, 5), round(raw_u / total, 5)
