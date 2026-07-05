import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv(override=True)


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    PERMANENT_SESSION_LIFETIME = timedelta(
        seconds=int(os.environ.get("SESSION_LIFETIME_SECONDS", "86400"))
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))

    # ── PostgreSQL Database Configuration ────────────────────────────────
    # Read the full connection string from DATABASE_URL.
    # Example: postgresql://user:password@host:5432/dbname?sslmode=require
    DATABASE_URL = os.environ.get("DATABASE_URL")

    # Back-compat: allow legacy DB_* variables to construct a URL if
    # DATABASE_URL is not provided directly.
    if not DATABASE_URL:
        _db_user = os.environ.get("DB_USER")
        _db_pw = os.environ.get("DB_PASSWORD")
        _db_host = os.environ.get("DB_HOST")
        _db_port = os.environ.get("DB_PORT", "5432")
        _db_name = os.environ.get("DB_NAME")
        if _db_user and _db_host and _db_name:
            DATABASE_URL = (
                f"postgresql://{_db_user}:{_db_pw or ''}@{_db_host}:{_db_port}/{_db_name}"
            )

    MODEL_PATH = os.environ.get("MODEL_PATH", "models/sign_language_model.h5")
    CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.70"))
    FRAME_RATE = int(os.environ.get("FRAME_RATE", "10"))

    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    # On Hugging Face Spaces the app is served behind HTTPS, so secure cookies are safe.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"

    def __init__(self):
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret == "dev-secret-change-in-prod":
            # Auto-generate one so the app can still boot in free hosting
            # environments where the user forgot to set it. Log a warning.
            import logging
            import secrets as _secrets
            logging.getLogger(__name__).warning(
                "SECRET_KEY not set — generated an ephemeral one. "
                "Set SECRET_KEY env var for stable sessions."
            )
            self.SECRET_KEY = _secrets.token_hex(32)
        else:
            self.SECRET_KEY = secret


class TestingConfig(BaseConfig):
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    cls = CONFIG_MAP.get(env, DevelopmentConfig)
    return cls()
