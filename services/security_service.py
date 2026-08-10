import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from flask import g, has_request_context, jsonify, request

DB_PATH = "database/picks.db"
_rate_lock = threading.Lock()
_requests = defaultdict(deque)
EXPENSIVE_PATHS = {
"/api/run-picks",
"/api/generate-pick",
"/api/update-results",
"/api/capture-clv",
"/api/model-control/learning-cycle",
"/api/analytics/sandbox",
"/api/game-card",
}


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute("""CREATE TABLE IF NOT EXISTS security_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL,
        event_type TEXT NOT NULL, severity TEXT NOT NULL, request_id TEXT,
        remote_hash TEXT, method TEXT, path TEXT, detail TEXT)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_security_events_time
                    ON security_events(occurred_at)""")
    conn.commit()
    return conn


def _remote_hash(value):
    return hashlib.sha256((value or "unknown").encode()).hexdigest()[:16]


def record_security_event(event_type, severity="info", detail=None):
    try:
        in_request = has_request_context()
        conn = _connect()
        conn.execute(
"""INSERT INTO security_events
            (occurred_at,event_type,severity,request_id,remote_hash,method,path,detail)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                event_type,
                severity,
                getattr(g, "request_id", None) if in_request else None,
                _remote_hash(request.remote_addr) if in_request else None,
                request.method if in_request else None,
                request.path if in_request else None,
                json.dumps(detail or {}, separators=(",", ":"), default=str),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:

        pass


def _is_loopback(remote):
    return remote in {"127.0.0.1", "::1", "localhost"}


def _same_origin():
    fetch_site = request.headers.get("Sec-Fetch-Site")
    if fetch_site == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        return True
    expected = request.host_url.rstrip("/")
    return hmac.compare_digest(origin.rstrip("/"), expected)


def _authorized_admin(app):
    configured = app.config.get("SECURITY_ADMIN_TOKEN") or ""
    supplied = request.headers.get("X-Admin-Token", "")
    if configured and supplied:
        return hmac.compare_digest(configured, supplied)
    return not app.config.get("PUBLIC_DEPLOYMENT") and _is_loopback(request.remote_addr)


def _rate_allowed(limit=12, window=60):
    key = (_remote_hash(request.remote_addr), request.path)
    now = time.monotonic()
    with _rate_lock:
        bucket = _requests[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def secure_local_files():

    for path in (Path(".env"), Path(DB_PATH)):
        try:
            if path.exists():
                path.chmod(0o600)
        except OSError:
            pass


def run_security_health_check(app=None):
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    debug = bool(app and app.debug)
    add(
"debug_disabled",
        not debug,
"Debug mode is disabled." if not debug else "Debug mode is enabled.",
    )
    public = bool(app and app.config.get("PUBLIC_DEPLOYMENT"))
    token = bool(app and app.config.get("SECURITY_ADMIN_TOKEN"))
    add(
"public_admin_auth",
        not public or token,
        (
"Admin token configured."
            if token
            else ("Local-only mode." if not public else "Missing SECURITY_ADMIN_TOKEN.")
        ),
    )
    add(
"odds_key_present",
        bool(os.getenv("ODDS_API_KEY")),
"Configured." if os.getenv("ODDS_API_KEY") else "Missing.",
    )
    for filename in (".env", DB_PATH):
        path = Path(filename)
        mode = path.stat().st_mode & 0o777 if path.exists() else None
        add(
            f"permissions:{filename}",
            mode is None or mode & 0o077 == 0,
"Not present." if mode is None else oct(mode),
        )
    try:
        conn = _connect()

        available = conn.execute("SELECT 1").fetchone()[0]
        recent_blocks = conn.execute("""SELECT COUNT(*) FROM security_events
            WHERE severity IN ('warning','critical')
              AND occurred_at >= datetime('now','-24 hours')""").fetchone()[0]
        conn.close()
        add("database_available", available == 1, "SQLite is responsive.")
    except Exception as exc:
        recent_blocks = None
        add("database_available", False, str(exc))
    status = "healthy" if all(c["ok"] for c in checks) else "attention"
    result = {
"health": status,
"checked_at": datetime.now(timezone.utc).isoformat(),
"checks": checks,
"blocked_events_24h": recent_blocks,
    }
    record_security_event("health_check", "info" if status == "healthy" else "warning", result)
    return result


def get_security_status(app):
    result = run_security_health_check(app)
    conn = _connect()
    conn.row_factory = sqlite3.Row
    result["recent_events"] = [dict(row) for row in conn.execute("""
        SELECT occurred_at,event_type,severity,request_id,method,path,detail
        FROM security_events ORDER BY id DESC LIMIT 50""").fetchall()]
    conn.close()
    return result


def init_security(app):
    secure_local_files()

    try:
        conn = _connect()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.close()
    except sqlite3.Error:
        pass

    @app.before_request
    def security_before_request():
        g.request_id = uuid.uuid4().hex[:16]
        if request.path in EXPENSIVE_PATHS and not (
            request.path == "/api/game-card" and request.method == "GET"
        ):
            if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
                record_security_event("unsafe_method", "warning")
                return jsonify({"status": "error", "message": "This operation requires POST."}), 405
            if not _same_origin():
                record_security_event("cross_site_blocked", "warning")
                return jsonify({"status": "error", "message": "Cross-site request rejected."}), 403
            if request.headers.get("X-Requested-With") != "Jingleez":
                record_security_event("missing_request_header", "warning")
                return (
                    jsonify({"status": "error", "message": "Required request header missing."}),
                    403,
                )
            if not _authorized_admin(app):
                record_security_event("admin_denied", "critical")
                return (
                    jsonify(
                        {"status": "error", "message": "Administrative authorization required."}
                    ),
                    403,
                )
            if not _rate_allowed():
                record_security_event("rate_limited", "warning")
                return (
                    jsonify(
                        {
"status": "error",
"message": "Too many expensive requests. Try again shortly.",
                        }
                    ),
                    429,
                )

    @app.after_request
    def security_headers(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
"camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Content-Security-Policy"] = (
"default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
"form-action 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
"style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com; "
"font-src 'self' data: https://fonts.gstatic.com https://unpkg.com; "
"img-src 'self' data: https://midfield.mlbstatic.com https://img.mlbstatic.com; "
"connect-src 'self'; frame-src https://www.mlb.com"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.pop("Server", None)
        return response

    @app.errorhandler(413)
    def request_too_large(_):
        record_security_event("request_too_large", "warning")
        return jsonify({"status": "error", "message": "Request payload is too large."}), 413

    @app.route("/api/security-health")
    def security_health():
        if not _authorized_admin(app):
            record_security_event("health_denied", "warning")
            return jsonify({"status": "error", "message": "Not authorized."}), 403
        return jsonify({"status": "success", **get_security_status(app)})
