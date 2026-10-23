# 1.0.0 — concept algorithm and reference implementation

Defines 1.0 as the concept algorithm/reference-tool release. Software tests, finite models and artifact verification are available; long-term engineering validation has not been performed. Chinese and English README files describe the algorithm, implementation, current evidence and research work directly.

Adds `edk.exact-input/v1`: a typed `ConceptContext` and `derive_observation_pin` compose the existing manifest-bound encoder, 3-of-6 recovery and HKDF/PIN mapping. Context and observations must match the registered manifest; ambiguous/missing inputs and invalid quorums are rejected. The synthetic `concept-run` command verifies all 20 quorums, repair and invalid-input handling, and emits a public JSON check report. Adds a fixed synthetic vector and regression tests. Observation metadata does not enter derivation.

The inherited raw-byte API/KDF domain, valid legacy vectors, JSON v1 schemas and EDK1 wire bytes are retained. The new profile encodes different environmental bytes, so it has separate vectors. Installed-wheel verification now checks concept execution and verifies README content in distribution metadata. The package includes both README languages. Local versioning and package construction do not publish a GitHub Release.

# 0.2.0a2 — journaled laboratory engineering alpha (historical local revision)

Adds strict six-slot local wiring configuration, an owner-only append-only enrollment journal, intent-before-write and readback receipts, all-20-quorum final verification, offline status and read-only current inspection. Partial failures remain uncertain; no automatic resume, rollback or secret recovery file is added. New `hardware-enroll` is the preferred initial provisioning workflow; legacy low-level provisioning/repair remain experimental and lack these receipts. Damaged EDK1 headers now refuse overwrite even with explicit initialization, a deliberate stricter behavior.

Adds manifest-bound environment-study quality policies and anonymous assessment, plus strict public bench-report aggregation with distinct trial nonces, supply status and declared duration criteria. Passing criteria never authenticates physical evidence, establishes environmental entropy, or approves real-key derivation. Adds `bench-doctor --require-ready`, transport descriptor/transaction synchronization and path-to-minor validation.

Adds an offline source-to-distribution acceptance tool: deterministic public export, normal/optimized tests, wheel/sdist source and metadata checks, sdist rebuild and isolated wheel installation. Private record suffixes in public inputs fail packaging. No GitHub publication, native target ABI/electrical measurement, robust environmental extraction, share authentication or safe refresh is claimed. Cryptographic domains, valid legacy PIN vectors and EDK1 bytes are unchanged. See [engineering runbook](docs/ENGINEERING_RUNBOOK.zh-CN.md), [validation](docs/VALIDATION_ENGINEERING.md) and ADR 0004.

# 0.2.0a1 — Linux/Raspberry Pi laboratory bench revision (UNRELEASED historical snapshot)

Selects the Linux host-reader path. Adds metadata-only host checks, compiled Linux UAPI/ctypes layout comparison, a separate PUBLIC test-image domain, single-node pattern prepare/check commands, and a synthetic retention/loss demo. Public tests refuse EDK share records, do not dump actual SRAM data, and do not clear recorded power-failure flags. Operator timing is explicitly labeled rather than inferred.

Adds 13 tests (115 total), including constructor capabilities/major-number/cleanup checks, write interruptions, read-only flag preservation, nonmatching public tokens and prevention of share overwrite. Linux CI adds the native ABI probe. Local execution remains macOS/Python 3.12, with no physical Raspberry Pi/I²C or native Linux compile result claimed. Legacy PIN inputs, cryptographic domain and share wire format are unchanged. Previous preview archives remain available.

# 0.2.0a0 — observation and hardware-host engineering preview (UNRELEASED historical snapshot)

Adds strict versioned public anchor definitions with variable alphabets, non-echo manual collection, protected POSIX research storage, repeated-read/timing/correlated-disagreement statistics and anonymous aggregate export. Adds deterministic synthetic studies and lifecycle trajectories with location shocks, stress, maintenance cutoff, quorum-bounded repair and distinct history/erasure/read-error variables.

Adds experimental MCP7940N record programming/readback/replacement, a Linux i2c-dev transport, an in-memory bus, interruption/checksum regressions, conditional mathematical arguments and exhaustive finite models. Deployment, observation, engineering/BOM and proof documents are included, along with a deterministic public-tree source packager. Original PIN vectors and the 52 stage-1 tests are retained.

No measured entropy or physical retention, robust Secure Sketch/Fuzzy Extractor, authenticated hardware, target-MCU firmware image, distributed atomic refresh, real PIN enrollment/recovery, full machine-checked security proof or independent audit is claimed. Research raw records must not be reused as production environment-secret backups. No GitHub push/tag/Release performed.

# 0.1.0a1 — stage-1 review revision (UNRELEASED historical snapshot)

Continues the provided alpha codebase without changing its dual-source architecture or valid-input PIN derivation bytes. Adds strict input/finite-parameter validation, public share-threshold configuration checks, node debug redaction, explicit demo checks before any PIN output (including optimized Python), and 36 regression tests. The original 16 tests are unchanged. Includes ADR-0002 and an evidence/limitations report.

Compatibility changes: malformed shares now fail at construction; only 32-byte share payloads are supported; nondefault shares must carry their real threshold; raw observation lists cannot be text/bytes; invalid parameters consistently raise documented value errors. No authenticated shares, enrollment oracle, new KDF domain or real-device recovery path is added. Package version changes; existing valid-input PINs do not.

Packaging uses SPDX MIT metadata with an explicit license file and setuptools >=77 as a build-only requirement. There are still no third-party runtime dependencies. Source distributions explicitly include research documentation, public synthetic examples, tests and CI configuration.

This is the first-stage handoff implementation, not v0.2 observation tooling. No GitHub push, tag or Release has been performed.

# v0.1.0-alpha — provided initial research snapshot

This alpha introduces a **non-production simulation** of the Environment-Derived Key (EDK) concept: a final PIN depends on both environmental observations and a recovered volatile secret. The repository includes 3-of-6 Shamir sharing, failed-share replacement, HKDF-based derivation, a synthetic decay model, tests, hardware exploration notes, and an explicit threat model.

**Not included:** real physical entropy measurements; secure sketch; SRAM wiring/firmware; physical intrusion protection; validated retention/erase; production deployment and security audit.

The deliberately fragile maintenance-dependent lifecycle is a *research hypothesis* to be tested, not yet a demonstrated product capability.
