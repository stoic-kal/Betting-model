import sys, os

sys.path.insert(0, os.path.dirname(__file__))
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
from pathlib import Path

from loader import load_totals, load_all_picks, resolved, snapped, SNAP_NUMERIC, FIG_DIR
from feature_catalog import FEATURE_CATALOG, compute_feature_health, current_schema_version

plt.rcParams.update(
    {
        "figure.facecolor": "#0d1117",
        "axes.facecolor": "#161b22",
        "axes.edgecolor": "#30363d",
        "axes.labelcolor": "#c9d1d9",
        "text.color": "#c9d1d9",
        "xtick.color": "#8b949e",
        "ytick.color": "#8b949e",
        "grid.color": "#21262d",
        "grid.alpha": 0.6,
        "font.family": "monospace",
    }
)
PALETTE = {"OVER": "#f85149", "UNDER": "#3fb950", "neutral": "#58a6ff", "warn": "#d29922"}


def section_header(title):
    print("\n" + "═" * 70)
    print(f"  {title}")
    print("═" * 70)


def flag(msg, level="WARN"):
    icons = {"WARN": "", "CRIT": "", "OK": "", "INFO": "ℹ"}
    print(f"  {icons.get(level,'?')} [{level}] {msg}")


def _section1_body():
    df = load_totals()
    res = resolved(df)
    snp = snapped(res)

    section_header("1A — DATASET OVERVIEW")
    print(f"  Total picks (all statuses):  {len(df)}")
    print(f"  Resolved (won + lost):        {len(res)}")
    print(f"  With feature snapshot:        {len(snp)}")
    print(f"  Coverage:                     {len(snp)/max(len(res),1)*100:.1f}%")
    print(
        f"  Date range:                   {res['date'].min().date()} → {res['date'].max().date()}"
    )
    print(f"  Total columns:                {len(df.columns)}")

    snap_cols = [c for c in snp.columns if c.startswith("snap_")]
    print(f"  Snapshot-derived features:    {len(snap_cols)}")

    section_header("1B — CONSTANT & NEAR-CONSTANT FEATURES")
    issues = []
    for col in snap_cols:
        s = snp[col].dropna()
        if len(s) < 3:
            continue
        if s.dtype == object:
            continue
        cv = s.std() / (abs(s.mean()) + 1e-9)
        unique_ratio = s.nunique() / len(s)
        if s.nunique() == 1:
            flag(f"CONSTANT: {col} = {s.iloc[0]:.4f} (all {len(s)} rows identical)", "CRIT")
            issues.append((col, "CONSTANT", s.iloc[0], len(s)))
        elif cv < 0.01:
            flag(f"NEAR-CONSTANT: {col}  CV={cv:.4f}  unique={s.nunique()}", "WARN")
            issues.append((col, "NEAR-CONSTANT", s.mean(), len(s)))
        elif unique_ratio < 0.05:
            flag(f"LOW-VARIANCE: {col}  unique={s.nunique()}/{len(s)}", "INFO")

    if not issues:
        flag("No completely constant features detected.", "OK")

    section_header("1C — MISSING VALUE AUDIT")
    all_records = load_all_picks()
    cur_ver = current_schema_version(all_records)
    flag(
        f"Current snapshot schema version: {cur_ver}  "
        f"(rows on an older/absent version are historical, not broken)",
        "INFO",
    )

    for key in FEATURE_CATALOG:
        health = compute_feature_health(all_records, key, cur_ver)
        if health is None or health["missing_pct"] == 0:
            continue
        reason_str = ", ".join(
            f"{v} {k}" for k, v in sorted(health["reasons"].items(), key=lambda kv: -kv[1])
        )
        level = "INFO" if health["status"] == "Healthy" else "WARN"
        flag(
            f"{health['missing_pct']:.0f}% missing: {health['label']} ({key}) — {reason_str}", level
        )

    cataloged_cols = {f"snap_{k}" for k in FEATURE_CATALOG}
    uncataloged = [c for c in snap_cols if c not in cataloged_cols]
    miss_uncat = (
        (snp[uncataloged].isna().mean() * 100).sort_values(ascending=False)
        if uncataloged
        else pd.Series(dtype=float)
    )
    high_miss_uncat = miss_uncat[miss_uncat > 20]
    if len(high_miss_uncat):
        for col, pct in high_miss_uncat.items():
            flag(
                f"{pct:.0f}% missing: {col} — reason: Unknown (not yet root-caused)",
                "WARN" if pct < 50 else "CRIT",
            )

    miss = (snp[snap_cols].isna().mean() * 100).sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(14, max(4, len(snap_cols) * 0.28)))
    ax.barh(
        miss.index,
        miss.values,
        color=[PALETTE["warn"] if v > 20 else PALETTE["neutral"] for v in miss.values],
    )
    ax.set_xlabel("% Missing")
    ax.set_title(
        "Feature Missing Rate (%) — see 1C reasons above before assuming any bar is a bug",
        pad=10,
        fontsize=11,
        color="#c9d1d9",
    )
    ax.axvline(20, color=PALETTE["warn"], lw=1, ls="--", label="20% threshold")
    ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "01c_missing_rates.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 01c_missing_rates.png")

    section_header("1D — IMPOSSIBLE / SUSPICIOUS VALUES")
    checks = [
        ("snap_home_fip", lambda s: s[(s < 1.0) | (s > 8.0)], "FIP outside 1.0–8.0"),
        ("snap_away_fip", lambda s: s[(s < 1.0) | (s > 8.0)], "FIP outside 1.0–8.0"),
        ("snap_home_rsg", lambda s: s[(s < 1.5) | (s > 9.0)], "RSG outside 1.5–9.0"),
        ("snap_away_rsg", lambda s: s[(s < 1.5) | (s > 9.0)], "RSG outside 1.5–9.0"),
        ("snap_park_factor", lambda s: s[(s < 0.80) | (s > 1.30)], "Park factor outside 0.80–1.30"),
        (
            "snap_weather_factor",
            lambda s: s[(s < 0.80) | (s > 1.30)],
            "Weather factor outside 0.80–1.30",
        ),
        ("snap_temp_f", lambda s: s[(s < 20) | (s > 120)], "Temperature outside 20–120°F"),
        ("snap_expected_total", lambda s: s[(s < 3) | (s > 25)], "Expected total outside 3–25"),
        ("snap_market_line", lambda s: s[(s < 4) | (s > 20)], "Market line outside 4–20"),
        ("model_prob", lambda s: s[(s < 0.35) | (s > 0.95)], "Model prob outside 35–95%"),
    ]
    for col, fn, label in checks:
        if col not in snp.columns:
            continue
        bad = fn(snp[col].dropna())
        if len(bad) > 0:
            flag(f"{len(bad)} rows: {label} — {col}", "WARN")
            print(f"    Values: {bad.values[:5]}")
        else:
            flag(f"OK: {col}", "OK")

    section_header("1E — FEATURE DISTRIBUTION PLOTS")
    numeric_snap = [
        c for c in snap_cols if snp[c].dtype in [np.float64, np.int64] and snp[c].nunique() > 2
    ]
    cols_to_plot = [c for c in SNAP_NUMERIC if c in snp.columns]

    n = len(cols_to_plot)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(16, nrows * 3))
    axes = axes.flatten()
    for i, col in enumerate(cols_to_plot):
        ax = axes[i]
        data = snp[col].dropna()
        won_data = snp[snp["won"] == 1][col].dropna()
        lost_data = snp[snp["won"] == 0][col].dropna()
        if len(data) < 2:
            ax.set_visible(False)
            continue
        ax.hist(lost_data, bins=15, alpha=0.5, color=PALETTE["OVER"], label="Lost", density=True)
        ax.hist(won_data, bins=15, alpha=0.5, color=PALETTE["UNDER"], label="Won", density=True)
        ax.set_title(col.replace("snap_", ""), fontsize=8)
        ax.legend(fontsize=6)

        if data.std() < 0.001:
            ax.set_facecolor("#3d1a1a")
            ax.set_title(
                f"CONSTANT: {col.replace('snap_','')}", fontsize=8, color=PALETTE["warn"]
            )
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    fig.suptitle("Feature Distributions: Won (green) vs Lost (red)", fontsize=11, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "01e_feature_distributions.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 01e_feature_distributions.png")

    section_header("1F — FEATURE DRIFT OVER TIME")
    if "snap_park_factor" in snp.columns:
        fig, axes = plt.subplots(2, 2, figsize=(14, 8))
        drift_cols = [
            "snap_park_factor",
            "snap_weather_factor",
            "snap_home_fip",
            "snap_expected_total",
        ]
        for ax, col in zip(axes.flatten(), drift_cols):
            if col not in snp.columns:
                continue
            tmp = snp[["date", col]].dropna().set_index("date").resample("7D").mean()
            ax.plot(tmp.index, tmp[col], color=PALETTE["neutral"], lw=1.5)
            ax.set_title(col.replace("snap_", ""), fontsize=9)
            ax.set_xlabel("")

            if tmp[col].std() < 0.001:
                ax.set_facecolor("#3d1a1a")
                ax.text(
                    0.5,
                    0.5,
                    "CONSTANT — NO DRIFT\n(data pipeline bug?)",
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=10,
                    color=PALETTE["warn"],
                    bbox=dict(boxstyle="round", facecolor="#1a0a0a", alpha=0.8),
                )
        fig.suptitle("Weekly Feature Mean Over Time (flat = broken)", fontsize=11)
        plt.tight_layout()
        plt.savefig(FIG_DIR / "01f_feature_drift.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  → Saved: 01f_feature_drift.png")

    section_header("1G — FEATURE CORRELATION MATRIX")
    corr_cols = [c for c in SNAP_NUMERIC if c in snp.columns]
    if len(corr_cols) >= 4:
        corr = snp[corr_cols + ["won"]].corr()
        fig, ax = plt.subplots(figsize=(14, 11))
        mask = np.triu(np.ones_like(corr, dtype=bool))
        sns.heatmap(
            corr,
            mask=mask,
            cmap="RdBu_r",
            center=0,
            vmin=-1,
            vmax=1,
            ax=ax,
            annot=True,
            fmt=".2f",
            annot_kws={"size": 6},
            linewidths=0.3,
            cbar_kws={"shrink": 0.6},
        )
        ax.set_title("Feature Correlation Matrix (including won/lost)", fontsize=11)
        ax.set_xticklabels(
            [c.replace("snap_", "") for c in corr.columns], rotation=45, ha="right", fontsize=7
        )
        ax.set_yticklabels([c.replace("snap_", "") for c in corr.index], fontsize=7)
        plt.tight_layout()
        plt.savefig(FIG_DIR / "01g_correlation_matrix.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  → Saved: 01g_correlation_matrix.png")

    section_header("1H — FEATURE HEALTH REPORT")
    flag(f"{len(FEATURE_CATALOG)} audited features | current schema version: {cur_ver}", "INFO")
    status_icons = {"Healthy": "", "Partial": "", "Broken": "", "Historical Only": "ℹ"}
    health_reports = []
    for key in FEATURE_CATALOG:
        health = compute_feature_health(all_records, key, cur_ver)
        if health is None:
            continue
        health_reports.append(health)
        icon = status_icons.get(health["status"], "ℹ")
        print(
            f"\n  {icon} {health['label']}  [{health['status']}]  (priority: {health['priority']})"
        )
        print(f"    Missing %:              {health['missing_pct']:.1f}%")
        print(
            f"    Live coverage %:        " f"{health['live_coverage']:.1f}%"
            if health["live_coverage"] is not None
            else "    Live coverage %:        n/a (no current-schema rows yet)"
        )
        print(
            f"    Historical coverage %:  " f"{health['historical_coverage']:.1f}%"
            if health["historical_coverage"] is not None
            else "    Historical coverage %:  n/a (no historical rows)"
        )
        print(
            f"    Fallback rate %:        " f"{health['fallback_rate']:.1f}%"
            if health["fallback_rate"] is not None
            else "    Fallback rate %:        — (not instrumented)"
        )
        print(
            f"    Default rate %:         " f"{health['default_rate']:.1f}%"
            if health["default_rate"] is not None
            else "    Default rate %:         — (not instrumented)"
        )
        print(f"    Source:                 {health['source']}")
        print(f"    Pipeline:               {health['pipeline']}")
        print(f"    Recommendation:         {health['recommendation']}")

    section_header("1 — SUMMARY")
    constant_feats = [c for c in snap_cols if c in snp and snp[c].dropna().nunique() == 1]
    healthy_n = sum(h["status"] == "Healthy" for h in health_reports)
    partial_n = sum(h["status"] == "Partial" for h in health_reports)
    broken_n = sum(h["status"] == "Broken" for h in health_reports)
    print(f"""
  FINDINGS:
  • {healthy_n} of {len(health_reports)} audited features are Healthy going
    forward — their missing data is a historical-schema artifact (see 1C/1H),
    not a live pipeline bug.

  • {partial_n} features are Partial: weather (silent-default risk on API
    failure, now tagged via weather_source) and live reliever-availability
    (API timeout risk, now retried with backoff and no longer cached as a
    failure for the rest of the day).

  • {broken_n} audited features are Broken. The original "starts_used is a
    hard constant" finding was a false positive — it is len(last_5_starts),
    arithmetically capped at 5 by design, not a data pipeline defect.

  • {len(constant_feats)} snapshot columns are still completely constant
    across all games. Cross-reference against 1H before treating any of
    these as a bug — some may simply be historically absent (all-null,
    which pandas also reports as zero variance).

  NEXT STEP:
    Historical rows before schema_version {cur_ver} will always show the
    catalogued features above as missing — that is expected and does not
    need fixing. Watch the Fallback Rate % on weather and reliever features
    going forward; a rising rate would indicate a genuine, ongoing API
    problem worth escalating, as distinct from the one-time historical gap.
""")

    return {
        "resolved_picks": len(res),
        "with_snapshot": len(snp),
        "coverage_pct": round(len(snp) / max(len(res), 1) * 100, 1),
        "constant_features": len(constant_feats),
        "healthy_features": healthy_n,
        "partial_features": partial_n,
        "broken_features": broken_n,
        "audited_features": len(health_reports),
    }


def run():
    from loader import run_section

    return run_section("s1", "Data Health Audit", _section1_body)


if __name__ == "__main__":
    run()
