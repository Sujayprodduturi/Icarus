"""Validate or explicitly import the schema-1 JSON trial ledger into PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import create_engine

from icarus.state.trial_ledger import PostgresTrialLedger, read_legacy_portfolio_ledger


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--apply", action="store_true")
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args(argv)

    legacy = read_legacy_portfolio_ledger(args.source)
    if args.check:
        print(
            json.dumps(
                {
                    "legacy_schema": legacy.schema,
                    "legacy_entry_count": len(legacy.trials),
                    "legacy_sha256": legacy.sha256,
                },
                sort_keys=True,
            )
        )
        return 0

    dsn = os.environ.get("ICARUS_PG_DSN")
    if not dsn:
        raise SystemExit("ICARUS_PG_DSN is required for --apply")
    engine = create_engine(dsn)
    try:
        receipt = PostgresTrialLedger(engine).import_legacy_and_activate(legacy)
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "legacy_entry_count": receipt.legacy_entry_count,
                "legacy_sha256": receipt.legacy_sha256,
                "lifetime_trial_count": receipt.lifetime_trial_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
