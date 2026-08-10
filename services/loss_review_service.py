import csv
import io
import sqlite3
from collections import Counter, defaultdict

from services.model_control_service import _attribution, _market_prob, _quality
from services.record_tracker_service import (
    DB_PATH,
    _feature_context,
    _num,
    _snapshot,
    get_record_tracker,
)


def _rnd(v, n=2):
    return round(v, n) if v is not None else None


def _tags(r):
    tags = []
    if not r.get("home_lineup_confirmed") or not r.get("away_lineup_confirmed"):
        tags.append(("missing_lineup", "Missing confirmed lineup", "data"))
    clv = r.get("clv")
    if clv is None:
        tags.append(("missing_clv", "Closing price unavailable", "data"))
    elif clv < 0:
        tags.append(("market_disagreement", "Market moved away from pick", "market"))
    elif clv >= 3:
        tags.append(("good_clv_bad_result", "Strong CLV, result lost", "variance"))
    if (r.get("model_prob") or 0) >= 0.62:
        tags.append(("high_confidence_loss", "High-confidence miss", "calibration"))
    if (r.get("ev") or 0) >= 15:
        tags.append(("high_ev_loss", "Projected EV may be overstated", "calibration"))
    if r["type"] == "totals":
        err = r.get("total_error")
        direction = "under" if str(r.get("pick", "")).upper().startswith("UNDER") else "over"
        if direction == "under":
            tags.append(("under_loss", "Under projection missed high", "direction"))
        if err is not None:
            miss = err if direction == "under" else -err
            if miss >= 4:
                tags.append(("large_total_miss", "Run environment missed by 4+ runs", "model"))
            elif miss <= 1:
                tags.append(("close_total_variance", "Within one run of projection", "variance"))
    else:
        hs, aws = r.get("home_score"), r.get("away_score")
        if hs is not None and aws is not None:
            parts = r.get("game", "").split(" @ ", 1)
            home = parts[1] if len(parts) > 1 else ""
            margin = (hs - aws) if r.get("pick") == home else (aws - hs)
            if margin == -1:
                tags.append(("one_run_loss", "One-run loss", "variance"))
            elif margin <= -4:
                tags.append(("decisive_side_miss", "Lost by four or more runs", "model"))
    return tags or [("unclassified", "Needs manual film/data review", "review")]


def _groups(rows, key):
    grouped = defaultdict(list)
    for r in rows:
        grouped[key(r)].append(r)
    out = []
    for label, sub in grouped.items():
        wins = sum(r["status"] == "won" for r in sub)
        clvs = [r["clv"] for r in sub if r.get("clv") is not None]
        probs = [r["model_prob"] for r in sub if r.get("model_prob") is not None]
        evs = [r["ev"] for r in sub if r.get("ev") is not None]
        out.append(
            {
"label": label,
"n": len(sub),
"wins": wins,
"losses": len(sub) - wins,
"win_rate": _rnd(wins / len(sub) * 100, 1),
"avg_prob": _rnd(sum(probs) / len(probs) * 100, 1) if probs else None,
"avg_ev": _rnd(sum(evs) / len(evs), 1) if evs else None,
"avg_clv": _rnd(sum(clvs) / len(clvs), 2) if clvs else None,
            }
        )
    return out


def get_loss_review(version="v3", date_str=None):
    rows = [
        r
        for r in get_record_tracker(version)["rows"]
        if r["status"] in ("won", "lost") and (not date_str or r["date"] == date_str)
    ]
    losses = [r for r in rows if r["status"] == "lost"]
    reasons = Counter()
    cats = Counter()
    detailed = []
    for r in losses:
        tags = _tags(r)
        for _, label, cat in tags:
            reasons[label] += 1
            cats[cat] += 1
        item = dict(r)
        item["loss_reasons"] = [x[1] for x in tags]
        item["reason_codes"] = [x[0] for x in tags]
        item["primary_reason"] = tags[0][1]
        item["data_quality"] = (
"complete"
            if r.get("home_lineup_confirmed")
            and r.get("away_lineup_confirmed")
            and r.get("clv") is not None
            else "incomplete"
        )
        detailed.append(item)

    def pb(r):
        p = (r.get("model_prob") or 0) * 100
        return "<55%" if p < 55 else "55-60%" if p < 60 else "60-65%" if p < 65 else "65%+"

    def eb(r):
        e = r.get("ev") or 0
        return "<5%" if e < 5 else "5-10%" if e < 10 else "10-20%" if e < 20 else "20%+"

    def cb(r):
        c = r.get("clv")
        return "Missing" if c is None else "Negative" if c < 0 else "0-2pp" if c < 2 else "2pp+"

    totals = [r for r in rows if r["type"] == "totals"]
    daily = _groups(rows, lambda r: r["date"])
    daily.sort(key=lambda x: x["label"])
    errors = [
        {
"game": r["game"],
"pick": r["pick"],
"status": r["status"],
"expected": r.get("expected_total"),
"actual": r.get("actual_total"),
"error": r.get("total_error"),
        }
        for r in totals
        if r.get("total_error") is not None
    ]
    wins = len(rows) - len(losses)
    wclv = [r["clv"] for r in rows if r["status"] == "won" and r.get("clv") is not None]
    lclv = [r["clv"] for r in losses if r.get("clv") is not None]
    incomplete = sum(r["data_quality"] == "incomplete" for r in detailed)
    warnings = []
    hev = sum((r.get("ev") or 0) >= 15 for r in losses)
    ul = sum(r["type"] == "totals" and str(r["pick"]).upper().startswith("UNDER") for r in losses)
    if hev:
        warnings.append(
            f"{hev} loss(es) carried projected EV of 15% or more; confidence calibration needs monitoring."
        )
    if ul >= 3:
        warnings.append(
            f"{ul} totals losses were Unders; compare expected-run inputs before increasing Under exposure."
        )
    if incomplete:
        warnings.append(
            f"{incomplete} loss(es) had incomplete lineup or closing-price data and should not drive weight changes."
        )
    return {
"filters": {"version": version, "date": date_str},
"summary": {
"resolved": len(rows),
"wins": wins,
"losses": len(losses),
"win_rate": _rnd(wins / len(rows) * 100, 1) if rows else None,
"avg_win_clv": _rnd(sum(wclv) / len(wclv), 2) if wclv else None,
"avg_loss_clv": _rnd(sum(lclv) / len(lclv), 2) if lclv else None,
"large_total_misses": reasons["Run environment missed by 4+ runs"],
"incomplete_losses": incomplete,
        },
"warnings": warnings,
"losses": detailed,
"reason_counts": [{"label": k, "count": v} for k, v in reasons.most_common()],
"category_counts": [{"label": k, "count": v} for k, v in cats.most_common()],
"by_type": _groups(rows, lambda r: r["type"]),
"by_direction": _groups(
            totals, lambda r: "UNDER" if str(r["pick"]).upper().startswith("UNDER") else "OVER"
        ),
"probability_buckets": _groups(rows, pb),
"ev_buckets": _groups(rows, eb),
"clv_buckets": _groups(rows, cb),
"daily": daily,
"total_errors": errors,
"methodology": "Deterministic diagnostic tags; no automatic live-model weight changes.",
    }


def loss_review_csv(version="v3", date_str=None):
    rows = get_loss_review(version, date_str)["losses"]
    out = io.StringIO()
    if rows:
        flat = []
        for r in rows:
            x = dict(r)
            x["loss_reasons"] = " | ".join(x["loss_reasons"])
            x["reason_codes"] = " | ".join(x["reason_codes"])
            flat.append(x)
        w = csv.DictWriter(out, fieldnames=list(flat[0]), extrasaction="ignore")
        w.writeheader()
        w.writerows(flat)
    return out.getvalue()


from services.totals_model_v3 import LEAGUE_AVG_FIP, LEAGUE_AVG_RSG

_TOTALS_ADJ_CAPS = {
"lineup_runs_adj": 0.60,
"bullpen_workload_adj": 0.70,
"defense_runs_adj": 0.30,
"contact_quality_runs_adj": 0.45,
}
_ADJ_LABELS = {
"lineup_runs_adj": "Lineup strength (confirmed OPS vs league)",
"bullpen_workload_adj": "Bullpen workload/fatigue",
"defense_runs_adj": "Defense (fielding pct)",
"contact_quality_runs_adj": "Contact quality (Statcast xERA vs FIP)",
"ump_runs_adj": "Home-plate umpire tendency",
}
_CONF_ORDER = {"High": 3, "Medium": 2, "Low": 1, "Insufficient evidence": 0}


def _thought_process_totals(snap):
    terms = []
    for key, label in _ADJ_LABELS.items():
        val = snap.get(key)
        if val is None:
            continue
        cap = _TOTALS_ADJ_CAPS.get(key)
        terms.append(
            {
"feature": label,
"contribution_runs": round(val, 3),
"unit": "runs (exact, additive to expected_total)",
"saturated_at_cap": bool(cap and abs(val) >= cap - 0.005),
            }
        )
    terms.sort(key=lambda t: abs(t["contribution_runs"]), reverse=True)

    base_inputs = []
    for key, ref, ref_label, kind in [
        ("home_fip", LEAGUE_AVG_FIP, "league avg FIP", "lower=stronger"),
        ("away_fip", LEAGUE_AVG_FIP, "league avg FIP", "lower=stronger"),
        ("home_rsg", LEAGUE_AVG_RSG, "league avg RS/G", "higher=more offense"),
        ("away_rsg", LEAGUE_AVG_RSG, "league avg RS/G", "higher=more offense"),
        ("park_factor", 1.0, "neutral park", "higher=hitter-friendly"),
        ("weather_factor", 1.0, "neutral weather", "higher=run-boosting"),
    ]:
        val = snap.get(key)
        if val is None:
            continue
        base_inputs.append(
            {
"feature": key.replace("_", " "),
"value": val,
"reference": ref,
"reference_label": ref_label,
"above_or_below_reference": (
"above" if val > ref else ("below" if val < ref else "at")
                ),
"scale": kind,
            }
        )

    return {
"top_contributing_adjustments": terms[:5],
"primary_base_inputs": base_inputs,
"note": (
"Base inputs (FIP/RSG/park/weather) combine multiplicatively into the model's "
"expected-runs formula and are not stored as separable run contributions — only "
"the additive adjustment terms above have an exact, stored run value."
        ),
    }


def _thought_process_moneyline(row, snap):
    market = _market_prob(row, snap)
    attribution = _attribution(row, snap, market)
    ranked = sorted(attribution, key=lambda a: abs(a["effect_pp"]), reverse=True)[:5]
    return {
"top_contributing_features": [
            {
"feature": a["feature"],
"contribution_pp": a["effect_pp"],
"unit": "percentage points of win probability (first-order estimate)",
            }
            for a in ranked
        ],
"market_prob_used_as_prior": market,
"note": (
"Contribution values use the same first-order attribution formula as the Model "
"Control page (services/model_control_service.py::_attribution) — a linear "
"approximation around the market prior, not an exact decomposition."
        ),
    }


def _expected_vs_reality_totals(row, snap):
    expected = _num(snap.get("expected_total"))
    actual = _num(row.get("actual_total"))
    market_line = _num(snap.get("market_line"))
    direction = "OVER" if "OVER" in str(row.get("pick", "")).upper() else "UNDER"
    checklist = snap.get("qualification_checklist") or {}
    return {
"expected_total": expected,
"actual_total": actual,
"market_line": market_line,
"total_error": (
            round(actual - expected, 2) if actual is not None and expected is not None else None
        ),
"model_picked": direction,
"market_missed_by": (
            round(actual - market_line, 2)
            if actual is not None and market_line is not None
            else None
        ),
"model_closer_than_market": (
            (abs(actual - expected) < abs(actual - market_line))
            if actual is not None and expected is not None and market_line is not None
            else None
        ),
"assumptions_confirmed_at_pick_time": [
            k.replace("_", " ") for k, v in checklist.items() if v
        ],
"assumptions_not_confirmed_at_pick_time": [
            k.replace("_", " ") for k, v in checklist.items() if not v
        ],
    }


def _expected_vs_reality_moneyline(row, snap):
    market = _market_prob(row, snap)
    prob = _num(row.get("model_prob"))
    hs, aws = row.get("home_score"), row.get("away_score")
    parts = (row.get("matchup") or "").split(" @ ")
    away_team, home_team = (parts[0], parts[1]) if len(parts) == 2 else (None, None)
    actual_winner = None
    if hs is not None and aws is not None:
        actual_winner = home_team if hs > aws else (away_team if hs < aws else "tie")
    quality = _quality(row, snap)
    return {
"model_prob_for_pick": prob,
"market_prob_for_pick": market,
"home_score": hs,
"away_score": aws,
"actual_winner": actual_winner,
"model_edge_vs_market_pp": (
            round((prob - market) * 100, 2) if prob is not None and market is not None else None
        ),
"data_quality_score": quality["score"],
"data_quality_label": quality["label"],
"missing_inputs_at_pick_time": quality["missing"],
    }


def _root_causes_totals(row, snap, quality):
    causes = []
    expected = _num(snap.get("expected_total"))
    actual = _num(row.get("actual_total"))
    error = (actual - expected) if actual is not None and expected is not None else None

    wsource = snap.get("weather_source")
    if wsource == "fallback_default":
        causes.append(
            {
"cause": "Weather assumption may be unreliable",
"confidence": "Medium",
"evidence": f"weather_source='fallback_default'"
                + (f", error: {snap.get('weather_error')}" if snap.get("weather_error") else "")
                + " — the live weather API failed and a neutral default was substituted.",
            }
        )
    elif wsource in ("wttr.in", "dome"):
        causes.append(
            {
"cause": "Weather impact incorrect",
"confidence": "Low",
"evidence": f"weather_source='{wsource}' — live weather data was used, so a forecast error is possible but not the likely primary cause.",
            }
        )
    else:
        causes.append(
            {
"cause": "Weather impact incorrect",
"confidence": "Insufficient evidence",
"evidence": "weather_source not recorded on this pick (older schema).",
            }
        )

    park_f = snap.get("park_factor")
    if park_f is not None and error is not None:
        if error > 0 and park_f < 1.0:
            causes.append(
                {
"cause": "Park factor may be underestimated",
"confidence": "Low",
"evidence": f"Actual total came in {error:+.1f} above expected while park_factor={park_f} was pitcher-friendly (<1.0) — direction is consistent, but this is a static per-venue constant, not verified against this specific game.",
                }
            )
        elif error < 0 and park_f > 1.0:
            causes.append(
                {
"cause": "Park factor may be overestimated",
"confidence": "Low",
"evidence": f"Actual total came in {error:+.1f} below expected while park_factor={park_f} was hitter-friendly (>1.0) — direction is consistent, but this is a static per-venue constant, not verified against this specific game.",
                }
            )
        else:
            causes.append(
                {
"cause": "Park factor error",
"confidence": "Insufficient evidence",
"evidence": f"park_factor={park_f} direction is not clearly consistent with the {error:+.1f}-run miss.",
                }
            )

    ctx = snap.get("context") or {}
    unavailable = (ctx.get("home_unavailable_relievers") or 0) + (
        ctx.get("away_unavailable_relievers") or 0
    )
    bw = snap.get("bullpen_workload_adj")
    if bw is not None and error is not None and unavailable:
        consistent = (error > 0 and bw > 0) or (error < 0 and bw < 0)
        causes.append(
            {
"cause": "Bullpen performed differently than modeled",
"confidence": "Medium" if consistent else "Low",
"evidence": f"bullpen_workload_adj={bw:+.2f} runs from {unavailable} combined unavailable reliever(s); miss was {error:+.1f} runs — "
                + (
"direction is consistent with the workload signal."
                    if consistent
                    else "direction does not clearly match the workload signal."
                )
                + " Actual bullpen runs allowed is not stored, so this is inferred from pre-game data only, not confirmed.",
            }
        )
    else:
        causes.append(
            {
"cause": "Bullpen performed differently than modeled",
"confidence": "Insufficient evidence",
"evidence": "No reliever-unavailability signal was stored for this pick.",
            }
        )

    causes.append(
        {
"cause": "Starting pitcher outperformed/underperformed the model's FIP assumption",
"confidence": "Insufficient evidence",
"evidence": f"Model assumed home_fip={snap.get('home_fip')}, away_fip={snap.get('away_fip')} (season-to-date FIP at pick time). "
"This pick's actual per-start pitching line (runs allowed, innings pitched) is not stored anywhere in the database, "
"so this cause cannot be confirmed or ruled out.",
        }
    )

    lra = snap.get("lineup_runs_adj")
    if ctx.get("context_complete"):
        causes.append(
            {
"cause": "Lineup stronger/weaker than expected",
"confidence": "Insufficient evidence" if lra is None else "Low",
"evidence": (
                    f"lineup_runs_adj={lra:+.2f} runs was applied from the confirmed lineup's pregame OPS. "
                    if lra is not None
                    else ""
                )
                + "Actual in-game batting production is not stored, so over/underperformance vs pregame OPS cannot be confirmed.",
            }
        )
    else:
        causes.append(
            {
"cause": "Lineup stronger/weaker than expected",
"confidence": "Insufficient evidence",
"evidence": "Lineups were not both confirmed at pick time, so lineup_runs_adj was not applied — this cannot be evaluated.",
            }
        )

    dra = snap.get("defense_runs_adj")
    if dra is not None:
        causes.append(
            {
"cause": "Defense",
"confidence": "Low" if abs(dra) > 0.05 else "Insufficient evidence",
"evidence": f"defense_runs_adj={dra:+.2f} runs from fielding-percentage inputs. Actual defensive plays/errors are not stored.",
            }
        )

    cqa = snap.get("contact_quality_runs_adj")
    if cqa is not None and abs(cqa) >= _TOTALS_ADJ_CAPS["contact_quality_runs_adj"] - 0.005:
        causes.append(
            {
"cause": "Contact-quality adjustment saturated at its clip bound",
"confidence": "Medium",
"evidence": f"contact_quality_runs_adj={cqa:+.2f} is at (or within 0.005 of) its ±{_TOTALS_ADJ_CAPS['contact_quality_runs_adj']} cap — the underlying signal may exceed what the model was allowed to apply.",
            }
        )

    market_line = _num(snap.get("market_line"))
    if expected is not None and market_line is not None:
        model_edge_runs = expected - market_line
        small_edge = abs(model_edge_runs) < 0.5
        causes.append(
            {
"cause": "Market variance (model was close to the market and lost anyway)",
"confidence": "Medium" if small_edge else "Low",
"evidence": f"Model's expected_total disagreed with market_line by {model_edge_runs:+.2f} runs."
                + (
" A sub-0.5-run disagreement is close to market consensus."
                    if small_edge
                    else " A larger disagreement than typical market noise."
                ),
            }
        )

    if error is not None:
        small_miss = abs(error) <= 1.0
        causes.append(
            {
"cause": "Random baseball variance",
"confidence": "Medium" if small_miss else "Low",
"evidence": f"Total missed by {error:+.1f} run(s)."
                + (
" A sub-1-run miss is within typical game-to-game scoring variance."
                    if small_miss
                    else " A miss this size is larger than typical single-game noise, so other causes above are more likely primary."
                ),
            }
        )

    if quality["score"] < 80:
        causes.append(
            {
"cause": "Data quality was incomplete at pick time",
"confidence": "High" if quality["score"] < 55 else "Medium",
"evidence": f"Data completeness score {quality['score']}% ({quality['label']}); missing: {', '.join(quality['missing']) or 'none listed'}.",
            }
        )

    causes.sort(key=lambda c: _CONF_ORDER.get(c["confidence"], 0), reverse=True)
    return causes


def _root_causes_moneyline(row, snap, quality):
    causes = []
    prob = _num(row.get("model_prob"))
    market = _market_prob(row, snap)
    hs, aws = row.get("home_score"), row.get("away_score")
    margin = abs(hs - aws) if hs is not None and aws is not None else None

    if quality["score"] < 80:
        causes.append(
            {
"cause": "Data quality was incomplete at pick time",
"confidence": "High" if quality["score"] < 55 else "Medium",
"evidence": f"Data completeness score {quality['score']}% ({quality['label']}); missing: {', '.join(quality['missing']) or 'none listed'}.",
            }
        )

    if prob is not None and market is not None:
        edge_pp = (prob - market) * 100
        small_edge = abs(edge_pp) < 2.0
        causes.append(
            {
"cause": "Market variance (model was close to the market and lost anyway)",
"confidence": "Medium" if small_edge else "Low",
"evidence": f"Model probability disagreed with the market-implied probability by {edge_pp:+.1f}pp.",
            }
        )

    if margin is not None:
        close = margin <= 1
        causes.append(
            {
"cause": "Random baseball variance",
"confidence": "Medium" if close else "Low",
"evidence": f"Final margin was {margin} run(s)."
                + (
" A one-run margin is consistent with normal game variance."
                    if close
                    else " A multi-run margin suggests the miss is less likely to be pure variance."
                ),
            }
        )

    causes.append(
        {
"cause": "Starting pitcher outperformed/underperformed the model's FIP assumption",
"confidence": "Insufficient evidence",
"evidence": "This pick's actual per-start pitching line is not stored in the database, so this cannot be confirmed or ruled out.",
        }
    )
    causes.append(
        {
"cause": "Lineup stronger/weaker than expected",
"confidence": "Insufficient evidence",
"evidence": "Actual in-game batting production is not stored; only the pregame confirmed-lineup OPS input is available.",
        }
    )
    causes.append(
        {
"cause": "Bullpen performed differently than expected",
"confidence": "Insufficient evidence",
"evidence": "Actual bullpen runs allowed is not stored; only pregame bullpen ERA/fatigue inputs are available.",
        }
    )

    causes.sort(key=lambda c: _CONF_ORDER.get(c["confidence"], 0), reverse=True)
    return causes


def _feature_review_totals(row, snap):
    expected = _num(snap.get("expected_total"))
    actual = _num(row.get("actual_total"))
    out = []
    if expected is not None and actual is not None:
        for key, label in _ADJ_LABELS.items():
            val = snap.get(key)
            if val is None:
                continue
            counterfactual = expected - val
            base_err, cf_err = abs(expected - actual), abs(counterfactual - actual)
            if base_err < cf_err:
                verdict = "Helped (removing it would have made the prediction worse)"
            elif base_err > cf_err:
                verdict = "Hurt (removing it would have made the prediction closer to actual)"
            else:
                verdict = "No measurable effect on this pick"
            out.append(
                {
"feature": label,
"expected_value": round(val, 3),
"actual_value": None,
"actual_value_note": "Not independently observed — this is a modeling adjustment, not a directly measured quantity.",
"verdict": verdict,
                }
            )
    for key, ref in [
        ("home_fip", LEAGUE_AVG_FIP),
        ("away_fip", LEAGUE_AVG_FIP),
        ("home_rsg", LEAGUE_AVG_RSG),
        ("away_rsg", LEAGUE_AVG_RSG),
        ("park_factor", 1.0),
        ("weather_factor", 1.0),
    ]:
        val = snap.get(key)
        if val is None:
            continue
        out.append(
            {
"feature": key.replace("_", " "),
"expected_value": val,
"actual_value": None,
"actual_value_note": "Not tracked post-game — no per-game pitcher/team box score attribution is stored.",
"verdict": "Cannot be isolated — combines multiplicatively into the base expected-runs calculation, not stored as a separable run contribution.",
            }
        )
    return out


def _feature_review_moneyline(row, snap):
    market = _market_prob(row, snap)
    attribution = _attribution(row, snap, market)
    won = row.get("status") == "won"
    out = []
    for a in attribution:
        if a["effect_pp"] == 0:
            continue
        agreed_with_pick = a["effect_pp"] > 0
        if won:
            verdict = (
"Helped (agreed with the winning pick)"
                if agreed_with_pick
                else "Was cautionary but pick won anyway"
            )
        else:
            verdict = (
"Hurt (agreed with the pick, which lost)"
                if agreed_with_pick
                else "Correctly cautious (disagreed with the pick, which lost)"
            )
        out.append(
            {
"feature": a["feature"],
"expected_value": a["effect_pp"],
"actual_value": None,
"actual_value_note": "Not tracked post-game.",
"verdict": verdict,
            }
        )
    return out


_COUNTERFACTUAL_FACTORS = [
    ("Contact Quality", "contact_quality_runs_adj", "additive"),
    ("Bullpen", "bullpen_workload_adj", "additive"),
    ("Lineup", "lineup_runs_adj", "additive"),
    ("Weather", "weather_factor", "multiplicative"),
    ("Park", "park_factor", "multiplicative"),
]


_ALL_ADDITIVE_KEYS = list(_ADJ_LABELS.keys())


def counterfactual_analysis(row, snap):

    expected = _num(snap.get("expected_total"))
    actual = _num(row.get("actual_total"))
    market_line = _num(snap.get("market_line"))
    if expected is None or actual is None:
        return []

    additive_sum = sum(snap.get(k) or 0.0 for k in _ALL_ADDITIVE_KEYS)
    base = expected - additive_sum

    def _direction(total, line):
        if line is None or total is None:
            return None
        if total > line:
            return "OVER"
        if total < line:
            return "UNDER"
        return "PUSH"

    orig_direction = _direction(expected, market_line)

    out = []
    for label, key, kind in _COUNTERFACTUAL_FACTORS:
        val = snap.get(key)
        if val is None:
            continue
        if kind == "additive":
            cf_expected = expected - val
        else:
            if not val:
                continue
            cf_expected = expected - base + (base / val)
        cf_expected = round(cf_expected, 3)

        cf_direction = _direction(cf_expected, market_line)
        would_pick_change = (
            orig_direction is not None
            and cf_direction is not None
            and cf_direction != orig_direction
        )

        would_result_change = None
        if cf_direction is not None:
            cf_would_have_won = (
                (
                    (cf_direction == "OVER" and actual > market_line)
                    or (cf_direction == "UNDER" and actual < market_line)
                )
                if market_line is not None
                else None
            )

            would_result_change = bool(cf_would_have_won) if cf_would_have_won is not None else None

        out.append(
            {
"factor": label,
"original_value": round(val, 3),
"kind": kind,
"counterfactual_expected_total": cf_expected,
"original_expected_total": round(expected, 3),
"would_pick_change": would_pick_change,
"would_result_change": would_result_change,
            }
        )
    return out


def _model_learning(row, pick_type, reason_codes):
    from services.model_learning_service import (
        MIN_PROMOTION_EXAMPLES,
        REQUIRED_QUALIFYING_RUNS,
        get_learning_status,
    )

    status = get_learning_status()
    latest_run = next((r for r in status["latest"] if r["pick_type"] == pick_type), None)
    active = status["active_models"].get(pick_type)

    review = get_loss_review(version=None)
    prob = _num(row.get("model_prob")) or 0

    def pb(p):
        return "<55%" if p < 0.55 else "55-60%" if p < 0.60 else "60-65%" if p < 0.65 else "65%+"

    bucket_label = pb(prob)
    prob_bucket = next(
        (b for b in review["probability_buckets"] if b["label"] == bucket_label), None
    )
    type_bucket = next((b for b in review["by_type"] if b["label"] == pick_type), None)
    same_reason_n = sum(
        1
        for l in review["losses"]
        if l.get("reason_codes") and reason_codes and l["reason_codes"][0] == reason_codes[0]
    )

    is_pattern = bool(
        prob_bucket and prob_bucket["n"] >= 15 and (prob_bucket["win_rate"] or 0) < 52.4
    )
    return {
"learning_service_state": {
"active_model_promoted": active is not None,
"active_model_metrics": active.get("metrics") if active else None,
"latest_training_run_status": latest_run.get("status") if latest_run else "collecting",
"promotion_requirement": f">= {MIN_PROMOTION_EXAMPLES} resolved examples with {REQUIRED_QUALIFYING_RUNS} consecutive qualifying retraining runs",
"note": (
"This single pick does not trigger any automatic weight change. "
"services/model_learning_service.py only retrains in scheduled batch cycles using "
"[model_logit, market_logit, disagreement] as inputs — no postgame or result field "
"is ever an input to that recalibration."
            ),
        },
"pattern_check": {
"probability_bucket": bucket_label,
"bucket_sample_n": prob_bucket["n"] if prob_bucket else 0,
"bucket_win_rate": prob_bucket["win_rate"] if prob_bucket else None,
"pick_type_sample_n": type_bucket["n"] if type_bucket else 0,
"pick_type_win_rate": type_bucket["win_rate"] if type_bucket else None,
"same_primary_reason_seen_before": max(same_reason_n - 1, 0),
"is_recurring_pattern": is_pattern,
"verdict": (
                (
                    f"Recurring pattern — this pick's probability bucket ({bucket_label}) has won only "
                    f"{prob_bucket['win_rate']}% across {prob_bucket['n']} resolved picks, below the 52.4% breakeven line."
                )
                if is_pattern
                else (
                    f"Isolated miss for now — either the sample size in this pick's bucket is too small "
                    f"(n={prob_bucket['n'] if prob_bucket else 0}) or its win rate is not below breakeven. "
"Treat as noise until more resolved picks accumulate."
                )
            ),
        },
"should_change_model_development": is_pattern,
"sufficient_evidence_to_change_model": bool(
            is_pattern and prob_bucket and prob_bucket["n"] >= 30
        ),
    }


def _suggested_action(quality, root_causes, learning):
    if quality["score"] < 55:
        return {
"action": "Manual review required",
"why": f"Data completeness was only {quality['score']}% ({quality['label']}) at pick time — "
"conclusions from this pick's stored data are not reliable enough to act on automatically.",
        }
    top_cause = root_causes[0] if root_causes else None
    if learning["pattern_check"]["is_recurring_pattern"]:
        if learning["sufficient_evidence_to_change_model"]:
            return {
"action": "Consider changing a feature",
"why": learning["pattern_check"]["verdict"]
                + " Sample size is large enough (n>=30) to warrant a targeted change, not just monitoring.",
            }
        return {
"action": "Run an experiment",
"why": learning["pattern_check"]["verdict"]
            + " Sample size supports investigating further, but is not yet large enough to change the live model.",
        }
    neutral_causes = (
"Random baseball variance",
"Market variance (model was close to the market and lost anyway)",
    )
    if (
        top_cause
        and top_cause["confidence"] in ("High", "Medium")
        and top_cause["cause"] not in neutral_causes
    ):
        return {
"action": "Investigate",
"why": f"Top-ranked possible cause is \"{top_cause['cause']}\" ({top_cause['confidence']} confidence): {top_cause['evidence']}",
        }
    if top_cause and top_cause["cause"] in neutral_causes:
        return {
"action": "No action",
"why": f"Leading explanation is \"{top_cause['cause']}\" — {top_cause['evidence']} No specific model defect is implicated.",
        }
    return {
"action": "Monitor",
"why": "No single high-confidence cause or established pattern was found; keep tracking this bucket/reason code going forward.",
    }


def get_loss_debrief(pick_id):

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM picks WHERE id=?", (int(pick_id),)).fetchone()
    conn.close()
    if row is None:
        return None
    row = dict(row)
    if row.get("status") != "lost":
        return {
"error": f"Pick {pick_id} status is '{row.get('status')}', not 'lost' — this debrief is only built for losing picks."
        }

    snap = _snapshot(row.get("feature_snapshot"))
    pick_type = row.get("pick_type")
    quality = _quality(row, snap)

    if pick_type == "totals":
        thought = _thought_process_totals(snap)
        expected_reality = _expected_vs_reality_totals(row, snap)
        causes = _root_causes_totals(row, snap, quality)
        features = _feature_review_totals(row, snap)
        counterfactuals = counterfactual_analysis(row, snap)
        total_error = expected_reality.get("total_error")
    else:
        thought = _thought_process_moneyline(row, snap)
        expected_reality = _expected_vs_reality_moneyline(row, snap)
        causes = _root_causes_moneyline(row, snap, quality)
        features = _feature_review_moneyline(row, snap)
        counterfactuals = []
        total_error = None

    feat, ctx = _feature_context(snap)
    tags = _tags(
        {
            **row,
"type": pick_type,
"game": row.get("matchup"),
"total_error": total_error,
"home_lineup_confirmed": ctx.get("home_lineup_confirmed"),
"away_lineup_confirmed": ctx.get("away_lineup_confirmed"),
        }
    )
    reason_codes = [t[0] for t in tags]

    learning = _model_learning(row, pick_type, reason_codes)
    action = _suggested_action(quality, causes, learning)

    return {
"pick_id": int(pick_id),
"date": row.get("date"),
"matchup": row.get("matchup"),
"pick_type": pick_type,
"pick": row.get("pick"),
"odds": row.get("odds"),
"model_prob": row.get("model_prob"),
"ev": row.get("ev"),
"clv": row.get("clv"),
"model_version": row.get("model_version"),
"model_build": row.get("model_build"),
"data_quality": quality,
"model_thought_process": thought,
"expected_vs_reality": expected_reality,
"root_cause_analysis": causes,
"counterfactual_analysis": counterfactuals,
"feature_review": features,
"model_learning": learning,
"suggested_action": action,
"diagnostic_tags": [t[1] for t in tags],
"disclaimer": (
"This debrief is built entirely from data already stored for this pick "
"(feature_snapshot, final score, and existing diagnostic aggregates). Root "
"causes are ranked hypotheses, not confirmed facts — items marked "
"'Insufficient evidence' mean the data needed to confirm or rule out that "
"cause is not captured anywhere in this system. This page never modifies "
"model weights or logic."
        ),
    }
