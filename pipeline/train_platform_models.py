"""Chronologically comparable model-family benchmark on platform features."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.data_platform import sha256_file

DATASET = "data/platform/historical_features.csv"
NON_FEATURES = {"canonical_game_id","game_date","home_team","away_team","venue_name","home_runs",
                "away_runs","home_runs_allowed","away_runs_allowed","total_runs","home_win","over","push",
                "feature_as_of","point_in_time_policy","doubleheader_number","closing_total"}


def ece(y, p, bins=10):
    edges=np.linspace(0,1,bins+1); total=len(y); score=0.0
    for lo,hi in zip(edges[:-1],edges[1:]):
        mask=(p>=lo)&(p<(hi if hi<1 else hi+1e-12))
        if mask.any(): score += mask.mean()*abs(float(np.mean(y[mask]))-float(np.mean(p[mask])))
    return score


def metrics(y,p):
    return {"n":len(y),"auc":roc_auc_score(y,p),"log_loss":log_loss(y,p),
            "brier":brier_score_loss(y,p),"ece":ece(np.asarray(y),p),
            "accuracy":accuracy_score(y,p>=.5)}


def roi_metrics(y,p,home_decimal,away_decimal,edge=.03):
    bankroll=0.0; kelly_bankroll=0.0; bets=0; stake=0.0
    for actual,prob,hd,ad in zip(y,p,home_decimal,away_decimal):
        side_home=prob >= .5; price=hd if side_home else ad; side_prob=prob if side_home else 1-prob
        if not np.isfinite(price): continue
        implied=1/price
        if side_prob-implied < edge: continue
        bets += 1; stake += 1; won=bool(actual)==side_home
        bankroll += (price-1) if won else -1
        b=price-1; fraction=max(0,min(.05,(b*side_prob-(1-side_prob))/b))
        kelly_bankroll += fraction*((price-1) if won else -1)
    return {"bets":bets,"flat_roi":bankroll/stake if stake else None,"kelly_profit_per_initial_bankroll":kelly_bankroll}


def builders():
    return {
      "lightgbm":lambda:LGBMClassifier(random_state=42,n_estimators=150,max_depth=5,learning_rate=.04,verbosity=-1),
      "extra_trees":lambda:ExtraTreesClassifier(random_state=42,n_estimators=250,max_depth=8,n_jobs=-1),
      "random_forest":lambda:RandomForestClassifier(random_state=42,n_estimators=250,max_depth=8,n_jobs=-1),
      "logistic_regression":lambda:Pipeline([("scale",StandardScaler()),("clf",LogisticRegression(max_iter=2000))]),
      "catboost":lambda:CatBoostClassifier(random_state=42,iterations=150,depth=6,learning_rate=.05,verbose=False),
      "xgboost":lambda:XGBClassifier(random_state=42,n_estimators=150,max_depth=5,learning_rate=.04,n_jobs=-1,eval_metric="logloss"),
      "hist_gradient_boosting":lambda:HistGradientBoostingClassifier(random_state=42,max_depth=6,learning_rate=.05),
    }


def run_target(df,target,features,outdir):
    work=df[df[target].notna()].copy()
    if target=="over": work=work[~work.push.fillna(False)]
    work=work.sort_values(["game_date","canonical_game_id"]).reset_index(drop=True)
    n=len(work); a=int(n*.70); b=int(n*.85)
    X=work[features].replace([np.inf,-np.inf],np.nan); y=work[target].astype(int)
    Xtr,Xv,Xte=X.iloc[:a],X.iloc[a:b],X.iloc[b:]; ytr,yv,yte=y.iloc[:a],y.iloc[a:b],y.iloc[b:]
    results={}; fitted={}
    for name,build in builders().items():
        raw=Pipeline([("impute",SimpleImputer(strategy="median")),("model",build())])
        raw.fit(Xtr,ytr)
        calibrations={}
        for method in ("sigmoid","isotonic"):
            calibrated=CalibratedClassifierCV(raw,method=method,cv="prefit"); calibrated.fit(Xv,yv)
            vp=calibrated.predict_proba(Xv)[:,1]
            calibrations[method]=(metrics(yv,vp),calibrated)
        selected=min(calibrations,key=lambda m:(calibrations[m][0]["log_loss"],calibrations[m][0]["brier"],calibrations[m][0]["ece"]))
        model=calibrations[selected][1]; p=model.predict_proba(Xte)[:,1]
        result={"family":name,"calibration":selected,"validation_calibrations":{k:v[0] for k,v in calibrations.items()},
                "test":metrics(yte,p),"split":{"train":a,"validation":b-a,"test":n-b,
                "train_end":work.iloc[a-1].game_date,"validation_end":work.iloc[b-1].game_date}}
        if target == "over":
            positive_price, negative_price = work.iloc[b:].over_price_decimal, work.iloc[b:].under_price_decimal
        else:
            positive_price, negative_price = work.iloc[b:].home_moneyline_price_decimal, work.iloc[b:].away_moneyline_price_decimal
        result["test"].update(roi_metrics(yte,p,positive_price,negative_price))
        results[name]=result; fitted[name]=model
        joblib.dump(model,outdir/f"{target}_{name}.joblib")
    top=sorted(results,key=lambda x:(results[x]["test"]["log_loss"],results[x]["test"]["brier"]))[:3]
    probs=np.mean([fitted[x].predict_proba(Xte)[:,1] for x in top],axis=0)
    ensemble={"family":"champion_ensemble","members":top,"calibration":"member_selected",
              "test":metrics(yte,probs),"split":results[top[0]]["split"]}
    if target == "over":
        positive_price, negative_price = work.iloc[b:].over_price_decimal, work.iloc[b:].under_price_decimal
    else:
        positive_price, negative_price = work.iloc[b:].home_moneyline_price_decimal, work.iloc[b:].away_moneyline_price_decimal
    ensemble["test"].update(roi_metrics(yte,probs,positive_price,negative_price))
    results["champion_ensemble"]=ensemble
    return results


def main():
    df=pd.read_csv(DATASET,dtype={"game_date":str})
    numeric=[c for c in df.select_dtypes(include=[np.number,"bool"]).columns if c not in NON_FEATURES]
    # Closing total is a legitimate pregame input for the totals target only.
    target_features={"home_win":numeric,"over":numeric+["closing_total"]}
    stamp=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    outdir=Path("reports/data_platform")/f"model_run_{stamp}"; outdir.mkdir(parents=True,exist_ok=True)
    report={"created_at":datetime.now(timezone.utc).isoformat(),"dataset":DATASET,
            "dataset_sha256":sha256_file(DATASET),"chronological_split":[.70,.15,.15],
            "calibration_candidates":["sigmoid","isotonic"],
            "calibration_not_implemented":["temperature_scaling","beta_calibration"],"targets":{}}
    for target,features in target_features.items(): report["targets"][target]=run_target(df,target,features,outdir)
    (outdir/"model_comparison.json").write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({"report":str(outdir/"model_comparison.json"),
      "best":{t:min(v,key=lambda m:v[m]["test"]["log_loss"]) for t,v in report["targets"].items()}},indent=2))


if __name__=="__main__": main()
