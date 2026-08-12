import math

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1); score = 0.0
    for index, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (p >= lo) & (p <= hi if index == bins - 1 else p < hi)
        if mask.any(): score += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(score)


def classification_metrics(frame, bins=10):
    y = frame.actual.astype(int).to_numpy(); p = frame.probability.to_numpy()
    return {"n": len(frame), "log_loss": float(log_loss(y, p)),
            "brier": float(brier_score_loss(y, p)),
            "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
            "ece": ece(y, p, bins), "win_rate": float(frame.won.mean()),
            "profit_units": float(frame.flat_profit.sum()),
            "roi": float(frame.flat_profit.sum() / frame.flat_stake.sum()) if frame.flat_stake.sum() else None,
            "kelly_profit_units": float(frame.kelly_profit.sum()),
            "kelly_roi": float(frame.kelly_profit.sum() / frame.kelly_stake.sum()) if frame.kelly_stake.sum() else None}


def calibration(frame, bins=10):
    work = frame.copy(); work["bucket"] = pd.cut(work.probability, np.linspace(0,1,bins+1), include_lowest=True)
    rows=[]
    for bucket, group in work.groupby("bucket", observed=True):
        rows.append({"bucket": str(bucket), "n": len(group), "predicted": float(group.probability.mean()),
                     "observed": float(group.actual.mean()), "absolute_error": float(abs(group.probability.mean()-group.actual.mean()))})
    return {"ece": ece(frame.actual.to_numpy(), frame.probability.to_numpy(), bins), "buckets": rows}


def segment_metrics(frame, bins=10):
    work=frame.copy(); work["month"]=pd.to_datetime(work.game_date).dt.month.astype(str)
    work["favorite_role"]=np.where(work.market_probability>=.5,"positive_side_favorite","negative_side_favorite")
    output={}
    for dimension in ("month","favorite_role"):
        output[dimension]={k:classification_metrics(g,bins) for k,g in work.groupby(dimension) if len(g)>=20}
    if "closing_total" in work and work.closing_total.notna().any():
        work["total_band"]=pd.qcut(work.closing_total,3,labels=["low","medium","high"],duplicates="drop")
        output["total_band"]={str(k):classification_metrics(g,bins) for k,g in work.groupby("total_band",observed=True) if len(g)>=20}
    return output


def drawdown(frame):
    daily=frame.groupby("game_date",as_index=False).agg(flat_profit=("flat_profit","sum"),kelly_profit=("kelly_profit","sum"))
    for kind in ("flat","kelly"):
        equity=daily[f"{kind}_profit"].cumsum(); dd=equity.cummax()-equity
        daily[f"{kind}_equity"]=equity; daily[f"{kind}_drawdown"]=dd
    return daily, {"max_flat_drawdown":float(daily.flat_drawdown.max()),"max_kelly_drawdown":float(daily.kelly_drawdown.max()),
                   "worst_flat_day":float(daily.flat_profit.min()),"worst_kelly_day":float(daily.kelly_profit.min())}

