from services.analytics_service import calibration_analysis


def test_headline_ece_uses_actual_probabilities_and_five_bins():
    picks = [
        {"model_prob": 0.61, "status": "won"},
        {"model_prob": 0.63, "status": "won"},
        {"model_prob": 0.64, "status": "lost"},
        {"model_prob": 0.52, "status": "lost"},
    ]
    result = calibration_analysis(picks)
    assert result["ece_bins"] == 5
    assert result["sample_size"] == 4
    assert result["provisional"] is True

    assert result["ece"] == 0.16
