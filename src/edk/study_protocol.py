"""Explicit environment-study quality criteria, never an entropy certification."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from .analysis import analyze_sessions
from .jsonio import integer, keys, read_document
from .manifest import AnchorManifest
from .observations import ObservationSession
from .simulation import _nonnegative_finite

POLICY_SCHEMA = "edk.study-policy/v1"
STUDY_REPORT_SCHEMA = "edk.study-assessment/v1"
_POLICY_FIELDS = {"schema_version", "manifest_fingerprint", "created_at",
                  "minimum_sessions", "minimum_observers", "minimum_span_seconds",
                  "maximum_operational_erasure_rate", "maximum_pairwise_disagreement_rate",
                  "maximum_p95_reading_ms"}


def _utc_timestamp(value: Any) -> datetime:
    if type(value) is not str:
        raise ValueError("study timestamp must be canonical UTC text")
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        if result.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
            raise ValueError
    except ValueError:
        raise ValueError("study timestamp must be canonical UTC text") from None
    return result


@dataclass(frozen=True)
class StudyPolicy:
    """A public, explicitly chosen policy bound to one public manifest.

    No quality thresholds have implicit security defaults. The timestamp is an
    operator declaration and does not establish trusted preregistration.
    """

    manifest_fingerprint: str
    created_at: str
    minimum_sessions: int
    minimum_observers: int
    minimum_span_seconds: float
    maximum_operational_erasure_rate: float
    maximum_pairwise_disagreement_rate: float
    maximum_p95_reading_ms: int
    schema_version: str = POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != POLICY_SCHEMA:
            raise ValueError("unsupported study policy schema")
        if (type(self.manifest_fingerprint) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", self.manifest_fingerprint)):
            raise ValueError("invalid study manifest fingerprint")
        _utc_timestamp(self.created_at)
        integer(self.minimum_sessions, 5, 1000)
        integer(self.minimum_observers, 1, 1000)
        _nonnegative_finite(self.minimum_span_seconds, "minimum study span")
        for rate in (self.maximum_operational_erasure_rate, self.maximum_pairwise_disagreement_rate):
            _nonnegative_finite(rate, "maximum study rate")
            if rate > 1:
                raise ValueError("maximum study rate outside permitted range")
        integer(self.maximum_p95_reading_ms, 1, 86_400_000)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version,
                "manifest_fingerprint": self.manifest_fingerprint, "created_at": self.created_at,
                "minimum_sessions": self.minimum_sessions, "minimum_observers": self.minimum_observers,
                "minimum_span_seconds": self.minimum_span_seconds,
                "maximum_operational_erasure_rate": self.maximum_operational_erasure_rate,
                "maximum_pairwise_disagreement_rate": self.maximum_pairwise_disagreement_rate,
                "maximum_p95_reading_ms": self.maximum_p95_reading_ms}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StudyPolicy":
        keys(value, _POLICY_FIELDS)
        return cls(**value)

    @classmethod
    def load(cls, path: str | Path) -> "StudyPolicy":
        return cls.from_dict(read_document(path))


def analyze_study(manifest: AnchorManifest, sessions: Sequence[ObservationSession],
                  policy: StudyPolicy) -> dict[str, Any]:
    """Evaluate stated repeatability/timing criteria on a single declared source.

    Sessions must start on or after the policy's declared timestamp. This check
    cannot authenticate that timestamp or prove independent human observations.
    No states, identifiers, manifest fingerprint or timestamp are exported.
    """
    if not isinstance(manifest, AnchorManifest) or not isinstance(policy, StudyPolicy):
        raise ValueError("study requires a validated manifest and policy")
    if (not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes, bytearray))
            or not 2 <= len(sessions) <= 1000):
        raise ValueError("study assessment requires 2..1000 sessions")
    if policy.manifest_fingerprint != manifest.fingerprint:
        raise ValueError("study policy belongs to a different manifest")
    declared_start = _utc_timestamp(policy.created_at)
    stamps = []
    for session in sessions:
        if not isinstance(session, ObservationSession):
            raise ValueError("study requires observation sessions")
        session.validate_for(manifest)
        stamp = _utc_timestamp(session.started_at)
        if stamp < declared_start:
            raise ValueError("study session predates declared policy")
        stamps.append(stamp)
    # Reuses validated source/duplicate rejection, missingness, mismatch, time,
    # externally assigned event labels and exploratory correlated differences.
    aggregate = analyze_sessions(manifest, sessions)
    observers = len({session.observer_code for session in sessions})
    span = (max(stamps) - min(stamps)).total_seconds()
    pairwise_rate = aggregate["pairwise_disagreement_rate"]
    criteria = {
        "minimum_sessions_met": len(sessions) >= policy.minimum_sessions,
        "minimum_observers_met": observers >= policy.minimum_observers,
        "minimum_span_met": span >= policy.minimum_span_seconds,
        "operational_erasure_rate_within_limit": (
            aggregate["operational_erasure_rate"] <= policy.maximum_operational_erasure_rate),
        "pairwise_disagreement_rate_within_limit": (
            pairwise_rate is not None and pairwise_rate <= policy.maximum_pairwise_disagreement_rate),
        "p95_reading_time_within_limit": (
            aggregate["reading_time_ms"]["p95"] <= policy.maximum_p95_reading_ms),
    }
    passed = all(criteria.values())
    source = aggregate["declared_source"]
    return {
        "schema_version": STUDY_REPORT_SCHEMA,
        "declared_source": source,
        "counts": {"sessions": len(sessions), "observers": observers,
                   "anchors": len(manifest.anchors),
                   "pairwise_normal_comparisons": aggregate["pairwise_normal_comparisons"]},
        "session_span_seconds": span,
        "requirements": {name: value for name, value in policy.to_dict().items()
                         if name not in ("schema_version", "manifest_fingerprint", "created_at")},
        "criteria": criteria,
        "study_quality_criteria_passed": passed,
        "manual_workflow_criteria_passed": source == "manual" and passed,
        "environment_entropy_validated": False,
        "real_key_derivation_approved": False,
        "aggregate": aggregate,
        "interpretation": {
            "policy": "Policy timestamps are declarations; software cannot prove trusted preregistration or prevent retrospective policy selection.",
            "source": "Manual/synthetic source labels, observer pseudonyms and timestamps are not authenticated; human identity and reading independence are not verified.",
            "quality": "Repeatability, missingness and reading time are study-quality measures, not conditional min-entropy or attacker recovery estimates.",
            "causes": "Disagreement is not automatically a misread; external event labels do not verify physical erasure or historical information loss.",
            "scope": "Passing quality criteria does not authorize real key derivation, fuzzy recovery or hardware PIN trials.",
            "privacy": "No raw states, per-anchor identifiers, observer/session identifiers, timestamps or manifest fingerprint are exported; not differential privacy.",
        },
    }
