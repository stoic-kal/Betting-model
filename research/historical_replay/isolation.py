from pathlib import Path

from .config import PROJECT_ROOT, ROOT


FORBIDDEN_WRITE_ROOTS = tuple((PROJECT_ROOT / p).resolve() for p in (
    "database", "models", "reports", "data", "analytics", "services", "routes", "pipeline"
))
ALLOWED_READ_DATASETS = {
    (PROJECT_ROOT / "data/platform/historical_features.csv").resolve(),
    (PROJECT_ROOT / "data/platform/historical_features_existing_data_v2.csv").resolve(),
}


def require_research_output(path):
    resolved = Path(path).resolve()
    if resolved != ROOT.resolve() and ROOT.resolve() not in resolved.parents:
        raise ValueError(f"Replay writes must remain under {ROOT}; got {resolved}")
    if any(root == resolved or root in resolved.parents for root in FORBIDDEN_WRITE_ROOTS):
        raise ValueError(f"Forbidden production write path: {resolved}")
    return resolved


def require_approved_dataset(path):
    resolved = Path(path).resolve()
    if resolved not in ALLOWED_READ_DATASETS:
        raise ValueError(f"Replay may only read approved point-in-time datasets; got {resolved}")
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    return resolved

