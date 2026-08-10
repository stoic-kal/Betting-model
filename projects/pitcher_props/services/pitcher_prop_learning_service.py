import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from services.pitcher_prop_db import DB_PATH
from services.pitcher_prop_analytics_service import (
    brier_score,
    mae,
    expected_calibration_error,
)

logger = logging.getLogger(__name__)


MIN_EXAMPLES_FOR_PROMOTION = 50


HOLDOUT_FRAC = 0.20


MIN_BRIER_IMPROVEMENT = 0.002
MIN_MAE_IMPROVEMENT = 0.10
MIN_ECE_IMPROVEMENT = 0.005


RESEARCH_ONLY_PROPS = frozenset({"strikeouts", "hits_allowed", "walks_allowed"})


def _conn(path: str = DB_PATH):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def _log_audit(
    conn: sqlite3.Connection,
    prop_type: str,
    action: str,
    champ: dict,
    challenger: dict,
    train_n: int,
    holdout_n: int,
    detail: str = "",
):
    conn.execute(
"""INSERT INTO pitcher_prop_learning_audit
           (run_at, prop_type, action, champion_brier, challenger_brier,
            champion_mae, challenger_mae, champion_ece, challenger_ece,
            training_examples, holdout_examples, detail)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            prop_type,
            action,
            champ.get("brier"),
            challenger.get("brier"),
            champ.get("mae"),
            challenger.get("mae"),
            champ.get("ece"),
            challenger.get("ece"),
            train_n,
            holdout_n,
            detail,
        ),
    )


def _fetch_resolved_outs(conn: sqlite3.Connection) -> list:

    return conn.execute("""SELECT *
           FROM pitcher_prop_official_locks
           WHERE prop_type='outs_recorded'
             AND forecast_stage='lineup_lock'
             AND result_status IN ('won','lost','push')
           ORDER BY lock_date ASC, id ASC""").fetchall()


def _metrics(rows: list) -> dict:

    return {
"brier": brier_score(rows),
"mae": mae(rows),
"ece": expected_calibration_error(rows),
"n": len(rows),
    }


def evaluate_challenger(
    challenger_model_version: str,
    path: str = DB_PATH,
) -> dict:

    conn = _conn(path)

    prop_type = "outs_recorded"

    try:
        rows = _fetch_resolved_outs(conn)
        n = len(rows)

        if n < MIN_EXAMPLES_FOR_PROMOTION:
            detail = f"Only {n} resolved examples — need {MIN_EXAMPLES_FOR_PROMOTION}"
            logger.info("Learning gate: %s", detail)
            _log_audit(conn, prop_type, "gate_failed", {}, {}, 0, 0, detail)
            conn.commit()
            return {"action": "gate_failed", "detail": detail}

        split_idx = int(n * (1 - HOLDOUT_FRAC))
        train = rows[:split_idx]
        holdout = rows[split_idx:]

        if len(holdout) < 10:
            detail = f"Holdout too small ({len(holdout)} rows) — need at least 10"
            _log_audit(conn, prop_type, "gate_failed", {}, {}, len(train), len(holdout), detail)
            conn.commit()
            return {"action": "gate_failed", "detail": detail}

        champ_rows = [r for r in holdout if r["model_version"] != challenger_model_version]
        chal_rows = [r for r in holdout if r["model_version"] == challenger_model_version]

        if len(chal_rows) < 5:
            detail = f"Challenger has only {len(chal_rows)} holdout predictions — insufficient"
            _log_audit(conn, prop_type, "gate_failed", {}, {}, len(train), len(holdout), detail)
            conn.commit()
            return {"action": "gate_failed", "detail": detail}

        champ_m = _metrics(champ_rows)
        chal_m = _metrics(chal_rows)

        brier_ok = (
            chal_m["brier"] is not None
            and champ_m["brier"] is not None
            and champ_m["brier"] - chal_m["brier"] >= MIN_BRIER_IMPROVEMENT
        )
        mae_ok = (
            chal_m["mae"] is not None
            and champ_m["mae"] is not None
            and champ_m["mae"] - chal_m["mae"] >= MIN_MAE_IMPROVEMENT
        )
        ece_ok = (
            chal_m["ece"] is not None
            and champ_m["ece"] is not None
            and champ_m["ece"] - chal_m["ece"] >= MIN_ECE_IMPROVEMENT
        )

        all_pass = brier_ok and mae_ok and ece_ok

        if all_pass:

            conn.execute(
"""UPDATE pitcher_prop_model_versions
                   SET status='retired', retired_at=datetime('now')
                   WHERE prop_type=? AND status='active'""",
                (prop_type,),
            )
            conn.execute(
"""INSERT OR IGNORE INTO pitcher_prop_model_versions
                   (prop_type, version, status, activated_at, notes)
                   VALUES (?, ?, 'active', datetime('now'), 'Promoted by champion-challenger evaluation')""",
                (prop_type, challenger_model_version),
            )
            _log_audit(
                conn,
                prop_type,
"promoted",
                champ_m,
                chal_m,
                len(train),
                len(holdout),
                f'Promoted {challenger_model_version} over champion. brier Δ={champ_m["brier"]-chal_m["brier"]:.4f}',
            )
            conn.commit()
            return {
"action": "promoted",
"challenger": challenger_model_version,
"champion_metrics": champ_m,
"challenger_metrics": chal_m,
            }
        else:
            gates_failed = []
            if not brier_ok:
                gates_failed.append(f'brier (champ={champ_m["brier"]}, chal={chal_m["brier"]})')
            if not mae_ok:
                gates_failed.append(f'mae (champ={champ_m["mae"]}, chal={chal_m["mae"]})')
            if not ece_ok:
                gates_failed.append(f'ece (champ={champ_m["ece"]}, chal={chal_m["ece"]})')
            detail = "Failed gates: " + "; ".join(gates_failed)
            _log_audit(
                conn, prop_type, "gate_failed", champ_m, chal_m, len(train), len(holdout), detail
            )
            conn.commit()
            return {
"action": "gate_failed",
"detail": detail,
"champion_metrics": champ_m,
"challenger_metrics": chal_m,
            }
    finally:
        conn.close()


def rollback_to_champion(prop_type: str, version: str, path: str = DB_PATH) -> bool:

    if prop_type in RESEARCH_ONLY_PROPS:
        logger.error("Cannot promote/rollback research-only prop %s", prop_type)
        return False

    conn = _conn(path)
    try:

        conn.execute(
"""UPDATE pitcher_prop_model_versions
               SET status='retired', retired_at=datetime('now')
               WHERE prop_type=? AND status='active'""",
            (prop_type,),
        )

        conn.execute(
"""UPDATE pitcher_prop_model_versions
               SET status='active', activated_at=datetime('now')
               WHERE prop_type=? AND version=?""",
            (prop_type, version),
        )
        _log_audit(conn, prop_type, "rolled_back", {}, {}, 0, 0, f"Manual rollback to {version}")
        conn.commit()
        return True
    finally:
        conn.close()
