import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

EASTERN = ZoneInfo("America/New_York")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")


def now_et():
    return datetime.now(EASTERN)


def today_et():
    return now_et().strftime("%Y-%m-%d")


class Config:
    DEBUG = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    TESTING = False
    TEMPLATES_AUTO_RELOAD = False
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 256 * 1024
    MAX_FORM_MEMORY_SIZE = 64 * 1024
    MAX_FORM_PARTS = 50
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PUBLIC_DEPLOYMENT = os.getenv("PUBLIC_DEPLOYMENT", "").lower() in {"1", "true", "yes"}
    SESSION_COOKIE_SECURE = PUBLIC_DEPLOYMENT
    SECURITY_ADMIN_TOKEN = os.getenv("SECURITY_ADMIN_TOKEN", "")
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "3000"))
    TRUSTED_HOSTS = [
        h.strip()
        for h in os.getenv("TRUSTED_HOSTS", "localhost,127.0.0.1,::1").split(",")
        if h.strip()
    ]


class DevelopmentConfig(Config):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class ProductionConfig(Config):
    DEBUG = False


EV_THRESHOLDS = {"moneyline": 0.000, "totals": 0.000, "high_confidence": 0.10}

FLASK_CONFIG = {"DEBUG": False, "PORT": 3000, "HOST": "127.0.0.1", "TEMPLATES_AUTO_RELOAD": True}
