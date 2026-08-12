import hashlib
import importlib
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from pipeline import model_manager

DEV_MODE_ENV_VAR = "DEV_MODE"
DEV_MODE_ENABLED_VALUE = "1"
POLL_INTERVAL_SECONDS = 1.0
DEBOUNCE_SECONDS = 0.4
EVENT_HISTORY_MAX_ENTRIES = 200

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "models" / "registry"
REPORTS_PATH = REPO_ROOT / "reports"
CONFIG_PATH = REPO_ROOT / "config.py"
DOTENV_PATH = REPO_ROOT / ".env"

WATCH_GROUPS = {
    "models": (REGISTRY_PATH,),
    "diagnostics": (REPORTS_PATH,),
    "config": (CONFIG_PATH, DOTENV_PATH),
}

PROCESS_START_MONOTONIC = time.monotonic()
PROCESS_START_WALL = datetime.now(timezone.utc).isoformat()

_DEV_MODE = os.environ.get(DEV_MODE_ENV_VAR) == DEV_MODE_ENABLED_VALUE
_app = None
_watcher = None
_config_snapshot = None
_event_history = deque(maxlen=EVENT_HISTORY_MAX_ENTRIES)
_config_lock = threading.RLock()


def is_dev_mode():
    return _DEV_MODE


def uptime_seconds():
    return round(time.monotonic() - PROCESS_START_MONOTONIC, 3)


def process_start_time():
    return PROCESS_START_WALL


def _record_event(subsystem, action, detail, success):
    entry = {
        "subsystem": subsystem,
        "action": action,
        "detail": detail,
        "success": success,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    _event_history.append(entry)
    print(f"[dev_mode] {subsystem} {action} success={success} {detail}")
    return entry


def event_history():
    return list(_event_history)


def _public_config_values(module):
    values = {}
    for key in dir(module):
        if key.startswith("_") or not key.isupper():
            continue
        values[key] = getattr(module, key)
    return values


def config_hash():
    import config

    values = _public_config_values(config)
    payload = json.dumps({k: repr(v) for k, v in sorted(values.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def reload_config(reason="manual"):
    import config

    started = time.perf_counter()
    with _config_lock:
        before = _public_config_values(config)
        try:
            source = CONFIG_PATH.read_text()
            compile(source, str(CONFIG_PATH), "exec")
            probe = {"__name__": "config_probe", "__file__": str(CONFIG_PATH)}
            exec(compile(source, str(CONFIG_PATH), "exec"), probe)
        except Exception as exc:
            detail = {"error": repr(exc), "rolled_back": True, "changed": {}}
            _record_event("config", reason, detail, False)
            return {
                "subsystem": "config",
                "success": False,
                "error": repr(exc),
                "changed": {},
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        try:
            if DOTENV_PATH.exists():
                from dotenv import load_dotenv

                load_dotenv(DOTENV_PATH, override=True)
            importlib.reload(config)
        except Exception as exc:
            for key, value in before.items():
                setattr(config, key, value)
            detail = {"error": repr(exc), "rolled_back": True, "changed": {}}
            _record_event("config", reason, detail, False)
            return {
                "subsystem": "config",
                "success": False,
                "error": repr(exc),
                "changed": {},
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        after = _public_config_values(config)
        changed = {}
        for key in sorted(set(before) | set(after)):
            old = before.get(key)
            new = after.get(key)
            if repr(old) == repr(new):
                if isinstance(old, (dict, list)):
                    setattr(config, key, old)
                continue
            changed[key] = {"old": repr(old), "new": repr(new)}
            if isinstance(old, dict) and isinstance(new, dict):
                old.clear()
                old.update(new)
                setattr(config, key, old)
            elif isinstance(old, list) and isinstance(new, list):
                old[:] = new
                setattr(config, key, old)
    duration = round((time.perf_counter() - started) * 1000, 3)
    _record_event("config", reason, {"changed": changed, "duration_ms": duration}, True)
    return {
        "subsystem": "config",
        "success": True,
        "error": None,
        "changed": changed,
        "duration_ms": duration,
    }


def reload_models(reason="manual"):
    started = time.perf_counter()
    results = model_manager.reload_if_needed(reason=reason)
    duration = round((time.perf_counter() - started) * 1000, 3)
    success = all(r["success"] for r in results)
    _record_event("models", reason, {"results": results, "duration_ms": duration}, success)
    return {
        "subsystem": "models",
        "success": success,
        "error": next((r["error"] for r in results if r["error"]), None),
        "changed": {r["model_name"]: r for r in results},
        "duration_ms": duration,
    }


def newest_report_timestamp():
    newest = None
    for path in (REPORTS_PATH,):
        if not path.exists():
            continue
        for child in path.rglob("*"):
            if child.is_file():
                mtime = child.stat().st_mtime
                if newest is None or mtime > newest:
                    newest = mtime
    return datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else None


def reload_diagnostics(reason="manual"):
    started = time.perf_counter()
    newest = newest_report_timestamp()
    duration = round((time.perf_counter() - started) * 1000, 3)
    detail = {"newest_report": newest, "cache_invalidated": False, "duration_ms": duration}
    _record_event("diagnostics", reason, detail, True)
    return {
        "subsystem": "diagnostics",
        "success": True,
        "error": None,
        "changed": detail,
        "duration_ms": duration,
    }


def reload_registry(reason="manual"):
    started = time.perf_counter()
    names = sorted(p.name for p in REGISTRY_PATH.iterdir() if p.is_dir()) if REGISTRY_PATH.exists() else []
    duration = round((time.perf_counter() - started) * 1000, 3)
    detail = {"registry_models": names, "cache_invalidated": False, "duration_ms": duration}
    _record_event("registry", reason, detail, True)
    return {
        "subsystem": "registry",
        "success": True,
        "error": None,
        "changed": detail,
        "duration_ms": duration,
    }


def reload_templates(reason="manual"):
    started = time.perf_counter()
    cleared = False
    if _app is not None:
        cache = getattr(_app.jinja_env, "cache", None)
        if cache is not None:
            cache.clear()
            cleared = True
    duration = round((time.perf_counter() - started) * 1000, 3)
    detail = {"jinja_cache_cleared": cleared, "duration_ms": duration}
    _record_event("templates", reason, detail, True)
    return {
        "subsystem": "templates",
        "success": True,
        "error": None,
        "changed": detail,
        "duration_ms": duration,
    }


RELOADERS = {
    "models": reload_models,
    "config": reload_config,
    "diagnostics": reload_diagnostics,
    "registry": reload_registry,
    "templates": reload_templates,
}


def reload_subsystems(targets, reason="manual"):
    names = list(RELOADERS) if "everything" in targets else [t for t in targets if t in RELOADERS]
    return [RELOADERS[name](reason) for name in names]


class FilesystemWatcher:

    def __init__(self, groups, poll_interval=POLL_INTERVAL_SECONDS, debounce=DEBOUNCE_SECONDS):
        self._groups = groups
        self._poll_interval = poll_interval
        self._debounce = debounce
        self._signatures = {}
        self._pending = {}
        self._stop = threading.Event()
        self._thread = None
        self.scan_count = 0

    def _signature(self, paths):
        parts = []
        for path in paths:
            if not path.exists():
                continue
            if path.is_file():
                parts.append((str(path), path.stat().st_mtime_ns))
                continue
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    try:
                        parts.append((str(child), child.stat().st_mtime_ns))
                    except OSError:
                        continue
        return hash(tuple(parts))

    def _handle(self, group):
        if group == "models":
            reload_models("watcher")
            reload_registry("watcher")
        elif group == "config":
            reload_config("watcher")
        elif group == "diagnostics":
            reload_diagnostics("watcher")

    def _tick(self):
        now = time.monotonic()
        for group, paths in self._groups.items():
            signature = self._signature(paths)
            if group not in self._signatures:
                self._signatures[group] = signature
                continue
            if signature != self._signatures[group]:
                self._signatures[group] = signature
                self._pending[group] = now
        for group, changed_at in list(self._pending.items()):
            if now - changed_at >= self._debounce:
                del self._pending[group]
                try:
                    self._handle(group)
                except Exception as exc:
                    _record_event(group, "watcher", {"error": repr(exc)}, False)
        self.scan_count += 1

    def _run(self):
        while not self._stop.wait(self._poll_interval):
            try:
                self._tick()
            except Exception as exc:
                _record_event("watcher", "tick", {"error": repr(exc)}, False)

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        for group, paths in self._groups.items():
            self._signatures[group] = self._signature(paths)
        self._thread = threading.Thread(target=self._run, name="jingleez-dev-watcher", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()


def get_watcher():
    return _watcher


def watcher_status():
    return {
        "running": _watcher is not None and _watcher.is_alive(),
        "backend": "polling",
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "debounce_seconds": DEBOUNCE_SECONDS,
        "watched_groups": {k: [str(p) for p in v] for k, v in WATCH_GROUPS.items()},
        "scan_count": _watcher.scan_count if _watcher is not None else 0,
    }


def init_app(app):
    global _app, _watcher
    _app = app
    if not _DEV_MODE:
        return None
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.jinja_env.auto_reload = True
    if _watcher is None:
        _watcher = FilesystemWatcher(WATCH_GROUPS)
        _watcher.start()
    return _watcher
