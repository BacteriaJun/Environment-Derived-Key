# Linux/Raspberry Pi bench revision: 0.2.0a1

Selected reader path: **Linux/Raspberry Pi host I²C**, as confirmed by the project owner. This updates the development target; MCU firmware is not a prerequisite for this path. No physical board or remote host connection has been provided or accessed.

## Delivered changes

- Metadata-only `bench-doctor` with no adapter opens, ioctls, address scan or register traffic. Optional fixed-source C compilation compares Linux headers against ctypes message layouts without device access.
- Separate `EDKT` public test records, reconstructible from a public token, with prepare/readback and read-only-with-respect-to-data check operations. `EDK1` share headers are refused, even with damaged checksums or initialization options.
- Checks preserve PWRFAIL rather than invoking the stricter share-recovery gate or clearing events. Pattern mismatches/status changes are saved as observations and return status 3; they are not called erasure proofs.
- Linux major-89 device validation, closed-adapter checks and constructor cleanup/capability tests.
- Chinese Raspberry Pi wiring/voltage/isolation/permissions/ABI/measurement runbook. Read-only host checks do not attest the selected chip or supply.

## Evidence

**115 tests**: the prior 102 plus 13 bench/transport/ABI cases. The original 16 baseline tests remain unchanged. New tests include all 68 interrupted public-pattern prefixes, public token strict parsing, no share overwrite, wrong-token nonmatch, retained flags, status changes, no backup/NaN duration rejection, mocked constructor/capability/major/cleanup handling, actual CLI prepare/check/status-3 flows on a synthetic adapter, and absence of device opens in host diagnostics. Normal and optimized Python tests, build/install and installed-command smoke results are in the accompanying validation JSON.

Actual local execution is still Python 3.12.14 on macOS. Native Linux compilation is **unavailable locally**, not a passed check; CI now requires it on Linux when the workflow runs. No native 32-bit/64-bit Raspberry Pi result, I²C transfer, electrical measurement, retention duration, physical erasure or real PIN trial has been performed. Synthetic/mock records must not be presented as physical results.

The cryptographic KDF domain, legacy PIN vectors, EDK share wire format and formal theorem assumptions are unchanged. Public bench patterns are not secrets and are never PIN enrollment. A bench token is an expected image plan, not proof of successful preparation. A report's `physical_io` label names the calling workflow, not an authenticated hardware provenance claim.

Use [树莓派台架指南](RASPBERRY_PI_BENCH.zh-CN.md) for the first target run. Actual host diagnostics and component/board identification are the next evidence needed before choosing the exact electrical integration and interpreting measurements. GitHub push, tags and Release publication remain unperformed.
