TOTALS_ENABLED = True


ML_MIN_EV = 10.0
ML_MIN_PROB = 0.555
ML_MIN_EDGE = 1.5


SNAPSHOT_SCHEMA_VERSION = 2
MODEL_VERSION = "v3"
MODEL_BUILD = "v3.3-advanced"

import json
import sys

sys.path.insert(0, "src")


def _json_safe(obj):

    try:
        import numpy as np

        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    return str(obj)


from datetime import datetime
from pathlib import Path

from config import ODDS_API_KEY, today_et
from services.execution_service import sanitize_odds_quotes, validate_decimal_odds

if Path("models/lgbm_v2_moneyline.pkl").exists() and Path("models/lgbm_v2_totals.pkl").exists():
    _engine = "v2"
else:
    _engine = "v1 (market-implied)"

from track_picks import PickTracker

tracker = PickTracker()


def _factor_sentence(name, value, supports, detail):
    return {
        "name": name,
        "value": value,
        "effect": "supports" if supports else "opposes",
        "detail": detail,
    }


def _american_odds(decimal_odds):
    if decimal_odds <= 1:
        return "—"
    return (
        f"+{round((decimal_odds - 1) * 100)}"
        if decimal_odds >= 2
        else f"{round(-100 / (decimal_odds - 1))}"
    )


def _advanced_summary(summary, pick_type):

    model_name = (
        "market-anchored moneyline model"
        if pick_type == "moneyline"
        else "push-adjusted Poisson totals model"
    )

    def compose(factor_limit):
        factor_text = " ".join(
            f"{factor['name']} is classified as {factor['effect']}: {factor['detail']}"
            for factor in summary.get("factors", [])[:factor_limit]
        )
        return (
            f"{summary['overview']} The research treats the market as a strong baseline and tests whether the locked baseball inputs justify departing from that consensus. "
            f"The {model_name} identified this evidence: {factor_text} "
            f"Together, those findings support the recommendation because {summary['decision'].lower()} The estimated edge is analytical, not a promise that the selection will win. "
            f"Risk assessment: {summary['risk']} Baseball results can still turn on relief pitching, sequencing, defense, or a few high-impact plays. "
            f"Data assessment: {summary['data_quality']} The probability, price, and supporting inputs were locked before first pitch, preventing live events from rewriting the explanation. "
            "Judge the recommendation over many comparable predictions using calibration, closing-line value, prediction error, and return on investment—not one game."
        )

    text = compose(3)
    if len(text.split()) > 200:
        text = compose(2)
    if len(text.split()) < 150:
        text += " No single factor controls the forecast; the conclusion reflects their combined direction, magnitude, and reliability."
    return text


def _moneyline_summary(
    pick_team, home_team, model_prob, market_prob, ev, odds_display, features, advisory=None
):

    selected_home = pick_team == home_team
    direction = 1 if selected_home else -1
    factors = []
    specs = [
        (
            "Starting pitcher",
            features.get("fip_adv", 0),
            lambda v: f"FIP advantage is {v:+.2f} from the home-team perspective.",
        ),
        (
            "Venue scoring",
            features.get("rsg_adv", 0),
            lambda v: f"Home/road scoring-rate difference is {v:+.2f} runs per game.",
        ),
        (
            "Recent form",
            features.get("form_adv", 0),
            lambda v: f"Last-10 venue win-rate difference is {v*100:+.1f} percentage points.",
        ),
        (
            "Bullpen quality",
            features.get("bp_adv", 0),
            lambda v: f"Bullpen ERA advantage is {v:+.2f}; positive favors the home bullpen.",
        ),
        (
            "Season strength",
            features.get("wpct_adv", 0),
            lambda v: f"Season win-rate difference is {v*100:+.1f} percentage points.",
        ),
        (
            "Confirmed lineup",
            features.get("lineup_ops_adv", 0),
            lambda v: (
                f"Confirmed-lineup OPS difference is {v:+.3f}."
                if features.get("context_complete")
                else "Both lineups were not confirmed, so lineup adjustment was neutral."
            ),
        ),
        ("Rest", features.get("rest_adv", 0), lambda v: f"Rest-day difference is {v:+.0f} days."),
        (
            "Bullpen workload",
            features.get("bullpen_fatigue_adv", 0),
            lambda v: f"Recent workload advantage is {v:+.0f}; positive favors the home bullpen.",
        ),
        (
            "Defense",
            features.get("defense_adv", 0),
            lambda v: f"Fielding-percentage advantage is {v:+.3f} points.",
        ),
    ]
    for name, raw, describe in specs:
        raw = float(raw or 0)
        selected_value = raw * direction
        if abs(selected_value) < 0.001 and name not in ("Confirmed lineup",):
            continue
        factors.append(_factor_sentence(name, raw, selected_value >= 0, describe(raw)))
    advanced = features.get("advanced", {})
    home_sc = advanced.get("home_pitcher_statcast", {})
    away_sc = advanced.get("away_pitcher_statcast", {})
    if home_sc.get("available") and away_sc.get("available"):
        raw = float((away_sc.get("xera_proxy") or 4.2) - (home_sc.get("xera_proxy") or 4.2))
        xera_label = (
            "official Baseball Savant xERA"
            if not home_sc.get("xera_is_proxy") and not away_sc.get("xera_is_proxy")
            else "Statcast-derived xERA proxy"
        )
        factors.append(
            _factor_sentence(
                "Statcast contact quality",
                raw,
                raw * direction >= 0,
                f"{xera_label} is home {home_sc['xera_proxy']:.2f} versus {home_sc.get('era') or '—'} ERA and away {away_sc['xera_proxy']:.2f} versus {away_sc.get('era') or '—'} ERA; xBA/xwOBA/xSLG and sample sizes are retained in the locked snapshot.",
            )
        )
        factors.append(
            _factor_sentence(
                "Pitch arsenal",
                0,
                True,
                f"Average velocity is home {home_sc.get('avg_velocity') or '—'} mph and away {away_sc.get('avg_velocity') or '—'} mph, with pitch-mix samples retained in the locked snapshot.",
            )
        )
    if features.get("home_bullpen_pitches_3d") is not None:
        raw = float(
            (features.get("away_bullpen_fatigue") or 0)
            - (features.get("home_bullpen_fatigue") or 0)
        )
        factors.append(
            _factor_sentence(
                "Reliever availability",
                raw,
                raw * direction >= 0,
                f"Last-three-game bullpen usage is home {features.get('home_bullpen_pitches_3d')} pitches and away {features.get('away_bullpen_pitches_3d')} pitches; unavailable relievers: {features.get('home_unavailable_relievers')} / {features.get('away_unavailable_relievers')}.",
            )
        )
    platoon = advanced.get("lineup_handedness", {})
    hp = platoon.get("home_vs_away_sp", {})
    ap = platoon.get("away_vs_home_sp", {})
    if hp.get("available") and ap.get("available"):
        raw = float(hp.get("adjustment", 0) - ap.get("adjustment", 0))
        factors.append(
            _factor_sentence(
                "Lineup handedness",
                raw,
                raw * direction >= 0,
                f"Opposite-hand lineup rates are home {hp['opposite_hand_rate']:.1%} and away {ap['opposite_hand_rate']:.1%}. This is a conservative composition proxy, not a claimed historical platoon split.",
            )
        )
    factors.sort(key=lambda item: (item["effect"] != "supports", item["name"]))
    summary = {
        "title": f"Why v3 selected {pick_team}",
        "overview": (
            f"V3 estimates a {model_prob:.1%} win probability versus the "
            f"market’s {market_prob:.1%}. At {odds_display}, that produces "
            f"{ev:+.1f}% expected value."
        ),
        "decision": (
            "The selected side had the higher final model probability after "
            "market shrinkage and calibration."
        ),
        "factors": factors,
        "risk": advisory or ("This is a qualified selection under the current model rules."),
        "data_quality": (
            "Both starting lineups confirmed."
            if features.get("context_complete")
            else "Lineup information was incomplete; lineup impact was kept neutral."
        ),
    }
    summary["advanced"] = _advanced_summary(summary, "moneyline")
    return summary


def _totals_summary(result, market_line, advisory=None):
    expected = float(result["expected_total"])
    direction = result["direction"].upper()
    gap = expected - float(market_line)
    context = result.get("context", {})
    factors = [
        {
            "name": "Expected runs",
            "effect": "supports",
            "detail": f'Projected total is {expected:.2f}, {abs(gap):.2f} runs {"above" if gap > 0 else "below"} the {market_line} line.',
        },
        {
            "name": "Starting pitching",
            "effect": "context",
            "detail": f'Home/away starter FIP: {result["home_fip"]:.2f} / {result["away_fip"]:.2f}.',
        },
        {
            "name": "Expected starter duration",
            "effect": "context",
            "detail": (
                "Home/away expected starter innings: "
                f'{result.get("home_starter_usage", {}).get("expected_innings", 5.5):.2f} / '
                f'{result.get("away_starter_usage", {}).get("expected_innings", 5.5):.2f}. '
                "The remaining innings are assigned to the bullpens rather than a fixed 5.5/3.5 split."
            ),
        },
        {
            "name": "Available bullpen quality",
            "effect": "context",
            "detail": (
                "Home/away available-bullpen ERA estimate: "
                f'{result.get("home_team_available_bp_era", result.get("away_bp_era", 4.2)):.2f} / '
                f'{result.get("away_team_available_bp_era", result.get("home_bp_era", 4.2)):.2f}. '
                "This blends team quality with recently observed relievers who are not workload-flagged."
            ),
        },
        {
            "name": "Offense",
            "effect": "context",
            "detail": f'Home/away venue-adjusted RS/G: {result["home_rsg"]:.2f} / {result["away_rsg"]:.2f}.',
        },
        {
            "name": "Park",
            "effect": (
                "supports" if ((result["park_factor"] > 1) == (direction == "OVER")) else "opposes"
            ),
            "detail": f'Park scoring factor is {result["park_factor"]:.2f}.',
        },
        {
            "name": "Weather",
            "effect": (
                "supports"
                if ((result.get("weather_factor", 1) > 1) == (direction == "OVER"))
                else "opposes"
            ),
            "detail": f'Weather multiplier is {result.get("weather_factor", 1):.3f}.',
        },
        {
            "name": "Lineups",
            "effect": "context",
            "detail": (
                f'Confirmed-lineup run adjustment: {result.get("lineup_runs_adj", 0):+.2f}.'
                if context.get("context_complete")
                else "Both lineups were not confirmed, so lineup adjustment was neutral."
            ),
        },
        {
            "name": "Bullpen workload",
            "effect": "context",
            "detail": f'Recent workload adds {result.get("bullpen_workload_adj", 0):+.2f} projected runs.',
        },
        {
            "name": "Defense",
            "effect": "context",
            "detail": f'Defensive adjustment is {result.get("defense_runs_adj", 0):+.2f} projected runs.',
        },
    ]
    advanced = context.get("advanced", {})
    home_sc = advanced.get("home_pitcher_statcast", {})
    away_sc = advanced.get("away_pitcher_statcast", {})
    if home_sc.get("available") and away_sc.get("available"):
        factors.append(
            {
                "name": "Statcast contact quality",
                "effect": "context",
                "detail": f"Baseball Savant xERA values (or explicitly marked fallback proxies) are {home_sc['xera_proxy']:.2f}/{away_sc['xera_proxy']:.2f}; contact-quality adjustment is {result.get('contact_quality_runs_adj',0):+.2f} runs.",
            }
        )
    if context.get("home_bullpen_pitches_3d") is not None:
        factors.append(
            {
                "name": "Reliever availability",
                "effect": "context",
                "detail": f"Actual three-game bullpen pitch counts are {context.get('home_bullpen_pitches_3d')}/{context.get('away_bullpen_pitches_3d')}, with {context.get('home_unavailable_relievers')}/{context.get('away_unavailable_relievers')} relievers flagged unavailable.",
            }
        )
    factors.append(
        {
            "name": "Home-run environment",
            "effect": "context",
            "detail": f"Run park factor is {result['park_factor']:.2f}; derived HR-environment proxy is {result.get('hr_park_factor_proxy',1):.3f}.",
        }
    )
    game_day = advanced.get("game_day", {})
    if game_day.get("available"):
        factors.append(
            {
                "name": "Series and roof context",
                "effect": "context",
                "detail": f"{game_day.get('series_description') or 'Series game'}, game {game_day.get('series_game_number') or '—'} of {game_day.get('games_in_series') or '—'}, {game_day.get('day_night') or 'time unknown'}; roof/environment status: {game_day.get('roof_status') or 'unknown'}.",
            }
        )
    summary = {
        "title": f"Why v3 selected {direction} {market_line}",
        "overview": (
            f'The model projects {expected:.2f} runs and assigns {result["model_prob"]:.1%} '
            f'to {direction}, versus a {result["market_prob"]:.1%} market probability. '
            f'Best available odds create {result["ev"]:+.1f}% expected value.'
        ),
        "decision": "The selected direction had the higher push-adjusted Poisson probability after confidence shrinkage.",
        "factors": factors,
        "risk": advisory or "This is a qualified selection under the current model rules.",
        "data_quality": (
            "Both starting lineups confirmed."
            if context.get("context_complete")
            else "Lineup information was incomplete; lineup impact was kept neutral."
        ),
    }
    summary["advanced"] = _advanced_summary(summary, "totals")
    return summary


def summary_from_saved_pick(pick):

    try:
        snapshot = json.loads(pick.get("feature_snapshot") or "{}")
    except (TypeError, json.JSONDecodeError):
        snapshot = {}
    if pick.get("pick_type") == "moneyline":
        features = snapshot.get("features", {})
        home_team = pick.get("matchup", "").split(" @ ")[-1]
        market_prob = (
            snapshot.get("market_home")
            if pick.get("pick") == home_team
            else snapshot.get("market_away")
        )
        if market_prob is None:
            market_prob = 1 / float(pick.get("odds") or 2)
        return _moneyline_summary(
            pick.get("pick", "selection"),
            home_team,
            float(pick.get("model_prob") or 0),
            float(market_prob),
            float(pick.get("ev") or 0),
            _american_odds(float(pick.get("odds") or 2)),
            features,
            None,
        )
    expected = snapshot.get("expected_total")
    line = snapshot.get("market_line")
    direction = str(pick.get("pick", "TOTAL")).split()[0]
    factors = []
    if expected is not None and line is not None:
        factors.append(
            {
                "name": "Expected runs",
                "effect": "supports",
                "detail": f"The locked projection was {float(expected):.2f} runs against a {float(line):.1f} market total.",
            }
        )
    factors.extend(
        [
            {
                "name": "Starting pitching",
                "effect": "context",
                "detail": f'Locked home/away FIP was {snapshot.get("home_fip", "—")} / {snapshot.get("away_fip", "—")}.',
            },
            {
                "name": "Venue offense",
                "effect": "context",
                "detail": f'Locked home/away scoring rate was {snapshot.get("home_rsg", "—")} / {snapshot.get("away_rsg", "—")} runs per game.',
            },
            {
                "name": "Bullpen workload",
                "effect": "context",
                "detail": f'The stored workload adjustment was {float(snapshot.get("bullpen_workload_adj") or 0):+.2f} runs.',
            },
        ]
    )
    market_prob = 1 / float(pick.get("odds") or 2)
    summary = {
        "title": f'Why v3 selected {pick.get("pick", "the total")}',
        "overview": f'V3 assigned {float(pick.get("model_prob") or 0):.1%} probability to {direction}, versus approximately {market_prob:.1%} implied by the stored price.',
        "decision": "the locked run projection and contextual adjustments favored the selected side of the market total.",
        "factors": factors,
        "risk": "Totals remain sensitive to bullpen usage, lineup changes, weather, and run sequencing.",
        "data_quality": "This explanation uses only fields preserved in the original pregame snapshot.",
    }
    summary["advanced"] = _advanced_summary(summary, "totals")
    return summary


ALTITUDE_TEAMS = {"COL"}


RETRACTABLE_TEAMS = {"ARI", "HOU", "MIA", "MIL", "SEA", "TEX", "TOR"}


def _situation_score(pred: dict, pitcher_context) -> tuple:

    score = 0
    reasons = []

    matchup = pred.get("matchup", "")
    home_team = matchup.split(" @ ")[-1].strip() if " @ " in matchup else ""
    pick_str = pred.get("_pick_direction", "")

    if home_team in ALTITUDE_TEAMS:
        score += 2
        reasons.append("Coors Field (+2)")
    if home_team in RETRACTABLE_TEAMS:
        score -= 0

    if pitcher_context:
        home_fip = pitcher_context.get("home_fip")
        away_fip = pitcher_context.get("away_fip")

        if home_fip is not None and away_fip is not None:
            if home_fip < 3.5 and away_fip < 3.5:
                score -= 2
                reasons.append(f"Elite SP matchup FIP {home_fip:.1f}/{away_fip:.1f} (-2)")
            elif home_fip < 4.0 and away_fip < 4.0:
                score -= 1
                reasons.append(f"Good SP matchup FIP {home_fip:.1f}/{away_fip:.1f} (-1)")
            elif home_fip > 5.0 and away_fip > 5.0:
                score += 2
                reasons.append(f"Weak SP matchup FIP {home_fip:.1f}/{away_fip:.1f} (+2)")
            elif home_fip > 4.5 or away_fip > 4.5:
                score += 1
                reasons.append(f"Vulnerable SP (+1)")

        home_l10_rs = pitcher_context.get("home_L10_rs")
        away_l10_rs = pitcher_context.get("away_L10_rs")
        if home_l10_rs is not None and away_l10_rs is not None:
            if home_l10_rs > 5.0 and away_l10_rs > 5.0:
                score += 2
                reasons.append(f"Hot offenses L10 {home_l10_rs:.1f}/{away_l10_rs:.1f} (+2)")
            elif home_l10_rs < 3.5 and away_l10_rs < 3.5:
                score -= 1
                reasons.append(f"Cold offenses L10 {home_l10_rs:.1f}/{away_l10_rs:.1f} (-1)")

        temp_f = pitcher_context.get("temp_f")
        if temp_f is not None and temp_f < 48:
            score -= 1
            reasons.append(f"Cold weather {temp_f:.0f}°F (-1)")

        wind_out = pitcher_context.get("wind_out_factor")
        if wind_out is not None:
            if wind_out > 0.7:
                score += 1
                reasons.append(f"Wind blowing out (+1)")
            elif wind_out < -0.7:
                score -= 1
                reasons.append(f"Wind blowing in (-1)")

    return score, reasons


def _situation_confirms(situation_score: int, pick_direction: str) -> bool:

    if pick_direction == "over":
        return situation_score >= 0
    else:
        return situation_score <= 0


def generate_picks(forecast_stage="manual", eligible_game_pks=None):

    from services.schedule_service import get_today_games

    try:
        schedule_games = get_today_games(include_odds=False)
        if eligible_game_pks is not None:
            eligible = {str(x) for x in eligible_game_pks}
            schedule_games = [g for g in schedule_games if str(g.get("game_pk")) in eligible]
        if not schedule_games:
            return {"status": "error", "message": "No MLB games scheduled today."}

        from services.odds_feed_service import fetch_odds_games

        checkpoint = forecast_stage in ("morning_baseline", "lineup_update", "final_lock")
        odds_games = fetch_odds_games(
            forecast_stage,
            force=checkpoint,
            max_age_seconds=120 if forecast_stage == "manual" else 600,
        )

        generated = []
        unavailable = []
        for game in schedule_games:
            result = generate_pick_for_game(
                game["away_abbr"],
                game["home_abbr"],
                odds_games=odds_games,
                schedule_games=schedule_games,
                forecast_stage=forecast_stage,
            )
            picks = result.get("picks", [])
            generated.extend(picks)
            markets = {p.get("pick_type") for p in picks}
            missing = [m for m in ("moneyline", "totals") if m not in markets]
            if result.get("error") or missing:
                unavailable.append(
                    {
                        "matchup": f"{game['away_abbr']} @ {game['home_abbr']}",
                        "missing": missing,
                        "reason": result.get("error") or "Market odds unavailable",
                    }
                )

        return {
            "status": "success",
            "date": today_et(),
            "games_count": len(schedule_games),
            "picks_count": len(generated),
            "recorded_count": len(generated) if forecast_stage == "lineup_lock" else 0,
            "moneyline_count": sum(p["pick_type"] == "moneyline" for p in generated),
            "totals_count": sum(p["pick_type"] == "totals" for p in generated),
            "unavailable": unavailable,
            "forecast_stage": forecast_stage,
            "recorded": forecast_stage == "lineup_lock",
            "message": (
                "Official-lineup selections locked and recorded."
                if forecast_stage == "lineup_lock"
                else "Preview generated only. Official picks record when both MLB starting lineups are confirmed."
            ),
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


def generate_pick_for_game(
    away_abbr: str, home_abbr: str, odds_games=None, schedule_games=None, forecast_stage="manual"
):

    import json
    import sqlite3

    import numpy as np

    API_KEY = ODDS_API_KEY

    from services.schedule_service import _abbr, _american

    today = today_et()

    record_official = forecast_stage == "lineup_lock"

    from services.schedule_service import get_today_games as _get_schedule

    if schedule_games is None:
        schedule_games = _get_schedule()
    scheduled_game = next(
        (
            g
            for g in schedule_games
            if g.get("away_abbr") == away_abbr and g.get("home_abbr") == home_abbr
        ),
        None,
    )
    if scheduled_game:
        from datetime import timezone

        state = scheduled_game.get("game_state", "")
        detailed = scheduled_game.get("status", "")
        start_raw = scheduled_game.get("game_date_utc", "")
        start_reached = False
        if start_raw:
            try:
                start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                start_reached = datetime.now(timezone.utc) >= start_dt
            except (TypeError, ValueError):
                pass

        still_pregame = state in {"Preview", "Pre-Game", "Warmup", ""}
        if state in {"Live", "Final"} or (start_reached and not still_pregame):
            return {
                "picks": [],
                "locked": True,
                "error": (
                    f"Pregame picks are locked. {away_abbr} @ {home_abbr} "
                    f'is {detailed or state or "at/after scheduled start"}; '
                    "live odds cannot replace the original prediction."
                ),
            }

    if record_official:
        if not scheduled_game or not scheduled_game.get("game_pk"):
            return {"picks": [], "error": "Official lock waiting for a valid MLB game identifier."}
        if not scheduled_game.get("away_sp_id") or not scheduled_game.get("home_sp_id"):
            return {
                "picks": [],
                "error": "Official lock waiting for both probable starting pitchers.",
            }
        try:
            from services.game_context_service import get_lineup_status

            readiness = get_lineup_status(scheduled_game["game_pk"], force=True)
        except Exception as exc:
            return {"picks": [], "error": f"Official lineup verification failed: {exc}"}
        if not (
            readiness.get("home_confirmed")
            and readiness.get("away_confirmed")
            and readiness.get("home_count", 0) >= 9
            and readiness.get("away_count", 0) >= 9
        ):
            return {
                "picks": [],
                "error": "Official lock waiting for both confirmed nine-player lineups.",
                "lineup_readiness": readiness,
            }

    try:
        if odds_games is None:
            from services.odds_feed_service import fetch_odds_games

            odds_games = fetch_odds_games("generation", max_age_seconds=120)
    except Exception as e:
        return {"picks": [], "error": f"Odds API error: {e}"}

    target = None
    for g in odds_games:
        if (
            _abbr(g.get("home_team", "")) == home_abbr
            and _abbr(g.get("away_team", "")) == away_abbr
        ):
            target = g
            break

    if not target:
        return {
            "picks": [],
            "error": f"Game {away_abbr} @ {home_abbr} not found in live odds. May not be available yet.",
        }

    home_full = target["home_team"]
    away_full = target["away_team"]
    event_id = target.get("event_id", f"{away_abbr}_{home_abbr}_{today}")
    matchup = f"{away_full} @ {home_full}"
    scheduled_start = scheduled_game.get("game_date_utc") if scheduled_game else None

    home_ml_list, away_ml_list, totals_by_line = [], [], {}
    home_ml_books, away_ml_books = [], []

    for book in target.get("books", []):
        bookmaker = (
            book.get("book")
            or book.get("key")
            or book.get("title")
            or book.get("bookmaker")
            or book.get("sportsbook")
            or "Unknown"
        )
        mkt = book.get("market")
        if mkt == "h2h":
            for o in book.get("outcomes", []):
                p = o.get("price")
                if p:
                    valid_price, _ = validate_decimal_odds(p)
                    if not valid_price:
                        continue
                    if o.get("name") == home_full:
                        home_ml_list.append(float(p))
                        home_ml_books.append((float(p), bookmaker))
                    else:
                        away_ml_list.append(float(p))
                        away_ml_books.append((float(p), bookmaker))
        elif mkt == "totals":
            for o in book.get("outcomes", []):
                pt, p, n = o.get("point"), o.get("price"), o.get("name")
                if pt and p and n:
                    valid_price, _ = validate_decimal_odds(p)
                    if not valid_price:
                        continue
                    ln = float(pt)
                    totals_by_line.setdefault(
                        ln, {"over": [], "under": [], "over_books": [], "under_books": []}
                    )
                    if n == "Over":
                        totals_by_line[ln]["over"].append(float(p))
                        totals_by_line[ln]["over_books"].append((float(p), bookmaker))
                    else:
                        totals_by_line[ln]["under"].append(float(p))
                        totals_by_line[ln]["under_books"].append((float(p), bookmaker))

    if not home_ml_list or not away_ml_list:
        return {"picks": [], "error": "Moneyline market is not fully priced yet."}
    if record_official and not any(
        prices.get("over") and prices.get("under") for prices in totals_by_line.values()
    ):
        return {"picks": [], "error": "Official lock waiting for a complete totals market."}

    picks_out = []

    raw_home = np.mean([1 / o for o in home_ml_list])
    raw_away = np.mean([1 / o for o in away_ml_list])
    total_vig = raw_home + raw_away
    mkt_home = raw_home / total_vig
    mkt_away = raw_away / total_vig

    from services.ml_model_v3 import compute_ml_prob

    home_sp_id_ml = None
    away_sp_id_ml = None
    game_pk_ml = None
    try:
        sched_games = schedule_games
        for sg in sched_games:
            if sg["home_abbr"] == home_abbr and sg["away_abbr"] == away_abbr:
                home_sp_id_ml = sg.get("home_sp_id")
                away_sp_id_ml = sg.get("away_sp_id")
                game_pk_ml = sg.get("game_pk")
                break
    except Exception as e:
        print(f"   Schedule lookup (ML): {e}")

    ml_result = compute_ml_prob(
        away_abbr=away_abbr,
        home_abbr=home_abbr,
        away_sp_id=away_sp_id_ml,
        home_sp_id=home_sp_id_ml,
        mkt_home=mkt_home,
        mkt_away=mkt_away,
        game_pk=game_pk_ml,
    )
    model_home = ml_result["model_home"]
    model_away = ml_result["model_away"]
    ml_features = ml_result["features"]

    best_home_odds = max(home_ml_list)
    best_away_odds = max(away_ml_list)

    from services.prediction_math import expected_value

    home_ev = expected_value(model_home, best_home_odds)
    away_ev = expected_value(model_away, best_away_odds)

    def _book_for(price, books):
        return next((b for p, b in books if p == price), "Best Available")

    if model_home >= model_away:
        ml_pick_team = home_full
        ml_pick_prob = model_home
        ml_market_prob = mkt_home
        ml_best_odds = best_home_odds
        ml_ev = home_ev
        ml_opposite_odds = best_away_odds
        ml_sportsbook = _book_for(best_home_odds, home_ml_books)
    else:
        ml_pick_team = away_full
        ml_pick_prob = model_away
        ml_market_prob = mkt_away
        ml_best_odds = best_away_odds
        ml_ev = away_ev
        ml_opposite_odds = best_home_odds
        ml_sportsbook = _book_for(best_away_odds, away_ml_books)

    ml_odds_display = _american(ml_best_odds)
    ml_game_id = f"{event_id}_ML"
    model_edge = (ml_pick_prob - ml_market_prob) * 100

    try:
        from services.debug_reasoning import print_ml_reasoning

        print_ml_reasoning(
            matchup=f"{away_full} @ {home_full}",
            ml_result=ml_result,
            pick_team=ml_pick_team,
            pick_prob=ml_pick_prob,
            market_prob=ml_market_prob,
            model_edge=model_edge,
            home_sp_id=home_sp_id_ml,
            away_sp_id=away_sp_id_ml,
            ev=ml_ev,
        )
    except Exception as e:
        print(f"   Debug reasoning (ML) failed: {e}")

    from services.prediction_math import kelly_units

    def _ml_pick_dict(skipped=False, skip_reason=None):
        d = {
            "pick_type": "moneyline",
            "pick": ml_pick_team,
            "model_prob": round(ml_pick_prob, 4),
            "market_prob": round(ml_market_prob, 4),
            "model_edge": round(model_edge, 2),
            "odds_display": ml_odds_display,
            "odds_dec": round(ml_best_odds, 3),
            "ev": round(ml_ev, 2),
            "kelly_units": kelly_units(ml_pick_prob, ml_best_odds),
            "num_books": len(home_ml_list),
            "ml_logit_delta": ml_result.get("logit_delta"),
            "ml_features": ml_features,
        }
        if skipped:
            d["skipped"] = True
            d["skip_reason"] = skip_reason
        return d

    _is_slight_dog = 2.05 <= ml_best_odds <= 2.50
    _min_prob = 0.525 if _is_slight_dog else ML_MIN_PROB

    ml_skip_reason = None
    if ml_ev < ML_MIN_EV:
        ml_skip_reason = f"EV {ml_ev:.1f}% < {ML_MIN_EV}% minimum"
    elif ml_pick_prob < _min_prob:
        ml_skip_reason = f'model_prob {ml_pick_prob:.3f} < {_min_prob} minimum{"  [dog boost]" if _is_slight_dog else ""}'
    elif model_edge < ML_MIN_EDGE:
        ml_skip_reason = f"edge {model_edge:.1f}pp < {ML_MIN_EDGE}pp minimum"
    ml_recommendation_tier = "qualified_pick" if ml_skip_reason is None else "daily_forecast"

    snapshot_created_at = datetime.now().isoformat()
    ml_snapshot = json.dumps(
        {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "model_version": MODEL_VERSION,
            "snapshot_created_at": snapshot_created_at,
            "market_home": mkt_home,
            "market_away": mkt_away,
            "features": ml_features,
        },
        default=_json_safe,
    )

    ml_stake = {
        "theoretical_kelly_units": kelly_units(ml_pick_prob, ml_best_odds),
        "realized_stake_units": 0.0,
        "wager_status": "preview",
        "wager_reason": "preview is not an executed wager",
    }
    if record_official:
        try:
            conn = sqlite3.connect("database/picks.db")
            ml_theoretical = kelly_units(ml_pick_prob, ml_best_odds)
            from services.execution_service import allocate_realized_stake

            ml_stake = allocate_realized_stake(
                conn,
                date=today,
                matchup=matchup,
                game_id=ml_game_id,
                theoretical_kelly=ml_theoretical,
                recommendation_tier=ml_recommendation_tier,
            )
            conn.execute(
                """INSERT INTO picks
                   (game_id, date, matchup, pick_type, pick, odds, model_prob, ev,
                    kelly_units, theoretical_kelly_units, realized_stake_units,
                    wager_status, wager_reason, status, created_at, model_version, model_build,
                    opposite_opening_odds, opposite_price_source, forecast_stage, scheduled_start,
                    recommendation_tier, feature_snapshot)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'actual sportsbook generation quote',?,?,?,?)
                   ON CONFLICT(game_id) DO UPDATE SET
                     date=excluded.date, matchup=excluded.matchup,
                     pick_type=excluded.pick_type, pick=excluded.pick,
                     odds=excluded.odds, model_prob=excluded.model_prob,
                     ev=excluded.ev, kelly_units=excluded.kelly_units,
                     theoretical_kelly_units=excluded.theoretical_kelly_units,
                     realized_stake_units=COALESCE(picks.realized_stake_units,excluded.realized_stake_units),
                     wager_status=CASE
                         WHEN picks.realized_stake_units IS NULL THEN excluded.wager_status
                         ELSE picks.wager_status
                     END,
                     wager_reason=CASE
                         WHEN picks.realized_stake_units IS NULL THEN excluded.wager_reason
                         ELSE picks.wager_reason
                     END,
                     model_version=excluded.model_version,
                     model_build=excluded.model_build,
                     opposite_opening_odds=excluded.opposite_opening_odds,
                     opposite_price_source=excluded.opposite_price_source,
                     forecast_stage=excluded.forecast_stage,
                     scheduled_start=excluded.scheduled_start,
                     recommendation_tier=excluded.recommendation_tier,
                     feature_snapshot=excluded.feature_snapshot""",
                (
                    ml_game_id,
                    today,
                    matchup,
                    "moneyline",
                    ml_pick_team,
                    ml_best_odds,
                    ml_pick_prob,
                    ml_ev,
                    ml_theoretical,
                    ml_stake["theoretical_kelly_units"],
                    ml_stake["realized_stake_units"],
                    ml_stake["wager_status"],
                    ml_stake["wager_reason"],
                    "pending",
                    snapshot_created_at,
                    MODEL_VERSION,
                    MODEL_BUILD,
                    ml_opposite_odds,
                    forecast_stage,
                    scheduled_start,
                    ml_recommendation_tier,
                    ml_snapshot,
                ),
            )
            conn.execute(
                "UPDATE picks SET mlb_game_pk=? WHERE game_id=?",
                (scheduled_game.get("game_pk") if scheduled_game else None, ml_game_id),
            )
            conn.commit()
            conn.close()
            print(
                f"  ML: {ml_pick_team} | best: {ml_odds_display} | model: {ml_pick_prob:.1%} vs mkt: {ml_market_prob:.1%} | EV: {ml_ev:.1f}%"
            )
            print("  Moneyline committed")

            try:
                from services import discord_service

                ml_kelly = ml_stake["realized_stake_units"]

                print("  Sending moneyline model output...")
                discord_service.send_moneyline_output(
                    {
                        "matchup": matchup,
                        "prediction": ml_pick_team,
                        "model_prob": ml_pick_prob,
                        "market_prob": ml_market_prob,
                        "model_version": MODEL_BUILD,
                    }
                )
                print("  Model output sent")

                if ml_kelly > 0:
                    print("  Sending pick notification...")
                    discord_service.send_pick(
                    {
                        "pick_type": "moneyline",
                        "matchup": matchup,
                        "pick": ml_pick_team,
                        "model_prob": ml_pick_prob,
                        "kelly_units": ml_kelly,
                        "odds_dec": ml_best_odds,
                        "sportsbook": ml_sportsbook,
                    }
                    )
                    print("  Pick notification sent")
            except Exception as e:
                print(f"  Discord notification failed: {e}")

            try:
                from services import shadow_inference_service

                shadow_inference_service.shadow_moneyline(
                    home_abbr, away_abbr, home_sp_id_ml, away_sp_id_ml,
                    scheduled_start, ml_pick_prob, ml_market_prob, ml_best_odds,
                )
            except Exception:
                pass
        except Exception as e:
            print(f"   DB save error (ML): {e}")
    ml_pick = _ml_pick_dict()
    ml_pick["qualified"] = ml_skip_reason is None
    ml_pick["recommendation_tier"] = ml_recommendation_tier
    ml_pick["theoretical_kelly_units"] = kelly_units(ml_pick_prob, ml_best_odds)
    ml_pick["realized_stake_units"] = (
        ml_stake["realized_stake_units"] if record_official else 0.0
    )
    ml_pick["recorded"] = record_official
    ml_pick["advisory"] = ml_skip_reason
    ml_pick["summary"] = _moneyline_summary(
        ml_pick_team,
        home_full,
        ml_pick_prob,
        ml_market_prob,
        ml_ev,
        ml_odds_display,
        ml_features,
        ml_skip_reason,
    )
    picks_out.append(ml_pick)

    if TOTALS_ENABLED and totals_by_line:
        from services.totals_model_v3 import compute_totals_pick

        complete_lines = {
            line: prices
            for line, prices in totals_by_line.items()
            if prices["over"] and prices["under"]
        }
        if not complete_lines:
            return {"picks": picks_out, "error": "Totals market is not fully priced yet."}
        main_line = max(
            complete_lines,
            key=lambda line: min(
                len(complete_lines[line]["over"]), len(complete_lines[line]["under"])
            ),
        )
        odds_t = complete_lines[main_line]
        n_books_t = min(len(odds_t["over"]), len(odds_t["under"]))

        from services.schedule_service import get_today_games

        home_sp_id = None
        away_sp_id = None
        venue_city = ""
        game_pk = None
        try:
            today_games = schedule_games if schedule_games is not None else get_today_games()
            for g in today_games:
                if g["home_abbr"] == home_abbr and g["away_abbr"] == away_abbr:
                    home_sp_id = g.get("home_sp_id")
                    away_sp_id = g.get("away_sp_id")
                    venue_city = g.get("venue", "")
                    game_pk = g.get("game_pk")
                    break
        except Exception as e:
            print(f"   Schedule lookup error: {e}")

        tot_result = compute_totals_pick(
            away_abbr=away_abbr,
            home_abbr=home_abbr,
            away_sp_id=away_sp_id,
            home_sp_id=home_sp_id,
            market_line=main_line,
            over_odds_list=odds_t["over"],
            under_odds_list=odds_t["under"],
            n_books=n_books_t,
            venue_city=venue_city,
            game_pk=game_pk,
        )

        try:
            from services.debug_reasoning import print_totals_reasoning

            print_totals_reasoning(
                matchup=f"{away_abbr} @ {home_abbr}",
                tot_result=tot_result,
                market_line=main_line,
            )
        except Exception as e:
            print(f"   Debug reasoning (Totals) failed: {e}")

        if "pick" in tot_result:
            tot_game_id = f"{event_id}_TOTALS"
            tot_direction = tot_result["pick"].split()[0].upper()
            tot_opposite_odds = max(odds_t["under"] if tot_direction == "OVER" else odds_t["over"])

            _tot_books = odds_t.get("over_books" if tot_direction == "OVER" else "under_books", [])
            tot_sportsbook = next(
                (b for p, b in _tot_books if p == tot_result["best_odds"]), "Best Available"
            )
            tot_snapshot_created_at = datetime.now().isoformat()
            totals_snapshot = json.dumps(
                {
                    "schema_version": SNAPSHOT_SCHEMA_VERSION,
                    "model_version": MODEL_VERSION,
                    "snapshot_created_at": tot_snapshot_created_at,
                    "market_line": main_line,
                    "expected_total": tot_result["expected_total"],
                    "run_distribution": tot_result.get("run_distribution"),
                    "home_fip": tot_result["home_fip"],
                    "away_fip": tot_result["away_fip"],
                    "home_rsg": tot_result["home_rsg"],
                    "away_rsg": tot_result["away_rsg"],
                    "lineup_runs_adj": tot_result.get("lineup_runs_adj"),
                    "bullpen_workload_adj": tot_result.get("bullpen_workload_adj"),
                    "defense_runs_adj": tot_result.get("defense_runs_adj"),
                    "park_factor": tot_result.get("park_factor"),
                    "home_bp_era": tot_result.get("home_bp_era"),
                    "away_bp_era": tot_result.get("away_bp_era"),
                    "home_available_bp_era": tot_result.get("home_available_bp_era"),
                    "away_available_bp_era": tot_result.get("away_available_bp_era"),
                    "home_team_available_bp_era": tot_result.get("home_team_available_bp_era"),
                    "away_team_available_bp_era": tot_result.get("away_team_available_bp_era"),
                    "home_starter_usage": tot_result.get("home_starter_usage"),
                    "away_starter_usage": tot_result.get("away_starter_usage"),
                    "weather_factor": tot_result.get("weather_factor"),
                    "temp_f": tot_result.get("temp_f"),
                    "wind_info": tot_result.get("wind_info"),
                    "weather_source": tot_result.get("weather_source"),
                    "weather_error": tot_result.get("weather_error"),
                    "ump_name": tot_result.get("ump_name"),
                    "ump_runs_adj": tot_result.get("ump_runs_adj"),
                    "contact_quality_runs_adj": tot_result.get("contact_quality_runs_adj"),
                    "recommendation_tier": tot_result.get("recommendation_tier"),
                    "qualification_checklist": tot_result.get("qualification_checklist"),
                    "market_price_spread": tot_result.get("market_price_spread"),
                    "context": tot_result.get("context", {}),
                },
                default=_json_safe,
            )
            tot_theoretical = (
                kelly_units(tot_result["model_prob"], tot_result["best_odds"])
                if not tot_result.get("skipped")
                and tot_result.get("recommendation_tier") != "daily_forecast"
                else 0.0
            )
            tot_stake = {
                "theoretical_kelly_units": tot_theoretical,
                "realized_stake_units": 0.0,
                "wager_status": "preview",
                "wager_reason": "preview is not an executed wager",
            }
            if record_official:
                try:
                    conn = sqlite3.connect("database/picks.db")
                    from services.execution_service import allocate_realized_stake

                    tot_stake = allocate_realized_stake(
                        conn,
                        date=today,
                        matchup=matchup,
                        game_id=tot_game_id,
                        theoretical_kelly=tot_theoretical,
                        recommendation_tier=tot_result.get("recommendation_tier"),
                    )
                    conn.execute(
                        """INSERT INTO picks
                       (game_id, date, matchup, pick_type, pick, odds,
                       model_prob, ev, kelly_units, theoretical_kelly_units,
                       realized_stake_units, wager_status, wager_reason,
                       status, created_at, model_version, model_build,
                       opposite_opening_odds, opposite_price_source, forecast_stage, scheduled_start, recommendation_tier,
                       feature_snapshot)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'actual sportsbook generation quote',?,?,?,?)
                       ON CONFLICT(game_id) DO UPDATE SET
                         date=excluded.date, matchup=excluded.matchup,
                         pick_type=excluded.pick_type, pick=excluded.pick,
                         odds=excluded.odds, model_prob=excluded.model_prob,
                         ev=excluded.ev, kelly_units=excluded.kelly_units,
                         theoretical_kelly_units=excluded.theoretical_kelly_units,
                         realized_stake_units=COALESCE(picks.realized_stake_units,excluded.realized_stake_units),
                         wager_status=CASE
                             WHEN picks.realized_stake_units IS NULL THEN excluded.wager_status
                             ELSE picks.wager_status
                         END,
                         wager_reason=CASE
                             WHEN picks.realized_stake_units IS NULL THEN excluded.wager_reason
                             ELSE picks.wager_reason
                         END,
                         model_version=excluded.model_version,
                         model_build=excluded.model_build,
                         opposite_opening_odds=excluded.opposite_opening_odds,
                         opposite_price_source=excluded.opposite_price_source,
                         forecast_stage=excluded.forecast_stage,
                         scheduled_start=excluded.scheduled_start,
                         recommendation_tier=excluded.recommendation_tier,
                         feature_snapshot=excluded.feature_snapshot""",
                        (
                            tot_game_id,
                            today,
                            matchup,
                            "totals",
                            tot_result["pick"],
                            tot_result["best_odds"],
                            tot_result["model_prob"],
                            tot_result["ev"],
                            tot_theoretical,
                            tot_stake["theoretical_kelly_units"],
                            tot_stake["realized_stake_units"],
                            tot_stake["wager_status"],
                            tot_stake["wager_reason"],
                            "pending",
                            tot_snapshot_created_at,
                            MODEL_VERSION,
                            MODEL_BUILD,
                            tot_opposite_odds,
                            forecast_stage,
                            scheduled_start,
                            tot_result.get("recommendation_tier", "daily_forecast"),
                            totals_snapshot,
                        ),
                    )
                    conn.execute(
                        "UPDATE picks SET mlb_game_pk=? WHERE game_id=?",
                        (scheduled_game.get("game_pk") if scheduled_game else None, tot_game_id),
                    )
                    conn.commit()
                    conn.close()
                    print("  Totals committed")

                    try:
                        from services import discord_service

                        tot_kelly = tot_stake["realized_stake_units"]

                        print("  Sending totals model output...")
                        discord_service.send_totals_output(
                            {
                                "matchup": matchup,
                                "prediction": tot_result["pick"],
                                "expected_total": tot_result["expected_total"],
                                "market_line": main_line,
                                "model_prob": tot_result["model_prob"],
                                "kelly_units": tot_kelly,
                                "model_version": MODEL_BUILD,
                            }
                        )
                        print("  Model output sent")

                        if tot_kelly > 0:
                            print("  Sending pick notification...")
                            discord_service.send_pick(
                                {
                                "pick_type": "totals",
                                "matchup": matchup,
                                "pick": tot_result["pick"],
                                "model_prob": tot_result["model_prob"],
                                "expected_total": tot_result["expected_total"],
                                "market_line": main_line,
                                "kelly_units": tot_kelly,
                                "odds_dec": tot_result["best_odds"],
                                "sportsbook": tot_sportsbook,
                                }
                            )
                            print("  Pick notification sent")
                    except Exception as e:
                        print(f"  Discord notification failed: {e}")

                    try:
                        from services import shadow_inference_service

                        shadow_inference_service.shadow_totals(
                            home_abbr, away_abbr, home_sp_id, away_sp_id,
                            scheduled_start, tot_result["model_prob"], main_line, tot_result["best_odds"],
                            "OVER" in tot_result["pick"],
                        )
                    except Exception:
                        pass
                except Exception as e:
                    print(f"   DB save error (Totals): {e}")

            picks_out.append(
                {
                    "pick_type": "totals",
                    "pick": tot_result["pick"],
                    "model_prob": tot_result["model_prob"],
                    "market_prob": tot_result["market_prob"],
                    "model_edge": tot_result["model_edge"],
                    "odds_display": tot_result["best_odds_display"],
                    "odds_dec": tot_result["best_odds"],
                    "ev": tot_result["ev"],
                    "expected_total": tot_result["expected_total"],
                    "home_fip": tot_result["home_fip"],
                    "away_fip": tot_result["away_fip"],
                    "home_rsg": tot_result["home_rsg"],
                    "away_rsg": tot_result["away_rsg"],
                    "park_factor": tot_result["park_factor"],
                    "home_bp_era": tot_result.get("home_bp_era"),
                    "away_bp_era": tot_result.get("away_bp_era"),
                    "home_available_bp_era": tot_result.get("home_available_bp_era"),
                    "away_available_bp_era": tot_result.get("away_available_bp_era"),
                    "home_team_available_bp_era": tot_result.get("home_team_available_bp_era"),
                    "away_team_available_bp_era": tot_result.get("away_team_available_bp_era"),
                    "home_starter_usage": tot_result.get("home_starter_usage"),
                    "away_starter_usage": tot_result.get("away_starter_usage"),
                    "weather_factor": tot_result.get("weather_factor"),
                    "temp_f": tot_result.get("temp_f"),
                    "wind_info": tot_result.get("wind_info"),
                    "ump_name": tot_result.get("ump_name"),
                    "ump_runs_adj": tot_result.get("ump_runs_adj"),
                    "lineup_runs_adj": tot_result.get("lineup_runs_adj"),
                    "bullpen_workload_adj": tot_result.get("bullpen_workload_adj"),
                    "defense_runs_adj": tot_result.get("defense_runs_adj"),
                    "context": tot_result.get("context", {}),
                    "kelly_units": (
                        kelly_units(tot_result["model_prob"], tot_result["best_odds"])
                        if tot_result.get("recommendation_tier") != "daily_forecast"
                        else 0
                    ),
                    "theoretical_kelly_units": tot_stake["theoretical_kelly_units"],
                    "realized_stake_units": tot_stake["realized_stake_units"],
                    "wager_status": tot_stake["wager_status"],
                    "wager_reason": tot_stake["wager_reason"],
                    "num_books": n_books_t,
                    "qualified": tot_result.get("recommendation_tier")
                    in ("qualified_pick", "strong_lock"),
                    "recommendation_tier": tot_result.get("recommendation_tier", "daily_forecast"),
                    "qualification_checklist": tot_result.get("qualification_checklist", {}),
                    "recorded": record_official,
                    "advisory": tot_result.get("skip_reason"),
                    "summary": _totals_summary(
                        tot_result, main_line, tot_result.get("skip_reason")
                    ),
                }
            )
        else:
            reason = tot_result.get("skip_reason", "filter")
            print(f"  ⏭ Totals skipped: {reason}")

            picks_out.append(
                {
                    "pick_type": "totals",
                    "pick": tot_result.get("pick", f"O/U {main_line}"),
                    "model_prob": tot_result.get("model_prob", 0),
                    "market_prob": tot_result.get("market_prob", 0),
                    "model_edge": tot_result.get("model_edge", 0),
                    "odds_display": tot_result.get("best_odds_display", "—"),
                    "odds_dec": tot_result.get("best_odds", 1.91),
                    "ev": tot_result.get("ev", 0),
                    "expected_total": tot_result.get("expected_total", 0),
                    "home_fip": tot_result.get("home_fip", 0),
                    "away_fip": tot_result.get("away_fip", 0),
                    "home_rsg": tot_result.get("home_rsg", 0),
                    "away_rsg": tot_result.get("away_rsg", 0),
                    "park_factor": tot_result.get("park_factor", 1.0),
                    "num_books": n_books_t,
                    "skipped": True,
                    "skip_reason": reason,
                }
            )

    return {"picks": picks_out, "error": None}
