"""Unsupervised taxonomy of large totals model/market disagreement."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import brier_score_loss, log_loss, silhouette_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

PREDICTIONS=Path("reports/data_platform/segment_market_diagnostics/over_walk_forward_predictions.csv")
FEATURES=Path("data/platform/historical_features_existing_data_v2.csv")
OUT=Path("reports/data_platform/disagreement_taxonomy")
NUMERIC=["closing_total","home_form_edge","run_form_edge","away_bp_er_14g"]
CATEGORICAL=["home_team","moneyline_role","total_level","month"]


def metrics(frame):
    y=frame.target.to_numpy(dtype=int);base=frame.model_probability.clip(.001,.999);market=frame.market_probability.clip(.001,.999)
    return {"n":len(frame),"over_rate":float(y.mean()),"mean_signed_disagreement":float(frame.market_disagreement.mean()),
            "mean_absolute_disagreement":float(frame.abs_market_disagreement.mean()),
            "base_log_loss":float(log_loss(y,base)),"market_log_loss":float(log_loss(y,market)),
            "base_advantage":float(log_loss(y,market)-log_loss(y,base)),
            "base_brier":float(brier_score_loss(y,base)),"market_brier":float(brier_score_loss(y,market))}


def prepare():
    pred=pd.read_csv(PREDICTIONS); feat=pd.read_csv(FEATURES,low_memory=False)
    keep=["canonical_game_id","home_form_edge","run_form_edge","away_bp_er_14g"]
    frame=pred.merge(feat[keep],on="canonical_game_id",how="left",validate="one_to_one")
    frame["month"]=pd.to_datetime(frame.game_date).dt.month.astype(str)
    frame["moneyline_role"]=np.where(frame.market_home_probability>=.5,"home_favorite","road_favorite")
    # X is estimated from earlier OOF blocks only; the first block is reserved to establish the first cutoff.
    selected=[];cutoffs=[]
    for fold in (2,3,4):
        prior=frame[frame.fold<fold].abs_market_disagreement
        cutoff=float(prior.quantile(.8));cutoffs.append({"test_fold":fold,"x":cutoff,"prior_n":len(prior)})
        block=frame[frame.fold==fold].copy();block["x"]=cutoff;block["large_disagreement"]=block.abs_market_disagreement>cutoff
        selected.append(block)
    reference=pd.concat(selected,ignore_index=True)
    return reference,reference[reference.large_disagreement].copy(),cutoffs


def commonalities(cohort,reference):
    rows=[]
    for column in CATEGORICAL:
        base=reference[column].value_counts(normalize=True,dropna=False)
        selected=cohort[column].value_counts(normalize=True,dropna=False)
        for value,share in selected.items():
            ref=float(base.get(value,0));rows.append({"kind":"categorical","feature":column,"value":str(value),
                "cohort_value":float(share),"reference_value":ref,"enrichment":float(share/ref) if ref else None})
    for column in NUMERIC:
        mean=float(reference[column].mean());std=float(reference[column].std())
        value=float(cohort[column].mean());rows.append({"kind":"numeric","feature":column,"value":"mean",
            "cohort_value":value,"reference_value":mean,"enrichment":(value-mean)/std if std else None})
    return pd.DataFrame(rows)


def main():
    reference,cohort,cutoffs=prepare()
    transform=ColumnTransformer([
        ("numeric",make_pipeline(SimpleImputer(strategy="median"),StandardScaler()),NUMERIC),
        ("categorical",make_pipeline(SimpleImputer(strategy="most_frequent"),OneHotEncoder(handle_unknown="ignore")),CATEGORICAL),
    ])
    matrix=transform.fit_transform(cohort[NUMERIC+CATEGORICAL])
    candidates=[]
    for k in range(2,9):
        labels=KMeans(n_clusters=k,n_init=30,random_state=42).fit_predict(matrix)
        candidates.append({"k":k,"silhouette":float(silhouette_score(matrix,labels,sample_size=min(3000,len(cohort)),random_state=42))})
    best=max(candidates,key=lambda x:x["silhouette"]);model=KMeans(n_clusters=best["k"],n_init=50,random_state=42)
    cohort["cluster"]=model.fit_predict(matrix)

    profiles=[];trait_rows=[]
    for cluster,group in cohort.groupby("cluster"):
        traits=commonalities(group,reference)
        notable=traits.sort_values("enrichment",ascending=False).head(8)
        profiles.append({"cluster":int(cluster),**metrics(group),"top_traits":notable.to_dict("records")})
        traits.insert(0,"cluster",int(cluster));trait_rows.append(traits)
    overall=commonalities(cohort,reference)

    sensitivity=[]
    source=pd.read_csv(PREDICTIONS)
    for quantile in (.75,.80,.90):
        blocks=[]
        for fold in (2,3,4):
            cutoff=float(source[source.fold<fold].abs_market_disagreement.quantile(quantile))
            block=source[(source.fold==fold)&(source.abs_market_disagreement>cutoff)].copy();block["cutoff"]=cutoff;blocks.append(block)
        sample=pd.concat(blocks,ignore_index=True);sensitivity.append({"quantile":quantile,"mean_cutoff":float(sample.cutoff.mean()),**metrics(sample)})

    unavailable={
      "temperature":"not present in the 2012-2021 market platform",
      "wind":"not present in the 2012-2021 market platform",
      "starter_quality":"not present in the platform feature table",
      "lineup_quality":"no timestamped historical pregame lineups",
      "pitcher_handedness":"not present in the platform feature table",
      "division_game":"league/division membership is not stored",
      "interleague":"league membership is not stored",
      "park":"venue metadata covers only 404 games; home_team is used explicitly as a park/team context, not claimed as venue identity",
      "bullpen_quality":"only the accepted away bullpen ER over 14 games is available",
    }
    OUT.mkdir(parents=True,exist_ok=True)
    cohort.to_csv(OUT/"large_disagreement_games_clustered.csv",index=False)
    overall.to_csv(OUT/"overall_commonalities.csv",index=False)
    pd.concat(trait_rows,ignore_index=True).to_csv(OUT/"cluster_traits.csv",index=False)
    pd.DataFrame([{k:v for k,v in p.items() if k!="top_traits"} for p in profiles]).to_csv(OUT/"cluster_performance.csv",index=False)
    pd.DataFrame(sensitivity).to_csv(OUT/"cutoff_sensitivity.csv",index=False)
    report={"selection":"abs disagreement above prior-OOF 80th percentile","cutoffs":cutoffs,
            "reference_n":len(reference),"cohort":metrics(cohort),"cluster_selection":candidates,"selected_k":best["k"],
            "clusters":profiles,"overall_top_commonalities":overall.sort_values("enrichment",ascending=False).head(15).to_dict("records"),
            "cutoff_sensitivity":sensitivity,"unavailable":unavailable}
    (OUT/"taxonomy.json").write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({"cutoffs":cutoffs,"cohort":report["cohort"],"selected_k":best["k"],
                      "cluster_metrics":[{k:v for k,v in p.items() if k!="top_traits"} for p in profiles]},indent=2))


if __name__=="__main__":main()
