import json
import sqlite3
from datetime import datetime, timezone

from pipeline import model_manager

DB_PATH = "database/picks.db"

TEAM_IDS = {
    "AZ": 109, "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CIN": 113,
    "CLE": 114, "COL": 115, "CWS": 145, "DET": 116, "HOU": 117, "KC": 118, "LAA": 108,
    "LAD": 119, "MIA": 146, "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "ATH": 133,
    "PHI": 143, "PIT": 134, "SD": 135, "SEA": 136, "SF": 137, "STL": 138, "TB": 139,
    "TEX": 140, "TOR": 141, "WSH": 120, "WSN": 120,
}

VENUE_IDS = {
    "ARI": 15, "ATL": 4705, "BAL": 2, "BOS": 3, "CHC": 17, "CIN": 2602, "CLE": 5,
    "COL": 19, "CWS": 4, "DET": 2394, "HOU": 2392, "KC": 7, "LAA": 1, "LAD": 22,
    "MIA": 4169, "MIL": 32, "MIN": 3312, "NYM": 3289, "NYY": 3313, "ATH": 10,
    "PHI": 2681, "PIT": 31, "SD": 2680, "SEA": 680, "SF": 2395, "STL": 2889,
    "TB": 12, "TEX": 5325, "TOR": 14, "WSH": 3309,
}

IDENTITY_COLUMNS = (
    "model_version", "model_family", "feature_schema_version", "dataset_version",
    "calibration_version", "prediction_pipeline_version",
)


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS shadow_v2_predictions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at TEXT NOT NULL, "
        "pick_type TEXT NOT NULL, "
        "matchup TEXT NOT NULL, "
        "production_model_prob REAL, "
        "market_prob REAL, "
        "v2_model_prob REAL, "
        "odds_dec REAL, "
        "schema_version TEXT, "
        "degraded_features TEXT, "
        "features TEXT"
        ")"
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(shadow_v2_predictions)").fetchall()}
    if "odds_dec" not in existing:
        conn.execute("ALTER TABLE shadow_v2_predictions ADD COLUMN odds_dec REAL")
    if "schema_version" not in existing:
        conn.execute("ALTER TABLE shadow_v2_predictions ADD COLUMN schema_version TEXT")
    for column in IDENTITY_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE shadow_v2_predictions ADD COLUMN {column} TEXT")
    conn.commit()


def _log(pick_type, matchup, production_prob, market_prob, v2_prob, odds_dec, schema_version,
         degraded, features, identity):
    try:
        conn = sqlite3.connect(DB_PATH)
        _ensure_table(conn)
        conn.execute(
            "INSERT INTO shadow_v2_predictions "
            "(created_at, pick_type, matchup, production_model_prob, market_prob, v2_model_prob, odds_dec, "
            "schema_version, degraded_features, features, " + ", ".join(IDENTITY_COLUMNS) + ") "
            "VALUES (?,?,?,?,?,?,?,?,?,?," + ",".join("?" for _ in IDENTITY_COLUMNS) + ")",
            (
                datetime.now(timezone.utc).isoformat(), pick_type, matchup,
                production_prob, market_prob, v2_prob, odds_dec, schema_version,
                json.dumps(degraded), json.dumps(features),
            ) + tuple(identity.get(column) for column in IDENTITY_COLUMNS),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def shadow_moneyline(home_abbr, away_abbr, home_sp_id, away_sp_id, scheduled_start, production_prob, market_prob, odds_dec):
    if not home_sp_id or not away_sp_id:
        return
    loaded = model_manager.get_moneyline_model("shadow_inference")
    if loaded is None:
        return
    try:
        from pipeline.live_features_v2 import compute_v2_features
        game_dt = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00")) if scheduled_start else datetime.now(timezone.utc)
        home_team_id = TEAM_IDS.get(home_abbr)
        away_team_id = TEAM_IDS.get(away_abbr)
        venue_id = VENUE_IDS.get(home_abbr)
        if not home_team_id or not away_team_id or not venue_id:
            return
        result = compute_v2_features(
            home_team=home_abbr, away_team=away_abbr,
            home_team_id=home_team_id, away_team_id=away_team_id,
            home_sp_id=home_sp_id, away_sp_id=away_sp_id,
            venue_id=venue_id, game_datetime=game_dt,
        )
        import pandas as pd
        X = pd.DataFrame([result["features"]])[loaded.features]
        v2_prob = float(loaded.model.predict_proba(X)[0, 1])
        _log(
            "moneyline", f"{away_abbr} @ {home_abbr}", production_prob, market_prob, v2_prob,
            odds_dec, result["schema_version"], result["degraded"], result["features"], loaded.identity,
        )
    except Exception:
        pass


def shadow_totals(home_abbr, away_abbr, home_sp_id, away_sp_id, scheduled_start, production_prob, market_line, odds_dec, pick_is_over):
    if not home_sp_id or not away_sp_id:
        return
    loaded = model_manager.get_totals_model("shadow_inference")
    if loaded is None:
        return
    try:
        from pipeline.live_features_v2 import compute_v2_features
        game_dt = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00")) if scheduled_start else datetime.now(timezone.utc)
        home_team_id = TEAM_IDS.get(home_abbr)
        away_team_id = TEAM_IDS.get(away_abbr)
        venue_id = VENUE_IDS.get(home_abbr)
        if not home_team_id or not away_team_id or not venue_id:
            return
        result = compute_v2_features(
            home_team=home_abbr, away_team=away_abbr,
            home_team_id=home_team_id, away_team_id=away_team_id,
            home_sp_id=home_sp_id, away_sp_id=away_sp_id,
            venue_id=venue_id, game_datetime=game_dt,
        )
        import pandas as pd
        X = pd.DataFrame([result["features"]])[loaded.features]
        v2_prob_over = float(loaded.model.predict_proba(X)[0, 1])
        v2_prob_picked_side = v2_prob_over if pick_is_over else (1.0 - v2_prob_over)
        _log(
            "totals", f"{away_abbr} @ {home_abbr}", production_prob, market_line, v2_prob_picked_side,
            odds_dec, result["schema_version"], result["degraded"], result["features"], loaded.identity,
        )
    except Exception:
        pass
