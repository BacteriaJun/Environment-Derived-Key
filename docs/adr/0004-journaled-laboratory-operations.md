# ADR 0004: Durable enrollment intent and explicit evidence gates

Status: accepted for the 0.2.0a2 laboratory engineering revision; no production-key approval.

Update: [ADR 0005](0005-concept-release-and-exact-input-profile.md) defines the subsequent 1.0 concept release designation. The journal decisions below remain in use; the alpha release label at the time of this ADR is historical.

## Problem

Sequential six-node programming can fail after committing some nodes. A generic error does not tell an operator which writes were attempted. Automatically rerunning creates a new secret and cannot resume the old polynomial. Public-pattern matches and software test success are also too weak to stand in for physical acceptance or environmental entropy.

## Decision

Add strict versioned local wiring configuration and a new `hardware-enroll` workflow. Persist the operation plan before opening devices. Validate all adapters and all slots before generating KV. Before each device write, sync an append-only intent file and directory; sync a separate receipt only after readback succeeds. Store only metadata, including the public generation ID; never store a payload, KV, environmental reading or secret hash. Verify all six readbacks and all 20 threshold combinations in RAM before recording completion.

There is no resume or distributed rollback API. A missing receipt after an intent means uncertain. Read-only inspection compares current data but cannot create historical receipts or promote interrupted enrollment to completion. Missing, malformed, reordered or broadly accessible journal files cause rejection. Acknowledged new-chip initialization is fixed in the plan; even damaged EDK1 headers are refused. Filesystem durability and exclusive cooperative access are assumptions.

Separate report criteria from physical authenticity. Strict bench aggregation rejects duplicate preparations and mixed sources, requires backup status/duration/pattern conditions, and never sets physical acceptance to verified. Environment study protocols bind an existing manifest and declare repeatability criteria before recorded sessions; quality acceptance never authorizes real-key derivation or establishes conditional min-entropy.

## Consequences

No master recovery file is introduced, preserving the intended dependence on maintained physical and electronic state. A process crash may permanently prevent completing an enrollment; receipts improve diagnosis rather than secret availability. Local journals and operator labels are unauthenticated. Same-user modification, malicious hardware, tampering, memory copies, stolen shares, reliable physical erasure and secure refresh remain unresolved.

Legacy low-level laboratory commands remain available but are not covered by the new operation lifecycle. New source export rejects private record suffixes in public trees; the offline release verifier tests the actual exported artifact and rebuilt distributions. The release remains alpha until empirical environmental/hardware evidence and independent review justify stronger claims.
