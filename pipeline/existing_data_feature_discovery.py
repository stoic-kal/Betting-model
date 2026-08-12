"""Discover only incremental, point-in-time features from the existing warehouse."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss, roc_auc_score

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pipeline.data_platform import connect
from pipeline.train_platform_models import DATASET, NON_FEATURES

OUTDIR=Path("reports/data_platform/existing_data_discovery")


def _num(raw,key):
    try:
        v=json.loads(raw or "{}").get(key); return np.nan if v is None else float(v)
    except (ValueError,TypeError,json.JSONDecodeError): return np.nan


def bullpen_features():
    conn=connect(); rows=pd.read_sql_query("""SELECT canonical_game_id,team,game_date,pitching_json
      FROM player_game_history WHERE source_quality='evt'""",conn); conn.close()
    for key in ("P_G","P_GS","P_OUT","P_ER","P_H","P_BB","P_SO","P_HR","P_PITCH"):
        rows[key]=rows.pitching_json.map(lambda x,k=key:_num(x,k))
    rows=rows[(rows.P_G.fillna(0)>0)&(rows.P_GS.fillna(0)==0)]
    agg=rows.groupby(["canonical_game_id","team","game_date"],as_index=False).agg(
        bp_outs=("P_OUT","sum"),bp_er=("P_ER","sum"),bp_hits=("P_H","sum"),bp_bb=("P_BB","sum"),
        bp_so=("P_SO","sum"),bp_hr=("P_HR","sum"),bp_pitches=("P_PITCH","sum"))
    agg["date"]=pd.to_datetime(agg.game_date); agg=agg.sort_values(["team","date","canonical_game_id"])
    for w in (3,7,14):
        for c in ("bp_outs","bp_er","bp_hits","bp_bb","bp_so","bp_hr","bp_pitches"):
            agg[f"{c}_{w}g"]=agg.groupby("team")[c].transform(lambda s:s.shift(1).rolling(w,min_periods=2).sum())
        innings=agg[f"bp_outs_{w}g"]/3
        agg[f"bp_era_{w}g"]=9*agg[f"bp_er_{w}g"]/innings.replace(0,np.nan)
        agg[f"bp_whip_{w}g"]=(agg[f"bp_hits_{w}g"]+agg[f"bp_bb_{w}g"])/innings.replace(0,np.nan)
        bf=(agg[f"bp_outs_{w}g"]+agg[f"bp_hits_{w}g"]+agg[f"bp_bb_{w}g"])
        agg[f"bp_k_minus_bb_{w}g"]=(agg[f"bp_so_{w}g"]-agg[f"bp_bb_{w}g"])/bf.replace(0,np.nan)
        agg[f"bp_pitches_per_out_{w}g"]=agg[f"bp_pitches_{w}g"]/agg[f"bp_outs_{w}g"].replace(0,np.nan)
    keep=["canonical_game_id","team"]+[c for c in agg if c.startswith("bp_") and c[-1:] == "g"]
    return agg[keep]


def add_candidates(base):
    df=base.copy(); families={}
    trend=[]
    for side in ("home","away"):
        for stat in ("runs","runs_allowed","hits","walks","strikeouts"):
            for short,long in ((5,10),(5,30),(10,30)):
                name=f"{side}_{stat}_accel_{short}v{long}"
                df[name]=df[f"{side}_{stat}_{short}g"]-df[f"{side}_{stat}_{long}g"]; trend.append(name)
        df[f"{side}_run_diff_5g"]=df[f"{side}_runs_5g"]-df[f"{side}_runs_allowed_5g"]
        df[f"{side}_run_diff_30g"]=df[f"{side}_runs_30g"]-df[f"{side}_runs_allowed_30g"]
        trend += [f"{side}_run_diff_5g",f"{side}_run_diff_30g"]
    families["rolling_trend"]=trend

    recent=[]
    for w in (5,10,30):
        for name,expr in {
          f"combined_scoring_form_{w}g":df[f"home_runs_{w}g"]+df[f"away_runs_{w}g"],
          f"combined_prevention_form_{w}g":df[f"home_runs_allowed_{w}g"]+df[f"away_runs_allowed_{w}g"],
          f"run_environment_form_{w}g":(df[f"home_runs_{w}g"]+df[f"away_runs_{w}g"]+df[f"home_runs_allowed_{w}g"]+df[f"away_runs_allowed_{w}g"])/2,
        }.items(): df[name]=expr; recent.append(name)
    df["rest_advantage"]=df.home_rest_days-df.away_rest_days; recent.append("rest_advantage")
    families["recent_form"]=recent

    market=[]
    p=df.market_home_probability.clip(.001,.999)
    df["market_home_logit"]=np.log(p/(1-p)); market.append("market_home_logit")
    df["market_favorite_strength"]=(p-.5).abs(); market.append("market_favorite_strength")
    df["market_price_asymmetry"]=np.log(df.home_moneyline_price_decimal/df.away_moneyline_price_decimal); market.append("market_price_asymmetry")
    df["total_juice_skew"]=np.log(df.over_price_decimal/df.under_price_decimal); market.append("total_juice_skew")
    season=pd.to_datetime(df.game_date).dt.year
    prior_mean=df.groupby(season).closing_total.transform(lambda s:s.shift(1).expanding(30).mean())
    prior_std=df.groupby(season).closing_total.transform(lambda s:s.shift(1).expanding(30).std())
    df["closing_total_prior_z"]=(df.closing_total-prior_mean)/prior_std.replace(0,np.nan); market.append("closing_total_prior_z")
    families["market_derived"]=market

    bp=bullpen_features()
    bpcols=[c for c in bp if c.startswith("bp_")]
    home=bp.rename(columns={"team":"home_team",**{c:f"home_{c}" for c in bpcols}})
    away=bp.rename(columns={"team":"away_team",**{c:f"away_{c}" for c in bpcols}})
    df=df.merge(home,on=["canonical_game_id","home_team"],how="left").merge(away,on=["canonical_game_id","away_team"],how="left")
    families["bullpen"]=[f"{s}_{c}" for s in ("home","away") for c in bpcols]

    interactions=[]
    specs={
      "market_logit_x_run_form":df.market_home_logit*df.run_form_edge,
      "market_strength_x_form_disagreement":df.market_favorite_strength*(df.home_form_edge-df.run_form_edge/10),
      "total_x_scoring_acceleration":df.closing_total*(df.combined_scoring_form_5g-df.combined_scoring_form_30g),
      "bullpen_era_diff_7g":df.home_bp_era_7g-df.away_bp_era_7g,
      "bullpen_quality_x_rest":(df.away_bp_era_7g-df.home_bp_era_7g)*df.rest_advantage,
      "bullpen_workload_diff_3g":df.home_bp_pitches_3g-df.away_bp_pitches_3g,
      "total_x_bullpen_era":df.closing_total*(df.home_bp_era_7g+df.away_bp_era_7g),
    }
    for n,v in specs.items():df[n]=v;interactions.append(n)
    families["interactions"]=interactions
    return df,families


def split_folds(n):
    return [(np.arange(0,int(n*x)),np.arange(int(n*x),int(n*(x+.1)))) for x in (.5,.6,.7,.8)]


def scores(work,features,target):
    X=work[features].replace([np.inf,-np.inf],np.nan); y=work[target].astype(int).to_numpy(); out=[]
    for tr,te in split_folds(len(work)):
        imp=SimpleImputer(strategy="median"); xt=imp.fit_transform(X.iloc[tr]); xv=imp.transform(X.iloc[te])
        m=ExtraTreesClassifier(random_state=42,n_estimators=180,max_depth=8,n_jobs=-1).fit(xt,y[tr])
        p=m.predict_proba(xv)[:,1]; out.append({"log_loss":log_loss(y[te],p),"auc":roc_auc_score(y[te],p)})
    return out


def discover(df,target,families):
    work=df[df[target].notna()].copy()
    if target=="over":work=work[~work["push"].astype("boolean").fillna(False)]
    work=work.sort_values(["game_date","canonical_game_id"]).reset_index(drop=True)
    baseline=[c for c in work.select_dtypes(include=[np.number,"bool"]).columns if c not in NON_FEATURES and c not in sum(families.values(),[])]
    if target=="over":baseline=baseline+["closing_total"]
    base_scores=scores(work,baseline,target); accepted=[]; family_results={}; individual=[]
    current=baseline[:]; current_scores=base_scores
    for family,candidates in families.items():
        candidate_scores=scores(work,current+candidates,target)
        deltas=[b["log_loss"]-c["log_loss"] for b,c in zip(current_scores,candidate_scores)]
        passed=bool(np.mean(deltas)>0 and sum(d>0 for d in deltas)>=3)
        family_results[family]={"features":candidates,"fold_logloss_improvement":deltas,"mean_improvement":float(np.mean(deltas)),"accepted":passed}
        for feature in candidates:
            s=scores(work,current+[feature],target); ds=[b["log_loss"]-c["log_loss"] for b,c in zip(current_scores,s)]
            keep=bool(np.mean(ds)>0 and sum(d>0 for d in ds)>=3)
            individual.append({"feature":feature,"family":family,"fold_improvement":ds,"mean_improvement":float(np.mean(ds)),"accepted":keep})
            if keep: current.append(feature);accepted.append(feature);current_scores=s
    return {"baseline_features":len(baseline),"accepted_features":accepted,"baseline_folds":base_scores,
            "final_folds":current_scores,"family_results":family_results,"individual_results":individual,
            "mean_logloss_improvement":float(np.mean([x["log_loss"] for x in base_scores])-np.mean([x["log_loss"] for x in current_scores])),
            "mean_auc_improvement":float(np.mean([x["auc"] for x in current_scores])-np.mean([x["auc"] for x in base_scores]))}


def main():
    source_path=Path(DATASET)
    base=pd.read_csv(source_path,dtype={"game_date":str},low_memory=False); enriched,families=add_candidates(base)
    OUTDIR.mkdir(parents=True,exist_ok=True); enriched.to_csv(OUTDIR/"candidate_features.csv",index=False)
    report={"created_at":datetime.now(timezone.utc).isoformat(),"gate":"mean log-loss improvement and positive in at least 3/4 expanding folds","targets":{}}
    for target in ("home_win","over"):report["targets"][target]=discover(enriched,target,families)
    (OUTDIR/"feature_discovery_report.json").write_text(json.dumps(report,indent=2,default=str))
    accepted_by_target={target:result["accepted_features"] for target,result in report["targets"].items()}
    accepted_union=sorted(set(sum(accepted_by_target.values(),[])))
    accepted_dataset=base.copy()
    for feature in accepted_union: accepted_dataset[feature]=enriched[feature]
    accepted_path=source_path.parent/"historical_features_existing_data_v2.csv"
    accepted_dataset.to_csv(accepted_path,index=False)
    manifest={
        "created_at":report["created_at"],
        "source_dataset":str(DATASET),
        "accepted_dataset":str(accepted_path),
        "selection_gate":report["gate"],
        "features_by_target":accepted_by_target,
    }
    (OUTDIR/"accepted_feature_manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({t:{"accepted":r["accepted_features"],"logloss_gain":r["mean_logloss_improvement"],"auc_gain":r["mean_auc_improvement"]} for t,r in report["targets"].items()},indent=2))


if __name__=="__main__":main()
