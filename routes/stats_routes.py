from flask import Blueprint, jsonify, request
from services.stats_service import get_stats, get_recent_picks, update_results
from datetime import date

from flask import Blueprint, jsonify, request

from services.stats_service import get_recent_picks, get_stats, update_results

stats_bp = Blueprint("stats", __name__, url_prefix="/api")


@stats_bp.route("/stats", methods=["GET"])
def stats():
    return jsonify(get_stats())


@stats_bp.route("/recent-picks", methods=["GET"])
def recent():
    return jsonify(get_recent_picks(20))


@stats_bp.route("/update-results", methods=["POST"])
def update():
    result = update_results()
    return jsonify(result)


@stats_bp.route("/capture-clv", methods=["POST"])
def capture_clv():
    try:
        from services.clv_service import capture_clv as _capture

        date_str = (request.get_json(silent=True) or {}).get("date")
        if date_str:
            date.fromisoformat(date_str)
        result = _capture(date_str)
        return jsonify(result)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid date; use YYYY-MM-DD."}), 400
    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})


@stats_bp.route("/clv-summary", methods=["GET"])
def clv_summary():
    try:
        from services.clv_service import get_clv_summary

        return jsonify({"status": "success", **get_clv_summary()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
