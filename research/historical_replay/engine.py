import json
import subprocess
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import REPLAY_SCHEMA_VERSION
from .config import ROOT
from .data_adapter import load_dataset, training_rows
from .isolation import require_research_output
from .metrics import calibration, classification_metrics, drawdown, segment_metrics
from .models import feature_importance, fit_model


def _git_commit():
    try: return subprocess.check_output(["git","rev-parse","HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: return "unavailable"


def _prices(row, target):
    if target == "home_win":
        return row.home_moneyline_price_decimal, row.away_moneyline_price_decimal, row.market_home_probability
    return row.over_price_decimal, row.under_price_decimal, row.market_over_probability


def _bet_fields(actual, p, positive_price, negative_price, market_p, config):
    positive_valid=np.isfinite(positive_price) and positive_price>1
    negative_valid=np.isfinite(negative_price) and negative_price>1
    positive_ev=p*positive_price-1 if positive_valid else -np.inf
    negative_ev=(1-p)*negative_price-1 if negative_valid else -np.inf
    positive=positive_ev>=negative_ev
    side_p=p if positive else 1-p
    price=positive_price if positive else negative_price
    selected_ev=positive_ev if positive else negative_ev
    won=bool(actual)==positive
    edge=side_p-(market_p if positive else 1-market_p)
    wager=bool(selected_ev>0 and edge>=config.min_edge)
    flat_stake = config.flat_stake_units if wager else 0.0
    flat_profit = flat_stake * ((price-1) if won else -1) if wager else 0.0
    b=price-1 if np.isfinite(price) and price>1 else 0
    full_kelly = max(0.0, (b*side_p-(1-side_p))/b) if b else 0.0
    fraction = min(config.max_kelly_fraction, full_kelly*config.kelly_multiplier) if wager else 0.0
    kelly_profit = fraction*((price-1) if won else -1) if wager else 0.0
    return positive,won,edge,float(selected_ev),flat_stake,flat_profit,fraction,kelly_profit


def _assert_prediction_integrity(pred, specs, expected_ids):
    if pred.duplicated(["model","canonical_game_id"]).any():
        duplicates=pred.loc[pred.duplicated(["model","canonical_game_id"],keep=False),["model","canonical_game_id"]].to_dict("records")
        raise ValueError(f"Duplicate model/game predictions: {duplicates[:10]}")
    coverage={name:set(group.canonical_game_id) for name,group in pred.groupby("model")}
    if set(coverage)!=set(spec.name for spec in specs):
        raise ValueError("Paired coverage differs: one or more configured models produced no predictions")
    if any(ids!=expected_ids for ids in coverage.values()):
        detail={name:{"missing":len(expected_ids-ids),"unexpected":len(ids-expected_ids)} for name,ids in coverage.items()}
        raise ValueError(f"Paired coverage differs or games were silently excluded: {detail}")


def run_replay(config):
    started=time.time(); dataset=load_dataset(config.dataset_path,config.target,config.include_features,config.exclude_features,config.feature_transforms)
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir=require_research_output(ROOT/"experiments"/config.experiment_name/"runs"/run_id)
    run_dir.mkdir(parents=True,exist_ok=False)
    evaluation=dataset.frame[(dataset.frame.game_date>=pd.Timestamp(config.start_date)) & (dataset.frame.game_date<=pd.Timestamp(config.end_date))]
    if evaluation.empty: raise ValueError("Evaluation window contains no games")
    predictions=[]; importance=defaultdict(lambda:defaultdict(list)); training_windows=[]
    specs=(config.historical_baseline,config.candidate)
    if len({spec.name for spec in specs})!=len(specs):
        raise ValueError("Historical baseline and candidate names must be unique")
    expected_ids=set(evaluation.canonical_game_id)
    for replay_date, games in evaluation.groupby("game_date",sort=True):
        train=training_rows(dataset,replay_date,config.training_window_days)
        if len(train)<config.min_training_rows:
            raise ValueError(f"Evaluation games would be silently excluded on {replay_date.date()}: insufficient training rows")
        Xtrain=train[dataset.features].replace([np.inf,-np.inf],np.nan); ytrain=train[config.target].astype(int)
        Xtest=games[dataset.features].replace([np.inf,-np.inf],np.nan)
        if ytrain.nunique()<2:
            raise ValueError(f"Evaluation games would be silently excluded on {replay_date.date()}: one-class training target")
        if train.game_date.max()>=replay_date:
            raise AssertionError("Training dates overlap the evaluation date")
        training_windows.append({"replay_date":str(replay_date.date()),"train_rows":len(train),"train_start":str(train.game_date.min().date()),"train_end":str(train.game_date.max().date())})
        for spec in specs:
            model=fit_model(spec,config.seed,Xtrain,ytrain); probs=model.predict_proba(Xtest)[:,1]
            fi=feature_importance(model,dataset.features)
            for name,value in fi.items(): importance[spec.name][name].append(value)
            for (_,row),p in zip(games.iterrows(),probs):
                pos_price,neg_price,market_p=_prices(row,config.target)
                positive,won,edge,selected_ev,flat_stake,flat_profit,kelly_stake,kelly_profit=_bet_fields(int(row[config.target]),float(p),pos_price,neg_price,market_p,config)
                predictions.append({"model":spec.name,"model_family":spec.family,"canonical_game_id":row.canonical_game_id,
                    "game_date":str(row.game_date.date()),"home_team":row.home_team,"away_team":row.away_team,
                    "target":config.target,"actual":int(row[config.target]),"probability":float(p),"market_probability":float(market_p),
                    "predicted_positive":positive,"won":won,"edge":float(edge),"selected_ev":selected_ev,"positive_price":pos_price,"negative_price":neg_price,
                    "flat_stake":flat_stake,"flat_profit":flat_profit,"kelly_stake":kelly_stake,"kelly_profit":kelly_profit,
                    "closing_total":row.get("closing_total",np.nan),"feature_as_of":str(row.feature_as_of.date()),
                    "training_max_date":str(train.game_date.max().date()),"training_rows":len(train)})
    pred=pd.DataFrame(predictions)
    if pred.empty: raise ValueError("No replay predictions produced")
    _assert_prediction_integrity(pred,specs,expected_ids)
    common=expected_ids
    pred=pred.sort_values(["game_date","canonical_game_id","model"])
    pred.to_csv(run_dir/"predictions.csv",index=False)
    overall={}; segments={}; calibrations={}; kelly={}; roi={}; dds={}; daily=[]
    for model_name,group in pred.groupby("model"):
        overall[model_name]=classification_metrics(group,config.probability_bins)
        segments[model_name]=segment_metrics(group,config.probability_bins)
        calibrations[model_name]=calibration(group,config.probability_bins)
        kelly[model_name]={k:overall[model_name][k] for k in ("kelly_profit_units","kelly_roi")}|{"total_stake":float(group.kelly_stake.sum()),"zero_kelly":int((group.kelly_stake==0).sum())}
        roi[model_name]={k:overall[model_name][k] for k in ("profit_units","roi","win_rate")}|{"bets":int((group.flat_stake>0).sum())}
        daily_frame,dds[model_name]=drawdown(group); daily_frame["model"]=model_name; daily.append(daily_frame)
    pd.concat(daily,ignore_index=True).to_csv(run_dir/"daily_results.csv",index=False)
    clv={"available":False,"reason":"Historical platform contains closing observations only; entry-to-close CLV cannot be reconstructed without fabrication.","models":{m:{"n":0,"average_clv":None} for m in overall}}
    comparison={"identical_games":len(common),"models":[s.name for s in specs],"metrics":overall,
        "deltas_candidate_minus_historical_baseline":{k:(overall[config.candidate.name].get(k)-overall[config.historical_baseline.name].get(k)) if overall[config.candidate.name].get(k) is not None and overall[config.historical_baseline.name].get(k) is not None else None for k in overall[config.historical_baseline.name]}}
    artifacts={"overall_metrics.json":overall|{"comparison":comparison},"segment_metrics.json":segments,
        "calibration_report.json":calibrations,"kelly_report.json":kelly,"roi_report.json":roi,
        "clv_report.json":clv,"drawdown_report.json":dds,
        "feature_importance.json":{m:{f:float(np.mean(v)) for f,v in vals.items()} for m,vals in importance.items()}}
    for name,payload in artifacts.items(): (run_dir/name).write_text(json.dumps(payload,indent=2,sort_keys=True,default=str))
    metadata={"run_id":run_id,"created_at":datetime.now(timezone.utc).isoformat(),"git_commit":_git_commit(),
        "dataset_path":dataset.path,"dataset_hash":dataset.sha256,"schema_version":dataset.schema_version,
        "replay_schema_version":REPLAY_SCHEMA_VERSION,"model_versions":{s.name:s.family for s in specs},
        "feature_list":dataset.features,"configuration":config.to_dict(),"training_windows":training_windows,
        "feature_provenance":dataset.feature_provenance,"exclusions":dataset.exclusions,
        "evaluation_window":{"start":config.start_date,"end":config.end_date,"identical_games":len(common)},
        "runtime_seconds":round(time.time()-started,3),"random_seed":config.seed,
        "isolation":{"production_writes":False,"registry_modified":False,"shadow_modified":False,"notifications_enabled":False}}
    (run_dir/"metadata.json").write_text(json.dumps(metadata,indent=2,sort_keys=True,default=str))
    return run_dir
