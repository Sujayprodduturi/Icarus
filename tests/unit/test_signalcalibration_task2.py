"""Test-only deterministic controls for Step-6a.2 Task 2."""

from __future__ import annotations

import inspect
import math
from typing import Any

import numpy as np
import pytest
import scripts.signal_calibration as calibration
from numpy.typing import NDArray
from scripts.signal_calibration import (
    BatchInterval,
    BatchRefusal,
    evaluate_batch_interval,
    generate_test_fixture_chunk,
    generate_test_fixture_replicate,
    load_manifest,
    parity_audit_ids,
)

from icarus.engine.signalmetrics import CandidateMoments, MetricRefusal, _cr2_moments

_TEST_SEED = 917_260_001  # Deliberately not either frozen phase seed.


def _manifest() -> dict[str, Any]:
    return load_manifest()


def test_public_fixture_apis_expose_no_seed_override() -> None:
    """Task 2 public fixtures cannot be redirected into protected phase streams."""
    assert "master_seed" not in inspect.signature(generate_test_fixture_replicate).parameters
    assert "master_seed" not in inspect.signature(generate_test_fixture_chunk).parameters


def test_reserved_private_seed_refuses_before_rng_or_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reserved streams fail before cache lookup or PCG construction, even for scripted callers."""
    monkeypatch.setattr(calibration, "_STREAM_CACHE", {})
    monkeypatch.setattr(np.random, "PCG64", lambda *_args: pytest.fail("RNG constructed"))
    with pytest.raises(ValueError, match="reserved"):
        calibration._test_or_rng(2026092602, 1, 0, 0, 1, 1)
    with pytest.raises(ValueError, match="reserved"):
        calibration._uniform_component_draw(2026092603, 1, 2, 0, 1, 1)


def test_scripted_latents_pin_outcome_benchmark_and_excess_formula() -> None:
    """A positive latent is a win and paired benchmark uses the named factor."""
    replicate = generate_test_fixture_replicate(
        _manifest(),
        phase="calibration",
        cell_id=7,
        replicate_id=0,
        scripted_latents=np.array([1.0, -1.0]),
        scripted_amplitudes=np.array([1.5, 0.5]),
        scripted_factors=np.array([2.0, 2.0]),
    )

    assert replicate.raw[:2] == pytest.approx((0.015, -0.005))
    assert replicate.benchmark[:2] == pytest.approx((0.012, 0.012))
    assert replicate.excess[:2] == pytest.approx((0.003, -0.017))
    assert replicate.wins[:2] == (True, False)


@pytest.mark.parametrize(
    "cell_id,expected_first_index",
    [(1, 3), (12, 0), (18, 0), (30, 3)],
)
def test_generator_uses_each_frozen_geometry_without_phase_seed(
    cell_id: int, expected_first_index: int
) -> None:
    """Representative ordinary, burst, overlap, and rare cells retain declared coordinates."""
    replicate = generate_test_fixture_replicate(
        _manifest(),
        phase="calibration",
        cell_id=cell_id,
        replicate_id=3,
    )

    assert replicate.entry_indices[0] == expected_first_index
    assert len(replicate.raw) == len(replicate.entry_indices)
    assert len(replicate.raw) == len(replicate.benchmark)


def test_generator_stream_address_is_reproducible_and_isolated_by_component() -> None:
    """A test-only PCG64 address is reproducible and a different address changes data."""
    manifest = _manifest()
    first = generate_test_fixture_replicate(
        manifest, phase="calibration", cell_id=1, replicate_id=7
    )
    same = generate_test_fixture_replicate(manifest, phase="calibration", cell_id=1, replicate_id=7)
    other = generate_test_fixture_replicate(
        manifest, phase="calibration", cell_id=1, replicate_id=8
    )

    assert first == same
    assert first.raw != other.raw


def test_dynamic_h_recomputes_block_membership_and_paired_excess() -> None:
    """Dynamic win/loss holding durations are not silently treated as a fixed geometry."""
    replicate = generate_test_fixture_replicate(
        _manifest(),
        phase="calibration",
        cell_id=44,
        replicate_id=0,
        scripted_wins=np.array([True, False] * 96),
    )

    assert replicate.block_length == 126
    assert set(replicate.holding_sessions) == {21, 42}
    assert replicate.excess == pytest.approx(
        tuple(
            raw - benchmark
            for raw, benchmark in zip(replicate.raw, replicate.benchmark, strict=True)
        )
    )


def test_batch_interval_matches_hand_cr2_and_clips_only_displayed_win_bounds() -> None:
    """The batch evaluator preserves raw endpoints while presentation clips win-rate bounds."""
    result = evaluate_batch_interval(
        np.array([0.0, 1.0, 2.0]), np.array([0, 1, 1]), confidence=0.95, is_win_rate=True
    )

    assert isinstance(result, BatchInterval)
    assert result.mean == pytest.approx(1.0)
    assert result.variance == pytest.approx(0.5)
    assert result.degrees_of_freedom == pytest.approx(1.0)
    assert result.raw_lower < 0.0 < result.raw_upper
    assert result.lower == 0.0
    assert result.upper == 1.0


def test_batch_refuses_only_the_degenerate_component() -> None:
    """An all-win component refusal must not erase a valid raw-return interval."""
    raw = evaluate_batch_interval(np.array([0.01, 0.02, 0.03]), np.array([0, 1, 1]))
    win = evaluate_batch_interval(np.array([1.0, 1.0, 1.0]), np.array([0, 1, 1]), is_win_rate=True)

    assert isinstance(raw, BatchInterval)
    assert win is BatchRefusal.ZERO_VARIANCE


def test_batch_interval_matches_dense_projection_oracle() -> None:
    """The compact batch formula agrees with an independently formed dense projection."""
    values = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    blocks = np.array([0, 1, 1, 2, 2, 2])
    result = evaluate_batch_interval(values, blocks)
    assert isinstance(result, BatchInterval)

    count = values.size
    projection = np.eye(count) - np.ones((count, count)) / count
    q = np.zeros((count, count))
    for block in np.unique(blocks):
        column = (blocks == block).astype(float)
        leverage = column.sum() / count
        vector = projection @ column / (count * math.sqrt(1.0 - leverage))
        q += np.outer(vector, vector)
    assert result.variance == pytest.approx(float(values @ q @ values), abs=1e-14)


def test_batch_interval_matches_scalar_production_moments() -> None:
    """Offline batching cannot silently diverge from the frozen scalar CR2 formula."""
    values = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    blocks = np.array([0, 1, 1, 2, 2, 2])
    batch = evaluate_batch_interval(values, blocks)
    scalar = _cr2_moments(
        tuple(float(value) for value in values), tuple(int(block) for block in blocks)
    )

    assert isinstance(batch, BatchInterval)
    assert isinstance(scalar, CandidateMoments)
    assert batch.variance == pytest.approx(scalar.cr2_variance, abs=1e-14)
    assert batch.degrees_of_freedom == pytest.approx(scalar.degrees_of_freedom, abs=1e-14)


def test_scripted_family_formulas_cover_burst_ar_rare_regime_dynamic_and_paired_excess() -> None:
    """Scripted fixtures pin every non-overlap family equation without a phase-seed draw."""
    manifest = _manifest()
    burst = generate_test_fixture_replicate(
        manifest,
        phase="calibration",
        cell_id=13,
        replicate_id=1,
        scripted_factors=np.array([2.0]),
        scripted_latents=np.array([1.0]),
    )
    assert burst.benchmark[:8] == pytest.approx((0.012,) * 8)

    ar = generate_test_fixture_replicate(
        manifest,
        phase="calibration",
        cell_id=25,
        replicate_id=1,
        scripted_factors=np.array([1.0, 2.0]),
        scripted_latents=np.zeros(192),
    )
    assert ar.benchmark[0] == pytest.approx(0.007)
    assert ar.benchmark[8] == pytest.approx(0.002 + 0.005 * (0.2 + math.sqrt(0.96) * 2.0))

    rare = generate_test_fixture_replicate(
        manifest,
        phase="calibration",
        cell_id=31,
        replicate_id=1,
        scripted_amplitudes=np.array([20.0, 1.0]),
        scripted_wins=np.array([True, False] + [False] * 190),
    )
    assert rare.raw[:2] == pytest.approx((0.2, -0.01))

    regime = manifest["phases"]["calibration"]["cells"][33]
    assert regime["family"] == "two_regime_shift"
    assert regime["targets"]["win_probability"] == pytest.approx(0.5)
    assert regime["targets"]["raw_mean"] == pytest.approx(0.0)

    dynamic = generate_test_fixture_replicate(
        manifest,
        phase="calibration",
        cell_id=44,
        replicate_id=1,
        scripted_wins=np.array([True, False] * 96),
    )
    assert set(dynamic.holding_sessions) == {21, 42}
    assert dynamic.block_length == 126
    assert dynamic.excess == pytest.approx(
        tuple(
            raw - benchmark for raw, benchmark in zip(dynamic.raw, dynamic.benchmark, strict=True)
        )
    )


def test_scripted_overlap_daily_innovation_is_shared_across_block_edge() -> None:
    """Late and early edge entries share the same declared daily innovation."""
    daily = np.zeros(1_600)
    daily[63] = 1.0
    replicate = generate_test_fixture_replicate(
        _manifest(),
        phase="calibration",
        cell_id=19,
        replicate_id=2,
        scripted_daily_innovations=daily,
    )
    expected = 0.002 + 0.005 / math.sqrt(21)
    assert replicate.entry_indices[4] == 59
    assert replicate.entry_indices[8] == 63
    assert replicate.benchmark[4] == pytest.approx(expected)
    assert replicate.benchmark[8] == pytest.approx(expected)


def test_parity_audit_ids_include_exact_first_last_and_128_fixed_positions() -> None:
    """The parity sampler is deterministic arithmetic, not an RNG draw from either phase stream."""
    ids = parity_audit_ids(10_000)
    assert len(ids) == 128
    assert ids[0] == 0
    assert ids[-1] == 9_999
    assert ids == tuple((index * 9_999) // 127 for index in range(128))


@pytest.mark.parametrize(
    ("values", "blocks"),
    [
        (np.array([0.0, 0.0, 1.0, 1.0]), np.array([0, 0, 1, 1])),
        (np.array([0.0, 1.0, 2.0, 3.0]), np.array([0, 0, 1, 1])),
        (np.array([0.0, 1.0, 2.0, 3.0]), np.array([0, 1, 0, 1])),
    ],
)
def test_batch_matches_scalar_status_under_reordering_and_equal_scores(
    values: NDArray[Any], blocks: NDArray[Any]
) -> None:
    """Batch status and moments follow the scalar formula at ordinary and equal-score boundaries."""
    batch = evaluate_batch_interval(values, blocks)
    scalar = _cr2_moments(
        tuple(float(value) for value in values), tuple(int(block) for block in blocks)
    )
    if isinstance(scalar, CandidateMoments):
        assert isinstance(batch, BatchInterval)
        assert batch.variance == pytest.approx(scalar.cr2_variance, rel=1e-11, abs=1e-14)
        assert batch.degrees_of_freedom == pytest.approx(
            scalar.degrees_of_freedom, rel=1e-11, abs=1e-12
        )
    else:
        assert isinstance(batch, BatchRefusal)
        assert batch.value == scalar.value


def test_scripted_fixture_cannot_mutate_cached_rng_row() -> None:
    """A scripted fixture is isolated from the reproducible addressed stream cache."""
    manifest = _manifest()
    baseline = generate_test_fixture_replicate(
        manifest, phase="calibration", cell_id=7, replicate_id=9
    )
    generate_test_fixture_replicate(
        manifest,
        phase="calibration",
        cell_id=7,
        replicate_id=9,
        scripted_latents=np.array([99.0]),
        scripted_amplitudes=np.array([1.5]),
        scripted_factors=np.array([2.0]),
    )
    replay = generate_test_fixture_replicate(
        manifest, phase="calibration", cell_id=7, replicate_id=9
    )

    assert replay == baseline


def test_chunk_generation_matches_addressed_replicates_without_redraw() -> None:
    """One declared 256-row chunk is sliced, rather than regenerated per replicate offset."""
    chunk = generate_test_fixture_chunk(
        _manifest(),
        phase="calibration",
        cell_id=7,
        chunk_id=0,
        rows=256,
    )

    assert len(chunk) == 256
    assert chunk[3] == generate_test_fixture_replicate(
        _manifest(), phase="calibration", cell_id=7, replicate_id=3
    )
    with pytest.raises(ValueError, match="declared chunk"):
        generate_test_fixture_chunk(
            _manifest(),
            phase="calibration",
            cell_id=7,
            chunk_id=39,
            rows=256,
        )


def test_fixed_h_overlap_retains_h42_when_every_outcome_is_a_win() -> None:
    """Fixed-H overlap must not inherit the dynamic-H win default of 21 sessions."""
    replicate = generate_test_fixture_replicate(
        _manifest(),
        phase="calibration",
        cell_id=22,
        replicate_id=0,
        scripted_wins=np.ones(192, dtype=bool),
    )

    assert set(replicate.holding_sessions) == {42}
    assert replicate.block_length == 126
    assert len(set(replicate.block_ids)) == 24


def test_batch_matches_scalar_status_for_tiny_nonzero_values() -> None:
    """Underflow may refuse as invalid variance but must never become zero variance."""
    values = np.array([0.0, 1e-200, 2e-200, 3e-200])
    blocks = np.array([0, 0, 1, 1])

    assert evaluate_batch_interval(values, blocks) is BatchRefusal.INVALID_VARIANCE
    scalar = _cr2_moments(
        tuple(float(value) for value in values), tuple(int(block) for block in blocks)
    )
    assert scalar is MetricRefusal.INVALID_VARIANCE


def test_batch_refuses_cr2_score_overflow_like_scalar_moments() -> None:
    """Finite CR2 score accumulation overflow remains a typed variance refusal."""
    values = np.array([3e153, 3e153, -3e153, -3e153] * 2)
    blocks = np.array([0, 0, 1, 1, 2, 2, 3, 3])
    assert evaluate_batch_interval(values, blocks) is BatchRefusal.INVALID_VARIANCE
    assert (
        _cr2_moments(tuple(float(value) for value in values), tuple(int(block) for block in blocks))
        is MetricRefusal.INVALID_VARIANCE
    )


def test_batch_refuses_finite_overflow_like_scalar_moments() -> None:
    """Finite input whose compensated arithmetic overflows is an invalid variance refusal."""
    assert (
        evaluate_batch_interval(np.array([1e308, 1e308, -1e308, -1e308]), np.array([0, 0, 1, 1]))
        is BatchRefusal.INVALID_VARIANCE
    )


@pytest.mark.parametrize("blocks", [np.array([0.5, 1.5, 1.5]), np.array([0.0, np.inf, 1.0])])
def test_batch_rejects_nonintegral_or_nonfinite_block_schema(blocks: NDArray[Any]) -> None:
    """Block identifiers are schema coordinates, not silently coerced cache keys."""
    with pytest.raises((TypeError, ValueError)):
        evaluate_batch_interval(np.array([0.0, 1.0, 2.0]), blocks)


def test_batch_uses_compensated_mean_at_cancellation_boundary() -> None:
    """Batch mean must retain the scalar formula's compensated cancellation result."""
    result = evaluate_batch_interval(np.array([1e16, 1.0, -1e16, 1.0]), np.array([0, 0, 1, 1]))

    assert isinstance(result, BatchInterval)
    assert result.mean == 0.5


@pytest.mark.parametrize(
    ("cell_id", "expected_h", "expected_l", "expected_blocks"),
    [
        (1, 21, 63, 24),
        (12, 21, 63, 24),
        (15, 21, 63, 24),
        (18, 21, 63, 24),
        (21, 42, 126, 24),
        (24, 21, 63, 24),
        (30, 21, 63, 24),
        (33, 21, 63, 24),
    ],
)
def test_representative_fixed_family_geometry_is_manifest_exact(
    cell_id: int, expected_h: int, expected_l: int, expected_blocks: int
) -> None:
    """Each fixed family retains its declared source geometry independently of outcomes."""
    replicate = generate_test_fixture_replicate(
        _manifest(), phase="calibration", cell_id=cell_id, replicate_id=5
    )
    assert set(replicate.holding_sessions) == {expected_h}
    assert replicate.block_length == expected_l
    assert len(set(replicate.block_ids)) == expected_blocks


def test_test_seed_parity_sweep_covers_each_phase_cell_and_fixed_128_ids() -> None:
    """Every phase/cell/metric parity address is differential-tested without phase-seed draws."""
    manifest = _manifest()
    for phase in ("calibration", "validation"):
        ids = parity_audit_ids(manifest["phases"][phase]["replicates"])
        for cell in manifest["phases"][phase]["cells"]:
            for replicate_id in ids:
                replicate = generate_test_fixture_replicate(
                    manifest,
                    phase=phase,
                    cell_id=cell["id"],
                    replicate_id=replicate_id,
                )
                for values in (
                    replicate.raw,
                    tuple(1.0 if win else 0.0 for win in replicate.wins),
                    replicate.excess,
                ):
                    batch = evaluate_batch_interval(
                        np.array(values), np.array(replicate.block_ids, dtype=np.int64)
                    )
                    scalar = _cr2_moments(
                        tuple(float(value) for value in values), replicate.block_ids
                    )
                    if isinstance(scalar, CandidateMoments):
                        assert isinstance(batch, BatchInterval)
                        scale = max(abs(value) for value in values)
                        assert abs(batch.mean - scalar.mean) <= (
                            1e-11 * max(abs(batch.mean), abs(scalar.mean)) + 1e-14 * scale
                        )
                        assert abs(batch.variance - scalar.cr2_variance) <= (
                            1e-11 * max(abs(batch.variance), abs(scalar.cr2_variance))
                            + 1e-14 * scale * scale
                        )
                        assert abs(batch.degrees_of_freedom - scalar.degrees_of_freedom) <= (
                            1e-11
                            * max(abs(batch.degrees_of_freedom), abs(scalar.degrees_of_freedom))
                            + 1e-12
                        )
                    else:
                        assert isinstance(batch, BatchRefusal)
                        assert batch.value == scalar.value


def test_every_frozen_calibration_family_generates_with_test_only_seed() -> None:
    """Every declared calibration family is executable without consuming a phase stream."""
    manifest = _manifest()
    cells = manifest["phases"]["calibration"]["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        assert isinstance(cell, dict)
        replicate = generate_test_fixture_replicate(
            manifest,
            phase="calibration",
            cell_id=cell["id"],
            replicate_id=11,
        )
        assert len(replicate.raw) == len(replicate.block_ids) > 0
        assert all(math.isfinite(value) for value in replicate.excess)
