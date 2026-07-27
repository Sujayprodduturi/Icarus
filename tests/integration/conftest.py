"""Integration-test fixtures: real Postgres + Valkey (docker compose up).

Skips the whole integration suite cleanly when the services aren't reachable, so the default
`pytest` run stays green on a machine without Docker. CI brings the services up (see ci.yml).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, text

PG_DSN = os.environ.get("ICARUS_PG_DSN", "postgresql+psycopg://icarus:icarus@localhost:5432/icarus")


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    engine = create_engine(PG_DSN)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # no DB -> skip integration tests, don't fail the run
        pytest.skip(f"Postgres not reachable ({exc}); run `docker compose up`")
    yield engine
    engine.dispose()
