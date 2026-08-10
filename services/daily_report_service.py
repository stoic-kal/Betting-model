from datetime import datetime, timedelta

from services import analytics_service, record_tracker_service

UNIT = record_tracker_service.UNIT


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _avg(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _fmt(value, suffix="", places=None, dash="—"):
    if value is None:
        return dash
    if places is not None:
        return f"{value:.{places}f}{suffix}"
    return f"{value}{suffix}"


def _record_str(wins, losses):
    return f"{wins}-{losses}"


def _to_kelly_shape(rows):

    return [
        {"status": r["status"], "odds": r["opening_odds"], "kelly_units": r.get("kelly_units") or 0}
        for r in rows
        if r["status"] in ("won", "lost") and r.get("opening_odds")
    ]


def _kelly_roi(rows):
    shaped = _to_kelly_shape(rows)
    if not shaped:
        return None
    return analytics_service.kelly_efficiency(shaped).get("kelly_roi")


def _type_block(rows):

    resolved = [r for r in rows if r["status"] in ("won", "lost")]
    wins = sum(1 for r in resolved if r["status"] == "won")
    losses = len(resolved) - wins
    profit = sum(r["profit"] for r in resolved if r["profit"] is not None)
    return {
"n": len(resolved),
"wins": wins,
"losses": losses,
"record": _record_str(wins, losses),
"win_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
"roi": round(profit / (len(resolved) * UNIT) * 100, 1) if resolved else None,
"profit": round(profit, 2) if resolved else None,
"avg_clv": _avg([r["clv"] for r in resolved]),
"avg_ev": _avg([r["ev"] for r in resolved]),
"kelly_roi": _kelly_roi(resolved),
    }


def _beat_close(rows):
    with_line = [r for r in rows if r.get("closing_odds") is not None]
    beat = [r for r in with_line if r.get("clv") is not None and r["clv"] > 0]
    return {
"beat_close": len(beat),
"with_closing_line": len(with_line),
"beat_close_pct": round(len(beat) / len(with_line) * 100, 1) if with_line else None,
    }


def _margin_for_row(r):

    if r["status"] != "won":
        return None
    if (
        r["type"] == "moneyline"
        and r.get("home_score") is not None
        and r.get("away_score") is not None
    ):
        return abs(r["home_score"] - r["away_score"])
    if (
        r["type"] == "totals"
        and r.get("actual_total") is not None
        and r.get("market_line") is not None
    ):
        return round(abs(r["actual_total"] - r["market_line"]), 2)
    return None


def generate_daily_report(date: str = None) -> dict:

    if date is None:
        from config import today_et

        date = today_et()

    all_rows = record_tracker_service.get_record_tracker(version=None)["timeline"]
    day_rows = [r for r in all_rows if r["date"] == date]
    day_resolved = [r for r in day_rows if r["status"] in ("won", "lost")]

    if not day_resolved:
        metrics = {"date": date, "total_picks": len(day_rows), "resolved_picks": 0}
        return {"metrics": metrics, "formatted_report": "No graded picks today."}

    ml_rows_today = [r for r in day_rows if r["type"] == "moneyline"]
    tot_rows_today = [r for r in day_rows if r["type"] == "totals"]

    glance = {
"total_picks": len(day_rows),
"moneyline_picks": len(ml_rows_today),
"totals_picks": len(tot_rows_today),
        **_beat_close(day_rows),
    }

    ml_block = _type_block(ml_rows_today)
    tot_block = _type_block(tot_rows_today)

    today_wins = [r for r in day_resolved if r["status"] == "won"]
    highest_ev = max(
        (r for r in today_wins if r.get("ev") is not None), key=lambda r: r["ev"], default=None
    )
    highest_kelly = max(
        (r for r in today_wins if r.get("kelly_units") is not None),
        key=lambda r: r["kelly_units"],
        default=None,
    )
    margins = [(r, _margin_for_row(r)) for r in today_wins]
    margins = [(r, m) for r, m in margins if m is not None]
    largest_margin = max(margins, key=lambda pair: pair[1], default=(None, None))

    best_picks = {
"highest_ev_winner": (
            {"game": highest_ev["game"], "ev": highest_ev["ev"]} if highest_ev else None
        ),
"highest_kelly_winner": (
            {"game": highest_kelly["game"], "kelly_units": highest_kelly["kelly_units"]}
            if highest_kelly
            else None
        ),
"largest_margin_win": (
            {"game": largest_margin[0]["game"], "margin": largest_margin[1]}
            if largest_margin[0]
            else None
        ),
    }

    misses = [r for r in tot_rows_today if r.get("total_error") is not None]
    misses.sort(key=lambda r: abs(r["total_error"]), reverse=True)
    biggest_misses = [
        {
"game": r["game"],
"expected_total": r["expected_total"],
"actual_total": r["actual_total"],
"error": r["total_error"],
        }
        for r in misses[:2]
    ]

    all_resolved = [r for r in all_rows if r["status"] in ("won", "lost")]
    ml_all = [r for r in all_resolved if r["type"] == "moneyline"]
    tot_all = [r for r in all_resolved if r["type"] == "totals"]

    all_time = {
"moneyline": _type_block(ml_all),
"totals": _type_block(tot_all),
"combined": {
            **_type_block(all_resolved),
            **_beat_close(all_rows),
"avg_ev": _avg([r["ev"] for r in all_resolved]),
"avg_clv": _avg([r["clv"] for r in all_resolved]),
        },
    }

    try:
        cutoff = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    except ValueError:
        cutoff = date
    last_7d = [r for r in all_rows if cutoff <= r["date"] <= date]
    last_7d_ml = _type_block([r for r in last_7d if r["type"] == "moneyline"])
    last_7d_tot = _type_block([r for r in last_7d if r["type"] == "totals"])

    resolved_chrono = [r for r in all_rows if r["status"] in ("won", "lost")]
    last_30 = resolved_chrono[-30:]
    last_100 = resolved_chrono[-100:]

    recent_form = {
"last_7_days": {"moneyline": last_7d_ml, "totals": last_7d_tot},
"last_30_picks": {
"moneyline": _type_block([r for r in last_30 if r["type"] == "moneyline"]),
"totals": _type_block([r for r in last_30 if r["type"] == "totals"]),
        },
"last_100_picks": {
"moneyline": _type_block([r for r in last_100 if r["type"] == "moneyline"]),
"totals": _type_block([r for r in last_100 if r["type"] == "totals"]),
        },
    }

    metrics = {
"date": date,
"glance": glance,
"moneyline": ml_block,
"totals": tot_block,
"best_picks": best_picks,
"biggest_misses": biggest_misses,
"all_time": all_time,
"recent_form": recent_form,
    }

    return {"metrics": metrics, "formatted_report": _format_report(metrics)}


_BAR = "━" * 30


def _type_lines(block):
    return (
        f"Record        {block['record']} ({_fmt(block['win_rate'], places=1)}%)\n"
        f"ROI           {_fmt(block['roi'], places=1)}%\n"
        f"Profit        ${_fmt(block['profit'], places=2)}\n"
        f"CLV           {_fmt(block['avg_clv'], places=2)}pp\n"
        f"Avg EV        {_fmt(block['avg_ev'], places=1)}%\n"
        f"Kelly ROI     {_fmt(block['kelly_roi'], places=1)}%"
    )


def _all_time_type_lines(block):
    return (
        f"Record        {block['record']}\n"
        f"Win Rate      {_fmt(block['win_rate'], places=1)}%\n"
        f"ROI           {_fmt(block['roi'], places=1)}%\n"
        f"Profit        ${_fmt(block['profit'], places=2)}\n"
        f"CLV           {_fmt(block['avg_clv'], places=2)}pp\n"
        f"Kelly ROI     {_fmt(block['kelly_roi'], places=1)}%"
    )


def _format_report(m: dict) -> str:
    g = m["glance"]
    ml, tot = m["moneyline"], m["totals"]
    bp = m["best_picks"]
    at = m["all_time"]
    rf = m["recent_form"]

    lines = [
        _BAR,
"📅 Daily Model Report",
        m["date"],
        _BAR,
"📌 TODAY AT A GLANCE",
        f"Total Picks        {g['total_picks']}",
        f"Moneyline          {g['moneyline_picks']}",
        f"Totals             {g['totals_picks']}",
        f"Beat Closing Line  {g['beat_close']}/{g['with_closing_line']}",
        f"({_fmt(g['beat_close_pct'], places=1)}%)",
        _BAR,
"⚾ MONEYLINE",
        _type_lines(ml),
        _BAR,
"🥎 TOTALS",
        _type_lines(tot),
        _BAR,
"🏆 BEST PICKS",
    ]

    if bp["highest_ev_winner"]:
        lines += [
"Highest EV Winner",
            bp["highest_ev_winner"]["game"],
            f"EV {_fmt(bp['highest_ev_winner']['ev'], places=1)}%",
        ]
    else:
        lines += ["Highest EV Winner", "No winning picks today"]
    if bp["highest_kelly_winner"]:
        lines += [
"Highest Kelly Winner",
            bp["highest_kelly_winner"]["game"],
            f"{_fmt(bp['highest_kelly_winner']['kelly_units'], places=2)}u",
        ]
    else:
        lines += ["Highest Kelly Winner", "No winning picks today"]
    if bp["largest_margin_win"]:
        lines += [
"Largest Margin Win",
            bp["largest_margin_win"]["game"],
            f"Won by {bp['largest_margin_win']['margin']}",
        ]
    else:
        lines += ["Largest Margin Win", "No margin data available"]

    lines += [_BAR, "⚠ BIGGEST MISSES"]
    if m["biggest_misses"]:
        for miss in m["biggest_misses"]:
            lines += [
                miss["game"],
                f"Expected: {_fmt(miss['expected_total'], places=2)}",
                f"Actual: {_fmt(miss['actual_total'], places=2)}",
                f"Error: {_fmt(miss['error'], places=2)}",
            ]
    else:
        lines.append("No totals misses to report")

    lines += [
        _BAR,
"🏆 ALL-TIME PERFORMANCE",
"Moneyline",
        _all_time_type_lines(at["moneyline"]),
"━" * 10,
"Totals",
        _all_time_type_lines(at["totals"]),
"━" * 10,
"Combined",
        f"Record        {at['combined']['record']}",
        f"Win Rate      {_fmt(at['combined']['win_rate'], places=1)}%",
        f"ROI           {_fmt(at['combined']['roi'], places=1)}%",
        f"Profit        ${_fmt(at['combined']['profit'], places=2)}",
        f"Beat Close    {_fmt(at['combined']['beat_close_pct'], places=1)}%",
        f"Average EV    {_fmt(at['combined']['avg_ev'], places=1)}%",
        f"Average CLV   {_fmt(at['combined']['avg_clv'], places=2)}pp",
        _BAR,
"📈 RECENT FORM",
"Last 7 Days",
"Moneyline",
        rf["last_7_days"]["moneyline"]["record"],
        f"ROI {_fmt(rf['last_7_days']['moneyline']['roi'], places=1)}%",
"Totals",
        rf["last_7_days"]["totals"]["record"],
        f"ROI {_fmt(rf['last_7_days']['totals']['roi'], places=1)}%",
"━" * 10,
"Last 30 Picks",
"Moneyline",
        rf["last_30_picks"]["moneyline"]["record"],
"Totals",
        rf["last_30_picks"]["totals"]["record"],
"━" * 10,
"Last 100 Picks",
"Moneyline",
        f"{_fmt(rf['last_100_picks']['moneyline']['win_rate'], places=1)}%",
"Totals",
        f"{_fmt(rf['last_100_picks']['totals']['win_rate'], places=1)}%",
        _BAR,
    ]

    return "\n".join(lines)
