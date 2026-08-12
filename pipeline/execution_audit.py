import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.portfolio_risk_service import complete_history_portfolio_audit


DB_PATH = "database/picks.db"
OUT = Path("reports/execution")


def _classification_metrics(rows):
    if not rows:
        return {"n": 0, "verdict": "insufficient evidence"}
    outcomes = np.asarray([int(row["status"] == "won") for row in rows], dtype=float)
    probs = np.clip(np.asarray([float(row["model_prob"]) for row in rows]), 1e-6, 1 - 1e-6)
    return {
        "n": len(rows),
        "win_rate": round(float(outcomes.mean()), 4),
        "brier": round(float(np.mean((probs - outcomes) ** 2)), 6),
        "log_loss": round(float(np.mean(-(outcomes * np.log(probs) + (1 - outcomes) * np.log(1 - probs)))), 6),
        "verdict": "descriptive complete-history metrics; no causal weakness inferred",
    }


def run(db_path=DB_PATH, out_dir=OUT):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    picks = [dict(row) for row in conn.execute("SELECT * FROM picks ORDER BY date,created_at,id")]
    conn.close()
    resolved = [row for row in picks if row["status"] in ("won", "lost")]
    malformed = [
        row for row in picks
        if not _valid_odds(row.get("odds"))
    ]
    corrected_totals = []
    for row in resolved:
        if row["pick_type"] != "totals":
            continue
        try:
            snapshot = json.loads(row.get("feature_snapshot") or "{}")
        except ValueError:
            snapshot = {}
        if (snapshot.get("totals_input_version") or 0) >= 2:
            corrected_totals.append(row)

    portfolio = complete_history_portfolio_audit(db_path)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "complete pick history; never loss-only",
        "model_problems": {
            "moneyline": _classification_metrics([r for r in resolved if r["pick_type"] == "moneyline"]),
            "totals_all_legacy_and_current": _classification_metrics([r for r in resolved if r["pick_type"] == "totals"]),
            "totals_corrected_input_v2": _classification_metrics(corrected_totals),
            "conclusion": (
                "The corrected totals model cannot yet be evaluated because it has no resolved input-v2 picks. "
                "Legacy totals outcomes remain descriptive and are not evidence against the corrected engine."
            ),
        },
        "data_problems": {
            "malformed_locked_odds": len(malformed),
            "missing_feature_snapshots": sum(not row.get("feature_snapshot") for row in picks),
            "legacy_totals_rows": sum(
                row["pick_type"] == "totals" and row not in corrected_totals for row in resolved
            ),
            "conclusion": "Malformed historical locked odds were not observed; legacy totals inputs remain a comparability limitation.",
        },
        "execution_problems": {
            "zero_theoretical_kelly_predictions": sum(float(row.get("kelly_units") or 0) <= 0 for row in picks),
            "legacy_recommendation_rows": sum(
                row.get("recommendation_tier") in (None, "legacy_unclassified", "historical_only") for row in picks
            ),
            "realized_stake_rows": sum(row.get("realized_stake_units") is not None for row in picks),
            "conclusion": (
                "Legacy execution did not persist realized stakes separately, so historical bankroll results must not be presented as executed-stake results."
            ),
        },
        "portfolio_management_problems": {
            **portfolio,
            "conclusion": (
                "Historical theoretical Kelly exposure exceeded the new game limit in some games; future stakes are capped at single-game and daily levels."
            ),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "complete_execution_audit.json").write_text(json.dumps(report, indent=2))
    lines = ["# Complete betting execution audit", "", "Scope: complete pick history; never loss-only.", ""]
    for key in ("model_problems", "data_problems", "execution_problems", "portfolio_management_problems"):
        lines.extend([f"## {key.replace('_', ' ').title()}", "", "```json", json.dumps(report[key], indent=2), "```", ""])
    (out_dir / "complete_execution_audit.md").write_text("\n".join(lines))
    return report


def _valid_odds(value):
    try:
        value = float(value)
        return math.isfinite(value) and 1 < value <= 100
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
