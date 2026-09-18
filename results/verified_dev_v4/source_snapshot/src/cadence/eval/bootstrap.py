"""Paired bootstrap confidence intervals (CONTRACT.md §13: 1000 resamples, seed 42)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from cadence.config import SEED


def bootstrap_distribution(
    metric_fn: Callable[..., Any],
    *arrays: Sequence[Any],
    n: int = 1000,
    seed: int = SEED,
) -> np.ndarray:
    """Evaluate ``metric_fn`` on ``n`` paired resamples of ``arrays``.

    All arrays are resampled with the same index vector, so paired inputs (gold vs prediction)
    stay aligned. ``metric_fn`` may return a scalar or a 1-D vector; the result is stacked into an
    array of shape ``(n,)`` or ``(n, k)``.
    """
    if not arrays:
        raise ValueError("bootstrap needs at least one array")
    length = len(arrays[0])
    if any(len(a) != length for a in arrays):
        raise ValueError("all arrays passed to bootstrap must have the same length")
    if length == 0:
        raise ValueError("cannot bootstrap an empty sample")
    if n <= 0:
        raise ValueError("n must be positive")
    rng = np.random.default_rng(seed)
    np_arrays = [np.asarray(a, dtype=object) for a in arrays]
    samples = []
    for _ in range(n):
        idx = rng.integers(0, length, size=length)
        samples.append(np.asarray(metric_fn(*(a[idx] for a in np_arrays)), dtype=float))
    return np.stack(samples)


def bootstrap_ci(
    metric_fn: Callable[..., Any],
    *arrays: Sequence[Any],
    n: int = 1000,
    seed: int = SEED,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Percentile ``(1 - alpha)`` confidence interval of a scalar metric via paired resampling.

    Deterministic for a fixed ``seed``. Raises ``ValueError`` on empty input.
    """
    dist = bootstrap_distribution(metric_fn, *arrays, n=n, seed=seed)
    if dist.ndim != 1:
        raise ValueError("bootstrap_ci expects a scalar metric; use bootstrap_distribution for vectors")
    lo, hi = np.nanpercentile(dist, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def bootstrap_ci_vector(
    metric_fn: Callable[..., Any],
    *arrays: Sequence[Any],
    n: int = 1000,
    seed: int = SEED,
    alpha: float = 0.05,
) -> list[tuple[float, float]]:
    """Per-component percentile CIs for a metric that returns a 1-D vector (e.g. per-class F1)."""
    dist = bootstrap_distribution(metric_fn, *arrays, n=n, seed=seed)
    if dist.ndim != 2:
        raise ValueError("bootstrap_ci_vector expects a vector-valued metric")
    lo = np.nanpercentile(dist, 100 * alpha / 2, axis=0)
    hi = np.nanpercentile(dist, 100 * (1 - alpha / 2), axis=0)
    return [(float(a), float(b)) for a, b in zip(lo, hi, strict=True)]
