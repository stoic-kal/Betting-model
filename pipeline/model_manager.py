import threading
import time
from collections import deque
from datetime import datetime, timezone

from pipeline import model_registry

HISTORY_MAX_ENTRIES = 200
MONEYLINE_MODEL = "moneyline"
TOTALS_MODEL = "totals"
SERVED_MODEL_NAMES = (MONEYLINE_MODEL, TOTALS_MODEL)


class LoadedModel:

    __slots__ = ("model", "metadata", "version", "features", "identity", "loaded_at")

    def __init__(self, model, metadata):
        raw = model
        if isinstance(raw, dict):
            raw = raw["model"]
        self.model = raw
        self.metadata = metadata
        self.version = metadata.get("version")
        self.features = list(metadata.get("feature_list") or [])
        self.identity = model_registry.model_identity(metadata, raw)
        self.loaded_at = datetime.now(timezone.utc).isoformat()


class ModelManager:

    def __init__(self):
        self._lock = threading.RLock()
        self._active = {}
        self._previous = {}
        self._history = deque(maxlen=HISTORY_MAX_ENTRIES)
        self._reload_count = 0

    def _record(self, model_name, old_version, new_version, started, reason, success, error):
        entry = {
            "model_name": model_name,
            "old_version": old_version,
            "new_version": new_version,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "reason": reason,
            "success": success,
            "error": error,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(entry)
        print(
            f"[model_manager] {model_name} reload success={success} "
            f"{old_version} -> {new_version} in {entry['duration_ms']}ms reason={reason}"
            + (f" error={error}" if error else "")
        )
        return entry

    def _load_version(self, model_name, version):
        metadata = model_registry.load_metadata(model_name, version)
        return LoadedModel(model_registry.load_model(model_name, version), metadata)

    def _swap(self, model_name, loaded):
        previous = self._active.get(model_name)
        if previous is not None:
            self._previous[model_name] = previous
        self._active[model_name] = loaded
        self._reload_count += 1

    def _ensure_loaded(self, model_name, reason):
        active = self._active.get(model_name)
        if active is not None:
            return active
        with self._lock:
            active = self._active.get(model_name)
            if active is not None:
                return active
            started = time.perf_counter()
            try:
                version = model_registry.get_champion_version(model_name)
                if version is None:
                    raise FileNotFoundError(f"no registry champion for {model_name}")
                loaded = self._load_version(model_name, version)
            except Exception as exc:
                self._record(model_name, None, None, started, reason, False, repr(exc))
                return None
            self._swap(model_name, loaded)
            self._record(model_name, None, loaded.version, started, reason, True, None)
            return self._active.get(model_name)

    def get(self, model_name, reason="initial_load"):
        return self._ensure_loaded(model_name, reason)

    def get_moneyline_model(self, reason="initial_load"):
        return self._ensure_loaded(MONEYLINE_MODEL, reason)

    def get_totals_model(self, reason="initial_load"):
        return self._ensure_loaded(TOTALS_MODEL, reason)

    def reload_if_needed(self, model_name=None, reason="manual"):
        names = (model_name,) if model_name else SERVED_MODEL_NAMES
        results = []
        for name in names:
            results.append(self._reload_one(name, reason))
        return results

    def _reload_one(self, model_name, reason):
        with self._lock:
            active = self._active.get(model_name)
            old_version = active.version if active is not None else None
            started = time.perf_counter()
            try:
                version = model_registry.get_champion_version(model_name)
                if version is None:
                    raise FileNotFoundError(f"no registry champion for {model_name}")
                if version == old_version:
                    return {
                        "model_name": model_name,
                        "changed": False,
                        "version": old_version,
                        "success": True,
                        "error": None,
                    }
                loaded = self._load_version(model_name, version)
            except Exception as exc:
                entry = self._record(model_name, old_version, None, started, reason, False, repr(exc))
                return {
                    "model_name": model_name,
                    "changed": False,
                    "version": old_version,
                    "success": False,
                    "error": entry["error"],
                }
            self._swap(model_name, loaded)
            entry = self._record(model_name, old_version, loaded.version, started, reason, True, None)
            return {
                "model_name": model_name,
                "changed": True,
                "version": loaded.version,
                "success": True,
                "error": None,
                "duration_ms": entry["duration_ms"],
            }

    def rollback(self, model_name, reason="rollback"):
        with self._lock:
            previous = self._previous.get(model_name)
            active = self._active.get(model_name)
            started = time.perf_counter()
            if previous is None:
                self._record(
                    model_name,
                    active.version if active else None,
                    None,
                    started,
                    reason,
                    False,
                    "no previous version retained",
                )
                return False
            self._active[model_name] = previous
            self._previous[model_name] = active
            self._reload_count += 1
            self._record(
                model_name,
                active.version if active else None,
                previous.version,
                started,
                reason,
                True,
                None,
            )
            return True

    def metadata(self, model_name):
        active = self._active.get(model_name)
        return active.metadata if active is not None else None

    def status(self):
        with self._lock:
            models = {}
            for name in SERVED_MODEL_NAMES:
                active = self._active.get(name)
                previous = self._previous.get(name)
                models[name] = {
                    "loaded": active is not None,
                    "version": active.version if active else None,
                    "loaded_at": active.loaded_at if active else None,
                    "previous_version": previous.version if previous else None,
                    "feature_count": len(active.features) if active else 0,
                    "identity": active.identity if active else None,
                }
            history = list(self._history)
        last = history[-1] if history else None
        return {
            "models": models,
            "reload_count": self._reload_count,
            "last_reload": last,
            "history": history,
        }


_manager = ModelManager()


def get_manager():
    return _manager


def get_moneyline_model(reason="initial_load"):
    return _manager.get_moneyline_model(reason)


def get_totals_model(reason="initial_load"):
    return _manager.get_totals_model(reason)


def reload_if_needed(model_name=None, reason="manual"):
    return _manager.reload_if_needed(model_name=model_name, reason=reason)
