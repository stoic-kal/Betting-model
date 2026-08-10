from services.totals_model_v3 import LEAGUE_AVG_FIP, LEAGUE_AVG_RSG

W = 63

_TOTALS_TERM_LABELS = [
    ("lineup_runs_adj", "Lineup Adjustment"),
    ("bullpen_workload_adj", "Bullpen Workload"),
    ("defense_runs_adj", "Defense"),
    ("contact_quality_runs_adj", "Contact Quality (Statcast)"),
    ("ump_runs_adj", "Umpire Tendency"),
]
_EFFECT_EPS = 0.02

_TOTALS_NARRATIVE = {
    "lineup_runs_adj": (
        "Lineup strength above average increased scoring expectation",
        "Lineup strength below average decreased scoring expectation",
    ),
    "bullpen_workload_adj": (
        "Bullpen fatigue / limited availability increased scoring expectation",
        "Fresh, available bullpen decreased scoring expectation",
    ),
    "defense_runs_adj": (
        "Below-average fielding increased scoring expectation",
        "Above-average fielding decreased scoring expectation",
    ),
    "contact_quality_runs_adj": (
        "Hitters facing contact quality worse than pitcher FIP implies increased scoring expectation",
        "Pitchers outperforming their FIP on contact quality decreased scoring expectation",
    ),
    "ump_runs_adj": (
        "Home-plate umpire tendency increased scoring expectation",
        "Home-plate umpire tendency decreased scoring expectation",
    ),
}


def _bar(title=None):
    if title is None:
        return "=" * W
    pad = max(W - len(title) - 2, 4)
    left = pad // 2
    right = pad - left
    return "=" * left + f" {title} " + "=" * right


def _split_terms(pairs, eps):
    positives = sorted([p for p in pairs if p[1] is not None and p[1] > eps], key=lambda p: -p[1])
    negatives = sorted([p for p in pairs if p[1] is not None and p[1] < -eps], key=lambda p: p[1])
    neutral = [p for p in pairs if p[1] is not None and abs(p[1]) <= eps]
    return positives, negatives, neutral


def _section(lines, title):
    lines.append("")
    lines.append(title)
    lines.append("-" * len(title))


def print_totals_reasoning(matchup, tot_result, market_line):
    if not tot_result or tot_result.get("expected_total") is None:
        return
    expected = tot_result["expected_total"]
    diff = round(expected - market_line, 2) if market_line is not None else None
    direction = tot_result.get("direction") or (
        tot_result.get("pick", "").split()[0].lower() if tot_result.get("pick") else None
    )

    terms = [
        (label, tot_result.get(key), key)
        for key, label in _TOTALS_TERM_LABELS
        if tot_result.get(key) is not None
    ]
    term_pairs = [(t[0], t[1]) for t in terms]
    positives, negatives, neutral = _split_terms(term_pairs, _EFFECT_EPS)
    checklist = tot_result.get("qualification_checklist") or {}

    lines = [_bar("MODEL REASONING — TOTALS"), matchup]

    _section(lines, "1. Prediction Summary")
    if tot_result.get("pick"):
        lines.append(f'  Pick:               {tot_result["pick"]}')
    if tot_result.get("model_prob") is not None:
        lines.append(f'  Model Probability:  {tot_result["model_prob"]:.1%}')
    if tot_result.get("market_prob") is not None:
        lines.append(f'  Market Probability: {tot_result["market_prob"]:.1%}')
    if tot_result.get("model_edge") is not None:
        lines.append(f'  Edge:               {tot_result["model_edge"]:+.1f}pp')
    if tot_result.get("ev") is not None:
        lines.append(f'  EV:                 {tot_result["ev"]:.1f}%')
    lines.append(f"  Expected Total:     {expected}")
    if market_line is not None:
        lines.append(f"  Market Line:        {market_line}")
    if diff is not None:
        lines.append(f"  Difference:         {diff:+.2f} runs")

    _section(lines, "2. Why The Model Likes This Pick")
    any_bullets = False
    for label, val, key in terms:
        if abs(val) <= _EFFECT_EPS:
            continue
        pos_text, neg_text = _TOTALS_NARRATIVE.get(
            key,
            (f"{label} increased scoring expectation", f"{label} decreased scoring expectation"),
        )
        text = pos_text if val > 0 else neg_text
        lines.append(f"  • {text}")
        lines.append(
            f'      feature: {label} | direction: {"up" if val>0 else "down"} | contribution: {val:+.2f} runs'
        )
        any_bullets = True

    hf, af = tot_result.get("home_fip"), tot_result.get("away_fip")
    if hf is not None and af is not None:
        avg_fip = (hf + af) / 2
        if avg_fip < LEAGUE_AVG_FIP - 0.15:
            lines.append("  • Elite starting pitching lowered projected runs")
            lines.append(
                f"      feature: Starting Pitching (FIP) | direction: down | value: {avg_fip:.2f} vs league avg {LEAGUE_AVG_FIP} (no isolated run contribution — multiplicative input)"
            )
            any_bullets = True
        elif avg_fip > LEAGUE_AVG_FIP + 0.15:
            lines.append("  • Below-average starting pitching raised projected runs")
            lines.append(
                f"      feature: Starting Pitching (FIP) | direction: up | value: {avg_fip:.2f} vs league avg {LEAGUE_AVG_FIP} (no isolated run contribution — multiplicative input)"
            )
            any_bullets = True
    hr, ar = tot_result.get("home_rsg"), tot_result.get("away_rsg")
    if hr is not None and ar is not None:
        avg_rsg = (hr + ar) / 2
        if avg_rsg > LEAGUE_AVG_RSG + 0.20:
            lines.append("  • Recent offensive form increased scoring expectation")
            lines.append(
                f"      feature: Offense (RS/G) | direction: up | value: {avg_rsg:.2f} vs league avg {LEAGUE_AVG_RSG} (no isolated run contribution — multiplicative input)"
            )
            any_bullets = True
        elif avg_rsg < LEAGUE_AVG_RSG - 0.20:
            lines.append("  • Below-average offense decreased scoring expectation")
            lines.append(
                f"      feature: Offense (RS/G) | direction: down | value: {avg_rsg:.2f} vs league avg {LEAGUE_AVG_RSG} (no isolated run contribution — multiplicative input)"
            )
            any_bullets = True
    wf = tot_result.get("weather_factor")
    if wf is not None and abs(wf - 1.0) < 0.02:
        lines.append("  • Weather had little impact")
        lines.append(f"      feature: Weather | direction: neutral | value: factor {wf}")
        any_bullets = True
    if neutral:
        lines.append(
            "  • Little / no effect: "
            + ", ".join(f"{label} ({val:+.2f})" for label, val in neutral)
        )
        any_bullets = True
    if not any_bullets:
        lines.append("  (No individually meaningful contributors — see Step-by-Step Projection.)")

    additive_sum = sum(v for _, v, _ in terms)
    base = round(expected - additive_sum, 3)
    park_f = tot_result.get("park_factor")
    weather_f = tot_result.get("weather_factor")
    _section(lines, "3. Step-By-Step Projection")
    running = base
    lines.append(
        f"  Base Projection (starting pitching + offense, park/weather-adjusted): {running:.2f}"
    )
    if park_f is not None and weather_f:
        base_no_pw = base / (park_f * weather_f) if (park_f and weather_f) else None
        if base_no_pw is not None:
            lines.append(f"    ↳ of which, before Park/Weather: {base_no_pw:.2f}")
            park_delta = (base_no_pw * park_f) - base_no_pw
            lines.append(f"         ↓ Park ({park_f}): {park_delta:+.2f}")
            weather_delta = base - (base_no_pw * park_f)
            lines.append(f"         ↓ Weather ({weather_f}): {weather_delta:+.2f}")
    for label, val, key in terms:
        running += val
        lines.append(f"    ↓ {label}: {val:+.2f}  →  running total {running:.2f}")
    lines.append(f"  Final Expected Total: {expected}")

    _section(lines, "4. Why The Market Disagrees")
    if diff is not None and abs(diff) > _EFFECT_EPS:
        drivers = negatives if diff < 0 else positives
        driver_names = [d[0] for d in drivers[:2]]
        lines.append(
            f'  Model total ({expected}) is {abs(diff):.2f} runs {"below" if diff<0 else "above"} the market line ({market_line}).'
        )
        if driver_names:
            lines.append(f'  Largest contributors to that gap: {", ".join(driver_names)}.')
        lines.append(
            "  This reflects the model weighting those specific inputs more heavily than the number implied by the market line;"
        )
        lines.append(
            "  it is not a claim about what the market itself is pricing feature-by-feature."
        )
    else:
        lines.append(
            "  Model total is close to the market line — no material disagreement to explain."
        )

    assumption_keys = [
        (
            "both_starters_confirmed",
            "Starting pitchers confirmed (not season-average fallback)",
            "Starting pitcher(s) not confirmed — using season-average FIP",
        ),
        ("confirmed_lineups", "Lineups confirmed", "Lineups not confirmed"),
        (
            "individual_reliever_availability",
            "Bullpens available (live MLB pitch-count data)",
            "Bullpen workload estimated from season ERA only",
        ),
        (
            "available_reliever_quality",
            "Sufficient available-reliever data",
            "Limited reliever-availability data",
        ),
    ]
    assumptions, unknowns_from_checklist = [], []
    for key, ok_text, bad_text in assumption_keys:
        if key not in checklist:
            continue
        (assumptions if checklist[key] else unknowns_from_checklist).append(
            ok_text if checklist[key] else bad_text
        )
    weather_source = tot_result.get("weather_source")
    if weather_source == "wttr.in":
        assumptions.append("Weather forecast available (live)")
    elif weather_source == "dome":
        assumptions.append("Dome — weather neutral by construction")
    elif weather_source == "fallback_default":
        unknowns_from_checklist.append("Weather forecast unavailable — fallback default used")
    ump_name = tot_result.get("ump_name")
    if ump_name and ump_name != "Unknown":
        assumptions.append(f"Home-plate umpire known ({ump_name})")
    else:
        unknowns_from_checklist.append("Umpire unknown")

    _section(lines, "5. Assumptions")
    for a in assumptions:
        lines.append(f"  {a}")
    for u in unknowns_from_checklist:
        lines.append(f"  {u}")
    if not assumptions and not unknowns_from_checklist:
        lines.append("  (No assumption data available.)")

    _section(lines, "6. Confidence By Data Source")
    conf = {}
    conf["Starting Pitchers"] = (
        "HIGH"
        if checklist.get("both_starters_confirmed")
        else ("LOW" if "both_starters_confirmed" in checklist else None)
    )
    if (
        "individual_reliever_availability" in checklist
        and "available_reliever_quality" in checklist
    ):
        live, quality = (
            checklist["individual_reliever_availability"],
            checklist["available_reliever_quality"],
        )
        conf["Bullpen"] = (
            "HIGH" if (live and quality) else ("MEDIUM" if (live or quality) else "LOW")
        )
    if weather_source == "wttr.in" or weather_source == "dome":
        conf["Weather"] = "HIGH"
    elif weather_source == "fallback_default":
        conf["Weather"] = "LOW"
    conf["Lineups"] = (
        "HIGH"
        if checklist.get("confirmed_lineups")
        else ("LOW" if "confirmed_lineups" in checklist else None)
    )
    conf["Umpire"] = "HIGH" if (ump_name and ump_name != "Unknown") else "UNKNOWN"
    printed_any = False
    for label, level in conf.items():
        if level is None:
            continue
        lines.append(f"  {label:<20}{level}")
        printed_any = True
    if not printed_any:
        lines.append("  (No confidence-relevant data available.)")

    _section(lines, "7. Biggest Risks")
    risks = []
    top_driver = (
        positives[0][0]
        if direction == "over" and positives
        else (
            negatives[0][0]
            if direction == "under" and negatives
            else (positives[0][0] if positives else (negatives[0][0] if negatives else None))
        )
    )
    if top_driver:
        risks.append(f"{top_driver} reversing direction would remove this pick's biggest edge")
    if not checklist.get("both_starters_confirmed", True):
        risks.append("a starter change before first pitch would invalidate the FIP inputs")
    if not checklist.get("confirmed_lineups", True):
        risks.append(
            "the confirmed lineup differing from the assumed one would shift scoring expectation"
        )
    if not checklist.get("individual_reliever_availability", True):
        risks.append("bullpen performing worse than season-average ERA implies")
    if weather_source == "fallback_default":
        risks.append("actual weather differing from the unavailable forecast")
    if risks:
        pick_label = tot_result.get("pick")
        lines.append(
            f"  This {pick_label} most likely loses if:"
            if pick_label
            else "  This projection is most likely wrong if:"
        )
        for r in risks:
            lines.append(f"    • {r}")
    else:
        lines.append("  No specific risk factors identified from current inputs.")

    _section(lines, "8. Biggest Unknowns")
    if unknowns_from_checklist:
        for u in unknowns_from_checklist:
            lines.append(f"  • {u}")
    else:
        lines.append("  None identified — all tracked inputs were available.")

    lines.append("")
    lines.append(_bar())
    print("\n" + "\n".join(lines) + "\n")


def print_ml_reasoning(
    matchup,
    ml_result,
    pick_team,
    pick_prob,
    market_prob,
    model_edge,
    home_sp_id=None,
    away_sp_id=None,
    ev=None,
):
    if not ml_result or "features" not in ml_result:
        return
    from services.model_control_service import _attribution

    features = ml_result["features"]
    row = {"pick_type": "moneyline", "pick": pick_team, "matchup": matchup}
    snap = {"features": features}
    attribution = _attribution(row, snap, market_prob) if market_prob is not None else []
    positives, negatives, neutral = _split_terms(
        [(a["feature"], a["effect_pp"]) for a in attribution], 0.05
    )

    lines = [_bar("MODEL REASONING — MONEYLINE"), matchup]

    _section(lines, "1. Prediction Summary")
    lines.append(f"  Pick:               {pick_team}")
    if pick_prob is not None:
        lines.append(f"  Model Probability:  {pick_prob:.1%}")
    if market_prob is not None:
        lines.append(f"  Market Probability: {market_prob:.1%}")
    if model_edge is not None:
        lines.append(f"  Edge:               {model_edge:+.1f}pp")
    if ev is not None:
        lines.append(f"  EV:                 {ev:.1f}%")

    _section(lines, "2. Why The Model Likes This Pick")
    any_bullets = False
    for label, val in positives + negatives:
        direction_word = "up" if val > 0 else "down"
        verb = "increased" if val > 0 else "decreased"
        lines.append(f"  • {label} {verb} win probability for {pick_team}")
        lines.append(
            f"      feature: {label} | direction: {direction_word} | contribution: {val:+.2f}pp"
        )
        any_bullets = True
    if neutral:
        lines.append(
            "  • Little / no effect: "
            + ", ".join(f"{label} ({val:+.2f}pp)" for label, val in neutral)
        )
        any_bullets = True
    if not any_bullets:
        lines.append("  (No individually meaningful contributors.)")

    _section(lines, "3. Step-By-Step Projection")
    if ml_result.get("logit_market") is not None and ml_result.get("logit_delta") is not None:
        lm, ld = ml_result["logit_market"], ml_result["logit_delta"]
        lines.append(f"  Market-implied logit:  {lm:.3f}")
        lines.append(f"    ↓ feature adjustments (sum): {ld:+.3f}")
        lines.append(f"  Model logit:           {lm + ld:.3f}")
        lines.append(
            "  (Individual feature logit deltas are not stored separately from the summed adjustment;"
        )
        lines.append(
            "   see Section 2 for the first-order probability-point breakdown per feature.)"
        )
    else:
        lines.append("  Not available — logit components were not returned for this pick.")

    _section(lines, "4. Why The Market Disagrees")
    if model_edge is not None and abs(model_edge) > 0.5:
        drivers = positives if model_edge > 0 else negatives
        driver_names = [d[0] for d in drivers[:2]]
        lines.append(
            f"  Model favors {pick_team} by {abs(model_edge):.1f}pp more than the market does."
        )
        if driver_names:
            lines.append(f'  Largest contributors to that gap: {", ".join(driver_names)}.')
        lines.append(
            "  This reflects the model weighting those specific inputs more heavily than the price implies;"
        )
        lines.append(
            "  it is not a claim about what the market itself is pricing feature-by-feature."
        )
    else:
        lines.append(
            "  Model probability is close to the market — no material disagreement to explain."
        )

    assumptions, unknowns = [], []
    if features.get("context_complete") is True:
        assumptions.append("Lineups confirmed")
    elif features.get("context_complete") is False:
        unknowns.append("Lineups not confirmed")
    if home_sp_id is not None and away_sp_id is not None:
        assumptions.append("Starting pitchers confirmed")
    else:
        if home_sp_id is None:
            unknowns.append("Home starter TBD — using league-average FIP")
        if away_sp_id is None:
            unknowns.append("Away starter TBD — using league-average FIP")
    hq = features.get("home_available_reliever_quality_count")
    aq = features.get("away_available_reliever_quality_count")
    if hq is not None and aq is not None:
        if hq >= 2 and aq >= 2:
            assumptions.append("Bullpens available (sufficient reliever-quality data both sides)")
        else:
            unknowns.append("Bullpen data incomplete for one or both teams")
    hu, au = features.get("home_unavailable_relievers"), features.get("away_unavailable_relievers")
    if hu:
        unknowns.append(f"{hu} home reliever(s) unavailable")
    if au:
        unknowns.append(f"{au} away reliever(s) unavailable")

    _section(lines, "5. Assumptions")
    for a in assumptions:
        lines.append(f"  {a}")
    for u in unknowns:
        lines.append(f"  {u}")
    if not assumptions and not unknowns:
        lines.append("  (No assumption data available.)")

    _section(lines, "6. Confidence By Data Source")
    conf = {}
    conf["Starting Pitchers"] = (
        "HIGH" if (home_sp_id is not None and away_sp_id is not None) else "LOW"
    )
    if hq is not None and aq is not None:
        conf["Bullpen"] = (
            "HIGH" if (hq >= 2 and aq >= 2) else ("MEDIUM" if (hq >= 1 and aq >= 1) else "LOW")
        )
    if features.get("context_complete") is not None:
        conf["Lineups"] = "HIGH" if features["context_complete"] else "LOW"
    for label, level in conf.items():
        lines.append(f"  {label:<20}{level}")
    lines.append("  Weather               N/A (not a moneyline model input)")
    lines.append("  Umpire                N/A (not a moneyline model input)")

    _section(lines, "7. Biggest Risks")
    risks = []
    top_driver = positives[0][0] if positives else (negatives[0][0] if negatives else None)
    if top_driver:
        risks.append(f"{top_driver} reversing direction would remove this pick's biggest edge")
    if features.get("context_complete") is False:
        risks.append("the confirmed lineup differing from the assumed one")
    if home_sp_id is None or away_sp_id is None:
        risks.append("a late starting-pitcher change")
    if hu or au:
        risks.append("bullpen availability worsening further before first pitch")
    if risks:
        lines.append(f"  This pick on {pick_team} most likely loses if:")
        for r in risks:
            lines.append(f"    • {r}")
    else:
        lines.append("  No specific risk factors identified from current inputs.")

    _section(lines, "8. Biggest Unknowns")
    if unknowns:
        for u in unknowns:
            lines.append(f"  • {u}")
    else:
        lines.append("  None identified — all tracked inputs were available.")

    lines.append("")
    lines.append(_bar())
    print("\n" + "\n".join(lines) + "\n")
