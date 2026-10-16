# Missing History Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare a fail-closed collector for the 2022-11-29 through 2022-12-30 pilot and 20-session liquidity-screen interval through evidence-pinned current symbols or explicit historical tokens while quarantining every unproved identity. This is not the 252-session strategy warmup required by longer-lookback cards.

**Architecture:** Keep the existing exact-current-symbol resolver and ordinary no-range CLI/run identity unchanged for the 13 modern aliases. Add an explicit candidate-route disposition for the two `-BE` names and one optional, separately hashed legacy-token manifest for the four removed current instruments. Before credentials or transport, candidate runs require exact bounded dates, caller-reviewed evidence digests, and immutable run binding. After authentication, a legacy run must fetch and separately seal a new instrument master, reject any legacy-token collision before every historical call, and keep legacy/BE chunks outside ordinary accepted coverage on fresh and resumed runs.

**Tech Stack:** Python 3.12, `argparse`, standard-library JSON/CSV/hash/path modules, pytest, PowerShell, Docker Compose.

**Spec:** `docs/data/2026-10-16-missing-history-routes.md`

## Global Constraints

- Preserve the original 694-line and 25-symbol request snapshots byte-for-byte.
- New legacy/BE candidate requests are exactly `2022-11-29` through `2022-12-30`, the union of the pilot dates and their 20-session liquidity-screen window. Ordinary downloads with no date arguments retain their existing daily `2011-01-01..2022-12-31` and M15 `2015-01-01..2022-12-31` defaults and byte-compatible run identity; optional paired pre-2023 dates remain supported. The existing lockbox guard remains authoritative.
- Only `GET /instruments/NSE` and `GET /instruments/historical/{token}/{day|15minute}` remain reachable after login; no order route is added.
- A returned candle has no symbol or ISIN and cannot prove security identity.
- Legacy-token and historical-EQ/current-BE results remain quarantined outside ordinary accepted coverage until separate identity review.
- No successor security is inferred across a merger, amalgamation, demerger, or changed ISIN.
- Credentials are entered only through hidden interactive prompts and are never accepted in chat, arguments, files, logs, or reports.
- Provider questions remain unsent. No new public archive acquisition runs until the separate archive-terms disposition allows it.

## Review Focus

- A legacy token reused by any fresh current-master row must halt before a historical request.
- A legacy entry with an extra current-retrieval symbol, a missing numeric token, or an unknown key must be rejected as ambiguous.
- Every current-symbol request must still resolve to one exact `NSE`/`EQ` master row, and the selected token must remain bound into the archived request identity.
- A valid candle response must remain `QUARANTINED_IDENTITY_UNPROVED`; coverage must never upgrade identity.
- Duplicate labels, duplicate legacy tokens, a candidate-route range other than `2022-11-29..2022-12-30`, and a route manifest that differs from its caller-supplied reviewed SHA-256 must fail before credential prompts or network I/O.
- A legacy run must archive a newly transported retrieval-day master under a distinct immutable request identity; an older cached master cannot satisfy the collision guard.
- A BE candidate's exact current-master token must match its hash-pinned evidence before any historical preflight; a mismatch halts with zero historical calls.

## Execution checkpoint — 2026-10-16

Tasks 1–4 are implemented offline in `tools/kite_acquire/acquire.py`, `scripts/start_kite_acquisition.ps1`, and `tests/unit/test_kite_acquire.py`, subject to the final frozen-byte review. The collector module passes 50 tests; repository-wide Ruff format/lint, repository-wide mypy, and PowerShell AST parsing pass. Independent review defects for total requested-chunk accounting and duplicate labels across ordinary/legacy routes were reproduced RED and repaired GREEN. The modern-alias pilot command below passes explicit bounded dates even though the ordinary no-date CLI remains backward compatible.

Task 5 has not run. Actual collection remains held on the source-use/retention disposition and then requires fresh credentials through hidden manual prompts. No authenticated request, price request, provider outreach, or trial-ledger action occurred.

---

### Task 1: Freeze the reviewed route contract — IMPLEMENTED OFFLINE

**Files:**
- Review: `docs/data/2026-10-16-missing-history-routes.md`
- Review: `var/kite-qualification/2026-10-16/history-routing/legacy-token-candidates.json`
- Review: `var/kite-qualification/2026-10-16/history-routing/series-route-evidence.json`
- Review: `var/kite-qualification/2026-10-16/history-routing/series-provenance.json`

**Interfaces:**
- Consumes: the unchanged 2026-10-15 alias request and frozen NSE/Kite metadata receipts.
- Produces: independently reviewed meanings for `current_symbol`, current-series candidate, and `legacy_instrument_token` routes.

- [ ] **Step 1: Verify every artifact hash and parse every JSON file**

```powershell
Get-FileHash -Algorithm SHA256 var/kite-qualification/2026-10-16/history-routing/*
Get-Content -Raw var/kite-qualification/2026-10-16/history-routing/legacy-token-candidates.json | ConvertFrom-Json | Out-Null
Get-Content -Raw var/kite-qualification/2026-10-16/history-routing/series-route-evidence.json | ConvertFrom-Json | Out-Null
```

- [ ] **Step 2: Confirm the existing collector accepts the series request without network I/O**

```powershell
uv run python -c "from pathlib import Path; from tools.kite_acquire.acquire import validate_symbol_file, validate_provenance; p=Path('var/kite-qualification/2026-10-16/history-routing'); print(validate_symbol_file(p/'requested-series-candidates.txt')); print(validate_provenance(p/'series-provenance.json', p/'requested-series-candidates.txt')['classification'])"
```

Expected: the symbols are exactly `HFCL-BE`, `MOREPENLAB-BE`, `NIFTY50`, and provenance validation succeeds.

- [ ] **Step 3: Record independent review before editing production code**

Expected decision: incorporate the finite corrections in `docs/reviews/2026-10-16-data-resolution-review.md`. D59 and the current instruction authorize the offline implementation and invented-fixture tests; raw acquisition remains held on the separate source-use disposition.

### Task 2: Validate an evidence-pinned legacy-token manifest — IMPLEMENTED OFFLINE

**Files:**
- Modify: `tools/kite_acquire/acquire.py`
- Modify: `tests/unit/test_kite_acquire.py`

**Interfaces:**
- Consumes: `validate_legacy_token_file(path: Path, expected_sha256: str) -> list[LegacyTokenRoute]` input JSON and caller-supplied reviewed digest.
- Produces: frozen `LegacyTokenRoute(requested_label: str, historical_tradingsymbol: str, instrument_token: int, nse_series: str, nse_isin: str, evidence_url: str)` values and `legacy_manifest_sha256(path: Path) -> str`.

- [ ] **Step 1: Write failing happy-path and ambiguity tests**

```python
EVIDENCE_URL = "https://kite.trade/forum/discussion/comment/9169/"


def _legacy_route(label: str = "HDFC", token: object = 340481) -> dict[str, object]:
    return {
        "requested_label": label,
        "historical_tradingsymbol": label,
        "historical_instrument_token": token,
        "provider_evidence_date": "2017-11",
        "provider_evidence_url": EVIDENCE_URL,
        "provider_evidence_observation": "published exact pair",
        "nse_2022_12_30_series": "EQ",
        "nse_2022_12_30_isin": "INE001A01036",
        "pilot_disposition": ["CONDITIONAL_QUALIFIES"] * 5,
        "route_status": "COLLECTION_CANDIDATE_ONLY",
        "identity_status": "UNKNOWN",
        "token_continuity": "UNKNOWN",
    }


def _write_legacy_manifest(tmp_path: Path, routes: list[dict[str, object]]) -> Path:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "EXPLICIT_LEGACY_TOKEN_CANDIDATES_NOT_IDENTITY_PROOF",
                "as_of_date": "2026-10-16",
                "scope": "metadata routing for the bounded 2022 pilot and its warmup only",
                "routes": routes,
                "limits": ["candidate only"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_legacy_token_manifest_accepts_only_explicit_candidate(tmp_path: Path) -> None:
    path = _write_legacy_manifest(tmp_path, [_legacy_route()])
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert validate_legacy_token_file(path, expected) == [
        LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", EVIDENCE_URL)
    ]


@pytest.mark.parametrize("mutation", ["extra_symbol", "missing_token"])
def test_legacy_token_manifest_rejects_ambiguous_routes(tmp_path: Path, mutation: str) -> None:
    route = _legacy_route()
    if mutation == "extra_symbol":
        route["current_retrieval_symbol"] = "HDFCBANK"
    else:
        del route["historical_instrument_token"]
    with pytest.raises(ValueError):
        path = _write_legacy_manifest(tmp_path, [route])
        validate_legacy_token_file(path, hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize(
    "routes",
    [
        [_legacy_route(), _legacy_route(token=341249)],
        [_legacy_route(), _legacy_route(label="OTHER")],
    ],
)
def test_legacy_token_manifest_rejects_duplicate_labels_or_tokens(
    tmp_path: Path, routes: list[dict[str, object]]
) -> None:
    with pytest.raises(ValueError):
        path = _write_legacy_manifest(tmp_path, routes)
        validate_legacy_token_file(path, hashlib.sha256(path.read_bytes()).hexdigest())
```

- [ ] **Step 2: Run the tests and verify RED**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -k legacy_token_manifest -q
```

Expected: failure because `LegacyTokenRoute` and `validate_legacy_token_file` do not exist.

- [ ] **Step 3: Implement the minimal frozen dataclass and strict parser**

```python
@dataclass(frozen=True)
class LegacyTokenRoute:
    requested_label: str
    historical_tradingsymbol: str
    instrument_token: int
    nse_series: str
    nse_isin: str
    evidence_url: str


def validate_legacy_token_file(path: Path, expected_sha256: str) -> list[LegacyTokenRoute]:
    """Parse schema 1 exactly; reject extra keys, booleans-as-ints, duplicates and non-NSE EQ evidence."""


def legacy_manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
```

The parser must require the top-level status `EXPLICIT_LEGACY_TOKEN_CANDIDATES_NOT_IDENTITY_PROOF`, `route_status=COLLECTION_CANDIDATE_ONLY`, `identity_status=UNKNOWN`, `token_continuity=UNKNOWN`, positive integer tokens, exact uppercase labels, `EQ`, a 12-character ISIN, HTTPS evidence URLs on `kite.trade`, and unique labels/tokens. It must reject unknown keys so schema drift halts.

- [ ] **Step 4: Run the focused tests and verify GREEN**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -k legacy_token_manifest -q
```

- [ ] **Step 5: Add hash-tamper and malformed-field tests, verify RED, then implement only those checks**

```python
def test_legacy_manifest_rejects_bytes_not_matching_reviewed_digest(tmp_path: Path) -> None:
    path = _write_legacy_manifest(tmp_path, [_legacy_route(token=340481)])
    reviewed = legacy_manifest_sha256(path)
    path = _write_legacy_manifest(tmp_path, [_legacy_route(token=341249)])
    with pytest.raises(ValueError, match="digest"):
        validate_legacy_token_file(path, reviewed)


@pytest.mark.parametrize("token", [True, 0, -1, "340481"])
def test_legacy_manifest_rejects_non_positive_integer_token(tmp_path: Path, token: object) -> None:
    with pytest.raises(ValueError):
        path = _write_legacy_manifest(tmp_path, [_legacy_route(token=token)])
        validate_legacy_token_file(path, hashlib.sha256(path.read_bytes()).hexdigest())
```

- [ ] **Step 6: Run the complete collector unit module**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -q
```

### Task 3: Refuse reuse and quarantine legacy-token output — IMPLEMENTED OFFLINE

**Files:**
- Modify: `tools/kite_acquire/acquire.py`
- Modify: `tests/unit/test_kite_acquire.py`

**Interfaces:**
- Consumes: `list[LegacyTokenRoute]`, exact validated bounds `2022-11-29..2022-12-30`, and a newly transported current NSE instrument master archived separately from any prior master.
- Produces: historical archives using the existing `KiteClient.historical()` path and `_quarantined_report_row(...)` rows that remain outside ordinary coverage while the final report always sets `source_qualified=False`.

- [ ] **Step 1: Write the failing current-master reuse test**

```python
def test_legacy_token_present_anywhere_in_current_master_halts_before_transport(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "instrument_token": "340481",
            "exchange_token": "1329",
            "tradingsymbol": "SOMEOTHER",
            "name": "Some Other Security",
            "last_price": "0",
            "expiry": "",
            "strike": "0",
            "tick_size": "0.05",
            "lot_size": "1",
            "instrument_type": "EQ",
            "segment": "NSE",
            "exchange": "NSE",
        }
    ]
    route = LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", EVIDENCE_URL)
    with pytest.raises(SchemaFailure, match="legacy token present in current master"):
        _validate_legacy_tokens_not_current(rows, [route])
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
uv run pytest tests/unit/test_kite_acquire.py::test_legacy_token_present_anywhere_in_current_master_halts_before_transport -q
```

- [ ] **Step 3: Implement the fresh-master path and minimal reuse guard**

```python
def _validate_legacy_tokens_not_current(
    rows: list[dict[str, str]], routes: Sequence[LegacyTokenRoute]
) -> None:
    current_tokens = {int(row["instrument_token"]) for row in rows}
    reused = sorted(
        route.instrument_token for route in routes if route.instrument_token in current_tokens
    )
    if reused:
        raise SchemaFailure(f"legacy token present in current master: {reused}")
```

Add a `fresh_instruments()` client path whose request identity includes a retrieval timestamp, always calls transport, validates the master schema, and writes a new immutable archive. Legacy runs must use that result and must run the collision guard before the ordinary probes or any historical call.

- [ ] **Step 4: Write failing tests for quarantine and identity honesty**

```python
def test_successful_legacy_candles_remain_identity_quarantined() -> None:
    route = LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", EVIDENCE_URL)
    metadata = {
        "result": "success",
        "coverage": {
            "count": 5,
            "first_ts": "2022-12-26T03:45:00+00:00",
            "last_ts": "2022-12-30T09:45:00+00:00",
        },
        "request_identity_sha256": "a" * 64,
    }
    row = _quarantined_report_row(
        symbol=route.requested_label,
        retrieval_kind="legacy_token_candidate",
        identity_status="QUARANTINED_IDENTITY_UNPROVED",
        instrument_token=route.instrument_token,
        interval="15minute",
        chunk_start=datetime(2022, 11, 29, tzinfo=IST),
        chunk_end=datetime(2022, 12, 30, 23, 59, 59, tzinfo=IST),
        metadata=metadata,
    )
    assert row["identity_status"] == "QUARANTINED_IDENTITY_UNPROVED"
    assert "isin_confirmed" not in json.dumps(row)


def test_empty_legacy_response_is_retained_as_retrieval_evidence() -> None:
    route = LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", EVIDENCE_URL)
    metadata = {
        "result": "empty",
        "coverage": {"count": 0, "first_ts": None, "last_ts": None},
        "request_identity_sha256": "b" * 64,
    }
    row = _quarantined_report_row(
        symbol=route.requested_label,
        retrieval_kind="legacy_token_candidate",
        identity_status="QUARANTINED_IDENTITY_UNPROVED",
        instrument_token=route.instrument_token,
        interval="day",
        chunk_start=datetime(2022, 11, 29, tzinfo=IST),
        chunk_end=datetime(2022, 12, 30, 23, 59, 59, tzinfo=IST),
        metadata=metadata,
    )
    assert row["result"] == "empty"
    assert row["identity_status"] == "QUARANTINED_IDENTITY_UNPROVED"


def test_legacy_section_cannot_qualify_source(report: dict[str, object]) -> None:
    assert report["source_qualified"] is False
    assert report["counts"]["accepted_chunks"] == 0
    assert report["counts"]["quarantined_chunks"] > 0
```

- [ ] **Step 5: Run the tests and verify RED**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -k "legacy and (quarantined or empty)" -q
```

- [ ] **Step 6: Integrate legacy routes through the existing range, archive, retry, validation, and lockbox functions**

Add paired optional date arguments, paired legacy-manifest arguments, and paired explicit series-evidence arguments. Exact `2022-11-29..2022-12-30` bounds are mandatory for a legacy or BE candidate run; an ordinary no-range run keeps its old ranges and identity fields. Validate every file, caller-reviewed digest and bound before `_bind_run`, TTY checks, credential prompts or transport. Bind the route digest, route values and candidate range to `request-identity.json`; then use the fresh-master guard. Request candidate daily and 15-minute chunks only for the bounded interval. Add separate `quarantined_routes` rows through `_quarantined_report_row`; legacy rows never increment ordinary accepted/empty coverage counters. When provenance classification is `CURRENT_SERIES_RETRIEVAL_CANDIDATES_NOT_IDENTITY_PROOF`, verify the explicitly staged evidence file against both the provenance digest and caller-reviewed digest, then route non-benchmark rows into the same quarantine section with `QUARANTINED_SERIES_IDENTITY_UNPROVED`. Keep `source_qualified=False`. Do not route legacy tokens through `_resolve()`, alter `_resolve()`, or infer identity from coverage.

- [ ] **Step 7: Verify GREEN and the unchanged lockbox tests**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -q
```

### Task 4: Pass the frozen legacy manifest through the isolated launcher — IMPLEMENTED OFFLINE

**Files:**
- Modify: `scripts/start_kite_acquisition.ps1`
- Modify: `tests/unit/test_kite_acquire.py`

**Interfaces:**
- Consumes: paired candidate bounds `-HistoryStart 2022-11-29` and `-HistoryEnd 2022-12-30`, paired optional legacy-manifest inputs, and paired optional explicit series-evidence inputs. Ordinary downloads may omit dates and preserve their prior behavior.
- Produces: byte-identical archived inputs named `legacy-token-routes-<run-id>.json` and/or `series-route-evidence-<run-id>.json`, exact candidate range arguments, and paired container path/digest arguments after archived bytes match the reviewed digests.

- [ ] **Step 1: Write a launcher contract test that inspects the script text**

```python
def test_launcher_archives_and_passes_legacy_manifest() -> None:
    script = Path("scripts/start_kite_acquisition.ps1").read_text(encoding="utf-8")
    assert "[string]$LegacyTokenFile" in script
    assert "legacy-token-routes-$effectiveRunId.json" in script
    assert '"--legacy-token-file", "/export/$legacyName"' in script
    assert '"--legacy-token-sha256", $expectedLegacyHash' in script
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
uv run pytest tests/unit/test_kite_acquire.py::test_launcher_archives_and_passes_legacy_manifest -q
```

- [ ] **Step 3: Add the optional parameter and use the existing copy-or-hash-compare pattern**

The launcher must require the exact bounded dates only when a candidate route input is present. It resolves each explicit source path, copies it into the export directory under a fixed run-derived name, refuses an existing target with different bytes, compares the archived target's SHA-256 with the caller-reviewed digest, appends the paired path/digest only in download mode, and never prints file content. The container receives only the archived copy; provenance-relative paths are never traversed at runtime.

- [ ] **Step 4: Run the collector module and static checks**

```powershell
uv run pytest tests/unit/test_kite_acquire.py -q
uv run ruff check tools/kite_acquire/acquire.py tests/unit/test_kite_acquire.py
uv run ruff format --check tools/kite_acquire/acquire.py tests/unit/test_kite_acquire.py
uv run mypy tools/kite_acquire/acquire.py
```

- [ ] **Step 5: Run the required reviews before committing**

Run `ponytail-review`, then `code-review`. Verify every finding against the source before changing code. For each real defect, first write a failing regression test and then fix it.

### Task 5: Run collection only after the source-use hold is released and manual authentication is available — HELD / NOT RUN

**Files:**
- Read unchanged: `var/kite-qualification/2026-10-15/alias-retrieval/requested-modern-aliases.txt`
- Read unchanged: `var/kite-qualification/2026-10-15/alias-retrieval/provenance.json`
- Read: `var/kite-qualification/2026-10-16/history-routing/requested-series-candidates.txt`
- Read: `var/kite-qualification/2026-10-16/history-routing/series-provenance.json`
- Read: `var/kite-qualification/2026-10-16/history-routing/legacy-token-candidates.json`
- Read: `var/kite-qualification/2026-10-16/history-routing/requested-legacy-probe.txt`
- Read: `var/kite-qualification/2026-10-16/history-routing/legacy-probe-provenance.json`
- Create at runtime: new immutable run directories under `var/kite-history/`

**Interfaces:**
- Consumes: fresh API key, API secret, and request token through hidden interactive prompts.
- Produces: byte-exact provider archives, coverage-only reports, and quarantined legacy/BE histories.

- [ ] **Step 1: Re-run the existing probe in an interactive terminal**

```powershell
.\scripts\start_kite_acquisition.ps1 -Mode probe -ExportDirectory C:\ICARUS\var\kite-history -RunId history-routing-probe-20261016-v1
```

Do not paste credentials into chat or save them in a file. Stop on auth failure, schema drift, or an empty required probe.

- [ ] **Step 2: Run the unchanged modern-alias request**

```powershell
.\scripts\start_kite_acquisition.ps1 -Mode download -ExportDirectory C:\ICARUS\var\kite-history -SymbolsFile C:\ICARUS\var\kite-qualification\2026-10-15\alias-retrieval\requested-modern-aliases.txt -ProvenanceFile C:\ICARUS\var\kite-qualification\2026-10-15\alias-retrieval\provenance.json -HistoryStart 2022-11-29 -HistoryEnd 2022-12-30 -RunId alias-retrieval-20261016-v1
```

- [ ] **Step 3: Run the two exact current-series candidates**

```powershell
.\scripts\start_kite_acquisition.ps1 -Mode download -ExportDirectory C:\ICARUS\var\kite-history -SymbolsFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\requested-series-candidates.txt -ProvenanceFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\series-provenance.json -SeriesRouteEvidenceFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\series-route-evidence.json -SeriesRouteEvidenceSha256 73b226633a44e40621f4a0ea107c50b540427cbf53167355345b5b9793f86d95 -HistoryStart 2022-11-29 -HistoryEnd 2022-12-30 -RunId series-retrieval-20261016-v1
```

- [ ] **Step 4: Run the four explicit legacy-token candidates through the reviewed extension**

```powershell
.\scripts\start_kite_acquisition.ps1 -Mode download -ExportDirectory C:\ICARUS\var\kite-history -SymbolsFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\requested-legacy-probe.txt -ProvenanceFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\legacy-probe-provenance.json -LegacyTokenFile C:\ICARUS\var\kite-qualification\2026-10-16\history-routing\legacy-token-candidates.json -LegacyTokenSha256 4cf78e5aeb24937f59c50a83e5d1d4794fe43be75b733787f75299f0830e3e48 -HistoryStart 2022-11-29 -HistoryEnd 2022-12-30 -RunId missing-history-legacy-20261016-v1
```

- [ ] **Step 5: Review reports without decoding price values**

Require byte hashes, requested ranges, candle counts, first/last timestamps, empty/rejected chunks, unresolved symbols, and quarantine labels. A success count is retrieval evidence only. Any identity decision requires the separate action-normalized comparison across this entire bounded pilot/liquidity-screen interval, or stronger provider evidence, as described in the spec.

- [ ] **Step 6: Update `docs/STATE.md` with the actual result and blockers**

State exactly which routes returned coverage, which remained empty/rejected, which are still quarantined, and whether fresh authentication was unavailable. Keep `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` unless a later separately approved qualification gate changes them.
