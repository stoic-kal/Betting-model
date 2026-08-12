import tempfile
from pathlib import Path

import pandas as pd
import pytest

from research.historical_replay import data_adapter, isolation
from research.historical_replay.config import ROOT


def _frame(feature_as_of="2020-01-01"):
    return pd.DataFrame([{
        "canonical_game_id":"g1","game_date":"2020-01-01","feature_as_of":feature_as_of,
        "point_in_time_policy":"rolling statistics shifted one completed game",
        "home_team":"A","away_team":"B","home_win":1,"over":0,"push":False,
        "home_runs":5,"away_runs":2,"total_runs":7,"home_runs_5g":.4,
        "market_home_probability":.55,"home_moneyline_price_decimal":1.8,"away_moneyline_price_decimal":2.1,
    }])


def _approved_temp(frame, monkeypatch):
    handle=tempfile.NamedTemporaryFile(suffix=".csv",delete=False); handle.close()
    frame.to_csv(handle.name,index=False); path=Path(handle.name).resolve()
    monkeypatch.setattr(isolation,"ALLOWED_READ_DATASETS",{path})
    return path


def test_future_feature_timestamp_is_rejected(monkeypatch):
    path=_approved_temp(_frame("2020-01-02"),monkeypatch)
    with pytest.raises(ValueError,match="Future feature timestamps"):
        data_adapter.load_dataset(path,"home_win")


def test_labels_and_postgame_columns_never_enter_features(monkeypatch):
    frame=_frame()
    path=_approved_temp(frame,monkeypatch)
    loaded=data_adapter.load_dataset(path,"home_win")
    assert "home_win" not in loaded.features
    assert "home_runs" not in loaded.features
    assert "actual_score_feature" not in loaded.features
    assert "final_weather" not in loaded.features
    assert "home_runs_5g" in loaded.features


def test_explicit_postgame_feature_is_rejected(monkeypatch):
    frame=_frame(); frame["actual_score_feature"]=7
    path=_approved_temp(frame,monkeypatch)
    with pytest.raises(ValueError,match="Postgame/leaking features"):
        data_adapter.load_dataset(path,"home_win")


def test_training_rows_are_strictly_before_replay_date(monkeypatch):
    frame=pd.concat([_frame("2020-01-01"),_frame("2020-01-02"),_frame("2020-01-03")],ignore_index=True)
    frame["canonical_game_id"]=["g1","g2","g3"]; frame["game_date"]=["2020-01-01","2020-01-02","2020-01-03"]
    path=_approved_temp(frame,monkeypatch); loaded=data_adapter.load_dataset(path,"home_win")
    train=data_adapter.training_rows(loaded,"2020-01-03")
    assert set(train.canonical_game_id)=={"g1","g2"}
    assert train.game_date.max()<pd.Timestamp("2020-01-03")


def test_production_write_paths_are_rejected():
    with pytest.raises(ValueError,match="Replay writes"):
        isolation.require_research_output(isolation.PROJECT_ROOT/"database"/"picks.db")
    assert isolation.require_research_output(ROOT/"experiments"/"safe").is_relative_to(ROOT)


def test_unapproved_dataset_is_rejected():
    with pytest.raises(ValueError,match="approved point-in-time"):
        isolation.require_approved_dataset(isolation.PROJECT_ROOT/"database"/"picks.db")


@pytest.mark.parametrize("column",["postgame_lineup_woba","observed_weather_temp","final_wind_mph"])
def test_untimestamped_lineup_and_weather_are_rejected(monkeypatch,column):
    frame=_frame(); frame[column]=1.0; path=_approved_temp(frame,monkeypatch)
    with pytest.raises(ValueError,match="lineup/weather"):
        data_adapter.load_dataset(path,"home_win")


def test_ambiguous_same_day_games_are_excluded(monkeypatch):
    frame=pd.concat([_frame(),_frame()],ignore_index=True)
    frame["canonical_game_id"]=["doubleheader_1","doubleheader_2"]
    path=_approved_temp(frame,monkeypatch); loaded=data_adapter.load_dataset(path,"home_win")
    assert loaded.frame.empty
    assert loaded.exclusions["ambiguous_same_day_games"]==2


def test_unknown_feature_without_provenance_is_rejected(monkeypatch):
    frame=_frame(); frame["mystery_numeric"]=1.0; path=_approved_temp(frame,monkeypatch)
    with pytest.raises(ValueError,match="Feature provenance missing"):
        data_adapter.load_dataset(path,"home_win")
