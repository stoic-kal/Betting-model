import unittest

from research.analytics.pick_analyzer import (
    _build_calibration_corrections,
    _calibration_curve,
    _ev_threshold_analysis,
    _generate_recommendations,
    apply_calibration_correction,
)


class PickAnalyzerDynamicTests(unittest.TestCase):
    def test_calibration_uses_bucket_mean_not_fixed_midpoint(self):
        picks = [
            {"model_prob": probability, "status": "won" if index % 2 else "lost"}
            for index, probability in enumerate([.501, .502, .503, .701, .702, .703, .704, .705, .706])
        ]
        curve = _calibration_curve(picks)
        flattened = sorted(float(p["model_prob"]) for p in picks)
        for index, bucket in enumerate(curve):
            start = index * len(flattened) // len(curve)
            end = (index + 1) * len(flattened) // len(curve)
            expected = round(sum(flattened[start:end]) / len(flattened[start:end]) * 100, 1)
            self.assertEqual(bucket["predicted"], expected)

    def test_ev_thresholds_are_sample_quantiles(self):
        picks = [
            {"ev": value, "status": "won" if value % 2 else "lost", "odds": 2.0}
            for value in range(1, 21)
        ]
        thresholds = [row["min_ev"] for row in _ev_threshold_analysis(picks)]
        self.assertEqual(thresholds, [1.0, 5.0, 10.0, 15.0, 18.0])

    def test_recommendations_do_not_select_ev_floor_or_fixed_calibration_bucket(self):
        stats = {"n":50,"win_rate":55.0,"roi":4.0,"profit":40.0,"roi_ci_low":-5.0,
                 "roi_ci_high":13.0,"roi_se":4.5}
        recommendations = _generate_recommendations(
            stats, stats,
            [{"prob_range":"0.70-0.75","predicted":72.5,"actual":40.0,"n":20}],
            [{"min_ev":25,"n":20,"win_rate":70.0,"profit":100.0,"roi":25.0}],
            .55,
        )
        titles = " ".join(row["title"] for row in recommendations)
        self.assertNotIn("EV floor", titles)
        self.assertNotIn("overconfident at", titles)

    def test_analytics_never_changes_production_probability(self):
        self.assertEqual(_build_calibration_corrections([]), {})
        self.assertEqual(apply_calibration_correction(.83), .83)


if __name__ == "__main__":
    unittest.main()
