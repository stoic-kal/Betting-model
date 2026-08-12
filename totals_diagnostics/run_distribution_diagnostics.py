import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import poisson


REPORT_DIR = Path(__file__).resolve().parent.parent / "reports" / "diagnostics"


def _wilson(wins, n, z=1.959963984540054):
    if not n:
        return (None, None)
    p = wins / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0, center - radius), min(1, center + radius)


def build_run_distribution_report(frame):
    data = frame.copy()
    data["expected"] = pd.to_numeric(data.get("snap_expected_total"), errors="coerce")
    data["actual"] = pd.to_numeric(data.get("actual_total"), errors="coerce")
    data = data.dropna(subset=["expected", "actual"])
    data = data[(data["expected"] > 0) & (data["actual"] >= 0)].copy()
    rows = []
    for _, row in data.iterrows():
        lam = float(row["expected"])
        actual = int(row["actual"])
        pmf = max(float(poisson.pmf(actual, lam)), 1e-15)
        pit = float(poisson.cdf(actual - 1, lam) + 0.5 * poisson.pmf(actual, lam))
        crps = float(
            sum(
                (poisson.cdf(k, lam) - (1.0 if actual <= k else 0.0)) ** 2
                for k in range(31)
            )
        )
        item = {
            "game_id": row.get("game_id"),
            "date": str(row.get("date")),
            "matchup": row.get("matchup"),
            "expected_total": lam,
            "actual_total": actual,
            "residual": actual - lam,
            "log_score": -np.log(pmf),
            "crps": crps,
            "mid_pit": pit,
            "input_version": row.get("snap_totals_input_version"),
        }
        for coverage in (0.80, 0.90, 0.95):
            alpha = (1 - coverage) / 2
            lower = int(poisson.ppf(alpha, lam))
            upper = int(poisson.ppf(1 - alpha, lam))
            item[f"pi_{int(coverage*100)}_lower"] = lower
            item[f"pi_{int(coverage*100)}_upper"] = upper
            item[f"pi_{int(coverage*100)}_covered"] = lower <= actual <= upper
        rows.append(item)

    scored = pd.DataFrame(rows)
    if scored.empty:
        return {"sample_size": 0, "status": "insufficient_data", "rows": []}
    intervals = {}
    for level in (80, 90, 95):
        covered = int(scored[f"pi_{level}_covered"].sum())
        low, high = _wilson(covered, len(scored))
        intervals[str(level)] = {
            "nominal_coverage": level / 100,
            "observed_coverage": covered / len(scored),
            "wilson_95_low": low,
            "wilson_95_high": high,
            "mean_width_runs": float(
                (scored[f"pi_{level}_upper"] - scored[f"pi_{level}_lower"]).mean()
            ),
            "statistically_misses_nominal": not (low <= level / 100 <= high),
        }
    actual_mean = float(scored["actual_total"].mean())
    actual_variance = float(scored["actual_total"].var(ddof=1))
    ks = stats.kstest(scored["mid_pit"], "uniform") if len(scored) >= 5 else None
    corrected = scored[pd.to_numeric(scored["input_version"], errors="coerce") >= 2]
    return {
        "sample_size": len(scored),
        "scope": "all resolved totals with expected_total and actual_total",
        "legacy_input_rows": int(len(scored) - len(corrected)),
        "corrected_input_rows": int(len(corrected)),
        "current_engine_verdict": (
            "not_evaluable_until_corrected_totals_resolve" if corrected.empty else "evaluable"
        ),
        "mean_diagnostics": {
            "mean_expected_runs": float(scored["expected_total"].mean()),
            "mean_actual_runs": actual_mean,
            "mean_residual_runs": float(scored["residual"].mean()),
            "mae_runs": float(scored["residual"].abs().mean()),
            "rmse_runs": float(np.sqrt(np.mean(scored["residual"] ** 2))),
        },
        "distribution_diagnostics": {
            "actual_run_variance": actual_variance,
            "actual_variance_to_mean": actual_variance / actual_mean if actual_mean else None,
            "poisson_assumed_variance_mean": float(scored["expected_total"].mean()),
            "mean_negative_log_probability": float(scored["log_score"].mean()),
            "mean_crps": float(scored["crps"].mean()),
            "mid_pit_mean": float(scored["mid_pit"].mean()),
            "mid_pit_ks_statistic": float(ks.statistic) if ks else None,
            "mid_pit_ks_pvalue": float(ks.pvalue) if ks else None,
        },
        "prediction_intervals": intervals,
        "rows": rows,
    }


def write_run_distribution_report(report, report_dir=REPORT_DIR):
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "totals_run_distribution.json").write_text(json.dumps(report, indent=2, default=str))
    pd.DataFrame(report.get("rows", [])).to_csv(
        report_dir / "totals_prediction_intervals.csv", index=False
    )
    return report_dir
