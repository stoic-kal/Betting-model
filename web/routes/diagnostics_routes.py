import glob
import json
import os
import subprocess
import sys

from flask import Blueprint, Response, jsonify, render_template, send_file

from flask import Blueprint, Response, jsonify, render_template, send_file

from services.diag_metrics_service import compute_diag_metrics, load_history, save_run_snapshot

diagnostics_bp = Blueprint("diagnostics", __name__)

DIAG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "research", "diagnostics", "totals")
FIG_DIR = os.path.join(DIAG_DIR, "figures")
VENV_PY = os.path.join(os.path.dirname(os.path.dirname(__file__)), "venv", "bin", "python")
RUNNER = os.path.join(DIAG_DIR, "run_all.py")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "picks.db")


@diagnostics_bp.route("/diagnostics")
def diagnostics_page():
    return render_template("diagnostics.html")

@diagnostics_bp.route("/api/diagnostics/run")
def run_diagnostics():
    def generate():
        python = VENV_PY if os.path.exists(VENV_PY) else sys.executable
        process = subprocess.Popen(
            [python, RUNNER],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=os.path.dirname(DIAG_DIR),
        )
        section_results = {}
        for line in process.stdout:
            stripped = line.rstrip("\n")
            if stripped.startswith("##DIAG_EVENT##"):
                try:
                    evt = json.loads(stripped[len("##DIAG_EVENT##") :])
                    if evt.get("type") == "result":
                        section_results[evt["section"]] = {
"title": evt.get("title"),
"status": evt.get("status"),
"metrics": evt.get("metrics", {}),
"error": evt.get("error"),
"reason": evt.get("reason"),
"elapsed": evt.get("elapsed"),
                        }
                except Exception:
                    pass
            yield f"data: {json.dumps({'line': stripped})}\n\n"
        process.wait()

        summary_payload = {"section_results": section_results}
        try:
            metrics = compute_diag_metrics()
            save_run_snapshot(metrics, section_results)
            summary_payload["history"] = load_history()
        except Exception as e:
            summary_payload["error"] = str(e)
        yield f"data: {json.dumps({'summary': summary_payload})}\n\n"

        yield f"data: {json.dumps({'done': True, 'code': process.returncode})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@diagnostics_bp.route("/api/diagnostics/history")
def diagnostics_history():
    try:
        return jsonify(load_history())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@diagnostics_bp.route("/api/diagnostics/figures")
def list_figures():
    os.makedirs(FIG_DIR, exist_ok=True)
    figs = sorted(os.path.basename(f) for f in glob.glob(os.path.join(FIG_DIR, "*.png")))
    mtime = (
        max((os.path.getmtime(os.path.join(FIG_DIR, f)) for f in figs), default=0) if figs else 0
    )
    return jsonify({"figures": figs, "last_run": mtime})

@diagnostics_bp.route("/api/diagnostics/figures/<filename>")
def serve_figure(filename):
    path = os.path.join(FIG_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="image/png")

@diagnostics_bp.route("/api/diag/data")
def diag_data():
    try:
        return jsonify(compute_diag_metrics())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
