"""Synthetic monthly trajectories; history loss is an assumed latent state."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random
from typing import Any

from .jsonio import identifier, integer
from .simulation import _nonnegative_finite


@dataclass(frozen=True)
class NodeModel:
    node_id: str
    location: str
    monthly_hazard: float
    stress_multiplier: float = 1.0
    continuously_powered: bool = False

    def __post_init__(self) -> None:
        identifier(self.node_id)
        identifier(self.location)
        _nonnegative_finite(self.monthly_hazard, "node hazard")
        _nonnegative_finite(self.stress_multiplier, "stress multiplier")
        if type(self.continuously_powered) is not bool:
            raise ValueError("powered flag must be boolean")


DEFAULT_NODES = (
    NodeModel("S1", "person", 0.09), NodeModel("S2", "home", 0.045),
    NodeModel("S3", "secondary", 0.05), NodeModel("S4", "vehicle", 0.11, 2.0),
    NodeModel("S5", "home", 0.002, continuously_powered=True),
    NodeModel("S6", "office", 0.06),
)


@dataclass(frozen=True)
class LifecycleConfig:
    anchors: int = 8
    nodes: tuple[NodeModel, ...] = DEFAULT_NODES
    location_hazards: tuple[tuple[str, float], ...] = (("home", 0.01), ("vehicle", 0.02))
    drift_hazard: float = 0.01
    physical_erasure_hazard: float = 0.003
    history_loss_hazard: float = 0.002
    misread_probability: float = 0.01
    ambiguous_probability: float = 0.01
    threshold: int = 3
    maintenance_interval: int | None = None
    maintenance_stop_after: int | None = None

    def __post_init__(self) -> None:
        integer(self.anchors, 1, 512)
        integer(self.threshold, 2, 6)
        if (type(self.nodes) is not tuple or len(self.nodes) != 6
                or any(not isinstance(n, NodeModel) for n in self.nodes)
                or len({n.node_id for n in self.nodes}) != 6):
            raise ValueError("six distinct node models required")
        locations = {n.location for n in self.nodes}
        seen: set[str] = set()
        if type(self.location_hazards) is not tuple:
            raise ValueError("invalid location hazards")
        for pair in self.location_hazards:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("invalid location hazard pair")
            name, hazard = pair
            identifier(name)
            if name not in locations or name in seen:
                raise ValueError("unknown or duplicate location hazard")
            _nonnegative_finite(hazard, "location hazard")
            seen.add(name)
        for value in (self.drift_hazard, self.physical_erasure_hazard, self.history_loss_hazard,
                      self.misread_probability, self.ambiguous_probability):
            _nonnegative_finite(value, "environment parameter")
        if self.misread_probability + self.ambiguous_probability > 1:
            raise ValueError("reading probabilities exceed one")
        if self.maintenance_interval is not None:
            integer(self.maintenance_interval, 1, 600)
        if self.maintenance_stop_after is not None:
            integer(self.maintenance_stop_after, 0, 600)
            if self.maintenance_interval is None:
                raise ValueError("maintenance stop requires a maintenance interval")


def _event_probability(hazard: float) -> float:
    return -math.expm1(-float(hazard))


def lifecycle_report(config: LifecycleConfig, *, months: int = 36, trials: int = 1000,
                     seed: int = 2026) -> dict[str, Any]:
    """No physical secrets or PINs; repair requires an intact quorum/history."""
    if not isinstance(config, LifecycleConfig):
        raise ValueError("lifecycle configuration required")
    integer(months, 0, 600)
    integer(trials, 1, 100000)
    if type(seed) is not int or (months + 1) * trials * (config.anchors + 6) > 20_000_000:
        raise ValueError("invalid seed or simulation work limit exceeded")
    rng = random.Random(seed)
    snapshots = [dict(quorum=0, history=0, exact=0, normal=0, system=0,
                      misreads=0, ambiguous=0, erased=0, history_lost=0,
                      node_repairs=0, environment_repairs=0) for _ in range(months + 1)]
    node_ps = [_event_probability(float(n.monthly_hazard) * float(n.stress_multiplier)) for n in config.nodes]
    location_ps = [(loc, _event_probability(rate)) for loc, rate in config.location_hazards]
    drift_p, erasure_p, loss_p = map(_event_probability,
                                    (config.drift_hazard, config.physical_erasure_hazard,
                                     config.history_loss_hazard))
    for _ in range(trials):
        live = [True] * 6
        history = [True] * config.anchors
        matches = [True] * config.anchors
        visible = [True] * config.anchors
        for month in range(months + 1):
            if month:
                for index, probability in enumerate(node_ps):
                    if rng.random() < probability:
                        live[index] = False
                for location, probability in location_ps:
                    if rng.random() < probability:
                        for index, node in enumerate(config.nodes):
                            if node.location == location:
                                live[index] = False
                for index in range(config.anchors):
                    if rng.random() < drift_p:
                        matches[index] = False
                    if rng.random() < erasure_p:
                        visible[index] = False
                    if rng.random() < loss_p:
                        history[index] = False
                        matches[index] = False
            row = snapshots[month]
            maintained = (month > 0 and config.maintenance_interval is not None
                          and month % config.maintenance_interval == 0
                          and (config.maintenance_stop_after is None or month <= config.maintenance_stop_after))
            if maintained:
                # Never manufacture a quorum or restore genuinely lost history.
                if sum(live) >= config.threshold:
                    row["node_repairs"] += 6 - sum(live)
                    live = [True] * 6
                for index in range(config.anchors):
                    if history[index] and (not matches[index] or not visible[index]):
                        row["environment_repairs"] += 1
                        matches[index] = visible[index] = True
            quorum = sum(live) >= config.threshold
            information = all(history)
            exact = True
            for index in range(config.anchors):
                sample = rng.random()
                ambiguous = sample < config.ambiguous_probability
                misread = config.ambiguous_probability <= sample < (
                    config.ambiguous_probability + config.misread_probability)
                row["ambiguous"] += int(ambiguous)
                row["misreads"] += int(misread and not ambiguous and visible[index])
                row["erased"] += int(not visible[index])
                row["history_lost"] += int(not history[index])
                if (ambiguous or misread or not visible[index]
                        or not matches[index] or not history[index]):
                    exact = False
            row["quorum"] += int(quorum)
            row["history"] += int(information)
            row["exact"] += int(exact)
            row["normal"] += int(quorum and exact)
            row["system"] += int(quorum and information)
    rows = []
    for month, row in enumerate(snapshots):
        denominator = trials * config.anchors
        rows.append({
            "month": month,
            "normal_recovery_rate": row["normal"] / trials,
            "electronic_quorum_rate": row["quorum"] / trials,
            "environment_information_survival_rate": row["history"] / trials,
            "environment_exact_read_rate": row["exact"] / trials,
            "system_recoverable_in_model_rate": row["system"] / trials,
            "misread_fraction": row["misreads"] / denominator,
            "ambiguous_fraction": row["ambiguous"] / denominator,
            "physical_erasure_fraction": row["erased"] / denominator,
            "historical_loss_fraction": row["history_lost"] / denominator,
            "node_repairs": row["node_repairs"], "environment_repairs": row["environment_repairs"],
        })
    return {"schema_version": "edk.synthetic-lifecycle/v1", "synthetic_assumptions_only": True,
            "seed": seed, "trials": trials, "parameters": asdict(config), "months": rows,
            "interpretation": {
                "history": "Latent information loss is imposed by the model, not detected by a decoder.",
                "recovery": "Model recoverability can require physical restoration; normal recovery needs exact reads.",
                "maintenance": "Repairs only with a surviving quorum and surviving historical information.",
                "attacker": "No attacker success probability or real retention lifetime is inferred.",
            }}
