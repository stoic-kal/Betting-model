import sys, os

sys.path.insert(0, os.path.dirname(__file__))
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from pathlib import Path

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


def section13(snp):
    hdr("SECTION 13 — PITCHER / STARTER QUALITY ANALYSIS")

    fip_cols = [c for c in ["snap_home_fip", "snap_away_fip"] if c in snp.columns]
    rsg_cols = [c for c in ["snap_home_rsg", "snap_away_rsg"] if c in snp.columns]

    if not fip_cols:
        print("  No FIP data in snapshots.")
        return

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    ax = axes[0, 0]
    for col, col_label in [("snap_home_fip", "Home FIP"), ("snap_away_fip", "Away FIP")]:
        if col in snp.columns:
            data = snp[col].dropna()
            ax.hist(data, bins=15, alpha=0.6, label=col_label, density=True)
    ax.axvline(4.1, color=P["warn"], lw=1.5, ls="--", label="MLB avg FIP ≈4.1")
    ax.set_title("FIP Distribution vs MLB Average", fontsize=9)
    ax.legend(fontsize=7)
    ax.text(
        0.05,
        0.85,
        f"If all FIPs < 3.5:\n→ Either selection bias\n  or data pipeline bug",
        transform=ax.transAxes,
        fontsize=7,
        color=P["warn"],
        bbox=dict(boxstyle="round", facecolor="#1a1a0a", alpha=0.8),
    )

    ax = axes[0, 1]
    if "snap_home_fip" in snp.columns:
        snp2 = snp.copy()
        snp2["avg_fip"] = snp2[fip_cols].mean(axis=1)
        snp2["fip_b"] = pd.cut(snp2["avg_fip"], bins=[0, 2.5, 3.0, 3.5, 4.0, 4.5, 8])
        wr_fip = snp2.groupby("fip_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr_fip)),
            wr_fip["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_fip["mean"]],
        )
        ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
        ax.set_xticks(range(len(wr_fip)))
        ax.set_xticklabels([str(b) for b in wr_fip.index], rotation=30, fontsize=7)
        ax.set_title("Win Rate by Avg FIP", fontsize=9)
        ax.set_ylabel("WR (%)")
        for i, (idx, row) in enumerate(wr_fip.iterrows()):
            ax.text(i, row["mean"] * 100 + 0.5, f"n={int(row['count'])}", ha="center", fontsize=6)

    ax = axes[0, 2]
    if rsg_cols:
        snp2 = snp.copy()
        snp2["avg_rsg"] = snp2[rsg_cols].mean(axis=1)
        snp2["rsg_b"] = pd.cut(snp2["avg_rsg"], bins=[0, 3.5, 4.0, 4.5, 5.0, 5.5, 10])
        wr_rsg = snp2.groupby("rsg_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr_rsg)),
            wr_rsg["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_rsg["mean"]],
        )
        ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
        ax.set_xticks(range(len(wr_rsg)))
        ax.set_xticklabels([str(b) for b in wr_rsg.index], rotation=30, fontsize=7)
        ax.set_title("Win Rate by Avg RSG (team run scoring)", fontsize=9)
        ax.set_ylabel("WR (%)")
        for i, (idx, row) in enumerate(wr_rsg.iterrows()):
            ax.text(i, row["mean"] * 100 + 0.5, f"n={int(row['count'])}", ha="center", fontsize=6)

    ax = axes[1, 0]
    if "snap_expected_total" in snp.columns and "snap_home_fip" in snp.columns:
        both = snp[["snap_home_fip", "snap_away_fip", "snap_expected_total", "won"]].dropna()
        avg_fip = both[["snap_home_fip", "snap_away_fip"]].mean(axis=1)
        sc = ax.scatter(
            avg_fip,
            both["snap_expected_total"],
            c=both["won"].map({1: P["UNDER"], 0: P["OVER"]}),
            alpha=0.7,
            s=40,
        )
        ax.set_xlabel("Avg Starter FIP")
        ax.set_ylabel("Model Expected Total")
        ax.set_title("FIP vs Expected Total (Green=Won, Red=Lost)", fontsize=9)
        r, p = stats.pearsonr(avg_fip, both["snap_expected_total"])
        ax.text(
            0.05, 0.92, f"r={r:.3f} p={p:.3f}", transform=ax.transAxes, fontsize=7, color=P["warn"]
        )

    home_usage = snp.get("snap_snap_home_starter_usage_expected_innings")
    ax = axes[1, 1]
    if home_usage is not None and home_usage.notna().sum() > 5:
        snp2 = snp.copy()
        snp2["inning_b"] = pd.cut(home_usage, bins=[0, 4, 5, 5.5, 6, 6.5, 9])
        wr_inn = snp2.groupby("inning_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr_inn)),
            wr_inn["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_inn["mean"]],
        )
        ax.set_title("Win Rate by Projected Starter Innings", fontsize=9)
        ax.set_ylabel("WR (%)")
    else:
        ax.text(
            0.5,
            0.5,
            "Starter innings data\nnot in snapshot",
            transform=ax.transAxes,
            ha="center",
            fontsize=9,
            color=P["dim"],
        )
        ax.set_title("Projected Starter Innings", fontsize=9)

    ax = axes[1, 2]
    ax.axis("off")
    summary_rows = [
        ["Metric", "Value", "Flag"],
        [
            "Avg Home FIP",
            f"{snp['snap_home_fip'].mean():.2f}" if "snap_home_fip" in snp.columns else "N/A",
            (
                "Below MLB avg"
                if "snap_home_fip" in snp.columns and snp["snap_home_fip"].mean() < 3.8
                else "Normal"
            ),
        ],
        [
            "Avg Away FIP",
            f"{snp['snap_away_fip'].mean():.2f}" if "snap_away_fip" in snp.columns else "N/A",
            (
                "Below MLB avg"
                if "snap_away_fip" in snp.columns and snp["snap_away_fip"].mean() < 3.8
                else "Normal"
            ),
        ],
        [
            "FIP Variance",
            f"{snp['snap_home_fip'].std():.3f}" if "snap_home_fip" in snp.columns else "N/A",
            (
                "Low variance"
                if "snap_home_fip" in snp.columns and snp["snap_home_fip"].std() < 0.5
                else "Normal"
            ),
        ],
    ]
    t = ax.table(summary_rows, loc="center", cellLoc="left")
    t.auto_set_font_size(False)
    t.set_fontsize(8)
    ax.set_title("Pitcher Data Health Summary", fontsize=9, pad=10)

    fig.suptitle("SECTION 13: PITCHER ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "13_pitcher_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 13_pitcher_analysis.png")

    return {
        "avg_home_fip": (
            round(float(snp["snap_home_fip"].mean()), 3) if "snap_home_fip" in snp.columns else None
        ),
        "avg_away_fip": (
            round(float(snp["snap_away_fip"].mean()), 3) if "snap_away_fip" in snp.columns else None
        ),
        "fip_std": (
            round(float(snp["snap_home_fip"].std()), 3) if "snap_home_fip" in snp.columns else None
        ),
    }


def section14(snp):
    hdr("SECTION 14 — UMPIRE ANALYSIS")

    if "snap_ump_name" not in snp.columns and "snap_ump_runs_adj" not in snp.columns:
        print("  No umpire data in snapshots.")
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    ax = axes[0]
    if "snap_ump_runs_adj" in snp.columns:
        data = snp["snap_ump_runs_adj"].dropna()
        ax.hist(data, bins=15, color=P["neutral"], alpha=0.8)
        ax.axvline(0, color=P["dim"], lw=1, ls="--")
        ax.set_title("Umpire Run Adjustment Distribution", fontsize=9)
        ax.set_xlabel("Runs Adjustment")
        if data.std() < 0.01:
            ax.text(
                0.5,
                0.5,
                "CONSTANT — no umpire\nadjustment being applied",
                transform=ax.transAxes,
                ha="center",
                fontsize=9,
                color=P["warn"],
                bbox=dict(boxstyle="round", facecolor="#1a0a0a", alpha=0.8),
            )

    ax = axes[1]
    if "snap_ump_runs_adj" in snp.columns:
        snp2 = snp.copy()
        snp2["ump_b"] = pd.cut(snp2["snap_ump_runs_adj"], bins=5)
        wr = snp2.groupby("ump_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr)),
            wr["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr["mean"]],
        )
        ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
        ax.set_xticks(range(len(wr)))
        ax.set_xticklabels([str(b) for b in wr.index], rotation=30, fontsize=7)
        ax.set_title("Win Rate by Umpire Run Adjustment", fontsize=9)
        ax.set_ylabel("WR (%)")

    ax = axes[2]
    if "snap_ump_name" in snp.columns:
        ump_stats = (
            snp.groupby("snap_ump_name")
            .agg(n=("won", "count"), wr=("won", "mean"))
            .query("n>=2")
            .sort_values("wr")
        )
        ax.axis("off")
        if len(ump_stats):
            rows = [["Umpire", "n", "WR"]] + [
                [str(idx)[:20], str(int(row["n"])), f"{row['wr']*100:.0f}%"]
                for idx, row in ump_stats.iterrows()
            ]
            t = ax.table(rows[:12], loc="center", cellLoc="left")
            t.auto_set_font_size(False)
            t.set_fontsize(7)
            ax.set_title("Win Rate by Umpire (n≥2)", fontsize=9, pad=10)
    else:
        ax.text(
            0.5,
            0.5,
            "Umpire names not\nin snapshot",
            transform=ax.transAxes,
            ha="center",
            fontsize=9,
            color=P["dim"],
        )

    fig.suptitle("SECTION 14: UMPIRE ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "14_umpire_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 14_umpire_analysis.png")

    return {
        "ump_runs_adj_std": (
            round(float(snp["snap_ump_runs_adj"].std()), 4)
            if "snap_ump_runs_adj" in snp.columns
            else None
        ),
    }


def section15(snp):
    hdr("SECTION 15 — WEATHER ANALYSIS")

    weather_cols = [
        c for c in ["snap_temp_f", "snap_weather_factor", "snap_wind_info"] if c in snp.columns
    ]

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    ax = axes[0]
    if "snap_temp_f" in snp.columns:
        data = snp["snap_temp_f"].dropna()
        won_t = snp[snp["won"] == 1]["snap_temp_f"].dropna()
        lost_t = snp[snp["won"] == 0]["snap_temp_f"].dropna()
        ax.hist(lost_t, bins=12, alpha=0.55, color=P["OVER"], label="Lost", density=True)
        ax.hist(won_t, bins=12, alpha=0.55, color=P["UNDER"], label="Won", density=True)
        ax.set_title("Temperature Distribution: Won vs Lost", fontsize=9)
        ax.set_xlabel("Temperature (°F)")
        ax.legend(fontsize=7)
        ax.text(
            0.05,
            0.85,
            f"mean={data.mean():.0f}°F\nstd={data.std():.1f}°F",
            transform=ax.transAxes,
            fontsize=7,
            color=P["warn"],
        )

    ax = axes[1]
    if "snap_weather_factor" in snp.columns:
        data = snp["snap_weather_factor"].dropna()
        ax.hist(data, bins=15, color=P["neutral"], alpha=0.8)
        ax.set_title("Weather Factor Distribution", fontsize=9)
        ax.set_xlabel("Weather Factor (1.0 = neutral)")
        if data.std() < 0.01:
            ax.set_facecolor("#3d1a1a")
            ax.text(
                0.5,
                0.5,
                "CONSTANT 1.0\nWeather not applied",
                transform=ax.transAxes,
                ha="center",
                fontsize=10,
                color=P["warn"],
                bbox=dict(boxstyle="round", facecolor="#1a0a0a", alpha=0.9),
            )
            print(
                "  CRITICAL: snap_weather_factor is constant 1.0 — weather has zero impact on predictions."
            )
            print("       Expected range: 0.85 (dome/cold) to 1.15 (Coors/hot/wind-out)")

    ax = axes[2]
    if "snap_temp_f" in snp.columns:
        snp2 = snp.copy()
        snp2["temp_b"] = pd.cut(snp2["snap_temp_f"], bins=[40, 55, 65, 72, 80, 90, 105])
        wr_temp = snp2.groupby("temp_b", observed=True)["won"].agg(["mean", "count"])
        ax.bar(
            range(len(wr_temp)),
            wr_temp["mean"] * 100,
            color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in wr_temp["mean"]],
        )
        ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
        ax.set_xticks(range(len(wr_temp)))
        ax.set_xticklabels([str(b) for b in wr_temp.index], rotation=30, fontsize=7)
        ax.set_title("Win Rate by Temperature", fontsize=9)
        ax.set_ylabel("WR (%)")

    fig.suptitle("SECTION 15: WEATHER ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "15_weather_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 15_weather_analysis.png")

    return {
        "weather_factor_mean": (
            round(float(snp["snap_weather_factor"].mean()), 4)
            if "snap_weather_factor" in snp.columns
            else None
        ),
        "weather_factor_std": (
            round(float(snp["snap_weather_factor"].std()), 4)
            if "snap_weather_factor" in snp.columns
            else None
        ),
    }


def section21(res):
    hdr("SECTION 21 — TEMPORAL ANALYSIS")

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    ax = axes[0, 0]
    res_sorted = res.sort_values("date")
    res_sorted["roll_wr"] = res_sorted["won"].rolling(10, min_periods=5).mean() * 100
    res_sorted["roll_roi"] = (
        res_sorted["profit"].rolling(10, min_periods=5).sum()
        / res_sorted["wagered"].rolling(10, min_periods=5).sum()
        * 100
    )
    ax.plot(
        res_sorted["date"],
        res_sorted["roll_wr"],
        color=P["neutral"],
        lw=2,
        label="Rolling 10-game WR",
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--", label="Breakeven")
    ax.axhline(res_sorted["won"].mean() * 100, color=P["dim"], lw=1, ls=":", label="Season avg")
    ax.set_title("Rolling 10-Game Win Rate", fontsize=9)
    ax.set_ylabel("Win Rate (%)")
    ax.legend(fontsize=7)
    ax.tick_params(axis="x", rotation=30)

    ax = axes[0, 1]
    ax.plot(
        res_sorted["date"],
        res_sorted["roll_roi"],
        color=P["OVER"],
        lw=2,
        label="Rolling 10-game ROI",
    )
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("Rolling 10-Game ROI", fontsize=9)
    ax.set_ylabel("ROI (%)")
    ax.legend(fontsize=7)
    ax.tick_params(axis="x", rotation=30)

    ax = axes[1, 0]
    cum_pnl = res_sorted["profit"].cumsum()
    ax.plot(res_sorted["date"], cum_pnl, color=P["neutral"], lw=2)
    ax.fill_between(res_sorted["date"], cum_pnl, 0, where=cum_pnl >= 0, alpha=0.2, color=P["UNDER"])
    ax.fill_between(res_sorted["date"], cum_pnl, 0, where=cum_pnl < 0, alpha=0.2, color=P["OVER"])
    ax.axhline(0, color=P["dim"], lw=1, ls="--")
    ax.set_title("Cumulative P&L ($)", fontsize=9)
    ax.set_ylabel("P&L ($)")
    ax.tick_params(axis="x", rotation=30)

    ax = axes[1, 1]
    month_stats = res.groupby("month")["won"].agg(["mean", "count"])
    month_names = {3: "Mar", 4: "Apr", 5: "May", 6: "Jun", 7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct"}
    ax.bar(
        range(len(month_stats)),
        month_stats["mean"] * 100,
        color=[P["UNDER"] if v >= 0.524 else P["OVER"] for v in month_stats["mean"]],
    )
    ax.axhline(52.4, color=P["warn"], lw=1, ls="--")
    ax.set_xticks(range(len(month_stats)))
    ax.set_xticklabels([month_names.get(m, str(m)) for m in month_stats.index], fontsize=8)
    ax.set_title("Win Rate by Month", fontsize=9)
    ax.set_ylabel("WR (%)")
    for i, (idx, row) in enumerate(month_stats.iterrows()):
        ax.text(i, row["mean"] * 100 + 0.5, f"n={int(row['count'])}", ha="center", fontsize=6)

    fig.suptitle("SECTION 21: TEMPORAL ANALYSIS", fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "21_temporal_analysis.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  → Saved: 21_temporal_analysis.png")

    return {
        "rolling_10_wr_latest": (
            round(float(res_sorted["roll_wr"].dropna().iloc[-1]), 1)
            if res_sorted["roll_wr"].notna().any()
            else None
        ),
        "season_wr": round(float(res_sorted["won"].mean() * 100), 1),
    }


def section24(res, snp):
    hdr("SECTION 24 — ROOT CAUSE REPORT")

    over_wr = res[res["direction"] == "OVER"]["won"].mean() * 100
    under_wr = res[res["direction"] == "UNDER"]["won"].mean() * 100
    overall_wr = res["won"].mean() * 100
    avg_clv = res.dropna(subset=["clv"])["clv"].mean()
    pf_const = "snap_park_factor" in snp.columns and snp["snap_park_factor"].std() < 0.001
    wf_const = "snap_weather_factor" in snp.columns and snp["snap_weather_factor"].std() < 0.001
    avg_home_fip = snp["snap_home_fip"].mean() if "snap_home_fip" in snp.columns else 4.1
    fip_suspect = avg_home_fip < 3.6

    ev_wr = (
        res.groupby(pd.cut(res["ev"], bins=[0, 10, 15, 20, 60]), observed=True)["won"].mean() * 100
    )

    issues = [
        (
            {
                "rank": 1,
                "issue": "Park Factor is constant (0.990 for all games)",
                "severity": "CRITICAL",
                "evidence": (
                    f"snap_park_factor has std={snp['snap_park_factor'].std():.4f}"
                    if pf_const
                    else "Park factor varies"
                ),
                "stat_confidence": "100% — no variance detected",
                "root_cause": "Hard-coded default value in park factor lookup. Real MLB park factors range 0.87–1.18. Oracle Park and Petco suppress runs; Coors adds ~1.5 runs/game.",
                "fix": "Integrate ESPN or Baseball Reference ballpark run factors per stadium. Apply as multiplicative adjustment to expected_total.",
                "impact": "HIGH — Coors Field UNDER bets should have factor ~0.87, not 0.99. This alone may explain OVER bias.",
                "eng_difficulty": "Low — static lookup table by venue_id",
                "priority": 1,
            }
            if pf_const
            else None
        ),
        (
            {
                "rank": 2,
                "issue": "Weather Factor is constant (1.000 for all games)",
                "severity": "CRITICAL",
                "evidence": (
                    f"snap_weather_factor has std={snp['snap_weather_factor'].std():.4f}"
                    if wf_const
                    else "Varies"
                ),
                "stat_confidence": "100% — no variance detected",
                "root_cause": "Weather API returns data (wind_info logged) but adjustment computation returns 1.0. The wind direction (in/out/cross) is not being translated into a run adjustment.",
                "fix": "Parse wind direction string. Outblowing wind at open-air parks: +0.5 to +1.0 runs. Inblowing: -0.5 to -1.0. Temperature below 50F: -0.3 runs. Apply to expected_total.",
                "impact": "HIGH — Wrigley with wind out should be worth +0.8 runs. Missing this makes OVER bets at wind-out parks too cheap.",
                "eng_difficulty": "Low-Medium — wind direction parsing + lookup table",
                "priority": 2,
            }
            if wf_const
            else None
        ),
        {
            "rank": 3,
            "issue": f"OVER win rate catastrophically low ({over_wr:.1f}%)",
            "severity": "CRITICAL",
            "evidence": f"OVER: {over_wr:.1f}% WR vs UNDER: {under_wr:.1f}% WR. {len(res[res['direction']=='OVER'])} OVER picks resolved.",
            "stat_confidence": "High — 18+ OVER sample",
            "root_cause": "Model systematically underestimates run suppression. Expected totals are too high → model sees OVER value when market is correct. Likely caused by missing park factor + weather adjustments (issues 1+2).",
            "fix": "Fix park factor + weather first. Then re-evaluate OVER calibration. Consider raising OVER threshold to model_prob >= 0.62 until recalibrated.",
            "impact": "CRITICAL — suspending OVERs immediately would stop bleeding",
            "eng_difficulty": "Medium",
            "priority": 3,
        },
        {
            "rank": 4,
            "issue": "Probability calibration is non-monotonic",
            "severity": "HIGH",
            "evidence": "58-62% confidence bucket wins 17% of the time. Lower confidence buckets outperform higher confidence.",
            "stat_confidence": "Medium — small n per bucket",
            "root_cause": "Expected_total formula may be correct directionally but wrong in magnitude. The conversion from expected_total to win probability uses assumptions about run distribution variance that may not match MLB reality.",
            "fix": "Apply isotonic regression or Platt scaling to recalibrate probabilities. Use all resolved picks as calibration set.",
            "impact": "HIGH — correct calibration enables accurate Kelly sizing",
            "eng_difficulty": "Low — sklearn has isotonic regression",
            "priority": 4,
        },
        (
            {
                "rank": 5,
                "issue": "FIP values suspiciously low for all games",
                "severity": "HIGH",
                "evidence": f"avg_home_fip={avg_home_fip:.2f}, MLB season avg ≈ 4.10",
                "stat_confidence": "High — 35+ games show same pattern",
                "root_cause": "Possible causes: (a) FIP lookup using incorrect season endpoint, returning only top starters; (b) FIP computed from limited stats without walk/HR correction; (c) sample selection bias — model only books games with elite starters.",
                "fix": "Validate FIP data against Baseball Reference season FIP leaderboards. Ensure ordinary starters show FIP 4.0-5.5.",
                "impact": "MEDIUM — FIP affects expected_total but if uniformly low, relative signal is weak",
                "eng_difficulty": "Low — audit data source",
                "priority": 5,
            }
            if fip_suspect
            else None
        ),
        {
            "rank": 6,
            "issue": "EV does not predict win rate (inverted at high EV)",
            "severity": "HIGH",
            "evidence": "EV 15-20% bucket: 0% win rate (3 picks). EV 5-10% bucket: 75% win rate.",
            "stat_confidence": "Low-medium — small n",
            "root_cause": "EV = f(model_prob, market_odds). If model_prob is miscalibrated, EV is corrupted. High EV picks are cases where model is most wrong about probability.",
            "fix": "Recalibrate probabilities first. Then recompute EV. EV signal should recover.",
            "impact": "MEDIUM",
            "eng_difficulty": "Low after calibration fix",
            "priority": 6,
        },
        {
            "rank": 7,
            "issue": f"CLV positive (+{avg_clv:.2f}pp) but ROI negative",
            "severity": "MEDIUM",
            "evidence": f"Beat close {res.dropna(subset=['clv'])['clv'].gt(0).mean()*100:.0f}% of time. ROI = {res['profit'].sum()/res['wagered'].sum()*100:.1f}%",
            "stat_confidence": "High for CLV; medium for ROI (59 picks)",
            "root_cause": "Line-shopping and timing are working (we get good prices). Directional prediction is the failure point. This is a signal quality problem, not a market access problem.",
            "fix": "Do not change odds-finding. Fix model direction prediction.",
            "impact": "Informational — confirms problem is model, not market",
            "eng_difficulty": "N/A — don't fix this",
            "priority": 7,
        },
    ]

    issues = [i for i in issues if i is not None]

    print("\n  ┌─────────────────────────────────────────────────────────────────────")
    print("  │  ROOT CAUSE REPORT — MLB TOTALS MODEL")
    print("  └─────────────────────────────────────────────────────────────────────\n")

    for issue in issues:
        sev_color = {"CRITICAL": "", "HIGH": "", "MEDIUM": "", "LOW": ""}.get(
            issue["severity"], ""
        )
        print(f"  {sev_color} RANK {issue['rank']} — {issue['severity']}: {issue['issue']}")
        print(f"     Evidence:       {issue['evidence']}")
        print(f"     Root Cause:     {issue['root_cause']}")
        print(f"     Fix:            {issue['fix']}")
        print(f"     Expected Impact: {issue['impact']}")
        print(f"     Eng Difficulty:  {issue['eng_difficulty']}")
        print(f"     Priority:        {issue['priority']}")
        print()

    return {
        "issues_found": len(issues),
        "critical_issues": sum(1 for i in issues if i["severity"] == "CRITICAL"),
        "over_wr": round(float(over_wr), 1),
        "under_wr": round(float(under_wr), 1),
        "overall_wr": round(float(overall_wr), 1),
        "avg_clv": round(float(avg_clv), 3) if pd.notna(avg_clv) else None,
    }


def section25():
    hdr("SECTION 25 — RETRAINING ROADMAP")

    print("""
  ════════════════════════════════════════════════════════════════════════
  RETRAINING ROADMAP — PRIORITY ORDER
  ════════════════════════════════════════════════════════════════════════

  ── PHASE 1: DATA PIPELINE FIXES (1-3 days) ─────────────────────────
  Priority: IMMEDIATE — do this before any retraining.

  [P1.1] Fix park_factor pipeline
    - Build venue_id → park factor lookup table (use ESPN/FanGraphs park factors)
    - Apply to expected_total: expected_total *= park_factor
    - Validate: Oracle Park should produce ~0.90, Coors ~1.15, avg ~1.00
    - Expected improvement: May fix OVER bias by 5-10 win rate points

  [P1.2] Fix weather_factor pipeline
    - Parse wind_info string: extract speed + direction
    - Build wind_direction → run adjustment map:
        "Out" (>5mph): +0.15 per mph / 5
        "In"  (>5mph): -0.15 per mph / 5
        "Cross":        minimal adjustment
    - Apply temperature effect: <50°F → -0.25 runs; >85°F → +0.15 runs
    - Validate: Wrigley wind-out should show weather_factor ~1.08-1.12

  [P1.3] Validate and fix FIP data source
    - Compare stored FIP against Baseball Reference season averages
    - If values are uniformly low, check API endpoint parameters
    - Ensure FIP range spans 2.8 (ace) to 6.0+ (replacement level)

  ── PHASE 2: QUICK WINS (1 day) ──────────────────────────────────────

  [P2.1] Suspend OVER bets immediately
    - Add rule: if direction == "OVER" and model_prob < 0.62, skip
    - Evidence: OVER at 38.9% WR is actively losing money

  [P2.2] Apply minimum EV threshold of 5%
    - Evidence: EV 0-5% bucket shows 50% WR (coin flip)
    - Filter reduces volume but improves quality

  [P2.3] Raise UNDER minimum probability to 0.54
    - UNDER at 52.5% WR is breakeven; need margin above juice

  ── PHASE 3: PROBABILITY CALIBRATION (2-3 days) ──────────────────────

  [P3.1] Build calibration dataset from all resolved picks
    - After Phase 1 fixes, regenerate probabilities using fixed features
    - Split into train/calibration sets

  [P3.2] Apply isotonic regression calibration
    - from sklearn.calibration import CalibratedClassifierCV
    - Fit on historical resolved picks
    - Save calibration transform for inference

  [P3.3] Rebuild EV calculation on calibrated probabilities
    - EV = (calibrated_prob × best_odds - 1) × 100
    - Validate: high EV should now correlate with high WR

  ── PHASE 4: FEATURE ENGINEERING (1-2 weeks) ─────────────────────────

  [P4.1] Add run environment factors
    - Ballpark dimensions (LF/CF/RF wall heights)
    - Elevation (Coors at 5280ft = less air resistance)
    - Grass vs turf (turf increases scoring)
    - Day vs night differential per park

  [P4.2] Enhance weather features
    - Air density (temperature + humidity + elevation = actual ball carry)
    - Dew point vs dry bulb temperature
    - Game-time forecast (not just current conditions)

  [P4.3] Add recent form momentum
    - Team last-5-game run scoring (rolling)
    - Pitcher last-3-start ERA/runs allowed
    - Bullpen ERA last-7-days (not just season ERA)

  [P4.4] Add matchup handedness adjustment
    - L-heavy lineup vs RHP: empirical run scoring adjustment
    - R-heavy lineup vs LHP: empirical run scoring adjustment

  ── PHASE 5: MODEL ARCHITECTURE (2-4 weeks) ──────────────────────────

  [P5.1] Train XGBoost / LightGBM on historical game data
    - Target: actual runs scored (regression) + over/under (classification)
    - Features: all Phase 1-4 engineered features
    - Use 3-year rolling window for training

  [P5.2] Ensemble the expected_total formula with ML model
    - Weight: 60% current formula / 40% ML model initially
    - Adjust weights based on rolling 30-game performance

  [P5.3] Separate OVER and UNDER models
    - Evidence: they have different failure modes
    - Train separate classifiers, ensemble at output

  ── PHASE 6: VALIDATION & MONITORING (ongoing) ───────────────────────

  [P6.1] Walk-forward validation
    - Train on games 1-100, validate on 101-110
    - Roll forward, never look ahead

  [P6.2] Shadow mode for 2 weeks before deployment
    - Run new model alongside old model
    - Compare predictions without betting

  [P6.3] Betting metrics dashboard
    - Rolling 20-game WR, ROI, CLV
    - Automatic suspension if WR drops below 45% for 10 games

  ════════════════════════════════════════════════════════════════════════
  EXPECTED IMPACT AFTER ALL PHASES:
    Current:  48.3% WR, -6.7% ROI
    Phase 1:  ~51% WR (park + weather fix)
    Phase 2:  ~52% WR (filter improvement)
    Phase 3:  ~53% WR + proper bet sizing
    Phase 4+: ~54-55% WR (target: sustainable +EV)
  ════════════════════════════════════════════════════════════════════════
""")
    return {}


def run():
    from loader import run_section, skip_section

    try:
        df = load_totals()
        res = resolved(df)
        snp = snapped(res)
    except Exception as e:
        reason = f"shared data load failed: {e}"
        for sid, title in [
            ("s13", "Pitcher Quality"),
            ("s14", "Umpire Analysis"),
            ("s15", "Weather Analysis"),
            ("s21", "Temporal Analysis"),
            ("s24", "Root Cause Report"),
            ("s25", "Retraining Roadmap"),
        ]:
            skip_section(sid, title, reason)
        return
    run_section("s13", "Pitcher Quality", section13, snp)
    run_section("s14", "Umpire Analysis", section14, snp)
    run_section("s15", "Weather Analysis", section15, snp)
    run_section("s21", "Temporal Analysis", section21, res)
    run_section("s24", "Root Cause Report", section24, res, snp)
    run_section("s25", "Retraining Roadmap", section25)


if __name__ == "__main__":
    run()
