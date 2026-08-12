"""Evidence-backed walk-forward verdicts for platform features."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import log_loss, roc_auc_score

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pipeline.train_platform_models import DATASET, NON_FEATURES


def folds(n):
    return [(np.arange(0,int(n*x)),np.arange(int(n*x),int(n*(x+.1)))) for x in (.5,.6,.7,.8)]


def diagnose(df,target,features,outdir):
    work=df[df[target].notna()].copy()
    if target=="over": work=work[~work["push"].fillna(False).astype(bool)]
    work=work.sort_values(["game_date","canonical_game_id"]).reset_index(drop=True)
    X=work[features].replace([np.inf,-np.inf],np.nan); y=work[target].astype(int).to_numpy()
    perm={f:[] for f in features}; lofo={f:[] for f in features}; fold_metrics=[]; last=None
    for train_idx,test_idx in folds(len(work)):
        imp=SimpleImputer(strategy="median"); xt=imp.fit_transform(X.iloc[train_idx]); xv=imp.transform(X.iloc[test_idx])
        model=ExtraTreesClassifier(random_state=42,n_estimators=150,max_depth=8,n_jobs=-1).fit(xt,y[train_idx])
        prob=model.predict_proba(xv)[:,1]; base=log_loss(y[test_idx],prob); fold_metrics.append({"auc":roc_auc_score(y[test_idx],prob),"log_loss":base})
        pi=permutation_importance(model,xv,y[test_idx],scoring="neg_log_loss",n_repeats=3,random_state=42,n_jobs=-1)
        for f,v in zip(features,pi.importances_mean): perm[f].append(float(v))
        for j,f in enumerate(features):
            reduced=np.delete(xv,j,axis=1); reduced_train=np.delete(xt,j,axis=1)
            m=ExtraTreesClassifier(random_state=42,n_estimators=80,max_depth=8,n_jobs=-1).fit(reduced_train,y[train_idx])
            lofo[f].append(float(log_loss(y[test_idx],m.predict_proba(reduced)[:,1])-base))
        last=(model,xv,test_idx)
    corr=X.corr(numeric_only=True).fillna(0)
    filled=SimpleImputer(strategy="median").fit_transform(X)
    try:
        sv=shap.TreeExplainer(last[0]).shap_values(last[1][:500])
        if isinstance(sv,list): sv=sv[-1]
        if np.asarray(sv).ndim==3: sv=np.asarray(sv)[:,:,1]
        shap_mean=np.mean(np.abs(sv),axis=0)
    except Exception:
        shap_mean=np.full(len(features),np.nan)
    rows=[]
    for i,f in enumerate(features):
        p=float(np.mean(perm[f])); l=float(np.mean(lofo[f])); stability=float(np.mean(np.array(perm[f])>0))
        redundancy=float(corr[f].drop(f).abs().max()) if len(features)>1 else 0
        target_corr=float(np.corrcoef(filled[:,i],y)[0,1]) if np.std(filled[:,i]) else 0
        verdict="KEEP" if p>0 and l>0 and stability>=.5 else ("REMOVE" if p<0 and l<0 and stability<=.25 else "INVESTIGATE")
        evidence=(f"permutation_logloss_gain={p:+.6f}; LOFO_logloss_delta={l:+.6f}; "
                  f"positive_fold_fraction={stability:.2f}; target_corr={target_corr:+.4f}; max_redundancy={redundancy:.4f}")
        rows.append({"feature":f,"verdict":verdict,"permutation_logloss_gain":p,"lofo_logloss_delta":l,
                     "stability":stability,"target_correlation":target_corr,"max_redundancy":redundancy,
                     "mean_abs_shap":float(shap_mean[i]),"evidence":evidence})
    result=pd.DataFrame(rows).sort_values(["verdict","permutation_logloss_gain"],ascending=[True,False])
    result.to_csv(outdir/f"{target}_feature_verdicts.csv",index=False)
    return {"features":len(features),"verdict_counts":result.verdict.value_counts().to_dict(),"walk_forward":fold_metrics}


def main():
    df=pd.read_csv(DATASET,dtype={"game_date":str}); numeric=[c for c in df.select_dtypes(include=[np.number,"bool"]).columns if c not in NON_FEATURES]
    out=Path("reports/data_platform")/"feature_diagnostics"; out.mkdir(parents=True,exist_ok=True)
    report={"created_at":datetime.now(timezone.utc).isoformat(),"method":"4 expanding walk-forward folds; Extra Trees; permutation, LOFO, SHAP, stability, correlation, redundancy","targets":{}}
    report["targets"]["home_win"]=diagnose(df,"home_win",numeric,out)
    report["targets"]["over"]=diagnose(df,"over",numeric+["closing_total"],out)
    (out/"summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=="__main__": main()
