import threading
import time
import fcntl
import os

from flask import Flask, render_template
from flask.json.provider import DefaultJSONProvider


class NumpySafeJSONProvider(DefaultJSONProvider):

    @staticmethod
    def default(obj):
        try:
            import numpy as np

            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return DefaultJSONProvider.default(obj)


from config import Config
from web.routes.analytics_routes import analytics_bp
from web.routes.diagnostics_routes import diagnostics_bp
from web.routes.game_routes import game_bp
from web.routes.picks_routes import picks_bp
from web.routes.results_routes import results_bp
from web.routes.stats_routes import stats_bp
from web.routes.system_routes import system_bp
from services import dev_mode
from services.security_service import init_security, run_security_health_check


def _migrate_db():

    import sqlite3

    conn = sqlite3.connect("database/picks.db")
    existing = [r[1] for r in conn.execute("PRAGMA table_info(picks)").fetchall()]
    migrations = [
        ("opening_odds", "REAL"),
        ("closing_odds", "REAL"),
        ("clv", "REAL"),
        ("clv_captured_at", "TEXT"),
        ("model_version", "TEXT"),
        ("kelly_units", "REAL"),
        ("feature_snapshot", "TEXT"),
        ("home_score", "INTEGER"),
        ("away_score", "INTEGER"),
        ("actual_total", "INTEGER"),
        ("model_build", "TEXT"),
        ("opposite_opening_odds", "REAL"),
        ("opposite_closing_odds", "REAL"),
        ("opposite_clv", "REAL"),
        ("opposite_price_source", "TEXT"),
        ("forecast_stage", "TEXT"),
        ("scheduled_start", "TEXT"),
        ("recommendation_tier", "TEXT"),
        ("theoretical_kelly_units", "REAL"),
        ("realized_stake_units", "REAL"),
        ("wager_status", "TEXT"),
        ("wager_reason", "TEXT"),
        ("mlb_game_pk", "INTEGER"),
        ("graded_at", "TEXT"),
        ("grade_source", "TEXT"),
        ("notification_sent", "INTEGER NOT NULL DEFAULT 0"),
        ("notification_sent_at", "TEXT"),
    ]
    for col, typ in migrations:
        if col not in existing:
            conn.execute(f"ALTER TABLE picks ADD COLUMN {col} {typ}")
            print(f"  DB migration: added picks.{col}")

    conn.execute("UPDATE picks SET opening_odds = odds WHERE opening_odds IS NULL")

    conn.execute("UPDATE picks SET model_version = 'v2' WHERE model_version IS NULL")
    conn.execute("UPDATE picks SET model_build = model_version WHERE model_build IS NULL")
    conn.execute(
        """UPDATE picks SET recommendation_tier='historical_only'
           WHERE recommendation_tier IS NULL OR recommendation_tier='legacy_unclassified'"""
    )

    conn.execute("""CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pick_id INTEGER, game_id TEXT,
        actual_result TEXT, won INTEGER, profit_loss REAL, updated_at TEXT,
        FOREIGN KEY(pick_id) REFERENCES picks(id)
    )""")
    conn.execute("DELETE FROM results WHERE pick_id NOT IN (SELECT id FROM picks)")
    conn.execute(
        """DELETE FROM results WHERE id NOT IN (
               SELECT MIN(id) FROM results WHERE pick_id IS NOT NULL GROUP BY pick_id
           ) AND pick_id IS NOT NULL"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_results_pick_id ON results(pick_id)"
    )
    conn.execute("""UPDATE results SET
        game_id=(SELECT p.game_id FROM picks p WHERE p.id=results.pick_id),
        actual_result=(SELECT p.status FROM picks p WHERE p.id=results.pick_id),
        won=(SELECT CASE WHEN p.status='won' THEN 1 WHEN p.status='lost' THEN 0 END
             FROM picks p WHERE p.id=results.pick_id),
        profit_loss=(SELECT CASE WHEN p.status='won' THEN (p.odds-1)*20.0
                                 WHEN p.status='lost' THEN -20.0 ELSE 0 END
                     FROM picks p WHERE p.id=results.pick_id),
        updated_at=(SELECT COALESCE(p.updated_at,p.created_at) FROM picks p WHERE p.id=results.pick_id)
        WHERE pick_id IN (SELECT id FROM picks WHERE status IN ('won','lost'))""")
    conn.execute("""INSERT INTO results
        (pick_id,game_id,actual_result,won,profit_loss,updated_at)
        SELECT p.id,p.game_id,p.status,CASE WHEN p.status='won' THEN 1 ELSE 0 END,
               CASE WHEN p.status='won' THEN (p.odds-1)*20.0 ELSE -20.0 END,
               COALESCE(p.updated_at,p.created_at)
        FROM picks p
        WHERE p.status IN ('won','lost')
          AND NOT EXISTS (SELECT 1 FROM results r WHERE r.pick_id=p.id)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS prediction_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_game_id TEXT NOT NULL,
        action TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        date TEXT, matchup TEXT, pick_type TEXT, pick TEXT, odds REAL,
        model_prob REAL, ev REAL, model_version TEXT, feature_snapshot TEXT
    )""")
    audit_existing = [r[1] for r in conn.execute("PRAGMA table_info(prediction_audit)").fetchall()]
    for col, typ in [("forecast_stage", "TEXT"), ("scheduled_start", "TEXT")]:
        if col not in audit_existing:
            conn.execute(f"ALTER TABLE prediction_audit ADD COLUMN {col} {typ}")
    conn.execute("""CREATE TABLE IF NOT EXISTS automation_state (
        task_key TEXT PRIMARY KEY, claimed_at TEXT NOT NULL, completed_at TEXT,
        status TEXT NOT NULL, detail TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pick_id INTEGER NOT NULL,
        notification_type TEXT NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        claimed_at TEXT, sent_at TEXT, last_error TEXT,
        UNIQUE(pick_id, notification_type),
        FOREIGN KEY(pick_id) REFERENCES picks(id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT, captured_at TEXT NOT NULL,
        stage TEXT NOT NULL, event_id TEXT, commence_time TEXT,
        home_team TEXT, away_team TEXT, bookmaker TEXT, market TEXT,
        outcome TEXT, price REAL, point REAL,
        UNIQUE(captured_at,event_id,bookmaker,market,outcome,point)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_call_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, called_at TEXT, service TEXT,
        stage TEXT, status_code INTEGER, games INTEGER, requests_remaining TEXT,
        requests_used TEXT, request_cost TEXT, error TEXT)""")
    conn.execute("DROP TRIGGER IF EXISTS audit_pick_insert")
    conn.execute("DROP TRIGGER IF EXISTS audit_pick_update")
    conn.execute("""CREATE TRIGGER audit_pick_insert
        AFTER INSERT ON picks BEGIN
          INSERT INTO prediction_audit
          (pick_game_id,action,date,matchup,pick_type,pick,odds,model_prob,ev,model_version,feature_snapshot,forecast_stage,scheduled_start)
          VALUES (NEW.game_id,'created',NEW.date,NEW.matchup,NEW.pick_type,NEW.pick,NEW.odds,NEW.model_prob,NEW.ev,NEW.model_version,NEW.feature_snapshot,NEW.forecast_stage,NEW.scheduled_start);
        END""")
    conn.execute("""CREATE TRIGGER audit_pick_update
        BEFORE UPDATE OF pick,odds,model_prob,ev,feature_snapshot ON picks BEGIN
          INSERT INTO prediction_audit
          (pick_game_id,action,date,matchup,pick_type,pick,odds,model_prob,ev,model_version,feature_snapshot,forecast_stage,scheduled_start)
          VALUES (OLD.game_id,'superseded',OLD.date,OLD.matchup,OLD.pick_type,OLD.pick,OLD.odds,OLD.model_prob,OLD.ev,OLD.model_version,OLD.feature_snapshot,OLD.forecast_stage,OLD.scheduled_start);
        END""")
    conn.execute("""INSERT INTO prediction_audit
        (pick_game_id,action,date,matchup,pick_type,pick,odds,model_prob,ev,model_version,feature_snapshot)
        SELECT p.game_id,'historical_snapshot',p.date,p.matchup,p.pick_type,p.pick,p.odds,p.model_prob,p.ev,p.model_version,p.feature_snapshot
        FROM picks p WHERE NOT EXISTS (
          SELECT 1 FROM prediction_audit a WHERE a.pick_game_id=p.game_id
        )""")

    rows = conn.execute("SELECT id, model_prob, odds FROM picks").fetchall()
    for row_id, prob, odds in rows:
        if prob and odds:
            b = float(odds) - 1
            if b > 0:
                p, q = float(prob), 1 - float(prob)
                half_kelly = ((b * p - q) / b) * 0.5
                if half_kelly <= 0:
                    k = 0.0
                elif half_kelly < 0.05:
                    k = 0.25
                elif half_kelly < 0.10:
                    k = 0.50
                else:
                    k = 1.00
                conn.execute("UPDATE picks SET kelly_units = ? WHERE id = ?", (k, row_id))
    conn.execute(
        "UPDATE picks SET theoretical_kelly_units=kelly_units WHERE theoretical_kelly_units IS NULL"
    )
    conn.execute(
        """UPDATE picks SET wager_status='historical_unknown',
           wager_reason='realized stake was not recorded by the legacy execution pipeline'
           WHERE wager_status IS NULL"""
    )
    conn.commit()
    conn.close()


def create_app(config_class=Config):
    _migrate_db()
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.json_provider_class = NumpySafeJSONProvider
    app.json = NumpySafeJSONProvider(app)
    app.config.from_object(config_class)
    init_security(app)

    app.register_blueprint(picks_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(system_bp)
    dev_mode.init_app(app)

    @app.route("/picks")
    def picks():
        return render_template("picks.html")

    @app.route("/all-picks")
    def all_picks():
        return render_template("all_picks.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/analytics")
    def analytics():
        return render_template("analytics.html")

    @app.route("/live-scores")
    def live_scores():

        return render_template("live_scores.html")

    @app.route("/model-control")
    def model_control():
        return render_template("model_control.html")

    @app.route("/opposite-model")
    def opposite_model():
        return render_template("opposite_model.html")

    @app.route("/record-tracker")
    def record_tracker():
        return render_template("record_tracker.html")

    @app.route("/pikkit")
    def pikkit():
        return render_template("pikkit.html")

    @app.route("/market-signals")
    def market_signals():
        return render_template("market_signals.html")

    @app.route("/loss-review")
    def loss_review():
        return render_template("loss_review.html")

    @app.route("/security")
    def security():
        return render_template("security.html")

    return app


def _start_automation_worker(app):

    def worker():
        cycle = 0
        while True:
            try:
                from services.automation_service import run_automation_tick

                run_automation_tick()
            except Exception as exc:
                print(f"   Automatic live update failed: {exc}")
            if cycle % 5 == 0:
                with app.app_context():
                    status = run_security_health_check(app)
                if status["health"] != "healthy":
                    print("   Security monitor needs attention; open /security.")
            cycle += 1
            time.sleep(60)

    threading.Thread(target=worker, name="jingleez-automation", daemon=True).start()


if __name__ == "__main__":
    # Two historical launchd plists can point at this application.  Hold a
    # process-wide advisory lock before migrations or the scheduler start so a
    # second launcher can never create another grading worker.
    _instance_lock = open("/tmp/jingleez-betting-model.lock", "w")
    try:
        fcntl.flock(_instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another Jingleez betting-model instance is already running")
    _instance_lock.write(str(os.getpid()))
    _instance_lock.flush()
    app = create_app()
    _start_automation_worker(app)
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        use_reloader=False,
    )
