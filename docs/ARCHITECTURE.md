# EDK 1.0 | Concept and reference architecture

The current release is a concept algorithm with a reference implementation. Software validation is available; long-term engineering validation has not been performed. The `edk.exact-input/v1` profile composes manifest-bound exact observation encoding, 3-of-6 recovery and the existing KDF/PIN mapping through `concept.py`. [CONCEPT_ALGORITHM.md](CONCEPT_ALGORITHM.md) defines that path. The following sections describe the inherited components and their development history.

## 1. Non-negotiable design constraints

1. **Environment input is indispensable.** A test must show that the electronic shares alone cannot reproduce the original PIN; merely storing devices in a room does not qualify.
2. **Maintenance determines recoverability**, not ownership. Charging somebody else's nodes also preserves those nodes; the protocol does not assert that it recognizes the legal owner.
3. **No secret from structure alone.** A 64-state cell is not automatically 6 bits of unpredictability; distributions and adversarial observations matter.
4. **Fail closed on detected errors.** Missing/ambiguous environmental readings, insufficient same-generation shares, or detected format/configuration errors must stop a recovery operation. This does not mean unauthenticated, well-formed wrong inputs can be detected. There is no real-device recovery or I/O adapter in this revision.
5. **Never use an actual protected device in the research harness.** Proof of concept outputs are ephemeral simulated PINs only.

## 2. Reference data flow

**Enrollment (simulator):**

1. Select a public ordered list of environment anchor definitions (location and reproducible measurement rule). No secret observations in public manifest.
2. Read physical states `X0` using a fixed explicit rule; v0.1 expects exactly 40 values 0…63. Canonicalize to exactly 40 bytes. This does **not** prove an entropy lower bound.
3. Generate independent 32-byte random `KV` from a trusted CSPRNG. Use Shamir 3-of-6 to create six shares; provision volatile stores only in future hardware implementation.
4. Generate a **public**, stable 32-byte enrollment salt and public stable device ID. Record a versioned public manifest and those parameters. **Do not persist a PIN, full environment sample, or a verifying PIN hash**.
5. Derive PIN as a function of both the raw environmental observation and `KV`.

**Recovery (simulator):**

1. Independently reobserve all environment anchor states (`Xt`); v0.1 rejects missing or ambiguous states and offers NO fuzzy correction.
2. Read three same-generation distinct live nodes; reconstruct `KV` using Shamir interpolation.
3. Compute `PIN = Map12(HKDF-SHA256(domain, public-salt, length-framed(Xt || KV), device-id))`.
4. If actual observations equal enrollment observations, derived PINs match. If environment has drifted, the output generally changes. **The research CLI cannot detect whether a well-formed but changed input is correct.**

**Planned later:** secure sketch / fuzzy extractor for noisy observations, robust helper-data integrity, trusted hardware reader, authenticated shares, secure read/repair, retention characterization.

## 3. Scope of the current mathematical claim

Given a valid 3-of-6 Shamir sharing of uniformly random 256-bit `KV`, any fewer than three distinct valid shares disclose no information about `KV`, *under the ideal finite-field scheme's assumptions*. The Python code is an educational illustration, not a hardened implementation.

The simulator uses **exact** physical readings. It does not claim security from `X0` or `Xt`: that requires measured conditional min-entropy and a realistic attacker knowledge model. An attacker with all shares and a low-entropy, guessable environment may successfully enumerate candidate PINs if a verification oracle exists. A 12-digit numeric PIN has no more than log2(10^12) ≈ 39.86 bits of output entropy.

## 4. Environmental lifecycle

`X0 (enrollment) → physical evolution Xt → optional maintenance restore to X0 → eventual insufficient historical information`.

The desired loss is best described by decreasing information about initial state, e.g. conditional mutual information `I(X0; Xt | W, E)`, where `W` is public error-correction helper data and `E` summarizes adversarial knowledge. This quantity does not necessarily decrease in every physical realization. Physical entropy growth by itself is not the proper security metric.

The distinction between **ECC guarantee failure** and **information-theoretic loss** is essential. RS(40,32) was an early theoretical profile, **not implemented here**: arbitrary room states are not automatically RS codewords. For a free environment input a secure-sketch construction such as a syndrome sketch would need to be designed and tested, with publicly released helper-data leakage budgeted.

## 5. Volatile lifecycle and repair

For nodes `S1 … S6`, any three intact shares may reconstruct the same `KV`; at most three independent shares may be destroyed before recovery becomes impossible. Recreating a **destroyed** `Si` from three remaining shares at the original share coordinate does not rotate `KV`.

A **stolen or potentially copied** `Si` must not be treated as destroyed. It needs an authenticated, coordinated share-refresh or a change of underlying key, after a separate compromise assessment. Proactive refresh of shares is **NOT implemented** in v0.1. Naively refreshing only a subset creates incompatible generations and may destroy recovery.

Only one permanently powered node (e.g. S5) is allowed as an availability anchor; it is not a recovery quorum by itself and does not confer immortality to the master secret.

## 6. Public and secret state

| Field | Status | v0.1 persistent? |
|---|---|---|
| Algorithm and version | Public | In source repository |
| Anchor names, measurement rules and canonical order | Potentially public (privacy review needed) | Public manifest example only |
| Enrollment salt and public device ID | Public | MUST remain stable for recovery; demo uses memory only |
| `X0` actual readings | Secret / attacker-dependent | NO |
| `KV` and Shamir share payloads | Secret | NO (demo only in RAM) |
| Generated PIN and PIN verifier | Secret | NO |
| Node health and generation ID | Generally non-secret; may leak operational info | Simulated in memory |

## 7. Open engineering questions

- Can the physical environment provide enough **conditional** min-entropy against a realistic observer, and how do we estimate it?
- Can a human re-read it quickly and without ambiguous boundary decisions in an irregular room?
- Can natural unattended changes actually cause *loss of information* rather than mere reversible movement?
- Which secure-sketch parameters minimize offline attacks through public helper data?
- What is an acceptable usable failure rate, physical loss curve, and end-of-life condition?
- How can a replacement node be written in a genuinely secure reader with no persistent secret copy?

## 8. Stage-1 software contracts and compatibility

Package version `0.1.0a1` is an unreleased review revision. The derivation domain remains `EDK-LAB/v0.1-alpha`; the length framing, HKDF source order, context bytes, counter and PIN mapping are unchanged. Three synthetic legacy PIN vectors lock this compatibility. Do not change the domain merely to match a package version.

The legacy environment profile is named `EDK-LAB/manual-40x64/v1` in `environment.py`. `canonicalize` defaults to 40 readings, supports explicit counts 1..65535 and encodes one 0..63 integer per byte. It rejects text/byte containers as raw observation lists, booleans, nonintegers and missing values. This identifier is a descriptive constant, not a new serialized Manifest or an entropy claim. `derive_pin` remains a lower-level byte API: it checks bytes/type/length framing, not physical provenance, enrollment identity or a Manifest schema. Callers must normalize observations first.

`Share(index, generation, payload)` remains valid for the default 3-of-6 profile. A new public `threshold=3` field travels through split, node read/write and repair. Nondefault splits must be recovered with the same explicitly supplied threshold. Malformed metadata, incompatible thresholds and invalid coordinates are rejected before interpolation. No wire format or authenticated metadata has been introduced. Legacy custom-threshold shares created manually must specify their threshold when constructed.

The HKDF helper accepts only 32-byte SHA-256 PRKs produced by Extract; this is narrower than RFC 5869's general PRK contract. Zero-length output is now supported; lengths beyond 8160 are rejected. The KDF does not create environmental entropy.

The PIN map rejects 30 fixed 12-digit strings (10 constant digits, 10 cyclic ascending and 10 cyclic descending sequences). A uniform 64-bit candidate below the largest multiple of `10^12` maps evenly to decimal strings; subsequent pattern rejection leaves a uniform accepted set under the pseudorandom-output model. No statistical histogram is treated as a proof. Exhaustion after 10000 candidates raises an error.

See [ADR-0002](adr/0002-review-boundaries-and-compatibility.md) and [review evidence](REVIEW_STAGE1.md). No added stored verifier, permanent secret backup, alternate recovery path or new cryptographic primitive is part of this revision.

## 9. v0.2 research/host architecture

The `0.2.0a0` revision introduced the following components; section 8 records the historical stage-1 compatibility decision, which remains in force for the legacy PIN demo:

- `manifest.py`, `observations.py`, `jsonio.py`: strict public schema, ordered anchors with variable state counts, explicit statuses and versioned research encoding.
- `private_store.py`: owner-only POSIX records; `analysis.py`: aggregate-only repeatability export without observations or identifiers.
- `lifecycle.py`: synthetic trajectories with common-location shocks, per-node stress, maintenance cutoff, quorum-bounded repair and separately tracked errors/erasures/history loss.
- `sram.py`, `linux_i2c.py`: 64-byte experimental record and host I²C writer, readback, and destroyed-node replacement; no authenticated secret interface or measured retention.
- `formal_models.py`: bounded checks connected to [conditional mathematical statements](FORMAL_SPEC.md).

Observation storage keeps research records separate from key enrollment. In the 0.2 revision the encoding and KDF were separate, as recorded in [ADR-0003](adr/0003-observation-research-and-sram-boundaries.md). Version 1.0 adds an explicit in-memory composition in `concept.py`; collection and SRAM commands remain separate. The SRAM writer provisions electronic shares rather than registering an environment or producing PINs. Research records do not become a permanent recovery route.

## 10. Selected Linux/Pi bench path

`0.2.0a1` selects a Linux host reader. `bench.py` separates public `EDKT` experiments from `EDK1` share programming, keeps PWRFAIL evidence during pattern checks, labels operator durations and emits no actual SRAM contents or PINs. `native_abi.py` compares the ctypes interface to a compiled Linux UAPI probe without device access. Metadata checks do not open adapters or attest electrical conditions. No MCU firmware is needed for this selected host path; real target and physical acceptance are still pending. See [bench validation](VALIDATION_PI.md).

`0.2.0a2` adds `deployment.py` and `operations.py` for a strict local six-slot topology and durable enrollment receipts. The initial plan is synced before adapter access, every node write has a synced intent, and interrupted intent without receipt remains uncertain. Read-only inspection cannot revise historical completion. No KV, share payload or secret hash is persisted. Transport locking protects each transaction and descriptor lifecycle, while whole enrollment still requires one cooperative writer and trustworthy hardware/filesystem behavior. See [engineering runbook](ENGINEERING_RUNBOOK.zh-CN.md) and [ADR 0004](adr/0004-journaled-laboratory-operations.md).

`study_protocol.py` binds declared repeatability/timing criteria to a public manifest and assesses private observations without granting entropy or real-derivation approval. `bench_acceptance.py` strictly validates public experiment reports and aggregates explicit criteria without attesting physical provenance. `tools/verify_release.py` tests the actual exported source, rebuilt distributions and isolated installation. None replaces empirical environmental security work.

The 1.0 concept interface binds a `ConceptContext` to the registered public manifest and evaluates exact normal observations. It performs no physical I/O. `concept-run` exercises it with synthetic inputs, comparing 20 quorums and repaired shares. The installed-wheel verifier checks this execution report in addition to source tests. Legacy raw-byte vectors, the KDF domain and SRAM schemas remain unchanged; profile inputs have their own vectors. See [ADR 0005](adr/0005-concept-release-and-exact-input-profile.md).
