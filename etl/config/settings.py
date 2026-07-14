"""
config/settings.py
===================
Centralised, environment-driven configuration for the Telecom Churn ETL
pipeline.

Design goals
------------
* Zero hardcoded secrets (database password, host, etc. are always read
  from environment variables / a ``.env`` file, never from source code).
* A single, immutable ``Settings`` object is constructed once and passed
  around the application, making configuration explicit and testable.
* Fails fast: missing mandatory variables raise a clear ``ConfigError`` at
  start-up rather than a confusing exception deep inside the pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load a local .env file if present. This is a no-op in environments (CI/CD,
# containers) where real environment variables are injected directly.
load_dotenv()


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_env(name: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Fetch an environment variable with optional default / required check."""
    value = os.environ.get(name, default)
    if required and (value is None or value == ""):
        raise ConfigError(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example to .env and populate it, or export the "
            f"variable in your shell/CI environment."
        )
    return value


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Environment variable '{name}' must be an integer, got: {raw!r}") from exc


def _get_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    # --- Database ---
    db_host: str
    db_port: int
    db_name: str
    db_schema: str
    db_user: str
    db_password: str
    db_pool_size: int
    db_max_overflow: int
    db_connect_timeout_seconds: int

    # --- Source data ---
    csv_path: Path

    # --- Pipeline behavior ---
    snapshot_date: date
    bulk_insert_batch_size: int
    drop_invalid_rows: bool

    # --- Output locations ---
    reports_dir: Path
    logs_dir: Path
    log_level: str

    @property
    def sqlalchemy_url(self) -> str:
        """Build a SQLAlchemy connection URL for psycopg2."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def masked_url(self) -> str:
        """Connection URL with the password redacted, safe for logging."""
        return (
            f"postgresql+psycopg2://{self.db_user}:***"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


def load_settings() -> Settings:
    """
    Build a Settings instance from environment variables.

    Raises
    ------
    ConfigError
        If a required variable is missing or a value cannot be parsed.
    """
    snapshot_date_raw = _get_env("SNAPSHOT_DATE", default="")
    if snapshot_date_raw:
        try:
            snapshot_date = datetime.strptime(snapshot_date_raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ConfigError(
                f"SNAPSHOT_DATE must be in YYYY-MM-DD format, got: {snapshot_date_raw!r}"
            ) from exc
    else:
        snapshot_date = date.today()

    settings = Settings(
        db_host=_get_env("DB_HOST", "localhost"),
        db_port=_get_int_env("DB_PORT", 5432),
        db_name=_get_env("DB_NAME", required=True),
        db_schema=_get_env("DB_SCHEMA", "churn"),
        db_user=_get_env("DB_USER", required=True),
        db_password=_get_env("DB_PASSWORD", required=True),
        db_pool_size=_get_int_env("DB_POOL_SIZE", 5),
        db_max_overflow=_get_int_env("DB_MAX_OVERFLOW", 10),
        db_connect_timeout_seconds=_get_int_env("DB_CONNECT_TIMEOUT_SECONDS", 10),
        csv_path=Path(_get_env("CSV_PATH", "data/telecom_churn.csv")),
        snapshot_date=snapshot_date,
        bulk_insert_batch_size=_get_int_env("BULK_INSERT_BATCH_SIZE", 5000),
        drop_invalid_rows=_get_bool_env("DROP_INVALID_ROWS", True),
        reports_dir=Path(_get_env("REPORTS_DIR", "reports")),
        logs_dir=Path(_get_env("LOGS_DIR", "logs")),
        log_level=_get_env("LOG_LEVEL", "INFO").upper(),
    )

    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    return settings
