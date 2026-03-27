import os
from pathlib import Path


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = Path(os.getenv("DB_PATH", "coaching.db")).resolve()
DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL") or f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5173")
APP_SECRET = os.getenv("APP_SECRET") or os.getenv("ADMIN_PASSWORD") or "change-this-secret-before-production"
AUTH_ACCESS_TTL_SECONDS = int(os.getenv("AUTH_ACCESS_TTL_SECONDS", str(12 * 60 * 60)))
AUTH_REFRESH_TTL_SECONDS = int(os.getenv("AUTH_REFRESH_TTL_SECONDS", str(7 * 24 * 60 * 60)))
REQUEST_SIZE_LIMIT_BYTES = int(os.getenv("REQUEST_SIZE_LIMIT_BYTES", str(10 * 1024 * 1024)))
UPLOAD_SIZE_LIMIT_BYTES = int(os.getenv("UPLOAD_SIZE_LIMIT_BYTES", str(5 * 1024 * 1024)))
WHATSAPP_TIMEOUT_SECONDS = float(os.getenv("WHATSAPP_TIMEOUT_SECONDS", "15"))
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
APP_ENV = os.getenv("APP_ENV", "development")
IS_PRODUCTION = APP_ENV.lower() == "production"
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", APP_ENV)
STRUCTLOG_JSON = os.getenv("STRUCTLOG_JSON", "false").lower() == "true"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "200/minute")
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
SEARCH_MAX_LENGTH = int(os.getenv("SEARCH_MAX_LENGTH", "100"))
INDIA_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "91")
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")
DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "50"))
MAX_PAGE_SIZE = int(os.getenv("MAX_PAGE_SIZE", "200"))
