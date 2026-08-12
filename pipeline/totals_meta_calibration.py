"""Leakage-safe second-stage calibration from totals out-of-fold predictions."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


OOF_PATH = Path("reports/data_platform/segment_market_diagnostics/over_walk_forward_predictions.csv")
FEATURE_PATH = Path("data/platform/historical_features_existing_data_v2.csv")
OUT = Path("reports/data_platform/totals_meta_calibration")
ACCEPTED = ["home_runs_accel_10v30", "home_hits_accel_5v10", "away_bp_er_14g"]
META_FEATURES = [
    "base_probability", "market_probability", "probability_difference",
    "closing_total", "confidence", *ACCEPTED,
]
METHODS = ["base", "market", "market_blend", "platt", "isotonic", "logistic_meta", "gradient_boosting_meta"]


def clip(values):
    return np.clip(np.asarray(values, dtype=float), .001, .999)


def ece(y, p, bins=10):
    y = np.asarray(y, dtype=int); p = clip(p)
    edges = np.linspace(0, 1, bins + 1); total = len(y); value = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & ((p < high) if high < 1 else (p <= high))
        if mask.any(): value += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(value)


def metrics(y, p):
    p = clip(p)
    return {"log_loss":float(log_loss(y,p)), "brier":float(brier_score_loss(y,p)), "ece":ece(y,p)}


def prepare():
    oof = pd.read_csv(OOF_PATH)
    features = pd.read_csv(FEATURE_PATH, usecols=["canonical_game_id", *ACCEPTED], low_memory=False)
    frame = oof.merge(features, on="canonical_game_id", how="left", validate="one_to_one")
    frame = frame.rename(columns={"model_probability":"base_probability"})
    frame["probability_difference"] = frame.base_probability - frame.market_probability
    frame["confidence"] = (frame.base_probability - .5).abs()
    return frame.sort_values(["fold", "game_date", "canonical_game_id"]).reset_index(drop=True)


def best_blend(train):
    y = train.target.to_numpy(dtype=int); base = train.base_probability; market = train.market_probability
    choices = np.linspace(0, 1, 101)
    losses = [log_loss(y, clip((1-a)*base+a*market)) for a in choices]
    return float(choices[int(np.argmin(losses))])


def fit_predict(train, test):
    y = train.target.to_numpy(dtype=int); xt = train[META_FEATURES]; xv = test[META_FEATURES]
    predictions = {
        "base":clip(test.base_probability),
        "market":clip(test.market_probability),
    }
    alpha = best_blend(train)
    predictions["market_blend"] = clip((1-alpha)*test.base_probability + alpha*test.market_probability)

    base_logit = np.log(clip(train.base_probability)/(1-clip(train.base_probability))).reshape(-1,1)
    test_logit = np.log(clip(test.base_probability)/(1-clip(test.base_probability))).reshape(-1,1)
    platt = LogisticRegression(C=1.0, max_iter=2000, random_state=42).fit(base_logit,y)
    predictions["platt"] = clip(platt.predict_proba(test_logit)[:,1])

    iso = IsotonicRegression(out_of_bounds="clip", y_min=.001, y_max=.999).fit(train.base_probability,y)
    predictions["isotonic"] = clip(iso.predict(test.base_probability))

    logistic = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(C=1.0,max_iter=2000,random_state=42)).fit(xt,y)
    predictions["logistic_meta"] = clip(logistic.predict_proba(xv)[:,1])

    imputer = SimpleImputer(strategy="median"); xi=imputer.fit_transform(xt); xvi=imputer.transform(xv)
    boosting = GradientBoostingClassifier(n_estimators=60,learning_rate=.03,max_depth=1,
                                          min_samples_leaf=50,random_state=42).fit(xi,y)
    predictions["gradient_boosting_meta"] = clip(boosting.predict_proba(xvi)[:,1])
    importance = {
        "logistic_meta":np.abs(logistic[-1].coef_[0]),
        "gradient_boosting_meta":boosting.feature_importances_,
    }
    return predictions, alpha, importance


def reliability_rows(frame, method, bins=10):
    rows=[]; p=frame[method]; y=frame.target
    edges=np.unique(np.quantile(p,np.linspace(0,1,bins+1)))
    for number,(low,high) in enumerate(zip(edges[:-1],edges[1:]),1):
        mask=(p>=low)&((p<high) if high<edges[-1] else (p<=high))
        if mask.any(): rows.append({"method":method,"bin":number,"low":low,"high":high,
                                    "n":int(mask.sum()),"mean_probability":float(p[mask].mean()),
                                    "event_rate":float(y[mask].mean())})
    return rows


def main():
    frame=prepare(); output=[]; fold_metrics=[]; alphas=[]; importances=[]
    # Fold 1 supplies the first genuinely out-of-fold meta-training block; folds 2-4 are untouched meta tests.
    for test_fold in (2,3,4):
        train=frame[frame.fold<test_fold].copy(); test=frame[frame.fold==test_fold].copy()
        predictions,alpha,importance=fit_predict(train,test); alphas.append({"test_fold":test_fold,"alpha":alpha})
        result=test[["canonical_game_id","game_date","fold","target","base_probability","market_probability",
                     "probability_difference","closing_total","confidence",*ACCEPTED]].copy()
        for method,prediction in predictions.items():
            result[method]=prediction
            fold_metrics.append({"test_fold":test_fold,"method":method,**metrics(result.target,prediction)})
        output.append(result)
        for method,values in importance.items():
            for feature,value in zip(META_FEATURES,values):
                importances.append({"test_fold":test_fold,"method":method,"feature":feature,"importance":float(value)})
    predictions=pd.concat(output,ignore_index=True); metric_frame=pd.DataFrame(fold_metrics)
    summary=[]
    for method,group in metric_frame.groupby("method"):
        row={"method":method}
        for metric in ("log_loss","brier","ece"):
            row[f"mean_{metric}"]=float(group[metric].mean());row[f"std_{metric}"]=float(group[metric].std(ddof=0))
        if method not in ("base","market"):
            joined=group.merge(metric_frame[metric_frame.method=="base"],on="test_fold",suffixes=("","_base"))
            for metric in ("log_loss","brier","ece"):
                row[f"folds_better_{metric}"]=int((joined[metric]<joined[f"{metric}_base"]).sum())
            row["promotion_gate"] = bool(
                row["mean_log_loss"] < metric_frame[metric_frame.method=="base"].log_loss.mean()
                and row["mean_brier"] < metric_frame[metric_frame.method=="base"].brier.mean()
                and row["mean_ece"] < metric_frame[metric_frame.method=="base"].ece.mean()
                and row["folds_better_log_loss"] == 3 and row["folds_better_brier"] == 3
                and row["folds_better_ece"] >= 2
            )
        summary.append(row)
    summary_frame=pd.DataFrame(summary).sort_values("mean_log_loss")

    reliability=[]
    for method in METHODS: reliability.extend(reliability_rows(predictions,method))
    reliability_frame=pd.DataFrame(reliability)
    disagreement=[]
    predictions["disagreement_bin"]=pd.qcut(predictions.probability_difference,5,
        labels=["most_market_bullish","market_bullish","aligned","model_bullish","most_model_bullish"])
    for bucket,group in predictions.groupby("disagreement_bin",observed=True):
        for method in METHODS:
            disagreement.append({"bucket":str(bucket),"n":len(group),"mean_difference":float(group.probability_difference.mean()),
                                 "method":method,**metrics(group.target,group[method])})

    OUT.mkdir(parents=True,exist_ok=True)
    predictions.to_csv(OUT/"meta_walk_forward_predictions.csv",index=False)
    metric_frame.to_csv(OUT/"walk_forward_comparison.csv",index=False)
    summary_frame.to_csv(OUT/"calibration_comparison.csv",index=False)
    reliability_frame.to_csv(OUT/"reliability.csv",index=False)
    pd.DataFrame(disagreement).to_csv(OUT/"disagreement_analysis.csv",index=False)
    importance_frame=pd.DataFrame(importances)
    importance_frame.to_csv(OUT/"meta_feature_importance_by_fold.csv",index=False)
    importance_frame.groupby(["method","feature"],as_index=False).importance.mean().sort_values(
        ["method","importance"],ascending=[True,False]).to_csv(OUT/"meta_feature_importance.csv",index=False)
    pd.DataFrame(alphas).to_csv(OUT/"market_blend_weights.csv",index=False)

    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,method_set,title in ((axes[0],["base","market","market_blend"],"Baselines"),
                                (axes[1],["platt","isotonic","logistic_meta","gradient_boosting_meta"],"Learned calibrators")):
        for method in method_set:
            group=reliability_frame[reliability_frame.method==method]
            ax.plot(group.mean_probability,group.event_rate,marker="o",label=method)
        ax.plot([0,1],[0,1],"k--",alpha=.5);ax.set(xlim=(.35,.65),ylim=(.35,.65),xlabel="Mean probability",ylabel="Observed over rate",title=title);ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(OUT/"reliability_diagrams.png",dpi=180);plt.close(fig)

    best=summary_frame.iloc[0].to_dict()
    report={"protocol":"meta train on prior OOF blocks; test on next OOF block","meta_test_folds":[2,3,4],
            "promotion_gate":"mean Log Loss/Brier/ECE improve; Log Loss and Brier improve 3/3 folds; ECE improves >=2/3",
            "best_method":best,"promotable_methods":summary_frame[summary_frame.get("promotion_gate",False)==True].method.tolist(),
            "market_blend_weights":alphas}
    (OUT/"summary.json").write_text(json.dumps(report,indent=2,default=str))
    print(summary_frame.to_string(index=False))


if __name__=="__main__":main()
