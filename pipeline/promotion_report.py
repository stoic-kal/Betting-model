import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import model_registry, shadow_report

REPORT_DIR = Path("reports/promotion")


def compare_model_versions(model_name):
    versions = model_registry.list_versions(model_name)
    if len(versions) < 2:
        return {"model_name": model_name, "comparison": "insufficient_versions", "versions_available": len(versions)}
    champion_version = model_registry.get_champion_version(model_name)
    if champion_version is None:
        return {"model_name": model_name, "comparison": "no_champion_metrics_available", "versions_available": len(versions)}
    challenger_version = model_registry.get_challenger_version(model_name, champion_version=champion_version)
    if challenger_version is None:
        return {
            "model_name": model_name,
            "comparison": "no_challenger_metrics_available",
            "champion_version": champion_version,
            "champion_metrics": model_registry.load_metadata(model_name, champion_version)["metrics"],
        }
    champion = model_registry.load_metadata(model_name, champion_version)
    challenger = model_registry.load_metadata(model_name, challenger_version)
    delta = {}
    for key in ("accuracy", "auc", "log_loss", "brier", "ece"):
        cv = challenger["metrics"].get(key)
        chv = champion["metrics"].get(key)
        if cv is not None and chv is not None:
            delta[key] = round(cv - chv, 6)
    return {
        "model_name": model_name,
        "comparison": "ok",
        "champion_version": champion_version,
        "challenger_version": challenger_version,
        "champion_metrics": champion["metrics"],
        "challenger_metrics": challenger["metrics"],
        "delta": delta,
    }


def compare_to_shadow(pick_type):
    rows = [r for r in shadow_report._fetch_graded_shadow_rows() if r["pick_type"] == pick_type]
    if len(rows) < 30:
        return {"pick_type": pick_type, "comparison": "insufficient_shadow_data", "graded_rows": len(rows)}
    y_true = [shadow_report._outcome_label(r) for r in rows]
    prod_prob = [r["production_model_prob"] for r in rows]
    v2_prob = [r["v2_model_prob"] for r in rows]
    odds_dec = [r["odds_dec"] for r in rows]
    return {
        "pick_type": pick_type,
        "comparison": "ok",
        "graded_rows": len(rows),
        "production_metrics": shadow_report.compute_metrics(y_true, prod_prob, odds_dec),
        "shadow_metrics": shadow_report.compute_metrics(y_true, v2_prob, odds_dec),
    }


def recommend(comparison):
    if comparison["comparison"] == "insufficient_shadow_data":
        return f"NO ACTION - insufficient shadow data ({comparison['graded_rows']} graded rows, need >= 30)"
    prod = comparison["production_metrics"]
    shadow = comparison["shadow_metrics"]
    if prod.get("insufficient_class_variation") or shadow.get("insufficient_class_variation"):
        return "NO ACTION - insufficient class variation in graded outcomes"
    reasons = []
    if shadow["log_loss"] < prod["log_loss"]:
        reasons.append("lower log_loss")
    if shadow["brier"] < prod["brier"]:
        reasons.append("lower brier")
    if shadow["roi"] is not None and prod["roi"] is not None and shadow["roi"] > prod["roi"]:
        reasons.append("higher ROI")
    if shadow["kelly_roi"] is not None and prod["kelly_roi"] is not None and shadow["kelly_roi"] > prod["kelly_roi"]:
        reasons.append("higher kelly ROI")
    if len(reasons) >= 2:
        return f"CANDIDATE FOR PROMOTION REVIEW - shadow engine shows {', '.join(reasons)}"
    return "NO PROMOTION - insufficient evidence of shadow engine superiority"


def main():
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version_comparisons": {},
        "shadow_comparisons": {},
    }
    for model_name in ("moneyline", "totals"):
        comparison = compare_model_versions(model_name)
        report["model_version_comparisons"][model_name] = comparison
        print(f"\n--- {model_name} model version comparison ---")
        print(json.dumps(comparison, indent=2, default=str))

    for pick_type in ("moneyline", "totals"):
        comparison = compare_to_shadow(pick_type)
        comparison["recommendation"] = recommend(comparison)
        report["shadow_comparisons"][pick_type] = comparison
        print(f"\n--- {pick_type} production vs shadow comparison ---")
        print(json.dumps(comparison, indent=2, default=str))
        print(f"RECOMMENDATION: {comparison['recommendation']}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\npromotion report written to {out_path}")
    return report


if __name__ == "__main__":
    main()
