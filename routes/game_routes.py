import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from config import now_et, today_et
from services.pick_service import summary_from_saved_pick
from services.schedule_service import get_game_detail, get_today_games

game_bp = Blueprint("game", __name__)


def _postgame_analysis(game, picks):
    if not game or str(game.get("game_state", "")).lower() != "final":
        return None
    away_score = game.get("away_score")
    home_score = game.get("home_score")
    if away_score is None or home_score is None:
        return None
    actual_total = int(away_score) + int(home_score)
    winner = game["away"] if away_score > home_score else game["home"]
    loser = game["home"] if away_score > home_score else game["away"]
    margin = abs(int(away_score) - int(home_score))
    rows = []
    for pick in picks:
        snapshot = {}
        try:
            snapshot = json.loads(pick.get("feature_snapshot") or "{}")
        except (TypeError, ValueError):
            pass
        row = {
"pick_type": pick.get("pick_type"),
"pick": pick.get("pick"),
"status": str(pick.get("status") or "pending").lower(),
"model_prob": pick.get("model_prob"),
"ev": pick.get("ev"),
"clv": pick.get("clv"),
"actual_total": actual_total,
        }
        if pick.get("pick_type") == "totals":
            expected = snapshot.get("expected_total")
            row["expected_total"] = expected
            row["projection_error"] = (
                actual_total - expected if isinstance(expected, (int, float)) else None
            )
            match = re.search(r"(OVER|UNDER)\s+([0-9.]+)", str(pick.get("pick", "")).upper())
            line = float(match.group(2)) if match else None
            row["line"] = line
            row["analysis"] = (
                f"The game finished with {actual_total} runs against a {line:g} line. "
                f'The locked {match.group(1).title()} was {row["status"]}.'
                if match and line is not None
                else f'The game finished with {actual_total} runs; the stored total was {row["status"]}.'
            )
        else:
            row["analysis"] = (
                f'{winner} won by {margin} run{"s" if margin != 1 else ""}. '
                f'The model assigned {float(pick.get("model_prob") or 0) * 100:.1f}% to {pick.get("pick")}, '
                f'and the locked selection was {row["status"]}.'
            )
        rows.append(row)
    return {
"away_score": int(away_score),
"home_score": int(home_score),
"actual_total": actual_total,
"winner": winner,
"loser": loser,
"margin": margin,
"picks": rows,
    }


@game_bp.route("/api/live-state")
def live_state():
    from services.schedule_service import get_live_state

    date = request.args.get("date", today_et())
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid date.", "games": []}), 400
    try:
        games = get_live_state(date)
        response = jsonify({"status": "success", "date": date, "games": games})
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc), "games": []}), 500


@game_bp.route("/")
def home():
    today = today_et()
    display = now_et().strftime("%A, %B %-d %Y")
    try:
        games = get_today_games(today)
        return render_template("home.html", games=games, today=display, error=None)
    except Exception as e:
        return render_template("home.html", games=[], today=display, error=str(e))


@game_bp.route("/game/<slug>")
def game_detail(slug):
    import sqlite3

    today = today_et()
    display = now_et().strftime("%A, %B %-d %Y")

    parts = slug.upper().split("-VS-")
    if len(parts) != 2:
        return render_template("game_detail.html", game=None, today=display, existing_picks=[])
    away_abbr, home_abbr = parts[0], parts[1]

    game = get_game_detail(away_abbr, home_abbr, today)

    existing_picks = []
    try:
        conn = sqlite3.connect("database/picks.db")
        conn.row_factory = sqlite3.Row
        matchup = f"{game['away']} @ {game['home']}" if game else None
        rows = conn.execute(
"SELECT * FROM picks WHERE date=? AND matchup=? ORDER BY pick_type", (today, matchup)
        ).fetchall()
        conn.close()
        existing_picks = [dict(r) for r in rows]
        for pick in existing_picks:
            pick["summary"] = summary_from_saved_pick(pick)
            try:
                saved_snapshot = json.loads(pick.get("feature_snapshot") or "{}")
            except (TypeError, ValueError):
                saved_snapshot = {}
            pick["recommendation_tier"] = (
                pick.get("recommendation_tier")
                or saved_snapshot.get("recommendation_tier")
                or "legacy_unclassified"
            )
            pick["qualification_checklist"] = saved_snapshot.get("qualification_checklist", {})
    except Exception:
        pass

    return render_template(
"game_detail.html",
        game=game,
        today=display,
        existing_picks=existing_picks,
        postgame=_postgame_analysis(game, existing_picks),
    )


@game_bp.route("/api/game-card", methods=["GET", "POST"])
def game_card():

    payload = request.get_json(silent=True) or {} if request.method == "POST" else request.args
    away = str(payload.get("away", "")).upper()
    home = str(payload.get("home", "")).upper()
    date = str(payload.get("date", today_et()))
    regen = request.method == "POST"

    if not re.fullmatch(r"[A-Z]{2,3}", away) or not re.fullmatch(r"[A-Z]{2,3}", home):
        return '<p style="color:red">Missing ?away=XXX&home=YYY params</p>', 400
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return '<p style="color:red">Invalid date</p>', 400

    card_path = Path(f"results/cards/{date}_{away}_{home}.html")

    if regen:
        cmd = [
            sys.executable,
"generate_game_card.py",
"--away",
            away,
"--home",
            home,
"--date",
            date,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                return f'<pre style="color:red">{result.stderr}</pre>', 500
        except subprocess.TimeoutExpired:
            return '<p style="color:red">Card generation timed out</p>', 500

    if not card_path.exists():
        abort(404)

    return send_file(card_path, mimetype="text/html")
