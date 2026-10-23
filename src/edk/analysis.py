"""Anonymous aggregate repeatability statistics; no entropy inference."""

from __future__ import annotations

from collections import Counter
import itertools
import math
from pathlib import Path
import statistics
from typing import Any, Sequence

from .manifest import AnchorManifest
from .observations import EVENT_LABELS, ObservationSession
from .private_store import write_new_aggregate

REPORT_SCHEMA = "edk.aggregate-report/v1"


def analyze_sessions(manifest: AnchorManifest,
                     sessions: Sequence[ObservationSession]) -> dict[str, Any]:
    if not 2 <= len(sessions) <= 1000:
        raise ValueError("analysis requires 2..1000 sessions")
    if any(not isinstance(s, ObservationSession) for s in sessions):
        raise ValueError("analysis requires observation sessions")
    if len({s.session_id for s in sessions}) != len(sessions):
        raise ValueError("duplicate study session")
    if len({s.source for s in sessions}) != 1:
        raise ValueError("do not pool synthetic and manual observations")
    for session in sessions:
        session.validate_for(manifest)
    ordered = sorted(sessions, key=lambda s: (s.started_at, s.session_id))
    readings = [r for session in ordered for r in session.readings]
    statuses = Counter(r.status for r in readings)
    labels = Counter(r.event_label for r in readings)
    comparisons, disagreements = 0, 0
    for column in zip(*(s.readings for s in ordered)):
        values = Counter(r.value for r in column if r.status == "normal")
        total = sum(values.values())
        pairs = total * (total - 1) // 2
        matches = sum(count * (count - 1) // 2 for count in values.values())
        comparisons += pairs
        disagreements += pairs - matches

    correlations = []
    eligible_pairs = 0
    # Bound O(anchor_count^2 * sessions). No selected-anchor subset is reported.
    correlation_status = "calculated" if len(manifest.anchors) <= 64 else "omitted_more_than_64_anchors"
    if len(manifest.anchors) <= 64:
        reference = ordered[0]
        for left, right in itertools.combinations(range(len(manifest.anchors)), 2):
            if reference.readings[left].status != "normal" or reference.readings[right].status != "normal":
                continue
            table = [0, 0, 0, 0]  # 00, 01, 10, 11 mismatch indicators, no values.
            for session in ordered[1:]:
                a, b = session.readings[left], session.readings[right]
                if a.status != "normal" or b.status != "normal":
                    continue
                x = int(a.value != reference.readings[left].value)
                y = int(b.value != reference.readings[right].value)
                table[2 * x + y] += 1
            a, b, c, d = table
            if sum(table) < 3:
                continue
            eligible_pairs += 1
            denominator = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
            if denominator:
                correlations.append((a * d - b * c) / denominator)

    times = sorted(r.duration_ms for r in readings)
    total = len(readings)
    return {
        "schema_version": REPORT_SCHEMA,
        "declared_source": ordered[0].source,
        "sessions": len(ordered), "anchors": len(manifest.anchors), "readings": total,
        "status_counts": {k: statuses[k] for k in ("normal", "ambiguous", "unreadable")},
        "operational_erasure_rate": (statuses["ambiguous"] + statuses["unreadable"]) / total,
        "pairwise_normal_comparisons": comparisons,
        "pairwise_disagreements": disagreements,
        "pairwise_disagreement_rate": disagreements / comparisons if comparisons else None,
        "externally_labeled_events": {k: labels[k] for k in EVENT_LABELS},
        "annotated_misread_fraction": labels["misread"] / total,
        "reading_time_ms": {"sum": sum(times), "mean": statistics.mean(times),
                            "median": statistics.median(times),
                            "p95": times[math.ceil(0.95 * len(times)) - 1]},
        "correlated_disagreement": {
            "status": correlation_status, "reference": "chronologically_first_session",
            "minimum_paired_repeats": 3, "eligible_anchor_pairs": eligible_pairs,
            "defined_phi_pairs": len(correlations),
            "mean_phi": statistics.mean(correlations) if correlations else None,
            "max_absolute_phi": max(map(abs, correlations)) if correlations else None,
        },
        "interpretation": {
            "events": "Externally assigned labels, not verified causes; unknown stays unknown.",
            "erasure": "Operational missingness is not proof of physical or historical information loss.",
            "entropy": "No entropy estimate or adversarial recovery probability is inferred.",
            "privacy": "No raw states, anchor identities, timestamps, observers or session IDs; not differential privacy.",
        },
    }


def export_aggregate(manifest: AnchorManifest, sessions: Sequence[ObservationSession],
                     path: str | Path) -> dict[str, Any]:
    if len(sessions) < 5 or len(manifest.anchors) < 3:
        raise ValueError("public aggregate export requires at least five sessions and three anchors")
    report = analyze_sessions(manifest, sessions)
    write_new_aggregate(path, report)
    return report
