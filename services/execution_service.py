import math

from config import PORTFOLIO_LIMITS


VALID_RECOMMENDATION_TIERS = {"qualified_pick", "strong_lock"}


def validate_decimal_odds(value):
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return False, "odds are not numeric"
    if not math.isfinite(odds):
        return False, "odds are not finite"
    if odds <= 1.0:
        return False, "decimal odds must be greater than 1.0"
    if odds > PORTFOLIO_LIMITS["max_decimal_odds"]:
        return False, f"decimal odds exceed {PORTFOLIO_LIMITS['max_decimal_odds']:.1f}"
    return True, None


def sanitize_odds_quotes(quotes):
    valid, rejected = [], []
    for quote in quotes or []:
        ok, reason = validate_decimal_odds(quote)
        if ok:
            valid.append(float(quote))
        else:
            rejected.append({"value": quote, "reason": reason})
    return valid, rejected


def allocate_realized_stake(
    conn, *, date, matchup, game_id, theoretical_kelly, recommendation_tier
):
    theoretical = max(0.0, float(theoretical_kelly or 0))
    if theoretical <= 0:
        return {
            "theoretical_kelly_units": 0.0,
            "realized_stake_units": 0.0,
            "wager_status": "no_wager",
            "wager_reason": "theoretical Kelly is zero",
        }
    if recommendation_tier not in VALID_RECOMMENDATION_TIERS:
        return {
            "theoretical_kelly_units": theoretical,
            "realized_stake_units": 0.0,
            "wager_status": "no_wager",
            "wager_reason": "prediction is not an execution-eligible recommendation tier",
        }

    game_used = conn.execute(
        """SELECT COALESCE(SUM(realized_stake_units),0) FROM picks
           WHERE date=? AND matchup=? AND game_id<>? AND wager_status='wagered'""",
        (date, matchup, game_id),
    ).fetchone()[0]
    day_used = conn.execute(
        """SELECT COALESCE(SUM(realized_stake_units),0) FROM picks
           WHERE date=? AND game_id<>? AND wager_status='wagered'""",
        (date, game_id),
    ).fetchone()[0]
    allowed = min(
        theoretical,
        PORTFOLIO_LIMITS["max_single_wager_units"],
        max(0.0, PORTFOLIO_LIMITS["max_game_exposure_units"] - float(game_used or 0)),
        max(0.0, PORTFOLIO_LIMITS["max_daily_exposure_units"] - float(day_used or 0)),
    )
    allowed = round(max(0.0, allowed), 4)
    if allowed <= 0:
        reason = "game exposure limit reached" if game_used >= PORTFOLIO_LIMITS["max_game_exposure_units"] else "daily exposure limit reached"
        status = "blocked_exposure"
    elif allowed < theoretical:
        reason = "stake reduced by portfolio exposure limits"
        status = "wagered"
    else:
        reason = None
        status = "wagered"
    return {
        "theoretical_kelly_units": round(theoretical, 4),
        "realized_stake_units": allowed,
        "wager_status": status,
        "wager_reason": reason,
    }
