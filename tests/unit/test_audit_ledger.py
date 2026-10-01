"""The ranked fix list has to stay readable as a checklist (`CLAUDE.md` §1).

`docs/reviews/*-audit.md` §6 is, by its own header, **the durable record**: chat is compacted and
`TASKS.md` only gets an entry once we commit to working on something, so between "found" and
"scheduled" a finding lives in that table and nowhere else.

A table that is the only record of what is outstanding is worth exactly as much as its status
column. Three rows (F29, F30, F38) went into task 2f already carrying their fix in the *finding*
cell while the *status* cell still read OPEN, and two more (F36, F37) had done the same in 2e —
five rows across two tasks describing themselves as both done and open. Nothing caught it, because
nothing was looking: it is prose, and prose is not run.

These tests are cheap and they close that. They check the shape of the record, never its content —
whether a particular finding *should* be closed is a judgement, but "this row contradicts itself"
is not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REVIEWS = Path(__file__).resolve().parents[2] / "docs" / "reviews"

# `| F12 / M1 / P1 / R1 | finding | status | next action |` — the four-column shape of the §6 table.
_ROW = re.compile(r"^\| ([A-Z]+\d+b?) \| (.+?) \| (.+?) \| (.+?) \|\s*$", re.M)

# Vocabulary declared in the table's own header line.
_STATUSES = (
    "OPEN",
    "DECIDED",
    "DEFERRED",
    "IN TASKS.md",
    "PARTLY DONE",
    "DONE",
    "CLOSED",
    "WON'T FIX",
    "BLOCKS",
)


def _audits() -> list[Path]:
    found = sorted(REVIEWS.glob("*-audit.md"))
    assert found, f"no audit files under {REVIEWS} — has the review folder moved?"
    return found


def _rows(path: Path) -> list[tuple[str, str, str, str]]:
    """Rows of the §6 ranked list only.

    Scoped rather than applied file-wide because §6d lists the *strategies* and numbers them
    ``F0``..``F8`` as well — a naming collision, not a defect, and a check that tripped over it
    would be noise on every run until somebody deleted the check.
    """
    body = path.read_text(encoding="utf-8")
    heading = re.search(r"^## (?:6\. )?Ranked fix list[^\n]*$", body, re.M)
    assert heading is not None, f"{path.name}: missing ranked fix list"
    end = body.find("\n## ", heading.end())
    rows = _ROW.findall(body[heading.end() : end if end != -1 else len(body)])
    assert rows, f"{path.name}: no findings in ranked fix list"
    return rows


@pytest.mark.parametrize("path", _audits(), ids=lambda p: p.name)
def test_no_finding_claims_to_be_both_done_and_open(path: Path) -> None:
    """A resolution written into the wrong cell leaves the checklist lying in both directions.

    It reads as outstanding work to anyone scanning the status column, and as finished work to
    anyone reading the row. Both readings are wrong, and the one that costs money is re-opening a
    settled question while a genuinely open one goes unread beside it.
    """
    contradictory = [
        (fid, status.strip()[:60])
        for fid, finding, status, _why in _rows(path)
        if "DONE" in finding and "DONE" not in status
    ]
    assert not contradictory, (
        f"{path.name}: these rows carry their fix in the FINDING cell while the STATUS cell still "
        f"reads open — the resolution belongs in the status column: {contradictory}"
    )


@pytest.mark.parametrize("path", _audits(), ids=lambda p: p.name)
def test_every_status_uses_the_declared_vocabulary(path: Path) -> None:
    """The table declares its own status words. A row outside them cannot be counted."""
    unknown = [
        (fid, status.strip()[:60])
        for fid, _finding, status, _why in _rows(path)
        if not any(word in status for word in _STATUSES)
    ]
    assert not unknown, (
        f"{path.name}: status cells not using the declared vocabulary {_STATUSES}: {unknown}"
    )


@pytest.mark.parametrize("path", _audits(), ids=lambda p: p.name)
def test_finding_ids_are_unique_within_the_ranked_list(path: Path) -> None:
    """Two rows sharing an id means one of them is invisible to every reference to that number."""
    ids = [fid for fid, *_ in _rows(path)]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"{path.name}: duplicate finding ids in the ranked list: {duplicates}"


@pytest.mark.parametrize("heading", ["## 6. Ranked fix list", "## Ranked fix list"])
@pytest.mark.parametrize("trailer", ["", "\n## Other section\n| M1 | outside | OPEN | ignored |\n"])
def test_ranked_parser_reads_all_namespaces_only_in_its_section(
    tmp_path: Path, heading: str, trailer: str
) -> None:
    path = tmp_path / "audit.md"
    path.write_bytes(
        (
            heading + "\n"
            "| M1 | model | OPEN | next model |\n"
            "| P1 | platform | BLOCKS | host |\n"
            "| R1 | integration | DEFERRED | datastore |\n"
            "| F12b | legacy | CLOSED | fixed |\n" + trailer
        ).encode()
    )
    assert _rows(path) == [
        ("M1", "model", "OPEN", "next model"),
        ("P1", "platform", "BLOCKS", "host"),
        ("R1", "integration", "DEFERRED", "datastore"),
        ("F12b", "legacy", "CLOSED", "fixed"),
    ]


@pytest.mark.parametrize(
    "body", ["# No ranked section\n", "## Ranked fix list\n| ID | Finding | Status | Why |\n"]
)
def test_ranked_parser_refuses_missing_or_empty_finding_lists(tmp_path: Path, body: str) -> None:
    path = tmp_path / "audit.md"
    path.write_bytes(body.encode())
    with pytest.raises(AssertionError):
        _rows(path)
