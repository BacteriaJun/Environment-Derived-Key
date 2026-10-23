"""Illustrative environmental + electronic lifetime model.

Survival/decay parameters are made up for demonstration, not measured data.
All simulations use a seeded NON-CRYPTOGRAPHIC PRNG for reproducibility.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def _nonnegative_finite(value: float, label: str) -> None:
    try:
        valid = (type(value) in (int, float) and math.isfinite(value) and value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must be finite and nonnegative")


def survival_probability(
    months: float, *, trials: int = 5000, seed: int = 2026,
    node_hazards: tuple[float, ...] = (0.09, 0.045, 0.05, 0.11, 0.002, 0.06),
    env_hazard: float = 0.03, threshold: int = 3
) -> dict[str, float | int]:
    """Unmaintained lifetime; independent exponential-loss assumption.

    env_hazard represents total loss of environment recovery, not actual
    spatial cell decay. S5's illustrative near-zero hazard models constant
    power, without assuming it is literally immortal.
    """
    _nonnegative_finite(months, "months")
    _nonnegative_finite(env_hazard, "environment hazard")
    if type(trials) is not int or trials <= 0:
        raise ValueError("trials must be a positive integer")
    if (not isinstance(node_hazards, Sequence)
            or isinstance(node_hazards, (str, bytes, bytearray)) or len(node_hazards) != 6):
        raise ValueError("six node hazards required")
    for hazard in node_hazards:
        _nonnegative_finite(hazard, "node hazard")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if type(threshold) is not int or not 1 <= threshold <= 6:
        raise ValueError("invalid threshold")
    rng = random.Random(seed)
    duration = float(months)
    nodes_alive = 0
    environment_alive = 0
    joint_alive = 0
    for _ in range(trials):
        live_count = sum(rng.random() < math.exp(-float(hazard) * duration)
                         for hazard in node_hazards)
        env_ok = rng.random() < math.exp(-float(env_hazard) * duration)
        if live_count >= threshold:
            nodes_alive += 1
        if env_ok:
            environment_alive += 1
        if live_count >= threshold and env_ok:
            joint_alive += 1
    return {
        "months": months,
        "trials": trials,
        "node_recovery_rate": nodes_alive / trials,
        "environment_recovery_rate": environment_alive / trials,
        "combined_recovery_rate": joint_alive / trials,
    }
