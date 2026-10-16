"""Run the invented seven-card daily-pilot proof or print held actual-run status."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine

from icarus.common.config import load_goal
from icarus.engine.daily_pilot import (
    build_invented_admission,
    load_actual_admission,
    load_daily_pilot_spec,
    publish_json_once,
    run_actual_daily_pilot,
    run_invented_daily_pilot,
)
from icarus.engine.timed_runner import ExecutionBinding, parse_run_authorization_json
from icarus.state.trial_ledger import PostgresTrialLedger

PROJECT = Path(__file__).resolve().parents[1]
INVENTORY = PROJECT / "config/daily_pilot_inventory.json"
SOURCE_INVENTORY = (
    PROJECT / "var/daily-descriptive-pilot/2026-10-16/source-inventory/source-inventory.json"
)
REQUESTED_LABELS = (
    PROJECT / "var/kite-qualification/2026-10-15/pilot-universe-qa/requested-labels.json"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--invented-proof",
        type=Path,
        metavar="OUTPUT_JSON",
        help="run the seven cards on deterministic invented prices and write one report",
    )
    action.add_argument("--actual", action="store_true", help="run an externally qualified pilot")
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--panel", type=Path)
    parser.add_argument("--activated-ledger-dsn")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-inventory", type=Path, default=SOURCE_INVENTORY)
    parser.add_argument("--requested-labels", type=Path, default=REQUESTED_LABELS)
    args = parser.parse_args()
    if args.invented_proof is None and not args.actual:
        print(
            json.dumps(
                {
                    "runner": "seven-strategy-daily-pilot",
                    "invented_proof_available": True,
                    "actual_run_status": "HELD_PENDING_QUALIFICATION_SOURCE_USE_AND_AUTHORIZATION",
                    "provider_questions": "UNSENT",
                },
                sort_keys=True,
            )
        )
        return 0

    if args.actual:
        required = {
            "--qualification": args.qualification,
            "--authorization": args.authorization,
            "--panel": args.panel,
            "--activated-ledger-dsn": args.activated_ledger_dsn,
            "--output": args.output,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            parser.error(f"--actual requires {', '.join(missing)}")
        goal = load_goal(PROJECT / "goal.yaml")
        spec = load_daily_pilot_spec(PROJECT, INVENTORY, goal)
        admission = load_actual_admission(
            args.qualification,
            args.source_inventory,
            args.requested_labels,
        )
        authorization_bytes = args.authorization.read_bytes()
        authorization = parse_run_authorization_json(authorization_bytes)
        if args.authorization.read_bytes() != authorization_bytes:
            raise ValueError("authorization changed while being read")
        binding = ExecutionBinding(
            authorization.bundle_sha256,
            authorization.approval_sha256,
            authorization.policy_sha256,
            authorization.qualification_sha256,
            authorization.goal_sha256,
            authorization.cards_sha256,
            authorization.runner_sha256,
        )

        def decode_prices() -> object:
            from icarus.engine.daily_pilot import DailyPilotPayload
            from icarus.engine.panelbuild import load_panel

            before = _file_sha256(args.panel)
            if before != admission.panel_file_sha256:
                raise ValueError("panel file differs from the qualification binding")
            panel = load_panel(args.panel, benchmark=None)
            if _file_sha256(args.panel) != before:
                raise ValueError("panel file changed while being decoded")
            return DailyPilotPayload.from_panel(panel, admission)

        engine = create_engine(args.activated_ledger_dsn)
        try:
            report = run_actual_daily_pilot(
                spec,
                admission,
                goal,
                authorization,
                binding,
                PostgresTrialLedger(engine),
                decode_prices,
                args.output.resolve(),
            )
        finally:
            engine.dispose()
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "evaluation_count": report["evaluation_count"],
                    "actual_trial_ledger_used": True,
                    "promotion_eligible": False,
                },
                sort_keys=True,
            )
        )
        return 0

    goal = load_goal(PROJECT / "goal.yaml")
    spec = load_daily_pilot_spec(PROJECT, INVENTORY, goal)
    report = run_invented_daily_pilot(spec, build_invented_admission(), goal)
    output = args.invented_proof.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    publish_json_once(output, report)
    print(
        json.dumps(
            {
                "output": str(output),
                "evaluation_count": report["evaluation_count"],
                "strategies": [item["strategy"] for item in report["evaluations"]],
                "model": report["evaluations"][0]["modeled_execution_frequency"],
                "benchmark": report["benchmark"],
                "pre_tax_alpha": report["pre_tax_alpha"],
                "promotion_eligible": report["promotion_eligible"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
