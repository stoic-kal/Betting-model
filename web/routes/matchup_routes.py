"""Routes for the read-only MLB Matchup Lab workspace."""
from flask import Blueprint, jsonify, render_template, request

from services.matchup_service import get_game, get_slate, get_status

matchup_bp = Blueprint("matchup", __name__)


@matchup_bp.get("/matchups")
def matchups_page():
    return render_template("matchups.html")


@matchup_bp.get("/api/matchups/slate")
def matchup_slate_api():
    return jsonify(get_slate(request.args.get("date")))


@matchup_bp.get("/api/matchups/game/<int:game_pk>")
def matchup_game_api(game_pk: int):
    game = get_game(game_pk, request.args.get("date"))
    if game is None:
        return jsonify({"error": "Matchup game not found."}), 404
    return jsonify(game)


@matchup_bp.get("/api/matchups/status")
def matchup_status_api():
    return jsonify(get_status())
