import json
import re
import sqlite3
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, request

from config import today_et
from services.pick_service import generate_pick_for_game, generate_picks

picks_bp = Blueprint("picks", __name__)
_slate_generation_lock = threading.Lock()


@picks_bp.route("/api/run-picks", methods=["POST"])
def run_picks():

    if not _slate_generation_lock.acquire(blocking=False):
        return jsonify({"status": "busy", "message": "Slate generation is already running."}), 409
    try:
        from services.game_context_service import get_lineup_status
        from services.schedule_service import get_today_games

        schedule_games = get_today_games(include_odds=False)

        lock_pks = []
        preview_pks = []
        pending_status = []

        for g in schedule_games:
            state = str(g.get("game_state", "")).lower()
            matchup = f"{g.get('away_abbr','?')} @ {g.get('home_abbr','?')}"
            if state in ("live", "final", "in progress", "game over"):
                continue
            pk = g.get("game_pk")

            if not g.get("away_sp_id") or not g.get("home_sp_id"):
                pending_status.append(
                    {
                        "matchup": matchup,
                        "blocking": "Waiting for both probable starters to be posted by MLB",
                    }
                )
                preview_pks.append(pk)
                continue

            try:
                ready = get_lineup_status(pk, force=True)
            except Exception as exc:
                ready = {"confirmed": False, "home_count": 0, "away_count": 0}
            if not ready.get("confirmed"):
                hc = ready.get("home_count", 0)
                ac = ready.get("away_count", 0)
                pending_status.append(
                    {
                        "matchup": matchup,
                        "blocking": f"Lineups not yet confirmed — away {ac}/9, home {hc}/9",
                    }
                )
                preview_pks.append(pk)
                continue

            lock_pks.append(pk)

        locked_result = generate_picks("lineup_lock", lock_pks) if lock_pks else {}
        preview_result = generate_picks("manual", preview_pks) if preview_pks else {}

        locked_ml = locked_result.get("moneyline_count", 0)
        locked_tot = locked_result.get("totals_count", 0)
        prev_ml = preview_result.get("moneyline_count", 0)
        prev_tot = preview_result.get("totals_count", 0)

        unavailable = (locked_result.get("unavailable") or []) + (
            preview_result.get("unavailable") or []
        )
        for ps in pending_status:
            unavailable.append(
                {
                    "matchup": ps["matchup"],
                    "reason": ps["blocking"],
                    "missing": ["moneyline", "totals"],
                }
            )

        response = jsonify(
            {
                "status": "success",
                "games_count": len(lock_pks) + len(preview_pks),
                "moneyline_count": locked_ml + prev_ml,
                "totals_count": locked_tot + prev_tot,
                "recorded_count": locked_ml + locked_tot,
                "locked_games": len(lock_pks),
                "preview_games": len(preview_pks),
                "unavailable": unavailable,
                "message": (
                    f"{locked_ml + locked_tot} picks RECORDED for {len(lock_pks)} confirmed-lineup game(s). "
                    f"{prev_ml + prev_tot} previewed for {len(preview_pks)} pending game(s) — will auto-lock when lineups confirm."
                    if lock_pks
                    else "Preview only — no lineups confirmed yet. Picks will auto-lock when MLB posts batting orders."
                ),
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        _slate_generation_lock.release()


@picks_bp.route("/api/picks-by-date", methods=["GET"])
def picks_by_date():

    date = request.args.get("date")

    if not date:
        return jsonify([])

    try:
        conn = sqlite3.connect("database/picks.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT game_id, date, matchup, pick_type, pick, odds, model_prob, ev, status
            FROM picks
            WHERE date = ?
            ORDER BY ev DESC
        """,
            (date,),
        )

        rows = cursor.fetchall()
        conn.close()

        return jsonify([dict(row) for row in rows])

    except Exception as e:
        return jsonify({"error": str(e)})


@picks_bp.route("/api/generate-pick", methods=["POST"])
def generate_pick_route():

    payload = request.get_json(silent=True) or {}
    away = str(payload.get("away", "")).upper()
    home = str(payload.get("home", "")).upper()
    if not re.fullmatch(r"[A-Z]{2,3}", away) or not re.fullmatch(r"[A-Z]{2,3}", home):
        return jsonify({"error": "Missing away or home param"}), 400
    from services.schedule_service import get_today_games

    scheduled = next(
        (
            g
            for g in get_today_games(today_et(), include_odds=False)
            if g.get("away_abbr") == away and g.get("home_abbr") == home
        ),
        None,
    )
    if scheduled and str(scheduled.get("game_state", "")).lower() == "final":
        return (
            jsonify({"error": "This game is final. Pregame picks cannot be generated or changed."}),
            409,
        )
    result = generate_pick_for_game(away, home)
    return jsonify(result)


@picks_bp.route("/api/all-predictions", methods=["GET"])
def all_predictions():

    date = request.args.get("date")

    if not date:
        return jsonify([])

    try:
        conn = sqlite3.connect("database/picks.db")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM picks WHERE date = ? ORDER BY ev DESC
        """,
            (date,),
        )

        rows = cursor.fetchall()
        conn.close()

        return jsonify([dict(row) for row in rows])

    except:
        return jsonify([])


def _monitor_completeness(snapshot, pick_type):

    features = snapshot.get("features", snapshot)
    context = features.get("context", snapshot.get("context", {}))
    if pick_type == "moneyline":
        checks = [
            ("Home lineup", features.get("home_lineup_confirmed")),
            ("Away lineup", features.get("away_lineup_confirmed")),
            ("Home starter FIP", features.get("home_fip")),
            ("Away starter FIP", features.get("away_fip")),
            ("Home offense", features.get("home_rsg")),
            ("Away offense", features.get("away_rsg")),
            ("Home bullpen", features.get("home_bp_era")),
            ("Away bullpen", features.get("away_bp_era")),
            ("Defense", features.get("defense_adv")),
            ("Rest", features.get("rest_adv")),
            ("Travel", features.get("travel_timezone_adv")),
            ("Market baseline", snapshot.get("market_home")),
        ]
    else:
        checks = [
            ("Home lineup", context.get("home_lineup_confirmed")),
            ("Away lineup", context.get("away_lineup_confirmed")),
            ("Home starter FIP", snapshot.get("home_fip")),
            ("Away starter FIP", snapshot.get("away_fip")),
            ("Home offense", snapshot.get("home_rsg")),
            ("Away offense", snapshot.get("away_rsg")),
            ("Bullpen workload", snapshot.get("bullpen_workload_adj")),
            ("Defense", snapshot.get("defense_runs_adj")),
            ("Rest", context.get("rest_adv")),
            ("Travel", context.get("travel_timezone_adv")),
            ("Market total", snapshot.get("market_line")),
            ("Expected runs", snapshot.get("expected_total")),
        ]

    def available(value):
        return value is not None and not (isinstance(value, bool) and value is False)

    present = [label for label, value in checks if available(value)]
    missing = [label for label, value in checks if not available(value)]
    return {"present": len(present), "total": len(checks), "missing": missing}


@picks_bp.route("/api/live-monitor", methods=["GET"])
def live_monitor():

    date = request.args.get("date") or datetime.now(ZoneInfo("America/New_York")).strftime(
        "%Y-%m-%d"
    )
    try:
        conn = sqlite3.connect("database/picks.db")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT game_id, date, matchup, pick_type, pick, odds, opening_odds,
                   closing_odds, clv, clv_captured_at, model_prob, ev, status,
                   model_version, model_build, forecast_stage, scheduled_start,
                   recommendation_tier, kelly_units, theoretical_kelly_units,
                   realized_stake_units, wager_status, wager_reason,
                   feature_snapshot, created_at, updated_at
            FROM picks WHERE date = ?
            ORDER BY matchup, CASE pick_type WHEN 'moneyline' THEN 0 ELSE 1 END
        """,
            (date,),
        ).fetchall()
        conn.close()

        output = []
        for row in rows:
            item = dict(row)
            try:
                snapshot = json.loads(item.pop("feature_snapshot") or "{}")
            except (TypeError, json.JSONDecodeError):
                snapshot = {}
            features = snapshot.get("features", snapshot)
            if item["pick_type"] == "moneyline":
                home_team = item["matchup"].split(" @ ")[-1]
                market_prob = (
                    snapshot.get("market_home")
                    if item["pick"] == home_team
                    else snapshot.get("market_away")
                )
                expected_runs = None
            else:
                market_prob = (1 / item["odds"]) if item.get("odds") else None
                expected_runs = snapshot.get("expected_total")

            resolved = item["status"] in ("won", "lost")
            outcome = 1 if item["status"] == "won" else 0
            item.update(
                {
                    "market_prob": market_prob,
                    "expected_runs": expected_runs,
                    "market_total": snapshot.get("market_line"),
                    "completeness": _monitor_completeness(snapshot, item["pick_type"]),
                    "brier_error": (
                        round((item["model_prob"] - outcome) ** 2, 4) if resolved else None
                    ),
                    "locked": True,
                    "key_features": {
                        "home_fip": features.get("home_fip", snapshot.get("home_fip")),
                        "away_fip": features.get("away_fip", snapshot.get("away_fip")),
                        "home_rsg": features.get("home_rsg", snapshot.get("home_rsg")),
                        "away_rsg": features.get("away_rsg", snapshot.get("away_rsg")),
                    },
                }
            )
            output.append(item)
        return jsonify({"date": date, "picks": output, "count": len(output)})
    except Exception as exc:
        return jsonify({"error": str(exc), "date": date, "picks": []}), 500


@picks_bp.route("/api/mobile-slate", methods=["GET"])
def mobile_slate():

    date = request.args.get("date") or datetime.now(ZoneInfo("America/New_York")).strftime(
        "%Y-%m-%d"
    )
    try:
        from services.schedule_service import get_today_games

        games = get_today_games(date, include_odds=False)
        conn = sqlite3.connect("database/picks.db")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT game_id,date,matchup,pick_type,pick,odds,
            opening_odds,closing_odds,clv,model_prob,ev,status,model_version,
            model_build,forecast_stage,scheduled_start,kelly_units,
            theoretical_kelly_units,realized_stake_units,wager_status,wager_reason,
            feature_snapshot,recommendation_tier
            FROM picks WHERE date=? ORDER BY matchup,pick_type""",
            (date,),
        ).fetchall()
        conn.close()
        picks_by_matchup = {}
        for row in rows:
            item = dict(row)
            try:
                snapshot = json.loads(item.pop("feature_snapshot") or "{}")
            except (TypeError, json.JSONDecodeError):
                snapshot = {}
            item["expected_runs"] = snapshot.get("expected_total")
            item["market_total"] = snapshot.get("market_line")
            item["completeness"] = _monitor_completeness(snapshot, item["pick_type"])
            picks_by_matchup.setdefault(item["matchup"], []).append(item)
        output = []
        for game in games:
            matchup = f"{game['away']} @ {game['home']}"
            output.append(
                {
                    "game_pk": game["game_pk"],
                    "date": date,
                    "matchup": matchup,
                    "away_team": game["away"],
                    "home_team": game["home"],
                    "away_abbr": game["away_abbr"],
                    "home_abbr": game["home_abbr"],
                    "away_team_id": game.get("away_team_id"),
                    "home_team_id": game.get("home_team_id"),
                    "away_pitcher": game.get("away_sp_name"),
                    "home_pitcher": game.get("home_sp_name"),
                    "away_pitcher_id": game.get("away_sp_id"),
                    "home_pitcher_id": game.get("home_sp_id"),
                    "venue": game.get("venue"),
                    "time": game.get("time"),
                    "status": game.get("status"),
                    "scheduled_start": game.get("game_date_utc"),
                    "picks": picks_by_matchup.get(matchup, []),
                    "official_locked": any(
                        p.get("forecast_stage") == "lineup_lock"
                        for p in picks_by_matchup.get(matchup, [])
                    ),
                }
            )
        return jsonify({"date": date, "games": output, "count": len(output)})
    except Exception as exc:
        return jsonify({"error": "Internal server error.", "date": date, "games": []}), 500
