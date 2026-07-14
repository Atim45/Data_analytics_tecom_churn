"""
Structured logging setup for Telecom Churn API.
Supports JSON formatting, file rotation, and console output.
"""

import json
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = LOG_DIR / "churn_api.log"
MAX_BYTES = 10 * 1024 * 1024   # 10 MB per file
BACKUP_COUNT = 5                # Keep 5 rotated files


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    SKIP_FIELDS = {
        "args", "exc_text", "filename", "funcName", "lineno",
        "module", "msecs", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include extra fields injected via logger.info("...", extra={...})
        for key, value in record.__dict__.items():
            if key not in self.SKIP_FIELDS and not key.startswith("_") and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Coloured human-readable formatter for console output."""

    COLOURS = {
        "DEBUG":    "\033[94m",   # blue
        "INFO":     "\033[92m",   # green
        "WARNING":  "\033[93m",   # yellow
        "ERROR":    "\033[91m",   # red
        "CRITICAL": "\033[95m",   # magenta
    }
    RESET = "\033[0m"

    FMT = "{colour}[{level}]{reset} {ts} | {name} | {message}"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self.COLOURS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S")
        line = self.FMT.format(
            colour=colour,
            level=record.levelname[0],
            reset=self.RESET,
            ts=ts,
            name=record.name,
            message=record.getMessage(),
        )
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(name: str = "churn_api") -> logging.Logger:
    """
    Build and return a fully configured logger.

    Call once at application startup:
        logger = configure_logging()

    Subsequent modules should use:
        import logging
        logger = logging.getLogger("churn_api")
    """
    root = logging.getLogger(name)
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Prevent duplicate handlers if called multiple times
    if root.handlers:
        return root

    # ── Console handler (human-readable) ──────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    use_json_console = os.getenv("LOG_JSON_CONSOLE", "false").lower() == "true"
    console_handler.setFormatter(JSONFormatter() if use_json_console else HumanFormatter())
    root.addHandler(console_handler)

    # ── Rotating file handler (JSON) ───────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)   # capture everything to disk
    file_handler.setFormatter(JSONFormatter())
    root.addHandler(file_handler)

    # ── Error-only file handler ────────────────────────────────────────────
    error_file = LOG_DIR / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        filename=error_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JSONFormatter())
    root.addHandler(error_handler)

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info(
        "Logging initialised",
        extra={"log_file": str(LOG_FILE), "level": LOG_LEVEL},
    )
    return root


# Module-level convenience logger (lazy — does NOT call configure_logging)
logger: logging.Logger = logging.getLogger("churn_api")
