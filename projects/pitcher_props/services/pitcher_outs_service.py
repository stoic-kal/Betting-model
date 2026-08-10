import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from services.pitcher_workload_service import project_pitcher_workload, line_probs
from services.pitcher_prop_quotes_service import get_market_for_player
from services.pitcher_prop_db import save_official_lock

logger = logging.getLogger(__name__)

MODEL_VERSION = "outs_v1.0"


THRESHOLDS = {
"min_dq_forecast": 0.30,
"min_dq_qualified": 0.55,
"min_dq_strong": 0.75,
"min_edge_qualified": 4.0,
"min_edge_strong": 7.0,
"min_prob_qualified": 0.535,
"min_prob_strong": 0.580,
"min_ev_qualified": 3.0,
"min_ev_strong": 6.0,
"lineup_required_qualified": True,
"lineup_required_strong": True,
}


def _ev_pct(model_prob: float, odds_dec: float) -> float:

    return (model_prob * (odds_dec - 1) - (1 - model_prob)) * 100


def classify(
    model_prob: float,
    market_prob: Optional[float],
    edge_pp: Optional[float],
    ev_pct: Optional[float],
    dq_score: float,
    lineup_confirmed: bool,
    has_market: bool,
) -> str:

    T = THRESHOLDS
    if dq_score < T["min_dq_forecast"]:
        return "No Output"

    if (
        has_market
        and lineup_confirmed
        and dq_score >= T["min_dq_strong"]
        and edge_pp is not None
        and edge_pp >= T["min_edge_strong"]
        and model_prob >= T["min_prob_strong"]
        and ev_pct is not None
        and ev_pct >= T["min_ev_strong"]
    ):
        return "Strong Lock"

    if (
        has_market
        and (not T["lineup_required_qualified"] or lineup_confirmed)
        and dq_score >= T["min_dq_qualified"]
        and edge_pp is not None
        and edge_pp >= T["min_edge_qualified"]
        and model_prob >= T["min_prob_qualified"]
        and ev_pct is not None
        and ev_pct >= T["min_ev_qualified"]
    ):
        return "Qualified Pick"

    if dq_score >= T["min_dq_forecast"]:
        return "Daily Forecast"

    return "No Output"


def analyze_pitcher_outs(
    player_id: int,
    pitcher_name: str,
    team_abbr: str,
    opp_abbr: str,
    opp_lineup_ops: float,
    lineup_confirmed: bool,
    bullpen_available: bool,
    rest_days: int,
    is_injury_return: bool,
    injury_return_verified: bool,
    game_pk: Optional[int],
    game_id: Optional[str],
    event_id: Optional[str],
    scheduled_start: Optional[str],
    lines_to_evaluate: Optional[list[float]] = None,
    stage: str = "preview",
    create_lock: bool = False,
) -> dict:

    errors = []

    try:
        workload = project_pitcher_workload(
            player_id=player_id,
            pitcher_name=pitcher_name,
            team_abbr=team_abbr,
            opp_abbr=opp_abbr,
            opp_lineup_ops=opp_lineup_ops,
            lineup_confirmed=lineup_confirmed,
            bullpen_available=bullpen_available,
            rest_days=rest_days,
            is_injury_return=is_injury_return,
            injury_return_verified=injury_return_verified,
            game_pk=game_pk,
        )
    except Exception as e:
        logger.error("Workload projection failed for %s: %s", pitcher_name, e)
        return {
"workload": None,
"lines": {},
"market": {},
"best_pick": None,
"classification": "No Output",
"data_checklist": _empty_checklist(),
"lock_id": None,
"errors": [str(e)],
        }

    dq = workload.get("data_quality", {})
    dq_score = dq.get("score", 0.0)

    dist = workload.get("outs_distribution", {})
    exp_outs = workload.get("expected_outs", 0)

    if not lines_to_evaluate:

        lines_to_evaluate = _default_lines(exp_outs)

    line_results: dict[float, dict] = {}
    for ln in lines_to_evaluate:
        lp = line_probs(workload, ln)
        line_results[float(ln)] = lp

    market_data: dict[float, dict] = {}
    if event_id:
        try:
            raw_market = get_market_for_player(
                event_id=event_id,
                player_name=pitcher_name,
                prop_type="outs_recorded",
                game_pk=game_pk,
                team=team_abbr,
                opponent=opp_abbr,
                stage=stage,
            )
            if raw_market:
                for ln, mkt in raw_market.items():
                    market_data[float(ln)] = mkt
        except Exception as e:
            logger.warning("Market fetch failed for %s: %s", pitcher_name, e)
            errors.append(f"Market fetch failed: {e}")

    has_market = bool(market_data)

    best_pick = None
    best_ev = -999.0

    for ln, lp in line_results.items():
        for direction in ("over", "under"):
            model_prob = lp.get(direction, lp.get(f"prob_{direction}", 0.0))
            if model_prob is None or model_prob <= 0:
                continue

            mkt = market_data.get(ln, {})
            odds_key = f"{direction}_odds_dec"
            mp_key = f"market_prob_{direction}"
            odds_dec = mkt.get(odds_key) if mkt else None
            market_prob = mkt.get(mp_key) if mkt else None

            edge_pp = None
            ev = None
            if market_prob is not None and model_prob is not None:
                edge_pp = (model_prob - market_prob) * 100
            if odds_dec is not None and model_prob is not None:
                ev = _ev_pct(model_prob, odds_dec)

            cls = classify(
                model_prob=model_prob,
                market_prob=market_prob,
                edge_pp=edge_pp,
                ev_pct=ev,
                dq_score=dq_score,
                lineup_confirmed=lineup_confirmed,
                has_market=odds_dec is not None,
            )

            if cls == "No Output":
                continue

            rank = ev if ev is not None else (edge_pp if edge_pp is not None else 0)
            if rank > best_ev:
                best_ev = rank
                best_pick = {
"line": ln,
"direction": direction.capitalize(),
"model_prob": round(model_prob, 4),
"market_prob": round(market_prob, 4) if market_prob else None,
"edge_pp": round(edge_pp, 2) if edge_pp else None,
"ev_pct": round(ev, 2) if ev else None,
"odds_dec": odds_dec,
"sportsbook": mkt.get("bookmaker") if mkt else None,
"fair_odds_dec": (round(1.0 / model_prob, 4) if model_prob > 0 else None),
"classification": cls,
                }

    overall_cls = (
        best_pick["classification"]
        if best_pick
        else ("Daily Forecast" if dq_score >= THRESHOLDS["min_dq_forecast"] else "No Output")
    )

    checklist = _build_checklist(
        workload=workload,
        lineup_confirmed=lineup_confirmed,
        has_market=has_market,
        game_pk=game_pk,
        event_id=event_id,
    )

    lock_id = None
    if create_lock and best_pick and stage == "lineup_lock" and game_id:
        if overall_cls in ("Qualified Pick", "Strong Lock", "Daily Forecast"):
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            today = date.today().isoformat()
            lock_dict = {
"lock_date": today,
"game_id": game_id,
"game_pk": game_pk,
"player_id": player_id,
"player_name": pitcher_name,
"team": team_abbr,
"opponent": opp_abbr,
"prop_type": "outs_recorded",
"line": best_pick["line"],
"pick_direction": best_pick["direction"],
"model_prob": best_pick["model_prob"],
"market_prob": best_pick.get("market_prob"),
"edge_pp": best_pick.get("edge_pp"),
"ev_pct": best_pick.get("ev_pct"),
"odds_dec": best_pick.get("odds_dec"),
"sportsbook": best_pick.get("sportsbook"),
"fair_odds_dec": best_pick.get("fair_odds_dec"),
"expected_value_stat": workload.get("expected_outs"),
"distribution_json": json.dumps(workload.get("outs_distribution", {})),
"data_quality_score": dq_score,
"data_quality_label": dq.get("label", ""),
"classification": overall_cls,
"forecast_stage": stage,
"model_version": MODEL_VERSION,
"feature_snapshot": json.dumps(workload.get("feature_snapshot", {})),
"scheduled_start": scheduled_start,
"created_at": now,
            }
            lock_id = save_official_lock(lock_dict)
            if lock_id is None:
                errors.append(
"Lock already exists for this game/player/prop/line — not overwritten"
                )
                logger.info(
"Lock already exists for %s %s line=%.1f",
                    pitcher_name,
"outs_recorded",
                    best_pick["line"],
                )
            else:
                logger.info(
"Official lock created id=%d for %s %s %.1f %s",
                    lock_id,
                    pitcher_name,
"outs_recorded",
                    best_pick["line"],
                    best_pick["direction"],
                )

    return {
"player_id": player_id,
"player_name": pitcher_name,
"team": team_abbr,
"opponent": opp_abbr,
"prop_type": "outs_recorded",
"model_version": MODEL_VERSION,
"workload": {
"expected_outs": workload.get("expected_outs"),
"expected_ip": workload.get("expected_ip"),
"expected_pitches": workload.get("expected_pitches"),
"expected_bf": workload.get("expected_bf"),
"std_outs": workload.get("std_outs"),
"early_removal_prob": workload.get("early_removal_prob"),
"starter_role": workload.get("starter_role"),
"starter_label": workload.get("starter_label"),
"data_quality": dq,
"provenance": workload.get("provenance", {}),
        },
"lines": line_results,
"market": market_data,
"best_pick": best_pick,
"classification": overall_cls,
"data_checklist": checklist,
"lock_id": lock_id,
"errors": errors,
"stage": stage,
    }


def _default_lines(expected_outs: float) -> list[float]:

    import math

    anchor = math.floor(expected_outs) + 0.5
    lines = []
    for i in range(-4, 6):
        ln = round(anchor + i, 1)
        if 3.5 <= ln <= 27.5:
            lines.append(ln)
    return sorted(lines)


def _build_checklist(
    workload: dict,
    lineup_confirmed: bool,
    has_market: bool,
    game_pk: Optional[int],
    event_id: Optional[str],
) -> list[dict]:

    prov = workload.get("provenance", {})
    dq = workload.get("data_quality", {})
    return [
        {
"item": "Recent game log (8 starts)",
"ok": prov.get("has_game_log", False),
"note": f"{prov.get('n_starts', 0)} starts found",
        },
        {"item": "Season stats", "ok": prov.get("has_season_stats", False)},
        {
"item": "Lineup confirmed",
"ok": lineup_confirmed,
"note": "Affects confidence — unconfirmed reduces classification tier",
        },
        {
"item": "Opponent lineup OPS",
"ok": bool(workload.get("opp_lineup_ops")),
"note": f"OPS={workload.get('opp_lineup_ops', 'N/A')}",
        },
        {"item": "Bullpen availability", "ok": True, "note": "Used for early-removal estimate"},
        {
"item": "Market price available",
"ok": has_market,
"note": "Required for EV and edge calculations",
        },
        {"item": "TheOddsAPI event id", "ok": bool(event_id)},
        {"item": "MLB game_pk", "ok": bool(game_pk)},
        {
"item": f"Data quality: {dq.get('label','?')}",
"ok": dq.get("score", 0) >= 0.5,
"note": f"Score={dq.get('score', 0):.2f}",
        },
    ]


def _empty_checklist() -> list[dict]:
    return [{"item": "Workload projection", "ok": False, "note": "Projection failed"}]
