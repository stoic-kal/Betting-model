import resource
import sys
import time

from flask import Blueprint, jsonify, request

from pipeline import feature_store, model_manager
from services import dev_mode

system_bp = Blueprint("system", __name__, url_prefix="/api/system")

MACOS_RUSAGE_IS_BYTES = sys.platform == "darwin"
RELOAD_TARGETS = tuple(dev_mode.RELOADERS) + ("everything",)


def _memory_mb():
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if MACOS_RUSAGE_IS_BYTES else 1024
    return round(max_rss / divisor, 2)


@system_bp.route("/status")
def system_status():
    manager_status = model_manager.get_manager().status()
    return jsonify(
        {
            "dev_mode": dev_mode.is_dev_mode(),
            "watcher": dev_mode.watcher_status(),
            "models": manager_status["models"],
            "reload_count": manager_status["reload_count"],
            "last_reload": manager_status["last_reload"],
            "reload_history": manager_status["history"],
            "event_history": dev_mode.event_history(),
            "config_hash": dev_mode.config_hash(),
            "diagnostics_newest_report": dev_mode.newest_report_timestamp(),
            "registry_models": sorted(
                p.name for p in dev_mode.REGISTRY_PATH.iterdir() if p.is_dir()
            )
            if dev_mode.REGISTRY_PATH.exists()
            else [],
            "feature_schema_version": feature_store.get_schema_version(),
            "memory_max_rss_mb": _memory_mb(),
            "uptime_seconds": dev_mode.uptime_seconds(),
            "started_at": dev_mode.process_start_time(),
        }
    )


@system_bp.route("/reload", methods=["POST"])
def system_reload():
    if not dev_mode.is_dev_mode():
        return jsonify({"error": "reload endpoint requires DEV_MODE=1"}), 403
    body = request.get_json(silent=True) or {}
    raw = body.get("targets") or body.get("target") or "everything"
    targets = [raw] if isinstance(raw, str) else list(raw)
    unknown = [t for t in targets if t not in RELOAD_TARGETS]
    if unknown:
        return jsonify({"error": f"unknown reload targets: {unknown}", "allowed": list(RELOAD_TARGETS)}), 400
    started = time.perf_counter()
    results = dev_mode.reload_subsystems(targets, reason="api")
    return jsonify(
        {
            "requested": targets,
            "results": results,
            "success": all(r["success"] for r in results),
            "errors": [r["error"] for r in results if r["error"]],
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    )
