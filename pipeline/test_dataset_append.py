import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import dataset_append
from services import schedule_service

TEST_DATASET_PATH = "/tmp/games_v2_features_final.test.csv"
TEST_VERSION_PATH = "/tmp/dataset_version.test.json"
TEST_LOG_PATH = "/tmp/dataset_append_validation_log.test.jsonl"

FAKE_GAME = {
    "home_abbr": "BOS", "away_abbr": "NYY",
    "home_team_id": 111, "away_team_id": 147,
    "home_sp_id": 605483, "away_sp_id": 592789,
    "home_score": 5, "away_score": 3,
    "game_state": "Final",
    "game_date_utc": "2026-08-09T23:10:00Z",
    "home": "Boston Red Sox", "away": "New York Yankees",
    "home_sp_name": "Test Home SP", "away_sp_name": "Test Away SP",
}


def run():
    shutil.copyfile(dataset_append.DATASET_PATH, TEST_DATASET_PATH)
    Path(TEST_VERSION_PATH).unlink(missing_ok=True)
    Path(TEST_LOG_PATH).unlink(missing_ok=True)

    dataset_append.DATASET_PATH = TEST_DATASET_PATH
    dataset_append.DATASET_VERSION_PATH = TEST_VERSION_PATH
    dataset_append.VALIDATION_LOG_PATH = TEST_LOG_PATH

    import pandas as pd
    before = pd.read_csv(TEST_DATASET_PATH)
    before_rows = len(before)

    original_get_today_games = schedule_service.get_today_games

    def fake_get_today_games(date_str=None, include_odds=True):
        if date_str == "2026-08-09":
            return [FAKE_GAME]
        return []

    schedule_service.get_today_games = fake_get_today_games

    try:
        result_1 = dataset_append.append_new_games(end_date=__import__("datetime").date(2026, 8, 9))
        after_first = pd.read_csv(TEST_DATASET_PATH)
        result_2 = dataset_append.append_new_games(end_date=__import__("datetime").date(2026, 8, 9))
        after_second = pd.read_csv(TEST_DATASET_PATH)
    finally:
        schedule_service.get_today_games = original_get_today_games

    print(f"rows before: {before_rows}")
    print(f"first run: {result_1}")
    print(f"rows after first run: {len(after_first)}")
    print(f"second run: {result_2}")
    print(f"rows after second run: {len(after_second)}")

    checks = []
    checks.append(("append-only growth", len(after_first) == before_rows + 1))
    checks.append(("idempotent on rerun", result_2["appended"] == 0 and len(after_second) == len(after_first)))
    original_columns = list(before.columns)
    checks.append(("no row overwrite", after_second.iloc[:before_rows][original_columns].equals(before[original_columns])))

    new_row = after_first.iloc[-1]
    checks.append(("dataset_version stamped", int(new_row["dataset_version"]) == result_1["dataset_version"]))
    checks.append(("feature_schema_version stamped", isinstance(new_row["feature_schema_version"], str) and len(new_row["feature_schema_version"]) > 0))
    checks.append(("feature_pipeline_version stamped", new_row["feature_pipeline_version"] == dataset_append.FEATURE_PIPELINE_VERSION))
    checks.append(("model_generation_version stamped", new_row["model_generation_version"] == dataset_append.MODEL_GENERATION_VERSION))
    checks.append(("creation_timestamp stamped", isinstance(new_row["creation_timestamp"], str) and len(new_row["creation_timestamp"]) > 0))
    checks.append(("home_win derived correctly", int(new_row["home_win"]) == 1))
    checks.append(("total_runs derived correctly", int(new_row["total_runs"]) == 8))

    all_passed = True
    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        all_passed = all_passed and passed

    Path(TEST_DATASET_PATH).unlink(missing_ok=True)
    Path(TEST_VERSION_PATH).unlink(missing_ok=True)
    Path(TEST_LOG_PATH).unlink(missing_ok=True)

    print("ALL CHECKS PASSED" if all_passed else "SOME CHECKS FAILED")
    return all_passed


if __name__ == "__main__":
    run()
