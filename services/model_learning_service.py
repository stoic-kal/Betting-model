import json
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

DB_PATH = "database/picks.db"
MIN_TRAINING_EXAMPLES = 40
MIN_PROMOTION_EXAMPLES = 120
FULL_CONFIDENCE_EXAMPLES = 200
MIN_PROMOTION_HOLDOUT = 40
MIN_BRIER_IMPROVEMENT = 0.0075
REQUIRED_QUALIFYING_RUNS = 3
MIN_NEW_QUALIFYING_EXAMPLES = 10
RETRAIN_EVERY_EXAMPLES = 10
LEGACY_V3_WEIGHT = 0.25
ROLLBACK_WINDOW = 40
ROLLBACK_MARKET_MARGIN = 0.015

_active_cache = {"loaded_at": 0.0, "models": {}}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS learning_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL,
        pick_type TEXT NOT NULL, eligible_examples INTEGER NOT NULL,
        training_examples INTEGER NOT NULL DEFAULT 0,
        holdout_examples INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL, champion_brier REAL, candidate_brier REAL,
        market_brier REAL, champion_log_loss REAL, candidate_log_loss REAL,
        champion_ece REAL, candidate_ece REAL, improvement REAL,
        artifact_json TEXT, detail TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS learning_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
        activated_at TEXT, pick_type TEXT NOT NULL, status TEXT NOT NULL,
        training_examples INTEGER NOT NULL, holdout_examples INTEGER NOT NULL,
        artifact_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
        activation_examples INTEGER, confidence_tier TEXT)""")
    model_columns = [
        row[1] for row in conn.execute("PRAGMA table_info(learning_models)").fetchall()
    ]
    if "activation_examples" not in model_columns:
        conn.execute("ALTER TABLE learning_models ADD COLUMN activation_examples INTEGER")
    if "confidence_tier" not in model_columns:
        conn.execute("ALTER TABLE learning_models ADD COLUMN confidence_tier TEXT")
    conn.commit()
    return conn


def _clip(value):
    return min(0.98, max(0.02, float(value)))


def _logit(value):
    value = _clip(value)
    return math.log(value / (1 - value))


def _snapshot(raw):
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _eligible_rows(conn, pick_type):
    return [
        dict(row)
        for row in conn.execute(
"""
        SELECT * FROM picks
        WHERE pick_type=? AND forecast_stage='lineup_lock'
          AND status IN ('won','lost') AND feature_snapshot IS NOT NULL
        ORDER BY date, COALESCE(scheduled_start, created_at), id
""",
            (pick_type,),
        ).fetchall()
    ]


def _legacy_v3_rows(conn, pick_type):

    return [
        dict(row)
        for row in conn.execute(
"""
        SELECT * FROM picks
        WHERE pick_type=? AND model_version='v3'
          AND COALESCE(forecast_stage, '')<>'lineup_lock'
          AND status IN ('won','lost') AND feature_snapshot IS NOT NULL
        ORDER BY date, COALESCE(scheduled_start, created_at), id
""",
            (pick_type,),
        ).fetchall()
    ]


def _example(row):

    snap = _snapshot(row.get("feature_snapshot"))
    won = row["status"] == "won"
    if row["pick_type"] == "moneyline":
        home = row["matchup"].split(" @ ")[-1]
        picked_reference = row["pick"] == home
        model_reference = row["model_prob"] if picked_reference else 1 - row["model_prob"]
        market_reference = snap.get("market_home")
        if market_reference is None:
            picked_market = 1 / row["odds"] if row.get("odds") else None
            market_reference = (
                picked_market
                if picked_reference
                else (1 - picked_market if picked_market else None)
            )
    else:
        picked_reference = str(row["pick"]).upper().startswith("OVER")
        model_reference = row["model_prob"] if picked_reference else 1 - row["model_prob"]
        picked_market = 1 / row["odds"] if row.get("odds") else None
        market_reference = (
            picked_market if picked_reference else (1 - picked_market if picked_market else None)
        )
    if market_reference is None:
        return None
    target = 1 if picked_reference == won else 0
    model_logit, market_logit = _logit(model_reference), _logit(market_reference)
    return (
        [model_logit, market_logit, model_logit - market_logit],
        target,
        _clip(model_reference),
        _clip(market_reference),
    )


def _brier(probs, targets):
    return float(np.mean((np.asarray(probs) - np.asarray(targets)) ** 2))


def _log_loss(probs, targets):
    probs = np.clip(np.asarray(probs), 1e-6, 1 - 1e-6)
    targets = np.asarray(targets)
    return float(-np.mean(targets * np.log(probs) + (1 - targets) * np.log(1 - probs)))


def _ece(probs, targets, bins=5):
    probs, targets = np.asarray(probs), np.asarray(targets)
    total = len(probs)
    error = 0.0
    for low in np.linspace(0, 1, bins + 1)[:-1]:
        high = low + 1 / bins
        mask = (probs >= low) & (probs < high if high < 1 else probs <= high)
        if mask.any():
            error += mask.sum() / total * abs(float(probs[mask].mean() - targets[mask].mean()))
    return float(error)


def _artifact(scaler, model):
    return {
"version": 1,
"features": ["model_logit", "market_logit", "disagreement"],
"mean": scaler.mean_.tolist(),
"scale": scaler.scale_.tolist(),
"coef": model.coef_[0].tolist(),
"intercept": float(model.intercept_[0]),
    }


def _predict_artifact(artifact, model_probability, market_probability):
    ml, mk = _logit(model_probability), _logit(market_probability)
    values = [ml, mk, ml - mk]
    z = [
        (value - mean) / (scale or 1)
        for value, mean, scale in zip(values, artifact["mean"], artifact["scale"])
    ]
    score = artifact["intercept"] + sum(coef * value for coef, value in zip(artifact["coef"], z))
    return _clip(1 / (1 + math.exp(-max(-30, min(30, score)))))


def _record_run(conn, pick_type, eligible, status, **values):
    fields = {
"run_at": datetime.now(timezone.utc).isoformat(),
"pick_type": pick_type,
"eligible_examples": eligible,
"status": status,
        **values,
    }
    columns = ",".join(fields)
    conn.execute(
        f"INSERT INTO learning_runs ({columns}) VALUES ({','.join('?' for _ in fields)})",
        tuple(fields.values()),
    )
    conn.commit()


def _rollback_guard(conn, pick_type, examples):

    active = conn.execute(
"SELECT * FROM learning_models WHERE pick_type=? AND status='active' ORDER BY id DESC LIMIT 1",
        (pick_type,),
    ).fetchone()
    if not active or active["activation_examples"] is None:
        return None
    available = len(examples) - int(active["activation_examples"])
    if available < ROLLBACK_WINDOW:
        return {"status": "monitoring", "observed": max(0, available), "required": ROLLBACK_WINDOW}
    window = examples[-ROLLBACK_WINDOW:]
    targets = [e[1] for e in window]
    champion_brier = _brier([e[2] for e in window], targets)
    market_brier = _brier([e[3] for e in window], targets)
    if champion_brier <= market_brier + ROLLBACK_MARKET_MARGIN:
        tier = "full" if len(examples) >= FULL_CONFIDENCE_EXAMPLES else "provisional"
        conn.execute(
"UPDATE learning_models SET confidence_tier=? WHERE id=?", (tier, active["id"])
        )
        conn.commit()
        return {
"status": "passed",
"observed": ROLLBACK_WINDOW,
"champion_brier": round(champion_brier, 6),
"market_brier": round(market_brier, 6),
        }
    conn.execute("UPDATE learning_models SET status='rolled_back' WHERE id=?", (active["id"],))
    previous = conn.execute(
"SELECT id FROM learning_models WHERE pick_type=? AND status='retired' ORDER BY id DESC LIMIT 1",
        (pick_type,),
    ).fetchone()
    if previous:
        conn.execute(
"UPDATE learning_models SET status='active',activated_at=?,activation_examples=?,confidence_tier='provisional' WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), len(examples), previous["id"]),
        )
    conn.commit()
    _active_cache["loaded_at"] = 0
    return {
"status": "rolled_back",
"observed": ROLLBACK_WINDOW,
"champion_brier": round(champion_brier, 6),
"market_brier": round(market_brier, 6),
"restored_previous": bool(previous),
    }


def _run_type(conn, pick_type):
    rows = _eligible_rows(conn, pick_type)
    examples = [item for row in rows if (item := _example(row)) is not None]
    legacy_examples = [
        item for row in _legacy_v3_rows(conn, pick_type) if (item := _example(row)) is not None
    ]
    eligible = len(examples)
    rollback = _rollback_guard(conn, pick_type, examples)
    previous_run = conn.execute(
"SELECT * FROM learning_runs WHERE pick_type=? ORDER BY id DESC LIMIT 1", (pick_type,)
    ).fetchone()
    if previous_run and (
        eligible == previous_run["eligible_examples"]
        or (
            eligible >= MIN_TRAINING_EXAMPLES
            and eligible - previous_run["eligible_examples"] < RETRAIN_EVERY_EXAMPLES
        )
    ):
        return {
"pick_type": pick_type,
"status": previous_run["status"],
"eligible_examples": eligible,
"training_examples": previous_run["training_examples"],
"holdout_examples": previous_run["holdout_examples"],
"cached": True,
"detail": previous_run["detail"],
"next_training_at": MIN_TRAINING_EXAMPLES,
"next_promotion_at": MIN_PROMOTION_EXAMPLES,
"legacy_warm_start": len(legacy_examples),
"rollback": rollback,
        }
    if eligible < MIN_TRAINING_EXAMPLES:
        detail = f"Collecting official lineup-lock outcomes ({eligible}/{MIN_TRAINING_EXAMPLES} needed for first shadow model)."
        _record_run(conn, pick_type, eligible, "collecting", detail=detail)
        return {
"pick_type": pick_type,
"status": "collecting",
"eligible_examples": eligible,
"next_training_at": MIN_TRAINING_EXAMPLES,
"next_promotion_at": MIN_PROMOTION_EXAMPLES,
"legacy_warm_start": len(legacy_examples),
"detail": detail,
"rollback": rollback,
        }

    holdout = (
        MIN_PROMOTION_HOLDOUT
        if eligible >= MIN_PROMOTION_EXAMPLES
        else max(10, min(30, eligible // 4))
    )
    official_train = examples[:-holdout]
    test = examples[-holdout:]
    train = legacy_examples + official_train
    weights = np.asarray(
        ([LEGACY_V3_WEIGHT] * len(legacy_examples)) + ([1.0] * len(official_train))
    )
    x_train = np.asarray([e[0] for e in train])
    y_train = np.asarray([e[1] for e in train])
    if len(set(y_train.tolist())) < 2:
        detail = (
"Training window contains only one outcome class; waiting for a representative sample."
        )
        _record_run(
            conn,
            pick_type,
            eligible,
"collecting",
            training_examples=len(train),
            holdout_examples=holdout,
            detail=detail,
        )
        return {
"pick_type": pick_type,
"status": "collecting",
"eligible_examples": eligible,
"detail": detail,
        }
    scaler = StandardScaler().fit(x_train)
    model = LogisticRegression(C=0.35, max_iter=2000, random_state=17).fit(
        scaler.transform(x_train), y_train, sample_weight=weights
    )
    artifact = _artifact(scaler, model)
    champion = [e[2] for e in test]
    market = [e[3] for e in test]
    targets = [e[1] for e in test]
    candidate = [_predict_artifact(artifact, e[2], e[3]) for e in test]
    metrics = {
"champion_brier": _brier(champion, targets),
"candidate_brier": _brier(candidate, targets),
"market_brier": _brier(market, targets),
"champion_log_loss": _log_loss(champion, targets),
"candidate_log_loss": _log_loss(candidate, targets),
"champion_ece": _ece(champion, targets),
"candidate_ece": _ece(candidate, targets),
    }
    improvement = metrics["champion_brier"] - metrics["candidate_brier"]
    qualifies = (
        eligible >= MIN_PROMOTION_EXAMPLES
        and holdout >= MIN_PROMOTION_HOLDOUT
        and improvement >= MIN_BRIER_IMPROVEMENT
        and metrics["candidate_brier"] < metrics["market_brier"]
        and metrics["candidate_log_loss"] < metrics["champion_log_loss"]
        and metrics["candidate_ece"] <= metrics["champion_ece"]
    )
    prior = conn.execute(
"""SELECT status,eligible_examples FROM learning_runs WHERE pick_type=?
                            ORDER BY id DESC LIMIT ?""",
        (pick_type, REQUIRED_QUALIFYING_RUNS - 1),
    ).fetchall()
    streak = 1 if qualifies else 0
    last_count = eligible
    if qualifies:
        for row in prior:
            if (
                row["status"] != "qualified"
                or last_count - row["eligible_examples"] < MIN_NEW_QUALIFYING_EXAMPLES
            ):
                break
            streak += 1
            last_count = row["eligible_examples"]
    status = (
"promoted"
        if qualifies and streak >= REQUIRED_QUALIFYING_RUNS
        else ("qualified" if qualifies else "shadow")
    )
    rounded = {key: round(value, 6) for key, value in metrics.items()}
    _record_run(
        conn,
        pick_type,
        eligible,
        status,
        training_examples=len(train),
        holdout_examples=holdout,
        improvement=round(improvement, 6),
        artifact_json=json.dumps(artifact),
        detail=json.dumps(rounded),
        **rounded,
    )
    tier = "full" if eligible >= FULL_CONFIDENCE_EXAMPLES else "provisional"
    conn.execute(
"""INSERT INTO learning_models
        (created_at,activated_at,pick_type,status,training_examples,holdout_examples,
         artifact_json,metrics_json,activation_examples,confidence_tier)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat() if status == "promoted" else None,
            pick_type,
"active" if status == "promoted" else status,
            len(train),
            holdout,
            json.dumps(artifact),
            json.dumps(rounded),
            eligible if status == "promoted" else None,
            tier if status == "promoted" else "shadow",
        ),
    )
    if status == "promoted":
        conn.execute(
"UPDATE learning_models SET status='retired' WHERE pick_type=? AND status='active' AND id<>last_insert_rowid()",
            (pick_type,),
        )
        _active_cache["loaded_at"] = 0
    conn.commit()
    return {
"pick_type": pick_type,
"status": status,
"eligible_examples": eligible,
"training_examples": len(train),
"holdout_examples": holdout,
"improvement": round(improvement, 6),
"metrics": rounded,
"qualification_streak": streak,
"required_streak": REQUIRED_QUALIFYING_RUNS,
"next_promotion_at": MIN_PROMOTION_EXAMPLES,
"full_confidence_at": FULL_CONFIDENCE_EXAMPLES,
"legacy_warm_start": len(legacy_examples),
"legacy_weight": LEGACY_V3_WEIGHT,
"rollback": rollback,
    }


def run_learning_cycle():

    conn = _connect()
    try:
        results = [_run_type(conn, kind) for kind in ("moneyline", "totals")]
        return {
"run_at": datetime.now(timezone.utc).isoformat(),
"results": results,
"policy": learning_policy(),
        }
    finally:
        conn.close()


def learning_policy():
    return {
"eligible_stage": "lineup_lock",
"first_shadow_examples": MIN_TRAINING_EXAMPLES,
"promotion_examples": MIN_PROMOTION_EXAMPLES,
"minimum_holdout": MIN_PROMOTION_HOLDOUT,
"full_confidence_examples": FULL_CONFIDENCE_EXAMPLES,
"minimum_brier_improvement": MIN_BRIER_IMPROVEMENT,
"required_qualifying_runs": REQUIRED_QUALIFYING_RUNS,
"new_examples_per_qualifying_run": MIN_NEW_QUALIFYING_EXAMPLES,
"retrain_every_examples": RETRAIN_EVERY_EXAMPLES,
"legacy_v3_weight": LEGACY_V3_WEIGHT,
"rollback_window": ROLLBACK_WINDOW,
"rollback_market_margin": ROLLBACK_MARKET_MARGIN,
"inputs": ["locked model probability", "locked market probability"],
"excluded": ["result-derived features", "CLV", "profit", "postgame diagnostics"],
    }


def get_learning_status():
    conn = _connect()
    try:
        latest, active = [], {}
        for kind in ("moneyline", "totals"):
            official_count = len(_eligible_rows(conn, kind))
            legacy_count = len(_legacy_v3_rows(conn, kind))
            row = conn.execute(
"SELECT * FROM learning_runs WHERE pick_type=? ORDER BY id DESC LIMIT 1", (kind,)
            ).fetchone()
            if row:
                item = dict(row)
                item.pop("artifact_json", None)
                item["eligible_examples"] = official_count
                item["legacy_warm_start"] = legacy_count
                latest.append(item)
            else:
                latest.append(
                    {
"pick_type": kind,
"status": "collecting",
"eligible_examples": official_count,
"legacy_warm_start": legacy_count,
"detail": f"{official_count}/{MIN_TRAINING_EXAMPLES} official outcomes collected.",
                    }
                )
            model = conn.execute(
"SELECT * FROM learning_models WHERE pick_type=? AND status='active' ORDER BY id DESC LIMIT 1",
                (kind,),
            ).fetchone()
            active[kind] = (
                {
"id": model["id"],
"activated_at": model["activated_at"],
"training_examples": model["training_examples"],
"holdout_examples": model["holdout_examples"],
"activation_examples": model["activation_examples"],
"confidence_tier": model["confidence_tier"],
"metrics": json.loads(model["metrics_json"]),
                }
                if model
                else None
            )
        history = [
            dict(row)
            for row in conn.execute(
"""SELECT id,run_at,pick_type,eligible_examples,
            training_examples,holdout_examples,status,champion_brier,candidate_brier,market_brier,
            champion_ece,candidate_ece,improvement FROM learning_runs ORDER BY id DESC LIMIT 50"""
            ).fetchall()
        ]
        return {
"latest": latest,
"active_models": active,
"history": history,
"policy": learning_policy(),
        }
    finally:
        conn.close()


def apply_active_calibration(pick_type, model_probability, market_probability):

    import time

    now = time.time()
    if now - _active_cache["loaded_at"] > 300:
        conn = _connect()
        try:
            models = {}
            for row in conn.execute(
"SELECT pick_type,artifact_json FROM learning_models WHERE status='active' ORDER BY id"
            ):
                models[row["pick_type"]] = json.loads(row["artifact_json"])
            _active_cache.update({"loaded_at": now, "models": models})
        finally:
            conn.close()
    artifact = _active_cache["models"].get(pick_type)
    return (
        _predict_artifact(artifact, model_probability, market_probability)
        if artifact
        else model_probability
    )
