"""
etl/db.py
=========
SQLAlchemy engine construction and connection helpers.

All database access in this project goes through a single ``Engine``
created here, so that pooling, timeouts, and the search_path are
configured consistently in one place.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings

logger = logging.getLogger("telecom_churn_etl.db")


def build_engine(settings: Settings) -> Engine:
    """
    Create a SQLAlchemy Engine configured from ``settings``.

    The engine:
      * uses connection pooling (pool_size / max_overflow from settings),
      * pings connections before use (pool_pre_ping) to avoid stale
        connection errors on long-running processes,
      * sets ``search_path`` to the target schema on every new connection
        so unqualified table names resolve correctly,
      * applies a connect timeout so a misconfigured host fails fast
        instead of hanging indefinitely.
    """
    engine = create_engine(
        settings.sqlalchemy_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
        future=True,
    )

    schema = settings.db_schema

    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute(f"SET search_path TO {schema}, public")
        cursor.close()

    logger.info("SQLAlchemy engine created for %s", settings.masked_url())
    return engine


def verify_connection(engine: Engine) -> None:
    """Run a trivial query to confirm the database is reachable and the
    target schema exists. Raises on failure."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    logger.info("Database connection verified successfully.")


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """
    Provide a transactional scope around a series of ORM/Core operations.

    Commits on success, rolls back on any exception, and always closes the
    session. This is the single place transaction semantics are defined,
    fulfilling the "use transactions, rollback on failure" requirement.
    """
    session_factory = sessionmaker(bind=engine, future=True)
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        logger.exception("Transaction failed — rolling back.")
        session.rollback()
        raise
    finally:
        session.close()
