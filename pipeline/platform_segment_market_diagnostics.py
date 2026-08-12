"""Chronological segment and market-disagreement diagnostics for platform champions."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.train_platform_models import NON_FEATURES


SOURCE = Path("data/platform/historical_features.csv")
ACCEPTED = Path("data/platform/historical_features_existing_data_v2.csv")
MANIFEST = Path("reports/data_platform/existing_data_discovery/accepted_feature_manifest.json")
OUT = Path("reports/data_platform/segment_market_diagnostics")


def folds(n):
    return [(np.arange(int(n * start)), np.arange(int(n * start), int(n * (start + .1))))
            for start in (.5, .6, .7, .8)]


def metric_row(frame):
    y = frame["target"].to_numpy(dtype=int)
    p = frame["model_probability"].clip(.001, .999).to_numpy()
    market = frame["market_probability"].clip(.001, .999).to_numpy()
    result = {
        "n": len(frame),
        "event_rate": float(y.mean()),
        "model_mean_probability": float(p.mean()),
        "market_mean_probability": float(market.mean()),
        "model_log_loss": float(log_loss(y, p)),
        "market_log_loss": float(log_loss(y, market)),
        "model_log_loss_advantage": float(log_loss(y, market) - log_loss(y, p)),
        "model_brier": float(brier_score_loss(y, p)),
        "market_brier": float(brier_score_loss(y, market)),
        "model_auc": float(roc_auc_score(y, p)) if len(np.unique(y)) == 2 else None,
        "calibration_error_signed": float((p - y).mean()),
    }
    if "fold" in frame:
        fold_advantages = []
        for _, fold in frame.groupby("fold"):
            if len(fold) < 25:
                continue
            fold_y = fold["target"].to_numpy(dtype=int)
            fold_model = fold["model_probability"].clip(.001, .999)
            fold_market = fold["market_probability"].clip(.001, .999)
            fold_advantages.append(float(log_loss(fold_y, fold_market) - log_loss(fold_y, fold_model)))
        result["fold_log_loss_advantages"] = fold_advantages
        result["folds_model_better"] = sum(value > 0 for value in fold_advantages)
        result["folds_evaluated"] = len(fold_advantages)
    return result


def grouped(frame, column, minimum=100):
    rows = []
    for value, group in frame.groupby(column, dropna=False, observed=True):
        if len(group) < minimum:
            continue
        rows.append({"segment": column, "value": str(value), **metric_row(group)})
    return rows


def predictions(df, base_columns, extra_columns, target, market_column):
    work = df[df[target].notna()].sort_values(["game_date", "canonical_game_id"]).reset_index(drop=True)
    if target == "over":
        work = work[~work["push"].astype("boolean").fillna(False)].reset_index(drop=True)
    columns = base_columns + (["closing_total"] if target == "over" else []) + extra_columns
    X = work[columns].replace([np.inf, -np.inf], np.nan)
    y = work[target].astype(int).to_numpy()
    parts = []
    for fold_number, (train, test) in enumerate(folds(len(work)), 1):
        imputer = SimpleImputer(strategy="median")
        x_train = imputer.fit_transform(X.iloc[train])
        x_test = imputer.transform(X.iloc[test])
        model = ExtraTreesClassifier(
            random_state=42, n_estimators=180, max_depth=8, n_jobs=-1
        ).fit(x_train, y[train])
        part = work.iloc[test][[
            "canonical_game_id", "game_date", "home_team", "away_team", "closing_total",
            "market_home_probability", "market_over_probability", "home_win", "over",
        ]].copy()
        part["fold"] = fold_number
        part["target"] = y[test]
        part["model_probability"] = model.predict_proba(x_test)[:, 1]
        part["market_probability"] = part[market_column]
        part["market_disagreement"] = part["model_probability"] - part["market_probability"]
        part["abs_market_disagreement"] = part["market_disagreement"].abs()
        total_cut = float(work.iloc[train]["closing_total"].median())
        part["total_level"] = np.where(part["closing_total"] >= total_cut, "high_total", "low_total")
        parts.append(part)
    result = pd.concat(parts, ignore_index=True)
    result["month"] = pd.to_datetime(result["game_date"]).dt.month
    result["moneyline_role"] = np.where(
        result["market_home_probability"] >= .5, "home_favorite_road_underdog", "road_favorite_home_underdog"
    )
    result["disagreement_direction"] = np.select(
        [result["market_disagreement"] >= .03, result["market_disagreement"] <= -.03],
        ["model_higher_by_3pp", "market_higher_by_3pp"], default="within_3pp"
    )
    result["disagreement_size"] = pd.qcut(
        result["abs_market_disagreement"], 4,
        labels=["smallest", "small", "large", "largest"], duplicates="drop"
    )
    return result


def main():
    source = pd.read_csv(SOURCE, low_memory=False)
    accepted = pd.read_csv(ACCEPTED, low_memory=False)
    manifest = json.loads(MANIFEST.read_text())
    base_columns = [c for c in source.select_dtypes(include=[np.number, "bool"]).columns if c not in NON_FEATURES]
    unavailable = {
        "day_vs_night": "scheduled_start_utc is absent for all 2012-2021 canonical games",
        "dome_vs_outdoor": "venue metadata covers only 404 games and has no roof classification",
        "starter_handedness": "not present in the 2012-2021 platform feature table",
        "division_games": "league/division membership is not stored",
        "interleague_games": "league membership is not stored",
        "clv": "the Vegas source contains closing observations only, not timestamped entry and close pairs",
    }
    report = {"method": "Extra Trees champion; four expanding chronological folds", "unavailable": unavailable, "targets": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    for target, market_column in (("home_win", "market_home_probability"), ("over", "market_over_probability")):
        pred = predictions(accepted, base_columns, manifest["features_by_target"][target], target, market_column)
        pred.to_csv(OUT / f"{target}_walk_forward_predictions.csv", index=False)
        segment_rows = []
        for column in ("moneyline_role", "total_level", "month", "disagreement_direction", "disagreement_size"):
            segment_rows.extend(grouped(pred, column))
        pd.DataFrame(segment_rows).to_csv(OUT / f"{target}_segments.csv", index=False)
        largest = pred.nlargest(250, "abs_market_disagreement")
        report["targets"][target] = {
            "overall": metric_row(pred),
            "segments": segment_rows,
            "largest_disagreement": metric_row(largest),
            "largest_disagreement_threshold": float(largest["abs_market_disagreement"].min()),
            "favorite_misses": int(((pred.market_home_probability >= .6) & (pred.home_win == 0)).sum()),
            "underdog_wins": int(((pred.market_home_probability <= .4) & (pred.home_win == 1)).sum()),
        }
    (OUT / "diagnostics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({target: data["overall"] for target, data in report["targets"].items()}, indent=2))


if __name__ == "__main__":
    main()
