# ADR-0001: Environmental observation is mandatory

- Status: Accepted for research prototype
- Date: 2026-10-22

## Context

The project evolved from physical room-state derivation into distributed volatile secret storage. A Shamir-only system would no longer be an environment-derived key. The primary research goal is not merely storing a key at a physical address, but requiring information from the current physical state itself.

## Decision

A successful EDK derivation must require both (1) normalized readings from the original physical environment and (2) a secret recovered through a quorum of live volatile shares. A future environment-only configuration may exist, but a share-only recovery path MUST NOT be called EDK. Ambiguous environment observations MUST fail closed until a valid, independently reviewed secure-sketch mechanism is added.

## Consequences

- Improves conceptual fidelity and enforces testable input dependence.
- Does not prove environmental entropy. V0.1 software uses synthetic readings, which are not evidence for physical properties.
- Makes legitimate users more vulnerable to accidental environment damage; this is an intentional research dimension and MUST be communicated as an explicit risk.
- A working physical implementation cannot be responsibly claimed before repeatability, entropy and decay measurement.
