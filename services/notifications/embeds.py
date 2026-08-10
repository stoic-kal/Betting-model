from datetime import datetime, timezone

COLOR_MONEYLINE = 0x22C55E
COLOR_TOTALS = 0x3B82F6
COLOR_WIN = 0x22C55E
COLOR_LOSS = 0xEF4444
COLOR_DAILY_SUMMARY = 0x8B5CF6
COLOR_WEEKLY_SUMMARY = 0xFACC15
COLOR_DIAGNOSTICS = 0xF97316
COLOR_MODEL_HEALTH = 0x06B6D4
COLOR_MODEL_OUTPUT = 0x3B82F6
COLOR_PUSH = 0x94A3B8

FOOTER_MODEL = "Model v3.3 Advanced"


_CONFIDENCE_BANDS = [
    (0.65, "Very High", "🟢"),
    (0.60, "High", "🟢"),
    (0.55, "Moderate", "🟡"),
    (0.0, "Low", "🔴"),
]


def _confidence_label(model_prob) -> str:
    try:
        p = float(model_prob)
    except (TypeError, ValueError):
        return "—"
    for threshold, label, emoji in _CONFIDENCE_BANDS:
        if p >= threshold:
            return f"{emoji} {label}"
    return "—"


def _f(value, fmt, default="—"):

    try:
        return format(float(value), fmt)
    except (TypeError, ValueError):
        return default


def _pct(value) -> str:

    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _odds(value) -> str:

    return _f(value, ".2f")


def _kelly(value) -> str:
    return f'{_f(value, ".2f", default="0.00")}u'


def _field(name, value, inline=True):
    return {"name": name, "value": str(value) if value not in (None, "") else "—", "inline": inline}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_pick_embed(pick: dict) -> dict:

    pick_type = (pick.get("pick_type") or "").lower()
    sportsbook = pick.get("sportsbook") or "Best Available"

    if pick_type == "totals":
        fields = [
            _field("Game", pick.get("matchup", "—"), inline=False),
            _field("Pick", pick.get("pick", "—")),
            _field("Probability", _pct(pick.get("model_prob"))),
            _field("Expected Total", _f(pick.get("expected_total"), ".2f")),
            _field("Market Line", _f(pick.get("market_line"), ".2f")),
            _field("Kelly Unit", _kelly(pick.get("kelly_units"))),
            _field("Sportsbook", sportsbook),
            _field("Odds", _odds(pick.get("odds_dec"))),
        ]
        title = "⚾ MLB TOTALS"
        color = COLOR_TOTALS
    else:
        fields = [
            _field("Game", pick.get("matchup", "—"), inline=False),
            _field("Pick", pick.get("pick", "—")),
            _field("Probability", _pct(pick.get("model_prob"))),
            _field("Kelly Unit", _kelly(pick.get("kelly_units"))),
            _field("Sportsbook", sportsbook),
            _field("Odds", _odds(pick.get("odds_dec"))),
        ]
        title = "⚾ MLB MONEYLINE"
        color = COLOR_MONEYLINE

    return {
"title": title,
"color": color,
"fields": fields,
"footer": {"text": FOOTER_MODEL},
"timestamp": _timestamp(),
    }


def build_result_embed(result: dict) -> dict:

    status = str(result.get("status", "")).lower()
    pick_type = (result.get("pick_type") or "").upper()

    if status == "won":
        result_label, color = "✅ WIN", COLOR_WIN
    elif status == "push":
        result_label, color = "➖ PUSH", COLOR_PUSH
    else:
        result_label, color = "❌ LOSS", COLOR_LOSS

    profit = result.get("profit_units")
    profit_str = _f(profit, "+.2f") if profit is not None else ("0.00" if status == "push" else "—")

    fields = [
        _field("Game", result.get("matchup", "—"), inline=False),
        _field("Pick", result.get("pick", "—")),
        _field("Result", result_label),
        _field("Profit/Loss (Units)", profit_str),
        _field("Running Overall Record", result.get("overall_record", "—")),
        _field("Moneyline Record", result.get("moneyline_record", "—")),
        _field("Totals Record", result.get("totals_record", "—")),
    ]

    return {
"title": f"⚾ MLB RESULT — {pick_type}" if pick_type else "⚾ MLB RESULT",
"color": color,
"fields": fields,
"footer": {"text": FOOTER_MODEL},
"timestamp": _timestamp(),
    }


def build_daily_summary_embed(data: dict) -> dict:
    fields = [
        _field("Moneyline Picks", data.get("moneyline_picks", "—")),
        _field("Totals Picks", data.get("totals_picks", "—")),
        _field("Highest Probability Pick", data.get("highest_probability_pick", "—"), inline=False),
        _field("Highest Kelly Pick", data.get("highest_kelly_pick", "—"), inline=False),
    ]
    return {
"title": "📊 DAILY SUMMARY",
"color": COLOR_DAILY_SUMMARY,
"fields": fields,
"footer": {"text": "Generated automatically"},
"timestamp": _timestamp(),
    }


def build_weekly_summary_embed(data: dict) -> dict:
    fields = [
        _field("Moneyline Record", data.get("moneyline_record", "—")),
        _field("Totals Record", data.get("totals_record", "—")),
        _field("Overall Record", data.get("overall_record", "—")),
        _field("ROI", _f(data.get("roi"), "+.1f") + "%" if data.get("roi") is not None else "—"),
        _field(
"Profit",
            _f(data.get("profit"), "+.2f") + "u" if data.get("profit") is not None else "—",
        ),
    ]
    return {
"title": "📈 WEEKLY SUMMARY",
"color": COLOR_WEEKLY_SUMMARY,
"fields": fields,
"footer": {"text": data.get("model_version", FOOTER_MODEL)},
"timestamp": _timestamp(),
    }


def build_model_health_embed(data: dict) -> dict:
    fields = [
        _field("Health Score", data.get("health_score", "—")),
        _field(
"Moneyline ROI",
            (
                _f(data.get("moneyline_roi"), "+.1f") + "%"
                if data.get("moneyline_roi") is not None
                else "—"
            ),
        ),
        _field(
"Totals ROI",
            _f(data.get("totals_roi"), "+.1f") + "%" if data.get("totals_roi") is not None else "—",
        ),
        _field("Calibration Grade", data.get("calibration_grade", "—")),
        _field("Recommendation", data.get("recommendation", "—"), inline=False),
    ]
    return {
"title": "🩺 MODEL HEALTH",
"color": COLOR_MODEL_HEALTH,
"fields": fields,
"footer": {"text": FOOTER_MODEL},
"timestamp": _timestamp(),
    }


def build_moneyline_output_embed(data: dict) -> dict:

    model_prob = data.get("model_prob")
    market_prob = data.get("market_prob")
    diff_str = "—"
    try:
        diff_pp = (float(model_prob) - float(market_prob)) * 100
        diff_str = f"{diff_pp:+.1f}pp"
    except (TypeError, ValueError):
        pass

    fields = [
        _field("Game", data.get("matchup", "—"), inline=False),
        _field("Prediction", data.get("prediction", "—")),
        _field("Model Probability", _pct(model_prob)),
        _field("Market Probability", _pct(market_prob)),
        _field("Difference", diff_str),
        _field("Confidence", _confidence_label(model_prob)),
        _field("Model Version", data.get("model_version", FOOTER_MODEL)),
    ]
    return {
"title": "🧠 MONEYLINE MODEL OUTPUT",
"color": COLOR_MODEL_OUTPUT,
"fields": fields,
"timestamp": _timestamp(),
    }


def build_totals_output_embed(data: dict) -> dict:

    expected_total = data.get("expected_total")
    market_line = data.get("market_line")
    diff_str = "—"
    try:
        diff_runs = float(expected_total) - float(market_line)
        diff_str = f"{diff_runs:+.2f} Runs"
    except (TypeError, ValueError):
        pass

    fields = [
        _field("Game", data.get("matchup", "—"), inline=False),
        _field("Prediction", data.get("prediction", "—")),
        _field("Expected Total", _f(expected_total, ".2f")),
        _field("Market Line", _f(market_line, ".2f")),
        _field("Difference", diff_str),
        _field("Model Probability", _pct(data.get("model_prob"))),
        _field("Confidence", _confidence_label(data.get("model_prob"))),
        _field("Kelly Unit", _kelly(data.get("kelly_units"))),
        _field("Model Version", data.get("model_version", FOOTER_MODEL)),
    ]
    return {
"title": "🧠 TOTALS MODEL OUTPUT",
"color": COLOR_MODEL_OUTPUT,
"fields": fields,
"timestamp": _timestamp(),
    }


def build_diagnostics_embed(data: dict) -> dict:

    fields = [_field(str(k).replace("_", " ").title(), v) for k, v in (data or {}).items()] or [
        _field("Status", "No diagnostics data provided", inline=False)
    ]
    return {
"title": "🔧 DIAGNOSTICS",
"color": COLOR_DIAGNOSTICS,
"fields": fields,
"footer": {"text": FOOTER_MODEL},
"timestamp": _timestamp(),
    }
