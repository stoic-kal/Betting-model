import pandas as pd
import pytest

from research.historical_replay.metrics import calibration, classification_metrics, drawdown
from research.historical_replay.engine import _assert_prediction_integrity, _bet_fields
from research.historical_replay.config import ModelSpec, ReplayConfig


def _predictions():
    return pd.DataFrame({"actual":[1,0,1,0],"probability":[.7,.3,.6,.4],"won":[1,1,1,1],
        "flat_profit":[1,1,1,1],"flat_stake":[1,1,1,1],"kelly_profit":[.1,.1,.1,.1],
        "kelly_stake":[.05,.05,.05,.05],"game_date":["2020-01-01","2020-01-01","2020-01-02","2020-01-02"]})


def test_metrics_are_finite_and_complete():
    result=classification_metrics(_predictions())
    assert result["n"]==4 and result["auc"]==1.0 and result["roi"]==1.0
    assert calibration(_predictions(),2)["buckets"]


def test_drawdown_uses_daily_portfolio_path():
    daily,report=drawdown(_predictions())
    assert len(daily)==2 and report["max_flat_drawdown"]==0.0


def test_wager_selects_highest_positive_ev_not_highest_probability():
    config=ReplayConfig(experiment_name="test",min_edge=0.0)
    # Home is more probable, but the away price creates the larger positive EV.
    positive,_,_,selected_ev,stake,_,_,_=_bet_fields(1,.60,1.55,3.00,.60,config)
    assert positive is False
    assert selected_ev==pytest.approx(.20)
    assert stake==1.0


def test_wager_skips_when_both_sides_have_nonpositive_ev():
    config=ReplayConfig(experiment_name="test",min_edge=0.0)
    *_,selected_ev,stake,_,_,_=_bet_fields(1,.50,1.90,1.90,.50,config)
    assert selected_ev<0 and stake==0.0


def test_prediction_integrity_rejects_duplicates_and_missing_coverage():
    specs=(ModelSpec("historical_baseline"),ModelSpec("candidate"))
    duplicate=pd.DataFrame({"model":["historical_baseline","historical_baseline","candidate"],"canonical_game_id":["g1","g1","g1"]})
    with pytest.raises(ValueError,match="Duplicate"):
        _assert_prediction_integrity(duplicate,specs,{"g1"})
    missing=pd.DataFrame({"model":["historical_baseline","candidate"],"canonical_game_id":["g1","g2"]})
    with pytest.raises(ValueError,match="coverage"):
        _assert_prediction_integrity(missing,specs,{"g1","g2"})
