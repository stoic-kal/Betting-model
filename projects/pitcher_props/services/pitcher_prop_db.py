import sqlite3
from typing import Optional

DB_PATH = "database/picks.db"


def _conn(path: str = DB_PATH) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


_DDL = [
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_projections (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        projection_date     TEXT    NOT NULL,
        game_id             TEXT    NOT NULL,
        game_pk             INTEGER,
        player_id           INTEGER NOT NULL,
        player_name         TEXT    NOT NULL,
        team                TEXT    NOT NULL,
        opponent            TEXT    NOT NULL,
        prop_type           TEXT    NOT NULL,  -- outs_recorded|strikeouts|hits_allowed|walks_allowed
        model_version       TEXT,
        expected_value      REAL,              -- e.g. expected outs
        expected_ip         REAL,
        expected_pitches    REAL,
        expected_bf         REAL,
        std_value           REAL,
        early_removal_prob  REAL,
        starter_role        TEXT,
        starter_label       TEXT,
        lineup_confirmed    INTEGER DEFAULT 0,
        opp_lineup_ops      REAL,
        data_quality_score  REAL,
        data_quality_label  TEXT,
        has_fallback        INTEGER DEFAULT 0,
        feature_snapshot    TEXT,              -- JSON
        distribution_json   TEXT,              -- JSON {outs: prob, ...}
        created_at          TEXT    NOT NULL,
        updated_at          TEXT    NOT NULL
    )
""",
"CREATE INDEX IF NOT EXISTS idx_ppp_date_game ON pitcher_prop_projections(projection_date, game_id)",
"CREATE INDEX IF NOT EXISTS idx_ppp_player ON pitcher_prop_projections(player_id, prop_type)",
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_quotes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        captured_at     TEXT    NOT NULL,
        stage           TEXT    NOT NULL,  -- preview|morning|lineup_lock|closing|live
        event_id        TEXT    NOT NULL,
        game_pk         INTEGER,
        player_id       INTEGER,
        player_name     TEXT    NOT NULL,
        team            TEXT,
        opponent        TEXT,
        prop_type       TEXT    NOT NULL,
        bookmaker       TEXT    NOT NULL,
        line            REAL    NOT NULL,
        over_odds_dec   REAL,
        under_odds_dec  REAL,
        is_pregame      INTEGER DEFAULT 1,
        is_live         INTEGER DEFAULT 0,
        market_prob_over  REAL,             -- vig-free probability Over wins
        market_prob_under REAL
    )
""",
"CREATE INDEX IF NOT EXISTS idx_ppq_event_player ON pitcher_prop_quotes(event_id, player_id, prop_type)",
"CREATE INDEX IF NOT EXISTS idx_ppq_stage ON pitcher_prop_quotes(stage, captured_at)",
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_official_locks (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        lock_date           TEXT    NOT NULL,
        game_id             TEXT    NOT NULL,
        game_pk             INTEGER,
        player_id           INTEGER NOT NULL,
        player_name         TEXT    NOT NULL,
        team                TEXT    NOT NULL,
        opponent            TEXT    NOT NULL,
        prop_type           TEXT    NOT NULL,
        line                REAL    NOT NULL,
        pick_direction      TEXT    NOT NULL,  -- Over|Under
        model_prob          REAL    NOT NULL,  -- model's win probability for pick direction
        market_prob         REAL,              -- vig-free market prob for same direction
        edge_pp             REAL,              -- model_prob - market_prob (pp)
        ev_pct              REAL,              -- expected value %
        odds_dec            REAL,              -- best available decimal odds
        sportsbook          TEXT,
        fair_odds_dec       REAL,
        expected_value_stat REAL,              -- expected outs/K/H/BB (float)
        distribution_json   TEXT,              -- JSON snapshot of distribution
        data_quality_score  REAL,
        data_quality_label  TEXT,
        classification      TEXT    NOT NULL,  -- Daily Forecast|Qualified Pick|Strong Lock|Research Only
        forecast_stage      TEXT    NOT NULL,  -- preview|lineup_lock
        model_version       TEXT,
        feature_snapshot    TEXT,              -- JSON — frozen at lock time
        scheduled_start     TEXT,
        created_at          TEXT    NOT NULL,
        -- Result fields (filled after game)
        result_value        INTEGER,           -- actual outs/K/H/BB recorded
        result_status       TEXT,              -- won|lost|push|void|pending|review
        result_graded_at    TEXT,
        -- CLV fields
        closing_over_odds   REAL,
        closing_under_odds  REAL,
        closing_market_prob REAL,
        clv_pp              REAL,              -- model_prob - closing_market_prob
        clv_captured_at     TEXT,
        -- Uniqueness: one official lock per game/player/prop/line
        UNIQUE(game_id, player_id, prop_type, line)
    )
""",
"CREATE INDEX IF NOT EXISTS idx_ppol_date ON pitcher_prop_official_locks(lock_date)",
"CREATE INDEX IF NOT EXISTS idx_ppol_player ON pitcher_prop_official_locks(player_id, prop_type)",
"CREATE INDEX IF NOT EXISTS idx_ppol_result ON pitcher_prop_official_locks(result_status)",
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_results (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        lock_id         INTEGER NOT NULL REFERENCES pitcher_prop_official_locks(id),
        game_id         TEXT    NOT NULL,
        player_id       INTEGER NOT NULL,
        prop_type       TEXT    NOT NULL,
        line            REAL    NOT NULL,
        pick_direction  TEXT    NOT NULL,
        result_value    INTEGER,
        result_status   TEXT    NOT NULL,  -- won|lost|push|void|review
        void_reason     TEXT,
        source          TEXT,
        graded_at       TEXT    NOT NULL
    )
""",
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_model_versions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        prop_type       TEXT    NOT NULL,
        version         TEXT    NOT NULL,
        status          TEXT    NOT NULL DEFAULT 'active',  -- active|shadow|retired
        activated_at    TEXT,
        retired_at      TEXT,
        notes           TEXT,
        UNIQUE(prop_type, version)
    )
""",
"""
    CREATE TABLE IF NOT EXISTS pitcher_prop_learning_audit (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        run_at              TEXT    NOT NULL,
        prop_type           TEXT    NOT NULL,
        action              TEXT    NOT NULL,  -- evaluated|promoted|rolled_back|gate_failed
        champion_brier      REAL,
        challenger_brier    REAL,
        champion_mae        REAL,
        challenger_mae      REAL,
        champion_ece        REAL,
        challenger_ece      REAL,
        training_examples   INTEGER,
        holdout_examples    INTEGER,
        detail              TEXT
    )
""",
"""
    CREATE TABLE IF NOT EXISTS player_prop_market_cache (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        game_date         TEXT NOT NULL,
        fetched_at        TEXT NOT NULL,
        player_name       TEXT NOT NULL,
        prop_type         TEXT NOT NULL,
        line              REAL NOT NULL,
        over_dec          REAL,
        under_dec         REAL,
        over_american     REAL,
        under_american    REAL,
        market_prob_over  REAL,
        market_prob_under REAL,
        best_over_book    TEXT,
        best_under_book   TEXT,
        n_books           INTEGER,
        source            TEXT NOT NULL,
        UNIQUE(game_date, player_name, prop_type, line, source)
    )
""",
"CREATE INDEX IF NOT EXISTS idx_ppmc_date_source ON player_prop_market_cache(game_date, source)",
]


_SEED_VERSIONS = [
    ("outs_recorded", "v1.0", "active", "Initial shared-workload outs model"),
    ("strikeouts", "v1.0", "shadow", "Research only — not eligible for recommendations"),
    ("hits_allowed", "v1.0", "shadow", "Research only — not eligible for recommendations"),
    ("walks_allowed", "v1.0", "shadow", "Research only — not eligible for recommendations"),
]


def migrate(path: str = DB_PATH) -> list[str]:

    conn = _conn(path)
    applied = []
    try:
        for ddl in _DDL:
            conn.execute(ddl)
            applied.append(ddl.strip().split("\n")[0][:80])

        for prop_type, version, status, notes in _SEED_VERSIONS:
            conn.execute(
"""INSERT OR IGNORE INTO pitcher_prop_model_versions
                   (prop_type, version, status, activated_at, notes)
                   VALUES (?, ?, ?, datetime('now'), ?)""",
                (prop_type, version, status, notes),
            )
        conn.commit()
    finally:
        conn.close()
    return applied


def save_quotes(quotes: list[dict], path: str = DB_PATH) -> int:

    if not quotes:
        return 0
    conn = _conn(path)
    try:
        conn.executemany(
"""INSERT INTO pitcher_prop_quotes
               (captured_at, stage, event_id, game_pk, player_id, player_name,
                team, opponent, prop_type, bookmaker, line,
                over_odds_dec, under_odds_dec, is_pregame, is_live,
                market_prob_over, market_prob_under)
               VALUES (:captured_at, :stage, :event_id, :game_pk, :player_id, :player_name,
                :team, :opponent, :prop_type, :bookmaker, :line,
                :over_odds_dec, :under_odds_dec, :is_pregame, :is_live,
                :market_prob_over, :market_prob_under)""",
            quotes,
        )
        conn.commit()
        return len(quotes)
    finally:
        conn.close()


def get_best_quotes(
    event_id: str,
    player_id: Optional[int],
    prop_type: str,
    stage: str = "lineup_lock",
    path: str = DB_PATH,
) -> dict:

    conn = _conn(path)
    try:
        rows = conn.execute(
"""SELECT bookmaker, line, over_odds_dec, under_odds_dec, market_prob_over, market_prob_under
               FROM pitcher_prop_quotes
               WHERE event_id=? AND prop_type=? AND stage=? AND is_pregame=1
               ORDER BY captured_at DESC""",
            (event_id, prop_type, stage),
        ).fetchall()
        if player_id:
            rows = [r for r in rows]

        if not rows:
            return {}

        from collections import defaultdict

        by_line: dict = defaultdict(lambda: {"over": [], "under": [], "books": []})
        for book, line, over, under, mp_over, mp_under in rows:
            if over:
                by_line[line]["over"].append((over, book))
            if under:
                by_line[line]["under"].append((under, book))
            if book not in by_line[line]["books"]:
                by_line[line]["books"].append(book)

        result = {}
        for line, data in by_line.items():
            best_over = max(data["over"], key=lambda x: x[0]) if data["over"] else (None, None)
            best_under = max(data["under"], key=lambda x: x[0]) if data["under"] else (None, None)
            result[line] = {
"line": line,
"best_over_odds": best_over[0],
"best_over_book": best_over[1],
"best_under_odds": best_under[0],
"best_under_book": best_under[1],
"n_books": len(data["books"]),
"books": data["books"],
            }
        return result
    finally:
        conn.close()


def save_official_lock(lock: dict, path: str = DB_PATH) -> Optional[int]:

    conn = _conn(path)
    try:
        existing = conn.execute(
"""SELECT id FROM pitcher_prop_official_locks
               WHERE game_id=? AND player_id=? AND prop_type=? AND line=?""",
            (lock["game_id"], lock["player_id"], lock["prop_type"], lock["line"]),
        ).fetchone()
        if existing:
            return None

        cur = conn.execute(
"""INSERT INTO pitcher_prop_official_locks
               (lock_date, game_id, game_pk, player_id, player_name, team, opponent,
                prop_type, line, pick_direction, model_prob, market_prob, edge_pp,
                ev_pct, odds_dec, sportsbook, fair_odds_dec, expected_value_stat,
                distribution_json, data_quality_score, data_quality_label,
                classification, forecast_stage, model_version, feature_snapshot,
                scheduled_start, created_at, result_status)
               VALUES (:lock_date,:game_id,:game_pk,:player_id,:player_name,:team,:opponent,
                :prop_type,:line,:pick_direction,:model_prob,:market_prob,:edge_pp,
                :ev_pct,:odds_dec,:sportsbook,:fair_odds_dec,:expected_value_stat,
                :distribution_json,:data_quality_score,:data_quality_label,
                :classification,:forecast_stage,:model_version,:feature_snapshot,
                :scheduled_start,:created_at,'pending')""",
            lock,
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def grade_lock(
    lock_id: int,
    result_value: int,
    result_status: str,
    void_reason: Optional[str] = None,
    source: str = "auto",
    path: str = DB_PATH,
) -> bool:

    conn = _conn(path)
    try:
        row = conn.execute(
"SELECT result_status FROM pitcher_prop_official_locks WHERE id=?", (lock_id,)
        ).fetchone()
        if not row or row[0] not in ("pending", None, ""):
            return False

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
"""UPDATE pitcher_prop_official_locks
               SET result_value=?, result_status=?, result_graded_at=?
               WHERE id=?""",
            (result_value, result_status, now, lock_id),
        )

        lock = dict(
            zip(
                ["game_id", "player_id", "prop_type", "line", "pick_direction"],
                conn.execute(
"SELECT game_id,player_id,prop_type,line,pick_direction FROM pitcher_prop_official_locks WHERE id=?",
                    (lock_id,),
                ).fetchone()
                or [None] * 5,
            )
        )
        if lock.get("game_id"):
            conn.execute(
"""INSERT INTO pitcher_prop_results
                   (lock_id,game_id,player_id,prop_type,line,pick_direction,
                    result_value,result_status,void_reason,source,graded_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    lock_id,
                    lock["game_id"],
                    lock["player_id"],
                    lock["prop_type"],
                    lock["line"],
                    lock["pick_direction"],
                    result_value,
                    result_status,
                    void_reason,
                    source,
                    now,
                ),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def update_closing_clv(
    lock_id: int, closing_over: Optional[float], closing_under: Optional[float], path: str = DB_PATH
):

    conn = _conn(path)
    try:
        row = conn.execute(
"SELECT model_prob, pick_direction FROM pitcher_prop_official_locks WHERE id=?",
            (lock_id,),
        ).fetchone()
        if not row:
            return
        model_prob, direction = row

        closing_market_prob = None
        if closing_over and closing_under:
            raw_over = 1.0 / closing_over
            raw_under = 1.0 / closing_under
            total = raw_over + raw_under
            closing_market_prob = raw_over / total if direction == "Over" else raw_under / total
        clv = (model_prob - closing_market_prob) if (model_prob and closing_market_prob) else None

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
"""UPDATE pitcher_prop_official_locks
               SET closing_over_odds=?, closing_under_odds=?,
                   closing_market_prob=?, clv_pp=?, clv_captured_at=?
               WHERE id=?""",
            (closing_over, closing_under, closing_market_prob, clv, now, lock_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_market_cache(
    normalized: dict,
    game_date: str,
    path: str = DB_PATH,
) -> int:

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for player_name, props in normalized.items():
        for prop_type, lines in props.items():
            for line, q in lines.items():
                rows.append(
                    {
"game_date": game_date,
"fetched_at": now,
"player_name": player_name,
"prop_type": prop_type,
"line": float(line),
"over_dec": q.get("over_dec"),
"under_dec": q.get("under_dec"),
"over_american": q.get("over_american"),
"under_american": q.get("under_american"),
"market_prob_over": q.get("market_prob_over"),
"market_prob_under": q.get("market_prob_under"),
"best_over_book": q.get("best_over_book") or q.get("bookmaker"),
"best_under_book": q.get("best_under_book") or q.get("bookmaker"),
"n_books": q.get("n_books", 1),
"source": q.get("source", "unknown"),
                    }
                )
    if not rows:
        return 0
    conn = _conn(path)
    try:
        conn.executemany(
"""INSERT OR REPLACE INTO player_prop_market_cache
               (game_date, fetched_at, player_name, prop_type, line,
                over_dec, under_dec, over_american, under_american,
                market_prob_over, market_prob_under,
                best_over_book, best_under_book, n_books, source)
               VALUES
               (:game_date,:fetched_at,:player_name,:prop_type,:line,
                :over_dec,:under_dec,:over_american,:under_american,
                :market_prob_over,:market_prob_under,
                :best_over_book,:best_under_book,:n_books,:source)""",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def load_market_cache(
    game_date: str,
    max_age_hours: float = 2.0,
    path: str = DB_PATH,
) -> dict:

    from datetime import datetime, timezone, timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
    conn = _conn(path)
    try:
        rows = conn.execute(
"""SELECT player_name, prop_type, line,
                      over_dec, under_dec, over_american, under_american,
                      market_prob_over, market_prob_under,
                      best_over_book, best_under_book, n_books, source
               FROM player_prop_market_cache
               WHERE game_date=? AND fetched_at>=?
               ORDER BY player_name, prop_type, line""",
            (game_date, cutoff),
        ).fetchall()
    finally:
        conn.close()

    result: dict = {}
    for row in rows:
        (
            player,
            prop_type,
            line,
            over_dec,
            under_dec,
            over_am,
            under_am,
            mp_over,
            mp_under,
            best_over_book,
            best_under_book,
            n_books,
            source,
        ) = row
        result.setdefault(player, {}).setdefault(prop_type, {})[float(line)] = {
"line": float(line),
"over_dec": over_dec,
"under_dec": under_dec,
"over_american": over_am,
"under_american": under_am,
"market_prob_over": mp_over,
"market_prob_under": mp_under,
"best_over_book": best_over_book,
"best_under_book": best_under_book,
"n_books": n_books,
"source": source,
        }
    return result


def market_cache_age(game_date: str, path: str = DB_PATH) -> Optional[float]:

    from datetime import datetime, timezone

    conn = _conn(path)
    try:
        row = conn.execute(
"SELECT MAX(fetched_at) FROM player_prop_market_cache WHERE game_date=?",
            (game_date,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    try:
        fetched = datetime.fromisoformat(row[0])
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - fetched).total_seconds() / 60, 1)
    except ValueError:
        return None
