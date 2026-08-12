import pytest

from web.routes.game_routes import _postgame_analysis


def test_postgame_analysis_grades_locked_context():
    game = {
"game_state": "Final",
"away_score": 5,
"home_score": 4,
"away": "Toronto Blue Jays",
"home": "Houston Astros",
    }
    picks = [
        {
"pick_type": "moneyline",
"pick": "Houston Astros",
"status": "lost",
"model_prob": 0.645,
"ev": -4.5,
"clv": None,
"feature_snapshot": "{}",
        },
        {
"pick_type": "totals",
"pick": "OVER 8.0",
"status": "won",
"model_prob": 0.565,
"ev": 7.8,
"clv": 1.2,
"feature_snapshot": '{"expected_total": 8.72}',
        },
    ]
    result = _postgame_analysis(game, picks)
    assert result["actual_total"] == 9
    assert result["winner"] == "Toronto Blue Jays"
    assert result["picks"][1]["projection_error"] == pytest.approx(0.28)


def test_postgame_analysis_is_absent_before_final():
    assert _postgame_analysis({"game_state": "Live"}, []) is None
