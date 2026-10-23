# 0.2.0a0 implementation and validation scope

This local engineering preview continues the supplied alpha and stage-1 code. It is not a GitHub publication or completed real-key system. Original source ZIP and the 0.1.0a1 deliverables are retained separately.

## Implemented workstreams

| Workstream | Code/evidence delivered | Boundary |
|---|---|---|
| Environment research algorithm | Strict versioned Manifest, typed readings, exact manifest-bound encoding and comparisons | No entropy estimator, robust extractor or real PIN bridge |
| Private acquisition | Non-echo collection, owner-only files, strict record validation and abort behavior | POSIX only; no ACL/encryption/backup guarantee |
| Repeatability study | Pairwise disagreement, erasure/status/time statistics, external labels, aggregate phi summaries | No automatic cause attribution, privacy theorem or physical measurements |
| Lifecycle | Shared-location shocks, distinct node rates/stress, powered-S5 failure, maintenance/stop, conditional repair | Fully synthetic and parameterized; no attack/retention forecast |
| Volatile-component programming | MCP7940N host record writer/reader/replacement, Linux combined-I²C adapter, memory transport | Physical I/O untested; no MCU binary, authenticated reader or distributed refresh |
| Mathematics/formalization | Stated theorems and proofs, data-processing boundary, toy erasure law, threshold and write-prefix models | Conditional arguments and bounded checks, not Lean/Coq or independent whole-system proof |
| Distribution | Standard-library runtime, sdist/wheel, deterministic public-tree source ZIP and CI smoke pipelines | Remote CI unexecuted; GitHub upload still unauthorized |

## Test evidence

The suite currently contains **102 tests**: the previous 52 tests plus 50 new cases. The original 16 baseline tests remain unchanged. Coverage includes strict/duplicate-key/nonfinite JSON parsing, manifest/order/version binding, explicit ambiguous/missing inputs, private file permissions, symlinks/hardlinks/FIFOs, no overwrite, deterministic studies, aggregate field exclusion, known correlation patterns, no inferred causes, CLI pipelines, actual POSIX terminal echo disabling, source packaging exclusion/determinism, maintenance invariants, all SRAM single-bit image changes, all interrupted blank-image write prefixes, register boundary/flag behavior and Linux message ABI serialization using a mock ioctl.

The local validation record delivered beside the source package contains the actual runtime and execution results, including optimized tests, wheel/sdist construction, isolated installation and installed-command study/model/SRAM checks. It does not retain demo PIN output. Only Python 3.12 on macOS has been available for local execution. CI configures Linux Python 3.11/3.12/3.13; that is not an execution result. Linux hardware ioctl behavior has only been checked at the mocked message/ABI boundary, not on a board or kernel adapter.

The explicit finite model reports 256 gate states, 1536 node-loss transitions, 22 GF(7) privacy-coordinate sets, 6860 GF(7) reconstruction cases and 138 SRAM write prefixes. A binary toy erasure calculation gives 81/256 exact-source guessing probability, and 73/128 after a one-bit parity helper. These are exact results of the declared small models; [FORMAL_SPEC.md](FORMAL_SPEC.md) states what general arguments and physical assumptions they do and do not support.

## Material limitations before a final real engineering release

No actual environment study, backup-supply wiring, current/retention measurement, physical intrusion test, cold readout, target hardware PIN attempt or independent mathematical audit was performed. Unknown source entropy remains the principal blocker. The host writer stores shares without authentication; CRC/commit checks do not solve malicious readers or corrupted exact quorums. New research records are not production enrollment, and the application intentionally does not derive real PINs from them.

The next physical work requires the chosen reader/board, real component order codes, supply topology and bench access. Target-MCU firmware and authenticated/robust recovery must be designed against those facts. No inferred or estimated value in the hardware budget is presented as measured performance. The target remains a complete engineering package combining those results with the code and conditional proofs already delivered.
