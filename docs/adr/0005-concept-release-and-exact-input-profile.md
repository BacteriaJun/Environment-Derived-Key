# ADR 0005: 1.0 concept release and exact-input reference profile

Status: accepted for the 1.0.0 concept algorithm and reference implementation.

## Decision

The project owner selected 1.0 for the concept algorithm release. This version identifies the software/concept scope; long-term engineering validation is recorded separately. README documents describe the implemented algorithm, software evidence and remaining physical research directly.

Add `edk.exact-input/v1` as the explicit composition of the existing manifest-bound observation encoder, Shamir recovery and inherited HKDF/PIN mapping. `ConceptContext` records public manifest binding, salt and device context. Exact normal readings are required; approximate or missing input is rejected. The wrapper performs no I/O and stores no secret verifier.

Keep the existing KDF domain, raw-byte API vectors, JSON v1 schemas and SRAM wire formats. Raw-byte inputs and the new profile are different representations and have separate fixed vectors. Changes to manifest text or ordering affect the new profile. Observation identity/timing metadata do not.

`concept-run` uses public synthetic inputs to execute all threshold combinations, repair and rejection cases, producing public check results. Source and installed-wheel execution are both part of distribution verification. The seeded fixture is a test convention; it is separate from the random KV generation used for hardware initialization.

## Consequences

The environmental observation layer now has one documented, typed path through the concept calculation. It still uses exact encoding rather than entropy extraction or fuzzy reconstruction. Current mathematical assumptions, source uncertainty, share authentication and physical validation status are unchanged. Later physical findings can be reported independently of the software version.
