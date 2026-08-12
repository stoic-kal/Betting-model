"""Canonical, immutable storage primitives for the MLB data platform."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

WAREHOUSE_PATH = "database/mlb_data_platform.db"
SCHEMA_VERSION = "1"

TEAM_ALIASES = {
    "ANA": "LAA", "FLA": "MIA", "MON": "WSH", "TBD": "TB", "WSN": "WSH", "WAS": "WSH",
    "KCA": "KC", "CHA": "CWS", "CHN": "CHC", "NYA": "NYY", "NYN": "NYM",
    "LAN": "LAD", "SLN": "STL", "SFN": "SF", "SDN": "SD", "TBA": "TB",
    "OAK": "ATH",
}

DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id TEXT PRIMARY KEY, source TEXT NOT NULL, source_version TEXT NOT NULL,
  source_sha256 TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT,
  status TEXT NOT NULL, row_count INTEGER NOT NULL DEFAULT 0, detail_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS canonical_games (
  canonical_game_id TEXT PRIMARY KEY, game_pk INTEGER UNIQUE, game_date TEXT NOT NULL,
  scheduled_start_utc TEXT, home_team TEXT NOT NULL, away_team TEXT NOT NULL,
  doubleheader_number INTEGER NOT NULL DEFAULT 0, game_type TEXT,
  status TEXT, resume_date TEXT, venue_id INTEGER, venue_name TEXT,
  source_first_seen TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_schedule
ON canonical_games(game_date,home_team,away_team,doubleheader_number);
CREATE TABLE IF NOT EXISTS game_aliases (
  source TEXT NOT NULL, source_game_id TEXT NOT NULL, canonical_game_id TEXT NOT NULL,
  confidence TEXT NOT NULL, evidence_json TEXT NOT NULL,
  PRIMARY KEY(source,source_game_id), FOREIGN KEY(canonical_game_id) REFERENCES canonical_games(canonical_game_id)
);
CREATE TABLE IF NOT EXISTS player_aliases (
  source TEXT NOT NULL, source_player_id TEXT NOT NULL, mlb_player_id INTEGER,
  canonical_player_id TEXT NOT NULL, player_name TEXT, evidence_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY(source,source_player_id)
);
CREATE TABLE IF NOT EXISTS player_game_history (
  source TEXT NOT NULL, source_game_id TEXT NOT NULL, canonical_game_id TEXT NOT NULL,
  source_player_id TEXT NOT NULL, team TEXT NOT NULL, opponent TEXT NOT NULL,
  game_date TEXT NOT NULL, appearance_date TEXT, source_quality TEXT NOT NULL,
  batting_json TEXT NOT NULL, pitching_json TEXT NOT NULL, fielding_json TEXT NOT NULL,
  ingestion_run_id TEXT NOT NULL, row_sha256 TEXT NOT NULL UNIQUE,
  FOREIGN KEY(canonical_game_id) REFERENCES canonical_games(canonical_game_id)
);
CREATE TABLE IF NOT EXISTS team_game_history (
  source TEXT NOT NULL, source_game_id TEXT NOT NULL, canonical_game_id TEXT NOT NULL,
  team TEXT NOT NULL, opponent TEXT NOT NULL, game_date TEXT NOT NULL,
  source_quality TEXT NOT NULL, batting_json TEXT NOT NULL, pitching_json TEXT NOT NULL,
  fielding_json TEXT NOT NULL, ingestion_run_id TEXT NOT NULL, row_sha256 TEXT NOT NULL UNIQUE,
  FOREIGN KEY(canonical_game_id) REFERENCES canonical_games(canonical_game_id)
);
CREATE TABLE IF NOT EXISTS historical_market_snapshots (
  source TEXT NOT NULL, source_event_id TEXT NOT NULL, canonical_game_id TEXT,
  captured_at TEXT, commence_time TEXT, bookmaker TEXT NOT NULL, market TEXT NOT NULL,
  outcome TEXT NOT NULL, price_american REAL, price_decimal REAL, point REAL,
  is_closing INTEGER NOT NULL DEFAULT 0, ingestion_run_id TEXT NOT NULL,
  row_sha256 TEXT NOT NULL UNIQUE, raw_json TEXT NOT NULL,
  FOREIGN KEY(canonical_game_id) REFERENCES canonical_games(canonical_game_id)
);
CREATE TABLE IF NOT EXISTS identity_quarantine (
  source TEXT NOT NULL, source_game_id TEXT NOT NULL, reason TEXT NOT NULL,
  payload_json TEXT NOT NULL, ingestion_run_id TEXT NOT NULL,
  PRIMARY KEY(source,source_game_id,reason)
);
CREATE TABLE IF NOT EXISTS dataset_manifests (
  dataset_name TEXT NOT NULL, version TEXT NOT NULL, created_at TEXT NOT NULL,
  row_count INTEGER NOT NULL, sha256 TEXT NOT NULL, query_json TEXT NOT NULL,
  PRIMARY KEY(dataset_name,version)
);
"""


def connect(path=WAREHOUSE_PATH):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def normalize_team(team):
    value = str(team or "").strip().upper()
    return TEAM_ALIASES.get(value, value)


def american_to_decimal(price):
    if price is None:
        return None
    value = float(price)
    if value == 0:
        raise ValueError("American odds cannot be zero")
    return 1 + value / 100 if value > 0 else 1 + 100 / abs(value)


def begin_run(conn, source, source_version, source_sha256):
    run_id = stable_hash({"source": source, "version": source_version, "sha": source_sha256})[:24]
    conn.execute("""INSERT OR IGNORE INTO ingestion_runs
      (run_id,source,source_version,source_sha256,started_at,status)
      VALUES (?,?,?,?,?,'running')""", (run_id, source, source_version, source_sha256, utc_now()))
    conn.commit()
    return run_id


def finish_run(conn, run_id, status, row_count, detail):
    conn.execute("""UPDATE ingestion_runs SET completed_at=?,status=?,row_count=?,detail_json=?
      WHERE run_id=?""", (utc_now(), status, int(row_count), json.dumps(detail, sort_keys=True), run_id))
    conn.commit()


def source_canonical_id(source, source_game_id):
    return f"{source}:{source_game_id}"


def register_source_game(conn, source, source_game_id, game_date, home_team, away_team,
                         doubleheader_number=0, game_pk=None, venue_name=None,
                         game_type=None, status=None, resume_date=None, confidence="source"):
    home, away = normalize_team(home_team), normalize_team(away_team)
    existing = None
    if game_pk is not None:
        existing = conn.execute("SELECT canonical_game_id FROM canonical_games WHERE game_pk=?", (int(game_pk),)).fetchone()
    if existing is None:
        existing = conn.execute("""SELECT canonical_game_id FROM canonical_games
          WHERE game_date=? AND home_team=? AND away_team=? AND doubleheader_number=?""",
          (game_date, home, away, int(doubleheader_number or 0))).fetchone()
    canonical_id = existing[0] if existing else (f"mlb:{int(game_pk)}" if game_pk is not None else source_canonical_id(source, source_game_id))
    conn.execute("""INSERT OR IGNORE INTO canonical_games
      (canonical_game_id,game_pk,game_date,home_team,away_team,doubleheader_number,game_type,status,resume_date,venue_name,source_first_seen,created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
      (canonical_id, game_pk, game_date, home, away, int(doubleheader_number or 0), game_type,
       status, resume_date, venue_name, source, utc_now()))
    conn.execute("""INSERT OR REPLACE INTO game_aliases
      (source,source_game_id,canonical_game_id,confidence,evidence_json) VALUES (?,?,?,?,?)""",
      (source, str(source_game_id), canonical_id, confidence,
       json.dumps({"date": game_date, "home": home, "away": away, "doubleheader": doubleheader_number}, sort_keys=True)))
    return canonical_id
