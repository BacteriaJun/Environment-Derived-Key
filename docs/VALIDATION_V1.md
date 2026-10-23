# EDK 1.0 software validation

Version 1.0.0 identifies the concept algorithm and reference implementation. Long-term engineering validation has not been performed. This document describes the software checks; the accompanying `validation.json` records the actual run.

## Test coverage

The suite contains 180 tests: the previous 168, ten exact-input concept tests, and two additional distribution-description/concept-report tests. The original 16 baseline tests remain unchanged.

The concept tests cover a fixed public seed-2026 vector, all 20 threshold combinations, repaired-share equivalence, public context parsing, manifest and order binding, observation-metadata independence, missing/ambiguous/unreadable inputs, insufficient/corrupt/mixed shares, source-coordinate constraints, seed bounds, CLI failure redaction, report overwrite refusal and execution without current-directory files. They also compare the wrapper directly with the existing environmental encoder and KDF composition.

Legacy GF(256), RFC 5869, raw-byte PIN, observation, lifecycle, transport, write-interruption, journal and packaging coverage remains in place. The concept known-answer vector is a synthetic fixture; it has no connection to measured physical state or a real security device.

## Distribution acceptance

The offline verifier exports the public source, reproduces its ZIP, runs ordinary and optimized tests, builds wheel/sdist, checks exact source and metadata correspondence, reruns the sdist tests and rebuilds a wheel, then installs the wheel in a new virtual environment. Both README languages must be included in source/sdist. The declared README text must match wheel/sdist package-description metadata.

Installed commands run from outside the source directory. The new `concept-run --seed 2026` check validates its profile, version, synthetic source, mode, 20-quorum result and boolean outcomes; its acceptance summary does not contain PINs or raw execution material.

## Execution scope

Local execution uses Python 3.12.14 on macOS. Linux CI is configured for Python 3.11/3.12/3.13, including the native I²C UAPI probe; the configured workflow is separate from a completed remote run. Actual command results and file hashes are provided in `validation.json` and `CHECKSUMS.sha256`.

Physical I²C transfers, supply switching, long-term environmental maintenance/decay, retention curves, residual-information recovery and target-keypad integration have no measured results yet. Mathematical arguments identify their assumptions; external proof/security review remains a research work item. Publication state is recorded separately from local builds.

See [algorithm/API](CONCEPT_ALGORITHM.md), [formal specification](FORMAL_SPEC.md), [version decision](adr/0005-concept-release-and-exact-input-profile.md) and [roadmap](ROADMAP.md). Earlier `VALIDATION_*` documents describe their historical snapshots.
