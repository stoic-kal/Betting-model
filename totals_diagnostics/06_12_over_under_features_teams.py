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
from itertools import product

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


def _ann(ax, txt):
    ax.text(
        0.97,
        0.03,
        txt,
        transform=ax.transAxes,
        fontsize=6,
        color=P["dim"],
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round", facecolor="#0d1117", alpha=0.7),
    )


def section6(res, snp):
    hdr("SECTION 6 — OVER vs UNDER FAILURE ANALYSIS")

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    ax = axes[0, 0]
    for i, (d, col) in enumerate([("OVER", P["OVER"]), ("UNDER", P["UNDER"])]):
        sub = res[res["direction"] == d]
        w = (sub["won"] == 1).sum()
        l = (sub["won"] == 0).sum()
        wr = w / (w + l) * 100 if (w + l) else 0
        roi = sub["profit"].sum() / max(sub["wagered"].sum(), 1) * 100
        ax.bar(i * 3, w, color=P["UNDER"], width=0.8)
        ax.bar(i * 3 + 1, l, color=P["OVER"], width=0.8)
        ax.text(
            i * 3 + 0.5,
            max(w, l) + 0.3,
            f"WR={wr:.0f}%\nROI={roi:.1f}%",
            ha="center",
            fontsize=8,
            color=col,
        )
    ax.set_xticks([0.5, 3.5])
    ax.set_xticklabels(["OVER", "UNDER"], fontsize=9)
    ax.set_title("Record by Direction", fontsize=9)
    ax.legend(["Won", "Lost"], fontsize=7)

    ax = axes[0, 1]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        data = res[res["direction"] == d]["model_prob"].dropna()
        ax.hist(data, bins=15, alpha=0.6, color=col, label=d, density=True)
    ax.set_title("Model Prob Distribution", fontsize=9)
    ax.legend(fontsize=7)
    _ann(ax, "Same distribution =\nmodel doesn't separate\nOVER from UNDER confidence.")

    ax = axes[0, 2]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        data = res[res["direction"] == d]["ev"].dropna()
        ax.hist(data, bins=15, alpha=0.6, color=col, label=d, density=True)
    ax.set_title("EV Distribution by Direction", fontsize=9)
    ax.legend(fontsize=7)

    ax = axes[1, 0]
    clv_data = res.dropna(subset=["clv"])
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = clv_data[clv_data["direction"] == d]["clv"]
        if len(sub) > 2:
            ax.hist(
                sub,
                bins=12,
                alpha=0.6,
                color=col,
                label=f"{d} (n={len(sub)},μ={sub.mean():.2f}pp)",
                density=True,
            )
    ax.axvline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("CLV Distribution by Direction", fontsize=9)
    ax.legend(fontsize=7)
    _ann(
        ax,
        "Positive CLV = beat closing price.\nROI can still be negative from\noutcome variance or model error.",
    )

    ax = axes[1, 1]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = res[res["direction"] == d].sort_values("date")
        cumulative = sub["profit"].cumsum().reset_index(drop=True)
        ax.plot(cumulative.index, cumulative.values, color=col, lw=2, label=d)
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("Cumulative P&L by Direction", fontsize=9)
    ax.set_xlabel("Pick #")
    ax.set_ylabel("P&L ($)")
    ax.legend(fontsize=7)

    ax = axes[1, 2]
    feat_diff = {}
    snap_num = [c for c in SNAP_NUMERIC if c in snp.columns and snp[c].std() > 0.001]
    for col in snap_num:
        over_won = snp[(snp["direction"] == "OVER") & (snp["won"] == 1)][col].mean()
        over_lost = snp[(snp["direction"] == "OVER") & (snp["won"] == 0)][col].mean()
        diff = over_won - over_lost
        if not np.isnan(diff):
            feat_diff[col.replace("snap_", "")] = diff
    if feat_diff:
        fd = pd.Series(feat_diff).sort_values()
        colors = [P["UNDER"] if v >= 0 else P["OVER"] for v in fd.values]
        ax.barh(fd.index, fd.values, color=colors)
        ax.axvline(0, color=P["dim"], lw=1)
        ax.set_title("OVER: Won minus Lost feature means", fontsize=9)
        ax.set_xlabel("Difference (won - lost means)")
        ax.tick_params(axis="y", labelsize=6)
    _ann(ax, "Green = higher when OVER wins.\nRed = higher when OVER loses.")

    fig.suptitle("SECTION 6: OVER vs UNDER FAILURE ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "06_over_under_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 06_over_under_analysis.png")

    print("\n  OVER/UNDER BREAKDOWN:")
    for d in ["OVER", "UNDER"]:
        sub = res[res["direction"] == d]
        w = (sub["won"] == 1).sum()
        l = (sub["won"] == 0).sum()
        wr = w / (w + l) * 100 if (w + l) else 0
        pnl = sub["profit"].sum()
        roi = pnl / max(sub["wagered"].sum(), 1) * 100
        avg_ev = sub["ev"].mean()
        avg_prob = sub["model_prob"].mean()
        clv_sub = sub.dropna(subset=["clv"])
        avg_clv = clv_sub["clv"].mean() if len(clv_sub) else float("nan")
        beat_clv = (clv_sub["clv"] > 0).mean() * 100 if len(clv_sub) else float("nan")
        print(f"\n  {d}:")
        print(f"    Record:       {w}W-{l}L  ({wr:.1f}% WR)")
        print(f"    P&L:          ${pnl:.2f}  ROI={roi:.1f}%")
        print(f"    Avg EV:       {avg_ev:.1f}%")
        print(f"    Avg Prob:     {avg_prob:.3f}")
        print(f"    Avg CLV:      {avg_clv:.2f}pp  Beat close: {beat_clv:.0f}%")

    over_sub = res[res["direction"] == "OVER"]
    under_sub = res[res["direction"] == "UNDER"]

    def _wr_roi(sub):
        w = (sub["won"] == 1).sum()
        l = (sub["won"] == 0).sum()
        wr = w / (w + l) * 100 if (w + l) else 0
        roi = sub["profit"].sum() / max(sub["wagered"].sum(), 1) * 100
        return round(wr, 1), round(roi, 2)

    over_wr, over_roi = _wr_roi(over_sub)
    under_wr, under_roi = _wr_roi(under_sub)
    return {
        "over_wr": over_wr,
        "over_roi": over_roi,
        "under_wr": under_wr,
        "under_roi": under_roi,
    }


def section7(snp):
    hdr("SECTION 7 — FEATURE IMPORTANCE (Correlation + Point-Biserial)")

    snap_num = [c for c in SNAP_NUMERIC if c in snp.columns and snp[c].std() > 0.001]
    target = "won"

    results = []
    for col in snap_num + ["model_prob", "ev", "kelly_units", "line"]:
        if col not in snp.columns:
            continue
        data = snp[[col, target]].dropna()
        if len(data) < 10:
            continue
        r, p = stats.pointbiserialr(data[target].astype(float), data[col].astype(float))
        results.append({"feature": col.replace("snap_", ""), "corr": r, "pval": p, "n": len(data)})

    if not results:
        print("  Insufficient data for feature importance.")
        return

    df_imp = pd.DataFrame(results).sort_values("corr", key=abs, ascending=False)
    print("\n  TOP FEATURES BY POINT-BISERIAL CORRELATION WITH WON:")
    print(f"  {'Feature':<40} {'Corr':>8} {'p-val':>8} {'n':>5}")
    for _, row in df_imp.head(15).iterrows():
        sig = "**" if row["pval"] < 0.05 else ("*" if row["pval"] < 0.1 else "")
        print(
            f"  {row['feature']:<40} {row['corr']:>8.3f} {row['pval']:>8.3f} {int(row['n']):>5}  {sig}"
        )

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]
    top = df_imp.head(15)
    colors = [P["UNDER"] if v >= 0 else P["OVER"] for v in top["corr"]]
    ax.barh(top["feature"][::-1], top["corr"][::-1], color=colors[::-1])
    ax.axvline(0, color=P["dim"], lw=1)
    ax.set_title("Feature Importance (Point-Biserial r with Won)", fontsize=9)
    ax.set_xlabel("Correlation with Win")

    for i, (_, row) in enumerate(top[::-1].iterrows()):
        if row["pval"] < 0.05:
            ax.text(row["corr"], len(top) - 1 - i, " *", color=P["warn"], fontsize=8)
    _ann(
        ax, "Green = positively correlated\nwith winning.\nRed = negatively correlated.\n* = p<0.05"
    )

    ax = axes[1]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = snp[snp["direction"] == d][["model_prob", "won"]].dropna()
        buckets = pd.cut(sub["model_prob"], bins=np.arange(0.48, 0.82, 0.04))
        wr = sub.groupby(buckets, observed=True)["won"].mean() * 100
        n = sub.groupby(buckets, observed=True)["won"].count()
        mids = [b.mid for b in wr.index]
        ax.plot(mids, wr.values, "o-", color=col, lw=2, ms=6, label=d)
        for x, y, nn in zip(mids, wr.values, n.values):
            if nn >= 2:
                ax.text(x, y + 1.5, f"{nn}", fontsize=5, ha="center")
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.plot([0.48, 0.80], [48, 80], color=P["dim"], lw=1, ls=":", label="Perfect calibration")
    ax.set_title("Win Rate vs Model Probability by Direction", fontsize=9)
    ax.set_xlabel("Model Probability")
    ax.set_ylabel("Actual Win Rate (%)")
    ax.legend(fontsize=7)

    fig.suptitle("SECTION 7: FEATURE IMPORTANCE", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "07_feature_importance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 07_feature_importance.png")

    top1 = df_imp.iloc[0] if len(df_imp) else None
    return {
        "top_feature": top1["feature"] if top1 is not None else None,
        "top_feature_corr": round(float(top1["corr"]), 3) if top1 is not None else None,
        "features_evaluated": len(df_imp),
    }


def section9(res, snp):
    hdr("SECTION 9 — EDGE ANALYSIS")

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    ax = axes[0, 0]
    res_c = res.copy()
    ev_bins = [0, 3, 6, 9, 12, 15, 20, 30, 60]
    res_c["ev_b"] = pd.cut(res_c["ev"], bins=ev_bins)
    roi_ev = res_c.groupby("ev_b", observed=True).apply(
        lambda x: x["profit"].sum() / max(x["wagered"].sum(), 1) * 100
    )
    n_ev = res_c.groupby("ev_b", observed=True)["won"].count()
    ax.bar(
        range(len(roi_ev)),
        roi_ev.values,
        color=[P["UNDER"] if v >= 0 else P["OVER"] for v in roi_ev.values],
    )
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_xticks(range(len(roi_ev)))
    ax.set_xticklabels([str(b) for b in roi_ev.index], rotation=30, fontsize=7)
    ax.set_title("ROI by EV Bucket", fontsize=9)
    ax.set_ylabel("ROI (%)")
    for i, (v, n) in enumerate(zip(roi_ev.values, n_ev.values)):
        ax.text(i, v + 0.5 if v >= 0 else v - 2, f"n={n}", ha="center", fontsize=6)
    _ann(ax, "Rightward trend = EV works.\nFlat/inverted = EV is noise.")

    ax = axes[0, 1]
    wr_ev = res_c.groupby("ev_b", observed=True)["won"].mean() * 100
    ax.bar(
        range(len(wr_ev)),
        wr_ev.values,
        color=[P["UNDER"] if v >= 52.4 else P["OVER"] for v in wr_ev.values],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.set_xticks(range(len(wr_ev)))
    ax.set_xticklabels([str(b) for b in wr_ev.index], rotation=30, fontsize=7)
    ax.set_title("Win Rate by EV Bucket", fontsize=9)
    ax.set_ylabel("WR (%)")
    ax.legend(fontsize=7)

    ax = axes[0, 2]
    thresholds = np.arange(0, 30, 2)
    roi_thresh = []
    n_thresh = []
    for th in thresholds:
        sub = res[res["ev"] >= th]
        roi_t = sub["profit"].sum() / max(sub["wagered"].sum(), 1) * 100
        roi_thresh.append(roi_t)
        n_thresh.append(len(sub))
    ax.plot(thresholds, roi_thresh, "o-", color=P["neutral"], lw=2)
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax2 = ax.twinx()
    ax2.plot(thresholds, n_thresh, "s--", color=P["warn"], lw=1, ms=4, alpha=0.6)
    ax2.set_ylabel("Sample Size", color=P["warn"], fontsize=8)
    ax.set_title("ROI vs Min EV Threshold", fontsize=9)
    ax.set_xlabel("Minimum EV (%)")
    ax.set_ylabel("ROI (%)")
    _ann(
        ax,
        "Find the EV threshold\nwhere ROI maximizes.\nHigher threshold =\nsmaller but better sample?",
    )

    ax = axes[1, 0]
    clv_df = res.dropna(subset=["clv"])
    if len(clv_df) > 5:
        clv_df["clv_b"] = pd.cut(clv_df["clv"], bins=[-5, -2, -1, 0, 1, 2, 5, 10])
        roi_clv = clv_df.groupby("clv_b", observed=True).apply(
            lambda x: x["profit"].sum() / max(x["wagered"].sum(), 1) * 100
        )
        n_clv = clv_df.groupby("clv_b", observed=True)["won"].count()
        ax.bar(
            range(len(roi_clv)),
            roi_clv.values,
            color=[P["UNDER"] if v >= 0 else P["OVER"] for v in roi_clv.values],
        )
        ax.axhline(0, color=P["dim"], lw=1, ls="--")
        ax.set_xticks(range(len(roi_clv)))
        ax.set_xticklabels([str(b) for b in roi_clv.index], rotation=30, fontsize=7)
        ax.set_title("ROI by CLV Bucket", fontsize=9)
        ax.set_ylabel("ROI (%)")
        for i, (v, n) in enumerate(zip(roi_clv.values, n_clv.values)):
            ax.text(i, v + 0.5 if v >= 0 else v - 2, f"n={n}", ha="center", fontsize=6)
        _ann(
            ax,
            "CLV and realized ROI measure different things.\nA short-run divergence does not identify\na directional or calibration defect by itself.",
        )

    ax = axes[1, 1]
    res_c["kelly_b"] = pd.cut(res_c["kelly_units"], bins=[-0.01, 0.01, 0.26, 0.51, 0.76, 1.01, 2.0])
    roi_k = res_c.groupby("kelly_b", observed=True).apply(
        lambda x: x["profit"].sum() / max(x["wagered"].sum(), 1) * 100
    )
    n_k = res_c.groupby("kelly_b", observed=True)["won"].count()
    ax.bar(
        range(len(roi_k)),
        roi_k.values,
        color=[P["UNDER"] if v >= 0 else P["OVER"] for v in roi_k.values],
    )
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_xticks(range(len(roi_k)))
    ax.set_xticklabels([str(b) for b in roi_k.index], rotation=30, fontsize=7)
    ax.set_title("ROI by Kelly Fraction", fontsize=9)
    ax.set_ylabel("ROI (%)")

    ax = axes[1, 2]
    mov_df = res.dropna(subset=["opening_odds", "closing_odds"])
    if len(mov_df) > 5:
        mov_df = mov_df.copy()
        mov_df["line_move"] = mov_df["closing_odds"] - mov_df["opening_odds"]
        mov_df["move_b"] = pd.cut(mov_df["line_move"], bins=[-1, -0.1, -0.02, 0.02, 0.1, 1])
        wr_mov = mov_df.groupby("move_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr_mov)),
            wr_mov["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_mov["mean"]],
        )
        ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
        ax.set_xticks(range(len(wr_mov)))
        ax.set_xticklabels([str(b) for b in wr_mov.index], rotation=30, fontsize=7)
        ax.set_title("Win Rate by Odds Line Movement", fontsize=9)
        ax.set_ylabel("WR (%)")
        _ann(ax, "If steam (sharp money)\nagrees with our pick,\ndoes WR improve?")

    fig.suptitle("SECTION 9: EDGE ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "09_edge_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 09_edge_analysis.png")

    best_idx = int(np.argmax(roi_thresh)) if roi_thresh else None
    return {
        "best_ev_threshold": int(thresholds[best_idx]) if best_idx is not None else None,
        "best_ev_threshold_roi": (
            round(float(roi_thresh[best_idx]), 2) if best_idx is not None else None
        ),
        "best_ev_threshold_n": int(n_thresh[best_idx]) if best_idx is not None else None,
    }


def section11(res):
    hdr("SECTION 11 — CLV ANALYSIS")

    clv_df = res.dropna(subset=["clv", "won"]).copy()
    if len(clv_df) < 5:
        print("  Insufficient CLV data.")
        return

    beat_close = (clv_df["clv"] > 0).sum()
    avg_clv = clv_df["clv"].mean()
    total_clv = len(clv_df)
    roi_pos_clv = (
        clv_df[clv_df["clv"] > 0]["profit"].sum()
        / max(clv_df[clv_df["clv"] > 0]["wagered"].sum(), 1)
        * 100
    )
    roi_neg_clv = (
        clv_df[clv_df["clv"] <= 0]["profit"].sum()
        / max(clv_df[clv_df["clv"] <= 0]["wagered"].sum(), 1)
        * 100
    )

    print(f"\n  CLV records:      {total_clv}")
    print(f"  Avg CLV:          {avg_clv:.2f}pp")
    print(f"  Beat closing:     {beat_close}/{total_clv} ({beat_close/total_clv*100:.0f}%)")
    print(f"  ROI (CLV > 0):   {roi_pos_clv:.1f}%")
    print(f"  ROI (CLV ≤ 0):   {roi_neg_clv:.1f}%")

    if avg_clv > 0 and (roi_pos_clv < 0 or res["profit"].sum() < 0):
        print(f"""
  OBSERVATION:
    Average CLV is POSITIVE (+{avg_clv:.2f}pp) — meaning the model consistently
    gets better prices than the closing line. This is a sign of genuine
    market edge-finding ability.

    Realized ROI is negative over this sample. That divergence does not, by
    itself, identify directional error or a calibration fix: closing-price
    value and realized outcomes converge on different horizons. More resolved
    picks and chronological out-of-sample testing are required.
""")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    ax = axes[0]
    ax.scatter(
        clv_df["clv"],
        clv_df["profit"],
        c=clv_df["won"].map({1: P["UNDER"], 0: P["OVER"]}),
        alpha=0.7,
        s=40,
    )
    ax.axvline(0, color=P["dim"], lw=1, ls="--")
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("CLV vs Profit", fontsize=9)
    ax.set_xlabel("Closing Line Value (pp)")
    ax.set_ylabel("Profit ($)")
    r, p = stats.pearsonr(clv_df["clv"], clv_df["profit"])
    ax.text(0.05, 0.92, f"r={r:.3f} p={p:.3f}", transform=ax.transAxes, fontsize=7, color=P["warn"])
    _ann(ax, "Green=Won Red=Lost.\nPositive correlation =\nCLV predicts profit.")

    ax = axes[1]
    for d, col in [("OVER", P["OVER"]), ("UNDER", P["UNDER"])]:
        sub = clv_df[clv_df["direction"] == d]["clv"]
        if len(sub) > 2:
            ax.hist(
                sub, bins=12, alpha=0.6, color=col, label=f"{d} μ={sub.mean():.2f}pp", density=True
            )
    ax.axvline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("CLV Distribution by Direction", fontsize=9)
    ax.set_xlabel("CLV (pp)")
    ax.legend(fontsize=7)

    ax = axes[2]
    clv_df["clv_b"] = pd.cut(clv_df["clv"], bins=5)
    wr_clv = clv_df.groupby("clv_b", observed=True)["won"].mean() * 100
    n_clv = clv_df.groupby("clv_b", observed=True)["won"].count()
    ax.bar(
        range(len(wr_clv)),
        wr_clv.values,
        color=[P["UNDER"] if v >= 52.4 else P["OVER"] for v in wr_clv.values],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="BE")
    ax.set_xticks(range(len(wr_clv)))
    ax.set_xticklabels([str(b) for b in wr_clv.index], rotation=30, fontsize=7)
    ax.set_title("Win Rate by CLV Bucket", fontsize=9)
    ax.set_ylabel("WR (%)")
    for i, (v, n) in enumerate(zip(wr_clv.values, n_clv.values)):
        ax.text(i, v + 0.5, f"n={n}", ha="center", fontsize=6)

    plt.suptitle("SECTION 11: CLV ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "11_clv_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 11_clv_analysis.png")

    return {
        "avg_clv": round(float(avg_clv), 3),
        "beat_close_pct": round(beat_close / total_clv * 100, 1),
        "roi_clv_positive": round(float(roi_pos_clv), 2),
        "roi_clv_nonpositive": round(float(roi_neg_clv), 2),
    }


def section12(res):
    hdr("SECTION 12 — TEAM ANALYSIS")

    dfs = []
    for side in ["home_team", "away_team"]:
        tmp = res.copy()
        tmp["team"] = tmp[side]
        dfs.append(tmp)
    all_teams = pd.concat(dfs)

    team_stats = (
        all_teams.groupby("team")
        .agg(
            picks=("won", "count"),
            wins=("won", "sum"),
            pnl=("profit", "sum"),
            wagered=("wagered", "sum"),
            avg_ev=("ev", "mean"),
            avg_prob=("model_prob", "mean"),
        )
        .assign(
            wr=lambda x: x["wins"] / x["picks"] * 100,
            roi=lambda x: x["pnl"] / x["wagered"] * 100,
        )
        .query("picks >= 3")
        .sort_values("roi", ascending=False)
    )

    print(f"\n  Teams with ≥ 3 picks: {len(team_stats)}")
    print(f"\n  TOP 5 ROI TEAMS:")
    print(team_stats[["picks", "wr", "roi", "avg_ev"]].head(5).to_string())
    print(f"\n  WORST 5 ROI TEAMS:")
    print(team_stats[["picks", "wr", "roi", "avg_ev"]].tail(5).to_string())

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    ax = axes[0]
    ts = team_stats.sort_values("roi")
    colors = [P["UNDER"] if v >= 0 else P["OVER"] for v in ts["roi"]]
    ax.barh(ts.index, ts["roi"], color=colors)
    ax.axvline(0, color=P["dim"], lw=1)
    ax.set_title("ROI by Team (≥3 picks)", fontsize=9)
    ax.set_xlabel("ROI (%)")
    ax.tick_params(axis="y", labelsize=7)
    _ann(ax, "Teams where model consistently\nfails or succeeds.")

    ax = axes[1]
    ax.scatter(
        team_stats["avg_prob"],
        team_stats["wr"],
        s=team_stats["picks"] * 15,
        alpha=0.7,
        c=[P["UNDER"] if v >= 0 else P["OVER"] for v in team_stats["roi"]],
    )
    ax.plot([0.5, 0.8], [50, 80], color=P["dim"], lw=1, ls="--", label="Perfect calibration")
    ax.axhline(52.4, color=P["warn"], lw=1, ls=":", alpha=0.5)
    ax.set_title("Avg Model Prob vs Actual Win Rate by Team", fontsize=9)
    ax.set_xlabel("Avg Model Prob")
    ax.set_ylabel("Actual Win Rate (%)")
    for team, row in team_stats.iterrows():
        if abs(row["roi"]) > 15:
            ax.annotate(team[:3], (row["avg_prob"], row["wr"]), fontsize=6, color=P["warn"])

    plt.suptitle("SECTION 12: TEAM ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "12_team_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 12_team_analysis.png")

    return {
        "teams_evaluated": len(team_stats),
        "best_team": team_stats.index[0] if len(team_stats) else None,
        "best_team_roi": round(float(team_stats["roi"].iloc[0]), 2) if len(team_stats) else None,
        "worst_team": team_stats.index[-1] if len(team_stats) else None,
        "worst_team_roi": round(float(team_stats["roi"].iloc[-1]), 2) if len(team_stats) else None,
    }


def section19(res, snp):
    hdr("SECTION 19 — BET FILTER OPTIMIZATION (Grid Search)")

    results = []

    filters = {
        "UNDER only": lambda df: df[df["direction"] == "UNDER"],
        "OVER only": lambda df: df[df["direction"] == "OVER"],
        "EV >= 5": lambda df: df[df["ev"] >= 5],
        "EV >= 10": lambda df: df[df["ev"] >= 10],
        "EV >= 15": lambda df: df[df["ev"] >= 15],
        "Kelly >= 0.5": lambda df: df[df["kelly_units"] >= 0.5],
        "Kelly >= 0.25": lambda df: df[df["kelly_units"] >= 0.25],
        "Prob >= 0.55": lambda df: df[df["model_prob"] >= 0.55],
        "Prob >= 0.60": lambda df: df[df["model_prob"] >= 0.60],
        "Line 7.5-8.5": lambda df: df[df["line"].between(7.5, 8.5)],
        "Line 8.0-9.0": lambda df: df[df["line"].between(8.0, 9.0)],
        "Line <= 8.0": lambda df: df[df["line"] <= 8.0],
        "Line >= 9.0": lambda df: df[df["line"] >= 9.0],
        "CLV > 0": lambda df: df[df["clv"] > 0],
        "CLV > 1": lambda df: df[df["clv"] > 1],
    }

    combined = {
        "UNDER + EV>=5": lambda df: df[(df["direction"] == "UNDER") & (df["ev"] >= 5)],
        "UNDER + EV>=10": lambda df: df[(df["direction"] == "UNDER") & (df["ev"] >= 10)],
        "UNDER + Prob>=0.55": lambda df: df[
            (df["direction"] == "UNDER") & (df["model_prob"] >= 0.55)
        ],
        "UNDER + Line<=8.5": lambda df: df[(df["direction"] == "UNDER") & (df["line"] <= 8.5)],
        "UNDER + CLV>0": lambda df: df[(df["direction"] == "UNDER") & (df["clv"] > 0)],
        "OVER + EV>=15": lambda df: df[(df["direction"] == "OVER") & (df["ev"] >= 15)],
        "EV>=5 + Prob>=0.55": lambda df: df[(df["ev"] >= 5) & (df["model_prob"] >= 0.55)],
    }

    all_filters = {**filters, **combined}

    for name, fn in all_filters.items():
        sub = fn(res.dropna(subset=["won"]))
        if len(sub) < 3:
            continue
        w = (sub["won"] == 1).sum()
        l = (sub["won"] == 0).sum()
        wr = w / (w + l) * 100 if (w + l) else 0
        roi = sub["profit"].sum() / max(sub["wagered"].sum(), 1) * 100
        avg_ev = sub["ev"].mean()
        results.append({"filter": name, "n": len(sub), "wr": wr, "roi": roi, "avg_ev": avg_ev})

    df_res = pd.DataFrame(results).sort_values("roi", ascending=False)

    print(f"\n  {'Filter':<35} {'n':>4} {'WR':>7} {'ROI':>8} {'AvgEV':>7}")
    print("  " + "-" * 63)
    for _, row in df_res.iterrows():
        marker = " " if row["roi"] > 0 and row["n"] >= 5 else ""
        print(
            f"  {row['filter']:<35} {int(row['n']):>4} {row['wr']:>6.1f}% {row['roi']:>7.1f}%  {row['avg_ev']:>6.1f}%{marker}"
        )

    top = df_res[df_res["n"] >= 5].head(15)
    if len(top):
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = [P["UNDER"] if v >= 0 else P["OVER"] for v in top["roi"]]
        ax.barh(top["filter"][::-1], top["roi"][::-1], color=colors[::-1])
        ax.axvline(0, color=P["dim"], lw=1)
        for i, (_, row) in enumerate(top[::-1].iterrows()):
            ax.text(
                row["roi"] + 0.2,
                i,
                f"n={int(row['n'])} WR={row['wr']:.0f}%",
                fontsize=7,
                va="center",
            )
        ax.set_title("Section 19: Bet Filter ROI Grid Search (n≥5)", fontsize=10)
        ax.set_xlabel("ROI (%)")
        plt.tight_layout()
        plt.savefig(FIG_DIR / "19_filter_optimization.png", dpi=150, bbox_inches="tight")
        plt.close()
        print("  → Saved: 19_filter_optimization.png")

    best = df_res.iloc[0] if len(df_res) else None
    return {
        "filters_evaluated": len(df_res),
        "best_filter": best["filter"] if best is not None else None,
        "best_filter_roi": round(float(best["roi"]), 2) if best is not None else None,
        "best_filter_n": int(best["n"]) if best is not None else None,
    }


def run():
    from loader import run_section, skip_section

    try:
        df = load_totals()
        res = resolved(df)
        snp = snapped(res)
    except Exception as e:
        reason = f"shared data load failed: {e}"
        for sid, title in [
            ("s6", "Over vs Under"),
            ("s7", "Feature Importance"),
            ("s9", "Edge Analysis"),
            ("s11", "CLV Analysis"),
            ("s12", "Team Analysis"),
            ("s19", "Filter Grid Search"),
        ]:
            skip_section(sid, title, reason)
        return
    run_section("s6", "Over vs Under", section6, res, snp)
    run_section("s7", "Feature Importance", section7, snp)
    run_section("s9", "Edge Analysis", section9, res, snp)
    run_section("s11", "CLV Analysis", section11, res)
    run_section("s12", "Team Analysis", section12, res)
    run_section("s19", "Filter Grid Search", section19, res, snp)


if __name__ == "__main__":
    run()
