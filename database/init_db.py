"""Database bootstrap entrypoint."""

from __future__ import annotations

from database.schema import create_schema
from database.seed import seed_database


def initialize_database() -> None:
    """Create schema and seed baseline operational data."""

    create_schema()
    seed_database()
