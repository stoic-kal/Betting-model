from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "data/platform/historical_features.csv"


@dataclass(frozen=True)
class ModelSpec:
    name: str
    family: str = "extra_trees"
    parameters: Dict = field(default_factory=dict)
    calibration: Optional[str] = None


@dataclass(frozen=True)
class ReplayConfig:
    experiment_name: str
    target: str = "home_win"
    start_date: str = "2019-01-01"
    end_date: str = "2021-12-31"
    min_training_rows: int = 2000
    training_window_days: Optional[int] = None
    seed: int = 42
    probability_bins: int = 10
    flat_stake_units: float = 1.0
    max_kelly_fraction: float = 0.05
    kelly_multiplier: float = 0.25
    min_edge: float = 0.0
    dataset_path: str = str(DEFAULT_DATASET)
    historical_baseline: ModelSpec = field(default_factory=lambda: ModelSpec(
        name="historical_baseline", family="extra_trees",
        parameters={"n_estimators": 120, "max_depth": 8, "min_samples_leaf": 5},
    ))
    candidate: ModelSpec = field(default_factory=lambda: ModelSpec(
        name="candidate", family="logistic_regression", parameters={"C": 1.0},
    ))
    include_features: List[str] = field(default_factory=list)
    exclude_features: List[str] = field(default_factory=list)
    feature_transforms: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
