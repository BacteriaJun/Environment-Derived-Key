# Laboratory engineering alpha: 0.2.0a2

The revision adds operational state and evidence handling to the existing EDK project. It preserves the environment-plus-volatile-secret architecture, the valid legacy PIN vectors and the EDK1 wire format. It adds no real-PIN recovery or permanent master/environment-secret backup.

## Automated coverage

The suite contains **168 tests**, including the unchanged original 16 baseline tests. The prior Pi snapshot had 115. Added coverage includes strict topology/risk parsing, each node's partial write failure, intent failure before device mutation, committed-node receipt failure, keyboard interruption, strict journal replay/permissions, no-write inspection, all-six polynomial consistency, explicit new-chip initialization and damaged-header protection. Descriptor close/transfer races and adapter minor mismatch are covered with mocks and threads.

Environment-study tests cover manifest/time binding, minimum sample/observer/span requirements, timing/missingness/disagreement limits, source separation, anonymous output and the impossibility of granting entropy/real-derivation approval. Public bench tests cover strict report parsing, duplicate preparations, source separation, backup/status/duration criteria and absence of physical attestation. CLI tests verify successful and negative-result exits, exception redaction and missing-store noncreation. Distribution checks exercise archive paths, duplicate members, public input/code matching, metadata and private-record exclusion.

## Acceptance artifact

Run `python tools/verify_release.py --output ../new-candidate` using locally installed build prerequisites. Its `validation.json` is the execution record. Require `status: passed`, ordinary/optimized source test counts, sdist test count, rebuilt wheel correspondence and an isolated offline installation check. A failed candidate records the failed stage and must not be used as accepted output. Check `CHECKSUMS.sha256` against the actual files.

The local engineering candidate was exercised with Python 3.12.14 on macOS. CI configures Python 3.11/3.12/3.13 on Linux and the native UAPI probe, but a configured workflow is not a completed remote run. Source ZIP reproduction is checked; wheel/sdist cross-toolchain byte reproducibility is not claimed. Test assertions use synthetic values; no measured environment or physical chip data is added to this source tree.

## Evidence limits

- Host native Linux ABI compilation and Raspberry Pi I²C transactions remain unperformed locally.
- Real supply switchover, backfeed, temperature/retention, physical erasure and six-board independence remain unmeasured.
- A declared `manual` or `physical_io` source and an operator timestamp are not authenticated provenance.
- Journal durability assumes the filesystem honors `fsync`; no real computer power-cut test was performed.
- Final all-20-quorum consistency is algebraic consistency, not authentication or proof of the original secret.
- No physical conditional min-entropy bound, robust Secure Sketch/Fuzzy Extractor, authenticated reader/shares, safe refresh, independent cryptographic/proof audit or target-keypad enrollment is provided.
- No GitHub push, tag or Release publication has been performed.

See [engineering runbook](ENGINEERING_RUNBOOK.zh-CN.md), [ADR 0004](adr/0004-journaled-laboratory-operations.md) and [formal specification](FORMAL_SPEC.md). Automated acceptance improves software delivery evidence; the unresolved environmental research question remains central.
