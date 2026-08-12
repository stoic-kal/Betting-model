from config import CONFIDENCE_BANDS, KELLY_CONFIG


def validate_odds(decimal_odds):
    try:
        return float(decimal_odds) > 1.0
    except (TypeError, ValueError):
        return False


def expected_value(prob, decimal_odds):
    if not validate_odds(decimal_odds):
        return 0.0
    return (float(prob) * float(decimal_odds) - 1.0) * 100.0


def kelly_fraction(prob, decimal_odds, fraction=None, prob_floor=None, prob_cap=None):
    if not validate_odds(decimal_odds):
        return 0.0
    fraction = KELLY_CONFIG["fraction"] if fraction is None else fraction
    floor = KELLY_CONFIG["prob_floor"] if prob_floor is None else prob_floor
    cap = KELLY_CONFIG["prob_cap"] if prob_cap is None else prob_cap
    p = min(max(float(prob), floor), cap)
    q = 1.0 - p
    b = float(decimal_odds) - 1.0
    return ((b * p - q) / b) * fraction


def kelly_units(prob, decimal_odds, fraction=None, min_units=None, max_units=None, prob_floor=None, prob_cap=None):
    f = kelly_fraction(prob, decimal_odds, fraction=fraction, prob_floor=prob_floor, prob_cap=prob_cap)
    if f <= 0:
        return 0.0
    lo = KELLY_CONFIG["min_units"] if min_units is None else min_units
    hi = KELLY_CONFIG["max_units"] if max_units is None else max_units
    return float(min(max(f, lo), hi))


def kelly_bankroll_stake(prob, decimal_odds, bankroll, fraction=None, min_units=None, max_units=None, prob_floor=None, prob_cap=None):
    units = kelly_units(prob, decimal_odds, fraction=fraction, min_units=min_units, max_units=max_units, prob_floor=prob_floor, prob_cap=prob_cap)
    return float(bankroll) * units


def confidence_label(prob):
    try:
        p = float(prob)
    except (TypeError, ValueError):
        return "—"
    for threshold, label, emoji in CONFIDENCE_BANDS:
        if p >= threshold:
            return f"{emoji} {label}"
    return "—"
