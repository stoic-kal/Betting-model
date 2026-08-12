import csv
import io
import json

from flask import Blueprint, Response, jsonify, request

from research.analytics.pick_analyzer import get_full_analytics
from services.analytics_service import _load_resolved, get_full_analytics_v2, sandbox_simulate
from services.loss_review_service import get_loss_debrief, get_loss_review, loss_review_csv
from services.market_signals_service import get_market_signals, signals_csv
from services.model_control_service import get_model_control
from services.model_lab import compare_candidates, get_candidate_detail, run_model_lab
from services.model_learning_service import run_learning_cycle
from services.opposite_model_service import get_opposite_model, opposite_csv
from services.pikkit_service import get_pikkit_calendar, pikkit_csv
from services.portfolio_risk_service import complete_history_portfolio_audit
from services.record_tracker_service import get_record_tracker, record_csv

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api")


def _internal_error():

    return jsonify({"status": "error", "message": "Internal server error."}), 500


@analytics_bp.route("/portfolio-risk")
def portfolio_risk_data():
    try:
        response = jsonify({"status": "success", **complete_history_portfolio_audit()})
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        return _internal_error()


@analytics_bp.route("/pikkit")
def pikkit_data():
    try:
        return jsonify(
            {
"status": "success",
                **get_pikkit_calendar(
                    request.args.get("month"),
                    request.args.get("type", "all"),
                    request.args.get("basis", "recorded"),
"v3",
                    request.args.get("unit_size", "20"),
                    request.args.get("tier", "all"),
                ),
            }
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@analytics_bp.route("/pikkit.csv")
def pikkit_export():
    try:
        month = request.args.get("month")
        payload = pikkit_csv(
            month,
            request.args.get("type", "all"),
            request.args.get("basis", "recorded"),
"v3",
            request.args.get("unit_size", "20"),
            request.args.get("tier", "all"),
        )
        return Response(
            payload,
            mimetype="text/csv",
            headers={
"Content-Disposition": f'attachment; filename="jingleez_pikkit_{month or "current"}.csv"',
"Cache-Control": "no-store",
            },
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@analytics_bp.route("/loss-review")
def loss_review_data():
    try:
        return jsonify(
            {
"status": "success",
                **get_loss_review(
                    request.args.get("version", "v3"), request.args.get("date") or None
                ),
            }
        )
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/loss-review.csv")
def loss_review_export():
    date_str = request.args.get("date") or None
    return Response(
        loss_review_csv(request.args.get("version", "v3"), date_str),
        mimetype="text/csv",
        headers={
"Content-Disposition": f'attachment; filename="jingleez_loss_review_{date_str or "all"}.csv"',
"Cache-Control": "no-store",
        },
    )


@analytics_bp.route("/loss-review/<int:pick_id>")
def loss_review_debrief(pick_id):
    try:
        result = get_loss_debrief(pick_id)
        if result is None:
            return jsonify({"status": "error", "message": "Pick not found."}), 404
        if "error" in result:
            return jsonify({"status": "error", "message": result["error"]}), 400
        return jsonify({"status": "success", "debrief": result})
    except Exception:
        return _internal_error()


@analytics_bp.route("/market-signals")
def market_signals_data():
    try:
        return jsonify({"status": "success", **get_market_signals(request.args.get("date"))})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/market-signals.csv")
def market_signals_export():
    dataset = request.args.get("dataset", "signals")
    if dataset not in ("signals", "movements", "snapshots", "movement_picks"):
        return jsonify({"status": "error", "message": "Unknown dataset"}), 400
    date_str = request.args.get("date")
    return Response(
        signals_csv(dataset, date_str),
        mimetype="text/csv",
        headers={
"Content-Disposition": f'attachment; filename="jingleez_market_{dataset}_{date_str or "today"}.csv"',
"Cache-Control": "no-store",
        },
    )


@analytics_bp.route("/record-tracker")
def record_tracker_data():
    try:
        return jsonify(
            {"status": "success", **get_record_tracker(request.args.get("version", "v3"))}
        )
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/record-tracker.csv")
def record_tracker_export():
    return Response(
        record_csv(request.args.get("version", "v3")),
        mimetype="text/csv",
        headers={
"Content-Disposition": 'attachment; filename="jingleez_detailed_record.csv"',
"Cache-Control": "no-store",
        },
    )


@analytics_bp.route("/opposite-model", methods=["GET"])
def opposite_model_data():
    try:
        response = jsonify({"status": "success", **get_opposite_model(request.args.get("version"))})
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/opposite-model.csv", methods=["GET"])
def opposite_model_export():
    return Response(
        opposite_csv(request.args.get("version")),
        mimetype="text/csv",
        headers={
"Content-Disposition": 'attachment; filename="jingleez_opposite_model.csv"',
"Cache-Control": "no-store",
        },
    )


@analytics_bp.route("/analytics", methods=["GET"])
def get_analytics():
    try:
        version = request.args.get("version", None)
        data = get_full_analytics_v2(model_version=version)
        return jsonify({"status": "success", "version_filter": version, **data})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/dashboard-analytics", methods=["GET"])
def get_dashboard_analytics():

    try:
        version = request.args.get("version", None)
        data = get_full_analytics(model_version=version)
        response = jsonify({"status": "success", "version_filter": version, **data})

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/analytics/sandbox", methods=["POST"])
def run_sandbox():
    try:
        body = request.get_json(force=True) or {}
        pick_type = body.get("pick_type", "all")
        picks = _load_resolved(pick_type=None if pick_type == "all" else pick_type)
        result = sandbox_simulate(picks)
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/model-lab", methods=["GET"])
def get_model_lab():
    try:
        data = run_model_lab()
        return jsonify({"status": "success", **data})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/model-lab/candidate/<path:candidate_id>", methods=["GET"])
def get_model_lab_candidate(candidate_id):
    try:
        detail = get_candidate_detail(candidate_id)
        if detail is None:
            return jsonify({"status": "error", "message": "candidate not found"}), 404
        return jsonify({"status": "success", "candidate": detail})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/model-lab/compare", methods=["GET"])
def get_model_lab_compare():
    try:
        id_a = request.args.get("a", "")
        id_b = request.args.get("b", "")
        result = compare_candidates(id_a, id_b)
        if result is None:
            return jsonify({"status": "error", "message": "one or both candidates not found"}), 404
        return jsonify({"status": "success", **result})
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/model-control", methods=["GET"])
def model_control_data():
    try:
        response = jsonify({"status": "success", **get_model_control()})
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception as e:
        return _internal_error()


@analytics_bp.route("/model-control.csv", methods=["GET"])
def model_control_csv():

    dataset = request.args.get("dataset", "picks")
    data = get_model_control()
    allowed = {
"picks",
"bankroll",
"errors",
"alerts",
"audit",
"market_snapshots",
"market_movements",
"api_calls",
"walk_forward",
"by_month",
    }
    if dataset not in allowed:
        return jsonify({"status": "error", "message": f"Unknown dataset: {dataset}"}), 400
    rows = data.get(dataset, [])
    output = io.StringIO()
    if rows:

        normalized = []
        for row in rows:
            normalized.append(
                {
                    k: (json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v)
                    for k, v in row.items()
                }
            )
        writer = csv.DictWriter(
            output, fieldnames=list(normalized[0].keys()), extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(normalized)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
"Content-Disposition": f'attachment; filename="jingleez_{dataset}.csv"',
"Cache-Control": "no-store",
        },
    )


@analytics_bp.route("/model-control/learning-cycle", methods=["POST"])
def model_learning_cycle():

    try:
        return jsonify({"status": "success", **run_learning_cycle()})
    except Exception as e:
        return _internal_error()
