"""Shared pytest fixtures + the ``--run-live`` gate.

Live tests (real broker/API calls) are skipped unless ``--run-live`` is passed AND creds
exist. This keeps the default `pytest` run hermetic and safe (never touches a venue).
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests marked `live` (needs real venue creds)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-live"):
        return
    skip_live = pytest.mark.skip(reason="needs --run-live + creds")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
