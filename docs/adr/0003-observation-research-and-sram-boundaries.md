# ADR-0003: Research observations and experimental SRAM I/O are not production recovery

- Status: Accepted for local 0.2.0a0 preview
- Update: The encoding-to-KDF separation was extended by the explicit 1.0 in-memory concept profile in [ADR 0005](0005-concept-release-and-exact-input-profile.md); collection and physical programming remain separate operations.
- Date: 2026-10-22

## Context

The project must progress toward physical engineering while preserving environmental dependence and intentional maintenance fragility. Repeatability studies need raw records, but retaining a production environmental secret would defeat that lifecycle. New anchor alphabets also require a distinct encoding and must not silently change existing PINs. A 64-byte laboratory SRAM record cannot be assumed to accommodate authenticated transactional refresh.

## Decision

Implement a strict public Manifest and private research sessions with statuses/ranges, public-definition fingerprint binding, and owner-only POSIX files. Only internally constructed anonymous aggregates may be exported by study commands. Reject mixed synthetic/manual cohorts and do not infer physical history loss from disagreement. New research encoding is versioned and refuses ambiguous/missing inputs. It is not connected to the legacy PIN KDF. No enrollment hash or production fallback backup is added.

Implement MCP7940N host programming, a Linux combined-I²C transport, CRC/commit record, readback checks and destroyed-node replacement. Restrict actual CLI I/O to explicitly selected laboratory adapters. No valid committed slot is overwritten. No whole-system PIN enrollment, chip authentication, in-place rotation, distributed atomic update or automatic retry is implied. CRC is an error-detection aid, not a cryptographic integrity decision.

Publish mathematical statements with explicit source/attacker/fault assumptions and executable bounded models. General arguments, bounded enumeration and physical experiments are different forms of evidence. Do not describe an unverified source assumption as a proved physical result.

## Consequences

Real study data can be collected without changing PIN compatibility; it remains sensitive research material. Production deployment will need a separate ephemeral observation/reconstruction flow that does not reuse these files as KE backups. Raw file permissions do not cover ACLs, administrators, backups or same-user malware.

The SRAM program is useful for bench measurements but not security-grade storage. A power event can race flag handling; partial multi-node setup leaves a subset with no atomic recovery. A larger SRAM or different integrity design may be required. Target-MCU firmware and electrical integration remain future work after selecting a board/reader.

The software preview can be packaged and locally installed now. It does not authorize GitHub push, tags, Release publication or real PIN use, and does not establish the final engineering release's security claims.
