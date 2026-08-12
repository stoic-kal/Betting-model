def baseball_innings(value):
    """Convert baseball's .1/.2 outs notation into true fractional innings."""
    text = str(value or "0")
    whole, _, outs = text.partition(".")
    return float(whole or 0) + min(int(outs or 0), 2) / 3


def fip_from_mlb_stat(stat, min_ip=0.0, lower=2.0, upper=6.5):
    """Calculate FIP from MLB Stats API season-stat field names."""
    ip = baseball_innings(stat.get("inningsPitched", 0))
    if ip < min_ip:
        return None
    hr = float(stat.get("homeRuns", 0) or 0)
    bb = float(stat.get("baseOnBalls", 0) or 0)
    hbp = float(stat.get("hitBatsmen", 0) or 0)
    strikeouts = float(stat.get("strikeOuts", 0) or 0)
    raw = (13 * hr + 3 * (bb + hbp) - 2 * strikeouts) / max(ip, 0.1) + 3.10
    return max(lower, min(upper, raw))
