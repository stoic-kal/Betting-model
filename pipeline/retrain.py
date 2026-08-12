import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import dataset_append, feature_store, promotion_report, train_moneyline, train_totals

DATASET_PATH = "data/games_v2_features_final.csv"


def update_dataset():
    result = dataset_append.append_new_games()
    print(f"dataset update: appended={result['appended']} rejected={result['rejected']} dataset_version={result['dataset_version']}")
    return result


def validate_dataset():
    df = feature_store.load_dataset(DATASET_PATH)
    for target in ("moneyline", "totals"):
        X, degraded = feature_store.build_training_frame(df, target)
        avg_degraded = float(degraded.mean())
        print(f"dataset validation [{target}]: {len(X)} rows, avg degraded features/row={avg_degraded:.3f}")
    return df


def main():
    print("STEP 1/5: updating dataset")
    update_dataset()
    print("\nSTEP 2/5: validating dataset")
    validate_dataset()
    print("\nSTEP 3/5: training moneyline model")
    train_moneyline.main()
    print("\nSTEP 4/5: training totals model")
    train_totals.main()
    print("\nSTEP 5/5: generating promotion report")
    promotion_report.main()


if __name__ == "__main__":
    main()
