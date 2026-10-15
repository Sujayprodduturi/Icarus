"""Invented, nonauthorizing full-file proof of the guarded timed CLI."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from scripts.run_timed_backtest import TimedCliError, _cards_hash, _runner_hash, main

from icarus.common.config import load_goal
from icarus.engine.timed_evaluation import load_strategy_catalogue
from icarus.state.trial_ledger import (
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialBatchTerminal,
    TrialEvaluationResult,
    TrialLedgerUnavailable,
    TrialReservationAuthorization,
    TrialTerminalState,
    canonical_reservation_sha256,
    evaluation_id,
)

ROLES = (
    "daily_stock",
    "pit_universe",
    "corporate_action",
    "m15_stock",
    "nifty_observation",
    "session_calendar",
    "opening_liquidity",
)


def _dump(path: Path, value: object) -> bytes:
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    path.write_bytes(raw)
    return raw


def _jsonl(path: Path, rows: list[dict[str, object]]) -> bytes:
    raw = b"".join(
        json.dumps(row, separators=(",", ":"), sort_keys=True).encode() + b"\n" for row in rows
    )
    path.write_bytes(raw)
    return raw


def _z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass
class _RecordingLedger:
    reservations: list[TrialBatchReservation] = field(default_factory=list)
    terminals: list[tuple[TrialBatchReceipt, tuple[TrialEvaluationResult, ...]]] = field(
        default_factory=list
    )
    failures: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt:
        self.events.append("reserve")
        self.reservations.append(batch)
        return TrialBatchReceipt(
            batch.run_group_id,
            canonical_reservation_sha256(batch),
            tuple(evaluation_id(batch, item) for item in batch.evaluations),
            sum(len(item.evaluations) for item in self.reservations),
            True,
            TrialReservationAuthorization.NEW_EVALUATION,
        )

    def complete(
        self, receipt: TrialBatchReceipt, results: tuple[TrialEvaluationResult, ...]
    ) -> TrialBatchTerminal:
        self.events.append("complete")
        self.terminals.append((receipt, results))
        return TrialBatchTerminal(
            receipt.run_group_id, TrialTerminalState.COMPLETED, "a" * 64, None
        )

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> TrialBatchTerminal:
        self.events.append("fail")
        self.failures.append(failure_code)
        return TrialBatchTerminal(
            receipt.run_group_id, TrialTerminalState.FAILED, None, failure_code
        )


class _Engine:
    disposed = False

    def dispose(self) -> None:
        self.disposed = True


def _build_packet(root: Path) -> tuple[list[str], Path]:
    bundle = root / "bundle"
    external = root / "external"
    bundle.mkdir()
    external.mkdir()
    start, end = date(2011, 1, 1), date(2014, 12, 31)
    all_days = tuple(start + timedelta(days=i) for i in range((end - start).days + 1))
    open_days = tuple(day for day in all_days if day.weekday() < 5)
    symbols = tuple(f"SYN{i:02d}" for i in range(31))
    opens = tuple(datetime.combine(day, time(3, 45), UTC) for day in open_days)

    calendar: list[dict[str, object]] = []
    source_index = 0
    for day in all_days:
        is_open = day.weekday() < 5
        at = datetime.combine(day, time(3, 45), UTC)
        calendar.append(
            {
                "schema_version": 1,
                "record_id": f"cal-{day}",
                "revision": "r1",
                "source_index": source_index if is_open else None,
                "session_date": str(day),
                "state": "special" if is_open else "closed",
                "open_ts": _z(at) if is_open else None,
                "close_ts": _z(at + timedelta(minutes=15)) if is_open else None,
            }
        )
        source_index += int(is_open)

    daily: list[dict[str, object]] = []
    pit: list[dict[str, object]] = []
    m15: list[dict[str, object]] = []
    liquidity: list[dict[str, object]] = []
    for i, session_open in enumerate(opens):
        for j, symbol in enumerate(symbols):
            inactive = i == 0 and j == 0
            cycle = i % 160
            wave = cycle * 0.5 if cycle < 80 else 40 - (cycle - 80) * 0.6
            close = 100 + j * 3 + wave * (1 + j * 0.01) + 2 * math.sin(i / 9 + j)
            if j == 0 and 760 <= i < 840:
                close = 100 if i < 815 else 110 if i < 835 else 99 - (i - 835) * 0.01
            open_price, high = close - 0.2, close + 1.5
            low = close - 1.5 - (7 if (i + j) % 17 == 0 else 0)
            if j == 0 and 802 <= i < 815:
                high, low = 104, 96
            values = tuple(f"{value:.8f}" for value in (open_price, high, low, close))
            daily.append(
                {
                    "schema_version": 1,
                    "record_id": f"d-{i}-{j}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": symbol,
                    "event_ts": _z(session_open),
                    "open": None if inactive else values[0],
                    "high": None if inactive else values[1],
                    "low": None if inactive else values[2],
                    "close": None if inactive else values[3],
                    "volume": None if inactive else "1000000",
                    "tradable": not inactive,
                    "state": "INACTIVE_ABSENT" if inactive else "OBSERVED",
                    "reason": "PRE_LISTING" if inactive else "",
                    "adjustment_basis": "BACK_ADJUSTED",
                }
            )
            pit.append(
                {
                    "schema_version": 1,
                    "record_id": f"p-{i}-{j}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": symbol,
                    "event_ts": _z(session_open),
                    "available_ts": _z(session_open),
                    "eligible": not inactive,
                }
            )
            if inactive:
                continue
            m15.append(
                {
                    "schema_version": 1,
                    "record_id": f"m-{i}-{j}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": symbol,
                    "event_ts": _z(session_open),
                    "end_ts": _z(session_open + timedelta(minutes=15)),
                    "open": values[0],
                    "high": values[1],
                    "low": values[2],
                    "close": values[3],
                    "volume": "1000000",
                    "adjustment_basis": "BACK_ADJUSTED",
                }
            )
            liquidity.append(
                {
                    "schema_version": 1,
                    "record_id": f"l-{i}-{j}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": symbol,
                    "event_ts": _z(session_open),
                    "available_ts": _z(session_open - timedelta(seconds=1)),
                    "quantity": "1000000",
                    "method": "PRIOR_OBSERVED_QUANTITY_V1",
                }
            )
    actions = [
        {
            "schema_version": 1,
            "record_id": f"a-{j}",
            "revision": "r1",
            "symbol": symbol,
            "effective_ts": _z(opens[0]),
            "adjustment_basis": "BACK_ADJUSTED",
        }
        for j, symbol in enumerate(symbols)
    ]
    nifty = [
        {
            "schema_version": 1,
            "record_id": f"n-{i}-{side}",
            "revision": "r1",
            "instrument": "NIFTY 50",
            "venue": "NSE",
            "price_basis": "PRICE_INDEX",
            "event_ts": _z(
                session_open if side == "open" else session_open + timedelta(minutes=15)
            ),
            "available_ts": _z(
                session_open if side == "open" else session_open + timedelta(minutes=15)
            ),
            "observed": True,
            "price_numerator": 100000 + i + (1 if side == "close" else 0),
            "price_denominator": 10,
        }
        for i, session_open in enumerate(opens)
        for side in ("open", "close")
    ]
    rows = {
        "daily_stock": daily,
        "pit_universe": pit,
        "corporate_action": actions,
        "m15_stock": m15,
        "nifty_observation": nifty,
        "session_calendar": calendar,
        "opening_liquidity": liquidity,
    }
    identities = {
        "daily_stock": ("CASH_EQUITY", "BACK_ADJUSTED", "NONE"),
        "pit_universe": ("CASH_EQUITY", "POINT_IN_TIME_MEMBERSHIP", "NONE"),
        "corporate_action": ("CASH_EQUITY", "BACK_ADJUSTED", "NONE"),
        "m15_stock": ("CASH_EQUITY", "BACK_ADJUSTED", "NONE"),
        "nifty_observation": ("NIFTY 50", "PRICE_INDEX", "EXACT_OBSERVED_SESSION_CLOSE"),
        "session_calendar": ("CASH_EQUITY", "EXCHANGE_SESSION", "NONE"),
        "opening_liquidity": ("CASH_EQUITY", "PRIOR_OBSERVED_QUANTITY", "NONE"),
    }
    artifacts = []
    raw_by_role: dict[str, bytes] = {}
    for role in ROLES:
        raw = _jsonl(bundle / f"{role}.jsonl", rows[role])
        raw_by_role[role] = raw
        instrument, basis, projection = identities[role]
        coverage_start = (
            "2011-01-01T00:00:00Z"
            if role == "session_calendar"
            else _z(opens[0] - timedelta(seconds=1))
        )
        coverage_end = (
            "2014-12-31T18:29:59Z"
            if role == "session_calendar"
            else _z(opens[-1] + timedelta(minutes=15))
        )
        artifacts.append(
            {
                "role": role,
                "path": f"{role}.jsonl",
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "format": "jsonl",
                "schema_version": 1,
                "parser_version": "icarus-real-data-v1",
                "vendor": (
                    "INDEPENDENT_VENDOR_M15" if role == "m15_stock" else "INVENTED_CLI_FIXTURE"
                ),
                "venue": "NSE",
                "instrument": instrument,
                "price_basis": basis,
                "source_revision": "r1",
                "retrieved_at": "2026-10-14T00:00:00Z",
                "coverage_start": coverage_start,
                "coverage_end": coverage_end,
                "archival_evidence": "INVENTED_NONAUTHORIZING",
                "use_evidence": "INVENTED_TEST_ONLY",
                "projection_policy": projection,
            }
        )
    manifest = bundle / "manifest.json"
    manifest_raw = _dump(manifest, {"schema_version": 1, "artifacts": artifacts})
    matching = external / "matching.json"
    matching_raw = _dump(
        matching,
        {
            "schema_version": 1,
            "policy_id": "invented-asof-v1",
            "selection": "latest_available_observed",
            "max_age_seconds": 86400,
            "registered_at": "2026-10-13T00:00:00Z",
            "source_binding": "invented-cli-r1",
        },
    )
    source_policy = external / "source-policy.json"
    source_policy_raw = _dump(
        source_policy,
        {
            "schema_version": 1,
            "max_manifest_bytes": 1_000_000,
            "max_artifact_bytes": 100_000_000,
            "max_total_bytes": 300_000_000,
            "matching_policy": "invented-asof-v1",
            "matching_policy_sha256": hashlib.sha256(matching_raw).hexdigest(),
            "registered_at": "2026-10-13T00:00:00Z",
            "source_binding": "invented-cli-r1",
        },
    )
    approval = external / "approval.json"
    approval_raw = _dump(
        approval,
        {
            "schema_version": 1,
            "authority": "INVENTED_EXTERNAL_TEST_REVIEWER",
            "licence_evidence": "INVENTED_NONAUTHORIZING",
            "approved_at": "2026-10-14T00:30:00Z",
            "invented": False,
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "policy_sha256": hashlib.sha256(source_policy_raw).hexdigest(),
            "artifact_sha256": {
                role: hashlib.sha256(raw_by_role[role]).hexdigest() for role in ROLES
            },
        },
    )
    evidence: dict[str, str] = {}
    for key in ("archive", "licence", "raw_event_availability"):
        evidence_raw = f"INVENTED NONAUTHORIZING {key}\n".encode()
        (external / f"{key}.txt").write_bytes(evidence_raw)
        evidence[key] = hashlib.sha256(evidence_raw).hexdigest()
    evidence.update(
        {
            "benchmark_identity": hashlib.sha256(raw_by_role["nifty_observation"]).hexdigest(),
            "calendar": hashlib.sha256(raw_by_role["session_calendar"]).hexdigest(),
            "corporate_adjustments": hashlib.sha256(raw_by_role["corporate_action"]).hexdigest(),
            "pit_delisted": hashlib.sha256(raw_by_role["pit_universe"]).hexdigest(),
            "prior_only_liquidity": hashlib.sha256(raw_by_role["opening_liquidity"]).hexdigest(),
        }
    )
    qualification = external / "qualification.json"
    qualification_raw = _dump(
        qualification,
        {
            "schema_version": 1,
            "qualification_id": "INVENTED-NONAUTHORIZING-CLI-PROOF",
            "reviewer": "INVENTED_EXTERNAL_TEST_REVIEWER",
            "approved_at": "2026-10-14T01:00:00Z",
            "policy_registered_at": "2026-10-13T00:00:00Z",
            "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "approval_sha256": hashlib.sha256(approval_raw).hexdigest(),
            "policy_sha256": hashlib.sha256(source_policy_raw).hexdigest(),
            "matching_policy_sha256": hashlib.sha256(matching_raw).hexdigest(),
            "evidence_sha256": evidence,
            "invented": False,
        },
    )
    goal = Path("goal.yaml")
    cards = load_strategy_catalogue(tuple(sorted(Path("strategies").glob("*.yaml"))), load_goal())
    now = datetime.now(UTC)
    authorization = external / "authorization.json"
    _dump(
        authorization,
        {
            "schema_version": 1,
            "authorization_id": "INVENTED-NONAUTHORIZING-CLI-PROOF",
            "issued_at": _z(now - timedelta(minutes=1)),
            "expires_at": _z(now + timedelta(hours=1)),
            "bundle_sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "approval_sha256": hashlib.sha256(approval_raw).hexdigest(),
            "policy_sha256": hashlib.sha256(source_policy_raw).hexdigest(),
            "qualification_sha256": hashlib.sha256(qualification_raw).hexdigest(),
            "goal_sha256": hashlib.sha256(goal.read_bytes()).hexdigest(),
            "cards_sha256": _cards_hash(cards),
            "runner_sha256": _runner_hash(),
            "actual_ledger_activated": True,
            "invented": False,
        },
    )
    out = root / "INVENTED-NONAUTHORIZING-report.json"
    argv = [
        "run",
        "--manifest",
        str(manifest),
        "--approval",
        str(approval),
        "--source-policy",
        str(source_policy),
        "--matching-policy",
        str(matching),
        "--qualification",
        str(qualification),
    ]
    for key in ("archive", "licence", "raw_event_availability"):
        argv.extend(["--qualification-evidence", f"{key}={external / f'{key}.txt'}"])
    argv.extend(
        [
            "--authorization",
            str(authorization),
            "--goal",
            str(goal),
            "--strategy-dir",
            "strategies",
            "--activated-ledger-dsn",
            "postgresql://INVENTED-DISPOSABLE-NO-CONNECTION",
            "--out",
            str(out),
        ]
    )
    return argv, out


def test_full_invented_cli_reserves_all_twenty_one_before_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, out = _build_packet(tmp_path)
    _add_valid_source_pair(argv, tmp_path)
    ledger = _RecordingLedger()
    engine = _Engine()
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_: engine)
    monkeypatch.setattr("icarus.state.trial_ledger.PostgresTrialLedger", lambda _: ledger)
    import icarus.engine.timed_runner as timed_runner

    original = timed_runner.assemble_timed_inputs

    def observed_decode(value: object, pair: object = None) -> object:
        ledger.events.append("decode")
        return original(value, pair)  # type: ignore[arg-type]

    monkeypatch.setattr(timed_runner, "assemble_timed_inputs", observed_decode)
    assert main(argv) == 0
    assert ledger.events[:21] == ["reserve"] * 21 and ledger.events[21] == "decode"
    assert len(ledger.reservations) == len(ledger.terminals) == 21 and not ledger.failures
    report = json.loads(out.read_text())
    assert len(report["results"]) == 21
    assert len({result["run_group_id"] for result in report["results"]}) == 21
    identities = {
        (result["plan"]["card"], result["plan"]["mode"], result["plan"]["capital"])
        for result in report["results"]
    }
    assert len({item[0] for item in identities}) == 7
    assert {item[1:] for item in identities} == {
        ("signal", None),
        ("portfolio", 100_000),
        ("portfolio", 1_000_000),
    }
    qualification_path = Path(argv[argv.index("--qualification") + 1])
    assert set(json.loads(qualification_path.read_text())["evidence_sha256"]) == {
        "archive",
        "benchmark_identity",
        "calendar",
        "corporate_adjustments",
        "licence",
        "pit_delisted",
        "prior_only_liquidity",
        "raw_event_availability",
        "source_pair",
    }
    outcomes = [outcome for result in report["results"] for outcome in result["outcomes"]]
    folds = [fold for outcome in outcomes for fold in outcome.get("folds", [])]
    runs = [*outcomes, *folds]
    assert sum(item.get("entry_count", 0) for item in runs) > 0
    assert sum(item.get("exit_count", 0) for item in runs) > 0
    assert sum(item.get("rebalance_events", 0) for item in runs) > 0
    by_card: dict[str, list[dict[str, Any]]] = {}
    for result in report["results"]:
        typed_result = cast(dict[str, Any], result)
        card_runs = by_card.setdefault(typed_result["plan"]["card"], [])
        card_runs.extend(typed_result["outcomes"])
        card_runs.extend(
            fold for outcome in typed_result["outcomes"] for fold in outcome.get("folds", [])
        )
    assert sum(item.get("entry_count", 0) for item in by_card["baseline_buy_and_hold"]) > 0
    assert any(
        leg["cause"] == "opposite_signal"
        for item in by_card["donchian_55_20"]
        for trade in item.get("trades", [])
        for leg in trade["exits"]
    )
    assert sum(item.get("rebalance_events", 0) for item in by_card["defensive_low_vol_252_q63"]) > 0
    assert any(
        leg["cause"] == "rebalance"
        for item in by_card["defensive_low_vol_252_q63"]
        for trade in item.get("trades", [])
        for leg in trade["exits"]
    )
    traces = [trade for item in runs for trade in item.get("trades", [])]
    assert traces and all("charges" in trade["entry"] for trade in traces)
    assert (
        traces[0]["symbol"],
        traces[0]["entry"]["quantity"],
        traces[0]["entry"]["price"],
        traces[0]["entry"]["charges"]["stt"],
    ) == ("SYN01", 951, "105.15", "99.99765")
    baseline_seed = next(
        item
        for item in by_card["baseline_buy_and_hold"]
        if item.get("capital") == 100_000 and item.get("cash") is not None
    )
    assert (
        baseline_seed["cash"],
        baseline_seed["final_equity"],
    ) == ("96411.04350571180", "100227.22091831180")
    benchmark = next(item["benchmark"][0] for item in runs if item.get("benchmark"))
    qualification = json.loads(qualification_path.read_text())
    assert (
        benchmark["source_identity"]["artifact_sha256"]
        == qualification["evidence_sha256"]["benchmark_identity"]
    )
    assert any(
        item.get("cash") is not None and item.get("final_equity") is not None for item in runs
    )
    assert all(batch.primitives for batch in ledger.reservations)
    assert engine.disposed
    proof_dir = Path("var/verification/2026-10-14/readiness/cli-proof")
    proof_dir.mkdir(parents=True, exist_ok=True)
    (proof_dir / "full-cli-output.json").write_bytes(out.read_bytes())
    before = len(ledger.reservations)
    with pytest.raises(RuntimeError, match="OUTPUT_EXISTS"):
        main(argv)
    assert len(ledger.reservations) == before


def test_default_cli_is_metadata_only_without_database_or_price_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, _out = _build_packet(tmp_path)
    manifest = argv[argv.index("--manifest") + 1]
    approval = argv[argv.index("--approval") + 1]
    source_policy = argv[argv.index("--source-policy") + 1]
    monkeypatch.setattr(
        "sqlalchemy.create_engine", lambda *_: pytest.fail("metadata mode must not open database")
    )
    monkeypatch.setattr(
        "icarus.engine.timed_runner.assemble_timed_inputs",
        lambda *_: pytest.fail("metadata mode must not decode prices"),
    )
    assert (
        main(["--manifest", manifest, "--approval", approval, "--source-policy", source_policy])
        == 0
    )


def test_source_policy_change_after_preflight_refuses_before_database_or_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, out = _build_packet(tmp_path)
    source_policy = Path(argv[argv.index("--source-policy") + 1])
    import scripts.run_timed_backtest as cli

    original_preflight = cast(Any, cli.__dict__["preflight_bundle"])

    def mutate_after_preflight(
        manifest_path: Path, approval_path: Path, policy_path: Path
    ) -> object:
        result = original_preflight(manifest_path, approval_path, policy_path)
        source_policy.write_bytes(source_policy.read_bytes() + b" ")
        return result

    monkeypatch.setattr(cli, "preflight_bundle", mutate_after_preflight)
    monkeypatch.setattr(
        "sqlalchemy.create_engine",
        lambda *_: pytest.fail("changed policy must refuse before database"),
    )
    monkeypatch.setattr(
        "icarus.engine.timed_runner.assemble_timed_inputs",
        lambda *_: pytest.fail("changed policy must refuse before price decode"),
    )
    with pytest.raises(RuntimeError, match="SOURCE_POLICY_BYTES_CHANGED"):
        main(argv)
    assert not out.exists()


def test_cli_failures_never_publish_or_evaluate_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, out = _build_packet(tmp_path)
    import icarus.engine.timed_runner as timed_runner

    original_decode = timed_runner.assemble_timed_inputs
    engine = _Engine()
    monkeypatch.setattr("sqlalchemy.create_engine", lambda *_: engine)

    class ReserveFailure(_RecordingLedger):
        def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt:
            if len(self.reservations) == 1:
                raise RuntimeError("invented reservation outage")
            return super().reserve(batch)

    reserve = ReserveFailure()
    monkeypatch.setattr("icarus.state.trial_ledger.PostgresTrialLedger", lambda _: reserve)
    monkeypatch.setattr(
        timed_runner,
        "assemble_timed_inputs",
        lambda *_: pytest.fail("reservation failure must precede decode"),
    )
    with pytest.raises(RuntimeError, match="RESERVATION_SET_INCOMPLETE"):
        main(argv)
    assert not out.exists() and reserve.events == ["reserve", "fail"]

    decode = _RecordingLedger()
    monkeypatch.setattr("icarus.state.trial_ledger.PostgresTrialLedger", lambda _: decode)
    monkeypatch.setattr(
        timed_runner,
        "assemble_timed_inputs",
        lambda *_: (_ for _ in ()).throw(ValueError("invented decode outage")),
    )
    with pytest.raises(RuntimeError, match="PRICE_DECODE_FAILED"):
        main(argv)
    assert not out.exists() and decode.events == ["reserve"] * 21 + ["fail"] * 21

    class PersistenceFailure(_RecordingLedger):
        complete_calls = 0

        def complete(
            self, receipt: TrialBatchReceipt, results: tuple[TrialEvaluationResult, ...]
        ) -> TrialBatchTerminal:
            self.complete_calls += 1
            self.events.append("complete")
            raise TrialLedgerUnavailable("invented persistence outage")

    persistence = PersistenceFailure()
    monkeypatch.setattr("icarus.state.trial_ledger.PostgresTrialLedger", lambda _: persistence)
    monkeypatch.setattr(timed_runner, "assemble_timed_inputs", original_decode)
    with pytest.raises(RuntimeError, match="TERMINAL_WRITE_FAILED"):
        main(argv)
    assert not out.exists() and persistence.complete_calls == 2
    assert persistence.events[:21] == ["reserve"] * 21
    assert persistence.events[21:23] == ["complete", "complete"]
    assert persistence.events[23:] == ["fail"] * 20


def test_bad_source_pair_binding_refuses_before_database_or_trial_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, _ = _build_packet(tmp_path)
    external = tmp_path / "external"
    pair_path = external / "source_pair.json"
    pair = {
        "schema_version": 1,
        "pair_id": "invented-negative-pair",
        "reviewer": "independent-invented-reviewer",
        "approved_at": "2026-10-14T00:45:00Z",
        "effective_start": "2011-01-01T00:00:00Z",
        "effective_end": "2014-12-31T23:59:59Z",
        "daily_sha256": "0" * 64,
        "m15_sha256": "1" * 64,
        "action_sha256": "2" * 64,
        "calendar_sha256": "3" * 64,
        "daily_source": {"vendor": "INVENTED_CLI_FIXTURE", "source_revision": "r1"},
        "m15_source": {"vendor": "INDEPENDENT_VENDOR_M15", "source_revision": "r1"},
        "daily_close_rule": "OFFICIAL_SESSION_CLOSE",
        "m15_capture_rule": "VENDOR_INTERVAL_CAPTURE_V1",
        "session_rule": "PINNED_NSE_CALENDAR_V1",
        "price_basis": {
            "split": "BACK_ADJUSTED",
            "bonus": "BACK_ADJUSTED",
            "rights": "BACK_ADJUSTED",
            "dividend": "UNADJUSTED",
        },
        "relations": {"open": "EQUAL", "extrema_containment": "SUPPORTED", "volume": "EQUAL"},
        "mappings": [
            {
                "symbol": "SYN00",
                "isin": "INE000000001",
                "daily_symbol": "SYN00",
                "m15_symbol": "SYN00",
                "m15_token": "vendor-0",
                "lineage_sha256": "4" * 64,
                "split_factor": "1",
                "bonus_factor": "1",
                "rights_factor": "1",
                "effective_start": "2011-01-01T00:00:00Z",
                "effective_end": "2014-12-31T23:59:59Z",
            }
        ],
        "invented": False,
    }
    pair_raw = _dump(pair_path, pair)
    qualification_path = Path(argv[argv.index("--qualification") + 1])
    qualification = json.loads(qualification_path.read_text())
    qualification["evidence_sha256"]["source_pair"] = hashlib.sha256(pair_raw).hexdigest()
    qualification_raw = _dump(qualification_path, qualification)
    authorization_path = Path(argv[argv.index("--authorization") + 1])
    authorization = json.loads(authorization_path.read_text())
    authorization["qualification_sha256"] = hashlib.sha256(qualification_raw).hexdigest()
    _dump(authorization_path, authorization)
    insert_at = argv.index("--authorization")
    argv[insert_at:insert_at] = ["--qualification-evidence", f"source_pair={pair_path}"]
    monkeypatch.setattr(
        "sqlalchemy.create_engine", lambda *_: pytest.fail("bad pair reached database")
    )
    with pytest.raises(TimedCliError, match="PAIR_ARTIFACT_BINDING"):
        main(argv)


def test_source_pair_second_capture_change_refuses_before_database_or_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.run_timed_backtest as timed_cli

    argv, _ = _build_packet(tmp_path)
    _add_valid_source_pair(argv, tmp_path)
    pair_path = tmp_path / "external" / "source_pair.json"
    original = timed_cli._validate_qualification_evidence

    def change_after_first_hash(*args: object, **kwargs: object) -> None:
        original(*args, **kwargs)  # type: ignore[arg-type]
        pair_path.write_bytes(pair_path.read_bytes() + b" ")

    monkeypatch.setattr(timed_cli, "_validate_qualification_evidence", change_after_first_hash)
    monkeypatch.setattr(
        "sqlalchemy.create_engine", lambda *_: pytest.fail("changed pair reached database")
    )
    with pytest.raises(TimedCliError, match="QUALIFICATION_EXTERNAL_EVIDENCE"):
        main(argv)


def _add_valid_source_pair(argv: list[str], root: Path) -> None:
    manifest = json.loads(Path(argv[argv.index("--manifest") + 1]).read_text())
    hashes = {row["role"]: row["sha256"] for row in manifest["artifacts"]}
    pair_path = root / "external" / "source_pair.json"
    mappings = [
        {
            "symbol": f"SYN{i:02d}",
            "isin": f"INE{i:09d}",
            "daily_symbol": f"SYN{i:02d}",
            "m15_symbol": f"SYN{i:02d}",
            "m15_token": f"vendor-{i}",
            "lineage_sha256": f"{i + 1:064x}",
            "split_factor": "1",
            "bonus_factor": "1",
            "rights_factor": "1",
            "effective_start": "2011-01-01T00:00:00Z",
            "effective_end": "2014-12-31T23:59:59Z",
        }
        for i in range(31)
    ]
    pair_raw = _dump(
        pair_path,
        {
            "schema_version": 1,
            "pair_id": "invented-valid-pair",
            "reviewer": "independent-invented-reviewer",
            "approved_at": "2026-10-14T00:45:00Z",
            "effective_start": "2011-01-01T00:00:00Z",
            "effective_end": "2014-12-31T23:59:59Z",
            "daily_sha256": hashes["daily_stock"],
            "m15_sha256": hashes["m15_stock"],
            "action_sha256": hashes["corporate_action"],
            "calendar_sha256": hashes["session_calendar"],
            "daily_source": {"vendor": "INVENTED_CLI_FIXTURE", "source_revision": "r1"},
            "m15_source": {"vendor": "INDEPENDENT_VENDOR_M15", "source_revision": "r1"},
            "daily_close_rule": "OFFICIAL_SESSION_CLOSE",
            "m15_capture_rule": "VENDOR_INTERVAL_CAPTURE_V1",
            "session_rule": "PINNED_NSE_CALENDAR_V1",
            "price_basis": {
                "split": "BACK_ADJUSTED",
                "bonus": "BACK_ADJUSTED",
                "rights": "BACK_ADJUSTED",
                "dividend": "UNADJUSTED",
            },
            "relations": {"open": "EQUAL", "extrema_containment": "SUPPORTED", "volume": "EQUAL"},
            "mappings": mappings,
            "invented": False,
        },
    )
    qualification_path = Path(argv[argv.index("--qualification") + 1])
    qualification = json.loads(qualification_path.read_text())
    qualification["evidence_sha256"]["source_pair"] = hashlib.sha256(pair_raw).hexdigest()
    qualification_raw = _dump(qualification_path, qualification)
    authorization_path = Path(argv[argv.index("--authorization") + 1])
    authorization = json.loads(authorization_path.read_text())
    authorization["qualification_sha256"] = hashlib.sha256(qualification_raw).hexdigest()
    _dump(authorization_path, authorization)
    insert_at = argv.index("--authorization")
    argv[insert_at:insert_at] = ["--qualification-evidence", f"source_pair={pair_path}"]
