"""SQLite connection management for PharmaGuard AI."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH, ensure_directories


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Create a configured SQLite connection."""

    ensure_directories()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    """Provide a transactional database session."""

    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
