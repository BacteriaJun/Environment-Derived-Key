"""Strict public bench-report checks; no hardware authenticity or lifetime proof."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
import statistics
from typing import Any

from .bench import BenchToken, TEST_PURPOSE
from .jsonio import integer, keys, read_document
from .simulation import _nonnegative_finite

OBSERVATION_SCHEMA = "edk.bench-observation/v1"
ACCEPTANCE_SCHEMA = "edk.bench-acceptance/v1"
_DURATION_PROVENANCE = "operator supplied, not measured by this program"
_INTERPRETATION = "A matching public pattern is an observation, not an erase, entropy or security proof."
_FIELDS = {"schema_version", "source", "purpose", "public_test_nonce",
           "matches_public_pattern", "status_before", "status_after",
           "status_changed_during_read", "operator_vcc_off_seconds",
           "duration_provenance", "observed_at", "interpretation"}
_STATUS_FIELDS = {"backup_enabled", "power_failure_recorded", "oscillator_running"}


def validate_bench_report(report: dict[str, Any]) -> None:
    """Validate the existing observation v1 schema without echoing field values.

    This verifies internal consistency only. JSON fields do not attest a device,
    measured voltage, clock or operator; a forged but consistent report may pass.
    """
    keys(report, _FIELDS)
    if (report["schema_version"] != OBSERVATION_SCHEMA
            or report["purpose"] != TEST_PURPOSE
            or report["source"] not in ("physical_io", "synthetic_bus")
            or report["duration_provenance"] != _DURATION_PROVENANCE
            or report["interpretation"] != _INTERPRETATION):
        raise ValueError("unsupported bench report metadata")
    if type(report["public_test_nonce"]) is not str or type(report["observed_at"]) is not str:
        raise ValueError("invalid bench report identity or timestamp")
    # The public nonce and canonical UTC syntax have the token format's rules.
    BenchToken(report["public_test_nonce"], report["observed_at"])
    for name in ("matches_public_pattern", "status_changed_during_read"):
        if type(report[name]) is not bool:
            raise ValueError("bench result must be boolean")
    for name in ("status_before", "status_after"):
        keys(report[name], _STATUS_FIELDS)
        if any(type(value) is not bool for value in report[name].values()):
            raise ValueError("bench status must be boolean")
    changed = report["status_before"] != report["status_after"]
    if report["status_changed_during_read"] != changed:
        raise ValueError("inconsistent bench status change")
    if report["operator_vcc_off_seconds"] is not None:
        _nonnegative_finite(report["operator_vcc_off_seconds"], "operator duration")


def load_bench_report(path: str | Path) -> dict[str, Any]:
    """Read bounded JSON; duplicate/unknown keys and malformed reports fail."""
    report = read_document(path)
    validate_bench_report(report)
    return report


def analyze_bench_reports(reports: Sequence[dict[str, Any]], *, minimum_trials: int = 5,
                          minimum_vcc_off_seconds: float = 0) -> dict[str, Any]:
    """Apply explicit acceptance criteria to public, same-source observations.

    Each trial must use a distinct public nonce. A matching repeated reading of
    the same preparation is not counted as another trial. Distinct nonces still
    do not establish statistical independence or confirm a real power cycle.
    """
    integer(minimum_trials, 1, 1000)
    _nonnegative_finite(minimum_vcc_off_seconds, "minimum operator duration")
    if (not isinstance(reports, Sequence) or isinstance(reports, (str, bytes, bytearray))
            or not 1 <= len(reports) <= 1000):
        raise ValueError("bench acceptance requires 1..1000 reports")
    for report in reports:
        validate_bench_report(report)
    if len({report["source"] for report in reports}) != 1:
        raise ValueError("do not mix physical and synthetic bench reports")
    if len({report["public_test_nonce"] for report in reports}) != len(reports):
        raise ValueError("duplicate public bench trial")

    criterion_names = ("pattern_match", "backup_enabled_before_and_after",
                       "status_unchanged", "duration_supplied", "minimum_duration_met")
    counts = {name: {"passed": 0, "failed": 0} for name in criterion_names}
    passed_trials = 0
    durations: list[float] = []
    for report in reports:
        duration = report["operator_vcc_off_seconds"]
        checks = (
            report["matches_public_pattern"],
            report["status_before"]["backup_enabled"] and report["status_after"]["backup_enabled"],
            not report["status_changed_during_read"],
            duration is not None,
            duration is not None and duration >= minimum_vcc_off_seconds,
        )
        for name, passed in zip(criterion_names, checks):
            counts[name]["passed" if passed else "failed"] += 1
        passed_trials += int(all(checks))
        if duration is not None:
            durations.append(float(duration))
    durations.sort()
    sample_requirement = len(reports) >= minimum_trials
    criteria_passed = sample_requirement and passed_trials == len(reports)
    source = reports[0]["source"]
    # Avoid overflow in (left + right) / 2 for large finite durations.
    middle = len(durations) // 2
    median = (durations[middle] if len(durations) % 2 else
              durations[middle - 1] + (durations[middle] - durations[middle - 1]) / 2) if durations else None
    return {
        "schema_version": ACCEPTANCE_SCHEMA,
        "declared_source": source,
        "trials": len(reports),
        "requirements": {"minimum_trials": minimum_trials,
                         "minimum_operator_vcc_off_seconds": minimum_vcc_off_seconds},
        "sample_count_requirement_met": sample_requirement,
        "trial_result_counts": {"passed": passed_trials, "failed": len(reports) - passed_trials},
        "criterion_counts": counts,
        "duration_seconds": {"supplied": len(durations), "missing": len(reports) - len(durations),
                             "minimum": min(durations) if durations else None,
                             "maximum": max(durations) if durations else None,
                             "mean": statistics.mean(durations) if durations else None,
                             "median": median},
        "acceptance_criteria_passed": criteria_passed,
        "declared_physical_workflow_criteria_passed": source == "physical_io" and criteria_passed,
        "physical_acceptance_verified": False,
        "interpretation": {
            "provenance": "Source labels and operator durations are untrusted declarations, not hardware attestation.",
            "trials": "Distinct nonces avoid duplicate preparations; statistical independence and actual power cycles are not verified.",
            "scope": "Criteria cover recorded public-pattern observations only; no entropy, erasure or reliability guarantee.",
            "statistics": "Zero observed failures is not proof of zero failure probability or measured device lifetime.",
            "privacy": "No per-trial nonce, timestamp, adapter, raw SRAM data or secret material is exported.",
        },
    }
