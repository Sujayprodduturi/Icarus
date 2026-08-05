"""The Phase-1 primitive library — catalogue §2-5 (task 1.4a).

:func:`default_registry` is the one place the vocabulary is assembled. Each module exposes a pure
``primitives()`` function and registers nothing on import, so "which words exist" never depends on
import order and a test cannot leak an extra word into the next one.

Adding a primitive means adding it to exactly one tuple, beside its own computation — which is the
property the whole design exists to protect (see :mod:`icarus.strategy.dsl`).
"""

from __future__ import annotations

from icarus.strategy.dsl import Registry
from icarus.strategy.library import (
    classics,
    oscillators,
    structure,
    trend,
    volatility,
    volume,
    zones,
)

MODULES = (trend, volatility, oscillators, volume, structure, zones, classics)


def default_registry() -> Registry:
    """A fresh registry holding every Phase-1 primitive. Callers own the instance."""
    registry = Registry()
    for module in MODULES:
        for primitive in module.primitives():
            registry.register(primitive)
    return registry


__all__ = ["MODULES", "default_registry"]
