# ADR-0002: Preserve derivation bytes; validate configuration without claiming authenticity

- Status: Accepted for the unreleased stage-1 review revision
- Date: 2026-10-22

## Context

Review found debug exposure of node payloads, malformed inputs reaching low-level arithmetic, nonfinite simulation parameters silently resembling decay, and caller-controlled reconstruction thresholds that could return unrelated bytes. The demo used an assert removed by optimized Python and printed a PIN before subsequent checks finished. The project must retain environmental dependence and must not create an offline enrollment verifier or a permanent recovery channel.

## Decision

Keep GF(256), uniformly random coefficients, HKDF-SHA256, source ordering, 16-bit source length framing, UTF-8 device context, the existing domain, counter schedule and decimal rejection mapping. The package revision changes to `0.1.0a1`; the cryptographic domain does not. Synthetic baseline vectors test compatibility.

Require typed, correctly sized 32-byte share payloads and 16-byte generation IDs. Carry a public threshold field (default 3) through sharing, nodes and repair, and require recovery configuration to match it. Reject malformed coordinates, booleans masquerading as integers, invalid lengths and nonfinite simulation parameters. Threshold/generation metadata are unauthenticated and are not a security boundary against an attacker who can rewrite inputs.

Redact node and share debug representations. Complete all synthetic demo consistency checks before printing its synthetic PIN, using explicit errors rather than assert. Keep the CLI restricted to the existing synthetic demo and simulation; do not add real-device submission, enrollment verification hashes, or a real recovery adapter.

## Consequences

Default-profile three-argument Share construction and valid-input derivations remain compatible. Custom-threshold manual construction needs explicit metadata; nondefault recovery still requires its matching threshold argument. Previously accepted malformed/raw-container inputs may now fail sooner with ValueError (EnvironmentUnavailable for observation errors). Python dataclass serialization may include the new field, so it is not a stable wire protocol.

No new cryptographic primitive is introduced. These checks cannot detect every well-formed changed environment or a corrupted exact-sized quorum. Authenticated sharing, robust extraction and enrollment correctness require separate protocol design and review. Redaction does not prevent direct serialization, process inspection or copies in Python memory.

The [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869) vectors verify component behavior, not the security of this two-source application. The [KP200 Quick Start Guide](https://media.kingston.com/support/downloads/IKKP200_QSG_EN.pdf) supports only a syntactic PIN-policy comparison; hardware behavior remains untested.
