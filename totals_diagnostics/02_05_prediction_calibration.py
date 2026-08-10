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
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss, log_loss

from loader import load_totals, resolved, snapped, SNAP_NUMERIC, FIG_DIR

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
P = {
"OVER": "#f85149",
"UNDER": "#3fb950",
"neutral": "#58a6ff",
"warn": "#d29922",
"dim": "#8b949e",
}


def hdr(t):
    print(f"\n{'═'*70}\n  {t}\n{'═'*70}")


def section2(res, snp):
    hdr("SECTION 2 — PREDICTION DISTRIBUTION")

    fig = plt.figure(figsize=(16, 10))
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)

    ax = fig.add_subplot(gs[0, 0])
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = res[res["direction"] == d]["model_prob"].dropna()
        ax.hist(sub, bins=15, alpha=0.6, color=col, label=d, density=True)
    ax.axvline(0.524, color=P["warn"], lw=1.5, ls="--", label="BE line")
    ax.set_title("Model Prob Distribution by Direction", fontsize=9)
    ax.set_xlabel("Model Probability")
    ax.legend(fontsize=7)
    _annotate(
        ax,
"Do OVER and UNDER probs\noccupy the same range?\nIf so, model makes no\ndirectional distinction.",
    )

    if "snap_expected_total" in snp.columns and "snap_market_line" in snp.columns:
        ax = fig.add_subplot(gs[0, 1])
        x = snp["snap_market_line"].dropna()
        y = snp["snap_expected_total"].dropna()
        both = snp[["snap_market_line", "snap_expected_total", "won"]].dropna()
        ax.scatter(
            both["snap_market_line"],
            both["snap_expected_total"],
            c=both["won"].map({1: P["UNDER"], 0: P["OVER"]}),
            alpha=0.7,
            s=40,
        )
        lims = [min(x.min(), y.min()) - 0.5, max(x.max(), y.max()) + 0.5]
        ax.plot(lims, lims, color=P["dim"], lw=1, ls="--", label="y=x (perfect)")
        ax.set_xlabel("Market Line")
        ax.set_ylabel("Model Expected Total")
        ax.set_title("Expected Total vs Market Line", fontsize=9)
        ax.legend(fontsize=7)
        _annotate(
            ax,
"Green=Won, Red=Lost\nPoints above line = model\npredicts more runs than\nmarket (OVER bias?).",
        )

    if "snap_expected_total" in snp.columns and "snap_market_line" in snp.columns:
        ax = fig.add_subplot(gs[0, 2])
        snp["edge_runs"] = snp["snap_market_line"] - snp["snap_expected_total"]
        won_e = snp[snp["won"] == 1]["edge_runs"].dropna()
        lost_e = snp[snp["won"] == 0]["edge_runs"].dropna()
        ax.hist(lost_e, bins=15, alpha=0.55, color=P["OVER"], label="Lost", density=True)
        ax.hist(won_e, bins=15, alpha=0.55, color=P["UNDER"], label="Won", density=True)
        ax.axvline(0, color=P["dim"], lw=1, ls="--")
        ax.set_title("Run Edge Distribution (market - model)", fontsize=9)
        ax.set_xlabel("Edge (runs)")
        ax.legend(fontsize=7)
        _annotate(
            ax,
"+edge = model predicts fewer\nruns than market → UNDER.\n"
"-edge = model predicts more\nruns than market → OVER.",
        )

    ax = fig.add_subplot(gs[1, 0])
    won_ev = res[res["won"] == 1]["ev"].dropna()
    lost_ev = res[res["won"] == 0]["ev"].dropna()
    ax.hist(lost_ev, bins=15, alpha=0.55, color=P["OVER"], label="Lost", density=True)
    ax.hist(won_ev, bins=15, alpha=0.55, color=P["UNDER"], label="Won", density=True)
    ax.axvline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("EV Distribution: Won vs Lost", fontsize=9)
    ax.set_xlabel("Expected Value (%)")
    ax.legend(fontsize=7)
    _annotate(ax, "If distributions overlap\nheavily, EV is not\ndiscriminating wins\nfrom losses.")

    ax = fig.add_subplot(gs[1, 1])
    probs = res["model_prob"].dropna()
    (osm, osr), (slope, intercept, r) = stats.probplot(probs, dist="uniform", fit=True)
    ax.plot(osm, osr, "o", color=P["neutral"], ms=4, alpha=0.6)
    ax.plot(osm, slope * np.array(osm) + intercept, color=P["warn"], lw=1.5)
    ax.set_title("QQ Plot — Model Prob vs Uniform", fontsize=9)
    ax.set_xlabel("Theoretical Quantiles")
    ax.set_ylabel("Sample Quantiles")
    _annotate(ax, "Deviations from diagonal\nreveal probability\ncompression or skew.")

    ax = fig.add_subplot(gs[1, 2])
    buckets = pd.cut(res["model_prob"], bins=np.arange(0.48, 0.80, 0.03))
    roi_by_bucket = (
        res.groupby(buckets, observed=True)["profit"].sum()
        / res.groupby(buckets, observed=True)["wagered"].sum()
        * 100
    )
    ax.bar(
        range(len(roi_by_bucket)),
        roi_by_bucket.values,
        color=[P["UNDER"] if v >= 0 else P["OVER"] for v in roi_by_bucket.values],
    )
    ax.set_xticks(range(len(roi_by_bucket)))
    ax.set_xticklabels([str(b) for b in roi_by_bucket.index], rotation=45, fontsize=6)
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("ROI by Model Probability Bucket", fontsize=9)
    ax.set_ylabel("ROI (%)")
    _annotate(ax, "Green = profitable bucket.\nRed = losing bucket.\nNo trend = no calibration.")

    fig.suptitle("SECTION 2: PREDICTION DISTRIBUTION ANALYSIS", fontsize=12, y=1.01)
    plt.savefig(FIG_DIR / "02_prediction_distribution.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("→ Saved: 02_prediction_distribution.png")

    print(
        f"\n  Model Prob:  mean={res['model_prob'].mean():.3f}  std={res['model_prob'].std():.3f}"
    )
    print(f"EV:          mean={res['ev'].mean():.1f}%  std={res['ev'].std():.1f}%")
    if "snap_expected_total" in snp.columns and "snap_market_line" in snp.columns:
        snp["edge_runs"] = snp["snap_market_line"] - snp["snap_expected_total"]
        print(
            f"Run Edge:    mean={snp['edge_runs'].mean():.2f}  std={snp['edge_runs'].std():.2f}"
        )
        over_edge = snp[snp["direction"] == "OVER"]["edge_runs"].mean()
        under_edge = snp[snp["direction"] == "UNDER"]["edge_runs"].mean()
        print(
            f"OVER picks mean edge:  {over_edge:.2f} runs  (negative = model predicts MORE than market)"
        )
        print(
            f"UNDER picks mean edge: {under_edge:.2f} runs  (positive = model predicts FEWER than market)"
        )
        return {
"model_prob_mean": round(float(res["model_prob"].mean()), 4),
"model_prob_std": round(float(res["model_prob"].std()), 4),
"ev_mean": round(float(res["ev"].mean()), 2),
"over_mean_edge_runs": round(float(over_edge), 2),
"under_mean_edge_runs": round(float(under_edge), 2),
        }
    return {
"model_prob_mean": round(float(res["model_prob"].mean()), 4),
"model_prob_std": round(float(res["model_prob"].std()), 4),
"ev_mean": round(float(res["ev"].mean()), 2),
    }


def section3(res, snp):
    hdr("SECTION 3 — RESIDUAL ANALYSIS")

    if "snap_expected_total" not in snp.columns or "snap_market_line" not in snp.columns:
        print("No expected_total or market_line in snapshots. Skipping residual analysis.")
        return

    snp = snp.copy()
    snp["edge_runs"] = snp["snap_market_line"] - snp["snap_expected_total"]
    snp["abs_edge"] = snp["edge_runs"].abs()

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    ax = axes[0, 0]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = snp[snp["direction"] == d]["edge_runs"].dropna()
        ax.hist(sub, bins=15, alpha=0.6, color=col, label=d, density=True)
    ax.axvline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("Run Edge by Direction", fontsize=9)
    ax.legend(fontsize=7)

    ax = axes[0, 1]
    snp["abs_bucket"] = pd.cut(snp["abs_edge"], bins=[0, 0.5, 1, 1.5, 2, 5, 10])
    wr = snp.groupby("abs_bucket", observed=True)["won"].mean() * 100
    n = snp.groupby("abs_bucket", observed=True)["won"].count()
    bars = ax.bar(
        range(len(wr)), wr.values, color=[P["UNDER"] if v >= 52.4 else P["OVER"] for v in wr.values]
    )
    ax.set_xticks(range(len(wr)))
    ax.set_xticklabels([str(b) for b in wr.index], rotation=30, fontsize=7)
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.set_title("Win Rate by Absolute Edge (runs)", fontsize=9)
    ax.set_ylabel("Win Rate (%)")
    ax.legend(fontsize=7)
    for i, (b, nn) in enumerate(zip(bars, n.values)):
        ax.text(
            b.get_x() + b.get_width() / 2, b.get_height() + 0.5, f"n={nn}", ha="center", fontsize=6
        )
    _annotate(
        ax,
"Larger edges should → higher WR.\nIf flat/inverted = model\ncannot translate edge to wins.",
    )

    ax = axes[0, 2]
    snp["line_bucket"] = pd.cut(snp["snap_market_line"], bins=[5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 15])
    wr_line = snp.groupby("line_bucket", observed=True)["won"].mean() * 100
    n_line = snp.groupby("line_bucket", observed=True)["won"].count()
    ax.bar(
        range(len(wr_line)),
        wr_line.values,
        color=[P["UNDER"] if v >= 52.4 else P["OVER"] for v in wr_line.values],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
    ax.set_xticks(range(len(wr_line)))
    ax.set_xticklabels([str(b) for b in wr_line.index], rotation=30, fontsize=7)
    ax.set_title("Win Rate by Market Total Line", fontsize=9)
    ax.set_ylabel("WR (%)")

    ax = axes[1, 0]
    res_c = res.copy()
    res_c["ev_bucket"] = pd.cut(res_c["ev"], bins=[0, 5, 10, 15, 20, 30, 60])
    wr_ev = res_c.groupby("ev_bucket", observed=True)["won"].agg(["mean", "count"])
    ax.bar(
        range(len(wr_ev)),
        wr_ev["mean"] * 100,
        color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_ev["mean"]],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.set_xticks(range(len(wr_ev)))
    ax.set_xticklabels([str(b) for b in wr_ev.index], rotation=30, fontsize=7)
    ax.set_title("Win Rate by EV Bucket", fontsize=9)
    ax.set_ylabel("WR (%)")
    for i, (idx, row) in enumerate(wr_ev.iterrows()):
        ax.text(i, row["mean"] * 100 + 0.5, f"n={int(row['count'])}", ha="center", fontsize=6)
    _annotate(
        ax, "Higher EV should correlate\nwith higher WR. Inversion\nhere = probability is wrong."
    )

    ax = axes[1, 1]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = res[res["direction"] == d]
        buckets = pd.cut(sub["model_prob"], bins=np.arange(0.48, 0.80, 0.04))
        wr_d = sub.groupby(buckets, observed=True)["won"].mean() * 100
        n_d = sub.groupby(buckets, observed=True)["won"].count()
        mids = [b.mid for b in wr_d.index]
        ax.plot(mids, wr_d.values, "o-", color=col, label=d, ms=5)
        for x, y, n in zip(mids, wr_d.values, n_d.values):
            if n >= 2:
                ax.text(x, y + 1, f"{n}", fontsize=5, ha="center")
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.set_title("Win Rate vs Model Prob (by Direction)", fontsize=9)
    ax.set_xlabel("Model Probability")
    ax.set_ylabel("Win Rate (%)")
    ax.legend(fontsize=7)

    ax = axes[1, 2]
    month_stats = res.groupby("month")["won"].agg(["mean", "count", "sum"])
    month_stats.columns = ["wr", "n", "wins"]
    month_names = {3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct"}
    ax.bar(
        range(len(month_stats)),
        month_stats["wr"] * 100,
        color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in month_stats["wr"]],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
    ax.set_xticks(range(len(month_stats)))
    ax.set_xticklabels([month_names.get(m, str(m)) for m in month_stats.index], fontsize=8)
    ax.set_title("Win Rate by Month", fontsize=9)
    ax.set_ylabel("WR (%)")
    for i, (idx, row) in enumerate(month_stats.iterrows()):
        ax.text(i, row["wr"] * 100 + 0.5, f"n={int(row['n'])}", ha="center", fontsize=6)

    fig.suptitle("SECTION 3: RESIDUAL ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "03_residual_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("→ Saved: 03_residual_analysis.png")

    print("\n  TOP SITUATIONS WHERE MODEL FAILS (lowest WR, min n=3):")
    breakdowns = {}
    for col in ["direction", "month", "weekday"]:
        if col in res.columns:
            g = res.groupby(col)["won"].agg(["mean", "count"])
            g = g[g["count"] >= 3].sort_values("mean")
            for idx, row in g.iterrows():
                breakdowns[f"{col}={idx}"] = (row["mean"] * 100, int(row["count"]))
    for k, (wr, n) in sorted(breakdowns.items(), key=lambda x: x[1][0])[:10]:
        print(f"{k:<30s}  WR={wr:.0f}%  n={n}")

    worst = sorted(breakdowns.items(), key=lambda x: x[1][0])[:1]
    return {
"worst_segment": worst[0][0] if worst else None,
"worst_segment_wr": round(worst[0][1][0], 1) if worst else None,
"worst_segment_n": worst[0][1][1] if worst else None,
    }


def section4(snp):
    hdr("SECTION 4 — ERROR HEATMAPS")

    def heatmap_wr(df, col1, col2, ax, title, bins1=4, bins2=4):
        d = df[[col1, col2, "won"]].dropna()
        if len(d) < 10:
            ax.text(0.5, 0.5, "Insufficient data", transform=ax.transAxes, ha="center")
            return
        d = d.copy()
        d["b1"] = pd.qcut(d[col1], bins1, duplicates="drop")
        d["b2"] = pd.qcut(d[col2], bins2, duplicates="drop")
        pivot = d.groupby(["b1", "b2"], observed=True)["won"].mean().unstack() * 100
        sns.heatmap(
            pivot,
            ax=ax,
            cmap="RdYlGn",
            center=52.4,
            vmin=0,
            vmax=100,
            annot=True,
            fmt=".0f",
            annot_kws={"size": 7},
            linewidths=0.3,
            cbar_kws={"shrink": 0.7, "label": "Win Rate %"},
        )
        ax.set_title(title, fontsize=9)
        ax.set_xlabel(col2.replace("snap_", ""), fontsize=7)
        ax.set_ylabel(col1.replace("snap_", ""), fontsize=7)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=20, fontsize=6)
        ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=6)

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))

    pairs = [
        ("snap_home_fip", "snap_away_fip", "Starter Quality (FIP×FIP)"),
        ("model_prob", "ev", "Model Prob × EV"),
        ("snap_market_line", "snap_expected_total", "Market Line × Expected Total"),
        ("snap_home_fip", "snap_market_line", "Home FIP × Market Line"),
        ("snap_away_fip", "snap_market_line", "Away FIP × Market Line"),
        ("snap_context_home_bullpen_fatigue", "snap_home_fip", "Bullpen Fatigue × Home FIP"),
    ]
    for ax, (c1, c2, title) in zip(axes.flatten(), pairs):
        if c1 in snp.columns and c2 in snp.columns:
            heatmap_wr(snp, c1, c2, ax, title)
        else:
            ax.text(
                0.5, 0.5, f"Missing: {c1} or {c2}", transform=ax.transAxes, ha="center", fontsize=8
            )
            ax.set_title(title, fontsize=9)

    fig.suptitle("SECTION 4: WIN RATE HEATMAPS — Green=Profitable, Red=Losing", fontsize=11, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "04_error_heatmaps.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("→ Saved: 04_error_heatmaps.png")
    print("""
  INTERPRETATION:
  Green cells = situations where model is profitable.
  Red cells   = systematic failure zones.
  Any consistent red band across a row/column identifies
  a feature value range where the model always fails.
""")


def section5(res):
    hdr("SECTION 5 — PROBABILITY CALIBRATION")

    y_true = res["won"].dropna().astype(int)
    y_prob = res.loc[y_true.index, "model_prob"]
    valid = y_prob.notna() & y_true.notna()
    y_true, y_prob = y_true[valid], y_prob[valid]

    bs = brier_score_loss(y_true, y_prob)
    ll = log_loss(y_true, y_prob)
    frac_pos, mean_pred = calibration_curve(y_true, y_prob, n_bins=8, strategy="quantile")
    ece = np.mean(np.abs(frac_pos - mean_pred))
    mce = np.max(np.abs(frac_pos - mean_pred))

    print(f"\n  Brier Score:  {bs:.4f}  (lower=better; 0.25=coin flip)")
    print(f"Log Loss:     {ll:.4f}  (lower=better)")
    print(f"ECE:          {ece:.4f}  (Expected Calibration Error; <0.05=good)")
    print(f"MCE:          {mce:.4f}  (Max Calibration Error)")
    print(f"Baseline BS:  {brier_score_loss(y_true, np.full(len(y_true), y_true.mean())):.4f}")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    ax = axes[0]
    ax.plot([0, 1], [0, 1], color=P["dim"], lw=1, ls="--", label="Perfect calibration")
    ax.plot(mean_pred, frac_pos, "o-", color=P["neutral"], lw=2, ms=7, label="Model")

    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = res[res["direction"] == d].dropna(subset=["won", "model_prob"])
        if len(sub) < 8:
            continue
        fp, mp = calibration_curve(
            sub["won"].astype(int), sub["model_prob"], n_bins=6, strategy="quantile"
        )
        ax.plot(mp, fp, "s--", color=col, lw=1.5, ms=5, alpha=0.8, label=d)
    ax.set_title("Reliability Diagram", fontsize=9)
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Fraction of Positives")
    ax.legend(fontsize=7)
    ax.text(
        0.05,
        0.92,
        f"ECE={ece:.3f}  MCE={mce:.3f}\nBrier={bs:.4f}  LogLoss={ll:.4f}",
        transform=ax.transAxes,
        fontsize=7,
        color=P["warn"],
        bbox=dict(boxstyle="round", facecolor="#161b22", alpha=0.9),
    )
    _annotate(
        ax,
"Above diagonal = underconfident.\nBelow diagonal = overconfident.\nS-curve = compressed probs.",
    )

    ax = axes[1]
    buckets = pd.cut(res["model_prob"], bins=np.arange(0.48, 0.82, 0.04))
    stats_b = res.groupby(buckets, observed=True)["won"].agg(["mean", "count"])
    mids = [b.mid for b in stats_b.index]
    ax.bar(
        range(len(stats_b)),
        stats_b["mean"] * 100,
        color=[P["UNDER"] if v >= 52.4 else P["OVER"] for v in stats_b["mean"]],
    )
    ax.plot(
        range(len(stats_b)),
        [m * 100 for m in mids],
"o--",
        color=P["warn"],
        lw=1.5,
        ms=6,
        label="Expected WR",
    )
    ax.axhline(52.4, color=P["dim"], lw=1, ls=":")
    ax.set_xticks(range(len(stats_b)))
    ax.set_xticklabels([f"{m:.2f}" for m in mids], rotation=45, fontsize=7)
    ax.set_title("Actual Win Rate vs Expected (per prob bucket)", fontsize=9)
    ax.set_ylabel("Win Rate (%)")
    ax.legend(fontsize=7)
    for i, (idx, row) in enumerate(stats_b.iterrows()):
        ax.text(i, row["mean"] * 100 + 1, f"n={int(row['count'])}", ha="center", fontsize=6)
    _annotate(ax, "Yellow line = ideal WR.\nBars = actual WR.\nGap = miscalibration.")

    ax = axes[2]
    gap = (stats_b["mean"] * 100) - np.array([m * 100 for m in mids])
    colors = [P["UNDER"] if v >= 0 else P["OVER"] for v in gap]
    ax.bar(range(len(gap)), gap.values, color=colors)
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_xticks(range(len(gap)))
    ax.set_xticklabels([f"{m:.2f}" for m in mids], rotation=45, fontsize=7)
    ax.set_title("Calibration Gap (Actual − Expected WR)", fontsize=9)
    ax.set_ylabel("Gap (pp)")
    _annotate(ax, "Green = model underconfident.\nRed = model overconfident.\nShould be near zero.")

    fig.suptitle("SECTION 5: PROBABILITY CALIBRATION", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "05_calibration.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("→ Saved: 05_calibration.png")

    print(f"""
  INTERPRETATION:
  ECE of {ece:.3f} means predictions are off by {ece*100:.1f}pp on average.
  A well-calibrated sports model should have ECE < 0.03.
  The reliability diagram shows whether high-confidence bets
  actually win more often — if not, the probability model needs
  recalibration (Platt scaling or isotonic regression).
""")

    return {
"brier": round(float(bs), 4),
"log_loss": round(float(ll), 4),
"ece": round(float(ece), 4),
"mce": round(float(mce), 4),
    }


def _annotate(ax, text):
    ax.text(
        0.97,
        0.03,
        text,
        transform=ax.transAxes,
        fontsize=6,
        color=P["dim"],
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round", facecolor="#0d1117", alpha=0.7),
    )


def run():
    from loader import run_section, skip_section

    try:
        df = load_totals()
        res = resolved(df)
        snp = snapped(res)
    except Exception as e:
        reason = f"shared data load failed: {e}"
        for sid, title in [
            ("s2", "Prediction Distribution"),
            ("s3", "Residual Analysis"),
            ("s4", "Error Heatmaps"),
            ("s5", "Calibration"),
        ]:
            skip_section(sid, title, reason)
        return
    run_section("s2", "Prediction Distribution", section2, res, snp)
    run_section("s3", "Residual Analysis", section3, res, snp)
    run_section("s4", "Error Heatmaps", section4, snp)
    run_section("s5", "Calibration", section5, res)


if __name__ == "__main__":
    run()
