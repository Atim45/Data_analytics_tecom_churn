"""
utils/logger.py
================
Centralised logging configuration for the ETL pipeline.

Every pipeline run writes to:
  * console (INFO and above, human readable)
  * a timestamped log file under ``logs/`` (full detail, per configured
    LOG_LEVEL) for later audit/debugging.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(logs_dir: Path, log_level: str = "INFO", run_id: str | None = None) -> logging.Logger:
    """
    Configure and return the root ETL logger.

    Parameters
    ----------
    logs_dir : Path
        Directory where the timestamped log file will be written.
    log_level : str
        Logging level name (DEBUG, INFO, WARNING, ERROR).
    run_id : str, optional
        Identifier appended to the log filename. Defaults to a timestamp.

    Returns
    -------
    logging.Logger
        Configured logger named "telecom_churn_etl".
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"etl_run_{run_id}.log"

    logger = logging.getLogger("telecom_churn_etl")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False

    # Avoid duplicate handlers if setup_logger() is called more than once
    # (e.g. in tests).
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(getattr(logging, log_level, logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info("Logger initialised. Writing full log to: %s", log_file)
    return logger


def get_logger() -> logging.Logger:
    """Return the already-configured ETL logger (call setup_logger() first)."""
    return logging.getLogger("telecom_churn_etl")
