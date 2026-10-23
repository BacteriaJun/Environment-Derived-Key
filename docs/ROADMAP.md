# Research work packages and evidence

Version **1.0.0** defines the EDK concept algorithm and its reference implementation. It brings together exact environmental input, 3-of-6 volatile shares, observation studies, Linux SRAM programming, conditional mathematical arguments and reproducible software packaging. Long-term engineering validation has not been completed. The software version names this implementation; it is not a hardware qualification or a measured security level.

The environmental source remains the central research question: which maintained physical states can contribute secret information, remain readable during normal use, and lose information about their original state after prolonged neglect? Future work is organized by evidence needed to answer that question, rather than by a sequence of version numbers implying increasing security.

## Implementation history

| Revision | Contribution | Evidence at that revision |
|---|---|---|
| `v0.1.0-alpha` | Provided two-input derivation simulator, Shamir 3-of-6, logical volatile nodes and independent decay model | 16 baseline tests |
| `0.1.0a1` | Strict inputs, threshold metadata, debug redaction and legacy compatibility vectors | 52 local tests; stage-1 review and ADR |
| `0.2.0a0` | Versioned observations, private collection, aggregate analysis, extended lifecycle model, Linux SRAM host I/O and conditional proofs | Software installation and synthetic pipelines; physical measurements pending |
| `0.2.0a1` | Linux/Pi host diagnosis, native ABI checker and separate public-pattern bench workflow | 115 local tests; target-host and electrical work still pending |
| `0.2.0a2` | Explicit study policies, bench assessment, configured enrollment journals, read-only reconciliation and offline release verification | Exported-source tests, distribution checks, rebuild and isolated installation |
| `1.0.0` | Concept algorithm and manifest-bound exact-input reference API, integrated with the existing research and engineering tools | Reproducible software checks; no claim of completed long-term environmental or hardware validation |

Historical validation records describe the runtime and checks actually used for each revision. Configured CI coverage and a future measurement plan are distinct from executed results.

## Current algorithm boundary

The reference API encodes a complete observation under an immutable public Manifest, reconstructs `KV` from compatible shares, and calls the inherited HKDF/PIN mapping with the registered public salt and device identifier. Ambiguous or missing readings are rejected. The `concept-run` command exercises synthetic inputs and independent quorums in memory without printing a PIN.

The reference observation profile and the legacy raw-byte profile are different inputs to the KDF. Package version `1.0.0` does not rename the existing KDF domain, SRAM records or JSON schemas. Each format has its own compatibility boundary. A stable deployment context must retain the original Manifest, salt, identifier and selected profile.

## Work packages

| Work package | Questions and implementation work | Evidence to produce |
|---|---|---|
| Physical environmental sources | Evaluate object anchors, reading rules, maintenance, bias, correlation and attacker knowledge; permit rejection of unsuitable sources | Repeated observations across people and time; separate missing reads, misreads, state changes and historical information loss; explicit adversary model and justified uncertainty estimates |
| Robust environment recovery | Evaluate established Secure Sketch/Fuzzy Extractor constructions under the observed source and noise model | Reproducible recovery experiments, helper-data leakage analysis, false-recovery behavior and assessment of offline verification channels |
| Single-node power behavior | Build the Linux/Pi MCP7940N bench and characterize independent VCC/VBAT, leakage, brownouts and temperature | Identified boards/components, recorded electrical conditions, repeated retention/loss observations and uncertainty; estimates kept separate from measurements |
| Six-node physical integration | Test independent power domains, shared-location failures, vehicle stress, maintenance and replacement above threshold | Fault-injection records, measured common-cause behavior and recovery results; no colocated quorum without an explicit compromise analysis |
| Record and reader authenticity | Define physical-read, hostile-share and compromised-host threats; evaluate authentication within the storage budget | Reviewed protocol and record layout, adversarial tests and a clear account of which host or hardware components must be trusted |
| Replacement and share refresh | Preserve repair of destroyed shares while designing responses to possibly copied shares | Coordinated update design, interruption/recovery tests and an explicit accumulated-copy model; identify when exposure of a past quorum requires changing the underlying secret |
| Model and proof review | Check source-dependence definitions, mathematical assumptions, state machines and their relationship to code | Independently reviewed arguments and, where useful, machine-checked invariants; explicit separation of abstract theorems from empirical premises |
| Release and target acceptance | Maintain tested source/wheel/sdist consistency and reproduce the host workflow on actual supported targets | Versioned validation records, target Linux ABI results, offline installation checks and reviewable release artifacts |

These work packages can progress in parallel. Adding a recovery mechanism depends on the source and leakage analysis; long-term lifecycle claims depend on physical evidence. An environment that cannot support the required uncertainty is a research result, not a reason to substitute electronic key storage for environmental derivation.

## Decisions that remain open

- The exact source of environmental secret information and its conditional unpredictability under realistic observation remain unmeasured.
- Exact input is implemented; robust noisy recovery and its helper-data design remain to be selected and reviewed.
- SRAM data loss, forensic recoverability and long-term reservoir behavior require different experiments.
- Authentication and safe distributed refresh must fit the actual hardware capacity; 64 bytes cannot be assumed sufficient for multiple record generations and transaction metadata.
- The selected Linux/Raspberry Pi reader path needs electrical integration and target execution, rather than an additional MCU firmware image.

Use [the experiment plan](EXPERIMENTS.md), [formal specification](FORMAL_SPEC.md), [hardware analysis](SRAM_ENGINEERING.md) and [engineering runbook](ENGINEERING_RUNBOOK.zh-CN.md) to turn each open question into a repeatable study. Publication of a package records the implementation and its evidence; it does not close the remaining research questions.
