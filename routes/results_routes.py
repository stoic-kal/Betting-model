from flask import Blueprint, jsonify, request

from services.results_service import get_results

results_bp = Blueprint("results", __name__, url_prefix="/api")


@results_bp.route("/results", methods=["GET"])
def get_all_results():
    date_filter = request.args.get("date", None)
    results = get_results(date_filter)
    return jsonify(results)
