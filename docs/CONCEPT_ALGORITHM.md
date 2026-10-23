# EDK 1.0: exact-input concept algorithm

EDK 1.0 is a concept algorithm and reference implementation for maintenance-dependent physical secret recovery. Its implemented profile is `edk.exact-input/v1`. Software tests and mathematical model arguments are available; long-term environmental and hardware validation has not been conducted.

## Inputs and composition

The reference API is:

```python
from edk.concept import ConceptContext, derive_observation_pin

pin = derive_observation_pin(manifest, observation_session, shares, context)
```

`manifest` is a validated `AnchorManifest`. `observation_session` is a validated session for that manifest, with one ordered normal reading per anchor. `shares` is a sequence of 3–6 distinct `Share` objects, coordinates 1–6, threshold 3 and one generation. `context` contains the registered public manifest fingerprint, a 32-byte public salt and a stable device identifier of at most 255 UTF-8 bytes. The context's JSON representation uses `edk.concept-context/v1` and contains only those public parameters plus the profile identifier.

The algorithm is the composition of existing operations:

```text
E = exact_observation_bytes(manifest, observation_session)
V = recover(shares, threshold=3)
P = derive_pin(E, V, salt=context.salt, device_id=context.device_id)
```

Here E is the exact environmental encoding supplied to the KDF. Encoding does not establish source entropy. V is the reconstructed 256-bit electronic secret. P is a fixed 12-digit decimal string.

The library function computes in memory; collection, private storage, physical I/O and PIN submission are separate operations. The supplied `concept-run` CLI creates its own synthetic inputs rather than loading private readings or hardware shares.

## Environmental encoding

For n ordered readings x_i, the byte representation is:

```text
ASCII("EDK-OBS/v1") || 00 || SHA256(canonical_public_manifest_json)
  || uint16_be(n) || uint16_be(x_1) || ... || uint16_be(x_n)
```

There are 1–512 anchors, each declaring an alphabet size between 2 and 65536. Values must be within their anchor's range. Manifest JSON is encoded by the repository's sorted-key, indented UTF-8 encoder, including its final newline; that exact encoding defines the fingerprint. The JSON document uses the existing `edk.anchor-manifest/v1` schema.

The fingerprint binds the manifest ID, anchor IDs, location hints, reading-rule text, state counts and order. Editing a description changes the fingerprint just as editing an alphabet does. The registered manifest is therefore retained as an exact public document. It contains reading definitions rather than secret state values. Observer code, timestamps, session ID, duration and external event labels are excluded from E.

Ambiguous and unreadable values raise `EnvironmentUnavailable`. Missing/reordered/out-of-range readings, a different context fingerprint or incompatible share metadata raise a value error. Valid but changed readings are evaluated as changed input. No stored hash or verifier identifies them as the original environment, and no approximate matching is performed.

## KDF and decimal mapping

The implementation reuses `derivation.py`: HKDF-SHA256, explicit source-length framing, public salt and a length-framed device identifier. The inherited KDF domain is `EDK-LAB/v0.1-alpha`. Each counter selects an HKDF-Expand call through counter-framed `info`, taking its first 8 bytes as a 64-bit sample. Rejection of the incomplete modulo range avoids modulo bias, and 30 repeated/cyclic digit patterns are excluded.

Software version 1.0.0 does not change that domain. The profile supplies a newly defined exact environmental encoding to the existing function. Old raw-byte inputs and this profile have separate input vectors. JSON schemas and EDK1 SRAM records likewise retain their own version fields.

The accepted decimal space has 10^12 - 30 members, approximately 39.86 bits. Input changes can collide after mapping. Requiring both sources at an API boundary establishes a protocol gate; the environmental security contribution depends on its conditional unpredictability under the attacker's side information. [FORMAL_SPEC.md](FORMAL_SPEC.md) gives the mathematical statements and assumptions.

## Reproducible execution

```sh
edk-lab concept-run --seed 2026
edk-lab concept-run --seed 2026 --output concept-result.json
```

`concept_fixture()` defines public source material for signed 64-bit integer seeds. SHA-256 over a fixed fixture domain, seed and labels produces the synthetic values, electronic secret and salt. This is a test-data convention. Shamir generation ID and coefficients still use the normal random generator; they do not affect the recovered secret or the final deterministic result.

The fixture uses six anchors with 2, 3, 8, 16, 64 and 256 states. The public seed-2026 vector is:

| Field | Value |
|---|---|
| Manifest fingerprint | `a578e937121c21248711bd42824c45f73034aabe199211c72a3b674474203af9` |
| Device context | `concept-device` |
| Synthetic output PIN | `488096914862` |

The command compares all 20 quorums and the repaired-share result, verifies public context serialization and checks rejected input cases. JSON reports record the software version, profile, mode, source, seed and boolean outcomes; they contain no PIN or secret-derived verifier. Reports are written only with explicit `--output`, to a new file.

## Research work

The environment source remains the main research question: which physical observations are repeatable under maintenance, change during abandonment, and retain unpredictability for a specified attacker? Study quality metrics measure reading behavior. Separate investigations are needed for conditional entropy, historical traces and copies, robust recovery/helper leakage, share authentication, physical power retention, generation refresh and long-term operation. These are described in [EXPERIMENTS.md](EXPERIMENTS.md) and [ROADMAP.md](ROADMAP.md).
