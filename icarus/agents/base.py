"""Agent base (CLAUDE.md §3, PRD §10).

Every agent is an independently-restartable, single-responsibility unit supervised by the
Orchestrator. Phase 0 defines the supervised loop (:meth:`run`); the message-handling contract
(``handle(msg) -> list[Msg]``) lands with the bus wiring in Phase 1, when agents start consuming.

An agent's ``run`` loop MUST honor the kill-line: check ``ctx.should_halt()`` and exit promptly
when it returns True (invariant #10/#17).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


@dataclass(frozen=True)
class RunContext:
    """What an agent's loop needs from the orchestrator: the kill-line check."""

    should_halt: Callable[[], Awaitable[bool]]


class Agent(abc.ABC):
    """Base class for every Icarus agent."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abc.abstractmethod
    async def run(self, ctx: RunContext) -> None:
        """The agent's supervised loop. Return to stop; raise to crash (supervisor restarts).

        Must poll ``ctx.should_halt()`` and exit when the kill-line is raised.
        """
