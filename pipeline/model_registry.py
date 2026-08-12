import hashlib
import json
import pickle
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_DIR = Path("models/registry")
EXPERIMENTS_LOG = REGISTRY_DIR / "experiments.jsonl"
DATASET_VERSION_PREFIX_LEN = 12
UNCALIBRATED = "uncalibrated"


def calibration_method(model_object):
    if isinstance(model_object, dict):
        model_object = model_object.get("model")
    return getattr(model_object, "method", None) or UNCALIBRATED


def get_git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def hash_dataset(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def new_version():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _model_dir(model_name, version):
    return REGISTRY_DIR / model_name / version


def register_model(model_name, version, model_object, feature_schema_version, feature_list,
                    dataset_path, metrics, calibration_metrics, hyperparameters, extra=None):
    model_dir = _model_dir(model_name, version)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model_object, f)
    metadata = {
        "model_name": model_name,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema_version": feature_schema_version,
        "feature_list": feature_list,
        "dataset_path": dataset_path,
        "dataset_hash": hash_dataset(dataset_path),
        "metrics": metrics,
        "calibration_metrics": calibration_metrics,
        "hyperparameters": hyperparameters,
        "calibration_method": calibration_method(model_object),
        "git_commit": get_git_commit(),
        "model_path": str(model_path),
    }
    if extra:
        metadata["extra"] = extra
    meta_path = model_dir / "metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    latest_path = REGISTRY_DIR / model_name / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    _append_experiment(metadata)
    return metadata


def _append_experiment(metadata):
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "model_name": metadata["model_name"],
        "version": metadata["version"],
        "trained_at": metadata["trained_at"],
        "dataset_hash": metadata["dataset_hash"],
        "feature_schema_version": metadata["feature_schema_version"],
        "hyperparameters": metadata["hyperparameters"],
        "metrics": metadata["metrics"],
        "calibration_metrics": metadata["calibration_metrics"],
        "git_commit": metadata["git_commit"],
    }
    with open(EXPERIMENTS_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def model_identity(metadata, model_object=None):
    extra = metadata.get("extra") or {}
    method = metadata.get("calibration_method")
    if method is None and model_object is not None:
        method = calibration_method(model_object)
    return {
        "model_name": metadata.get("model_name"),
        "model_version": metadata.get("version"),
        "model_family": extra.get("model_family"),
        "feature_schema_version": metadata.get("feature_schema_version"),
        "dataset_version": (metadata.get("dataset_hash") or "")[:DATASET_VERSION_PREFIX_LEN],
        "calibration_version": method,
        "prediction_pipeline_version": get_git_commit(),
    }


def list_versions(model_name):
    model_root = REGISTRY_DIR / model_name
    if not model_root.exists():
        return []
    return sorted(p.name for p in model_root.iterdir() if p.is_dir())


def load_metadata(model_name, version):
    meta_path = _model_dir(model_name, version) / "metadata.json"
    with open(meta_path) as f:
        return json.load(f)


def current_dataset_hash(model_name):
    latest = load_latest_metadata(model_name)
    return latest.get("dataset_hash") if latest else None


def get_best_version(model_name, metric="log_loss", lower_is_better=True, exclude=(), dataset_hash=None):
    comparable_hash = dataset_hash or current_dataset_hash(model_name)
    best_version = None
    best_value = None
    for version in list_versions(model_name):
        if version in exclude:
            continue
        meta = load_metadata(model_name, version)
        if comparable_hash is not None and meta.get("dataset_hash") != comparable_hash:
            continue
        value = (meta.get("metrics") or {}).get(metric)
        if value is None:
            continue
        if best_value is None or (value < best_value if lower_is_better else value > best_value):
            best_value = value
            best_version = version
    return best_version


def get_champion_version(model_name, metric="log_loss", lower_is_better=True):
    return get_best_version(model_name, metric=metric, lower_is_better=lower_is_better)


def get_challenger_version(model_name, metric="log_loss", lower_is_better=True, champion_version=None):
    champion = champion_version or get_champion_version(model_name, metric=metric, lower_is_better=lower_is_better)
    if champion is None:
        return None
    return get_best_version(model_name, metric=metric, lower_is_better=lower_is_better, exclude=(champion,))


def load_champion_metadata(model_name, metric="log_loss", lower_is_better=True):
    version = get_champion_version(model_name, metric=metric, lower_is_better=lower_is_better)
    if version is None:
        return None
    return load_metadata(model_name, version)


def load_champion_model(model_name, metric="log_loss", lower_is_better=True):
    metadata = load_champion_metadata(model_name, metric=metric, lower_is_better=lower_is_better)
    if metadata is None:
        return None, None
    return load_model(model_name, metadata["version"]), metadata


def load_latest_metadata(model_name):
    latest_path = REGISTRY_DIR / model_name / "latest.json"
    if not latest_path.exists():
        return None
    with open(latest_path) as f:
        return json.load(f)


def load_model(model_name, version):
    model_path = _model_dir(model_name, version) / "model.pkl"
    with open(model_path, "rb") as f:
        return pickle.load(f)


def load_latest_model(model_name):
    metadata = load_latest_metadata(model_name)
    if metadata is None:
        return None, None
    return load_model(model_name, metadata["version"]), metadata


def list_experiments():
    if not EXPERIMENTS_LOG.exists():
        return []
    records = []
    with open(EXPERIMENTS_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
