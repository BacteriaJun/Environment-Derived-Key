# Stage-1 handoff review | 第一阶段审查与修复

Date: 2026-10-22 (Australia/Sydney). Revision: **0.1.0a1, UNRELEASED**.

This is an internal engineering review, not an independent security audit or physical validation. It continues the supplied archive's source, tests and design. The original archive is preserved and has not been uploaded, tagged or released by this work.

## Baseline and scope

Input archive: `environment-derived-key-v0.1.0-alpha.zip`, 29 files.

SHA-256: `0a3d60d6f5b45043adc884d10092b49406cf060f21fef4a649c45cbb2149644d`.

All supplied source modules, tests, public example, project/CI configuration and documentation were reviewed. The original 16 tests remain unchanged; 36 new test methods bring the total to 52. New fixtures are public RFC vectors or explicitly synthetic values. No actual physical observations, production PINs or real electronic shares were used.

## Findings and resolution

| Area | Finding / review result | Resolution or remaining limit |
|---|---|---|
| Node representation | Default dataclass representation included the full share payload | Fixed: node memory and generation excluded from repr; share repr stays redacted |
| Share configuration | Recovery accepted inappropriate thresholds and could return unrelated bytes | Fixed accidental misuse: typed threshold range and public per-share threshold metadata checked through split/read/repair; metadata remains unauthenticated |
| Share shapes | Invalid indices/types/payloads reached arithmetic or reconstructed unexpected lengths | Fixed: validate Share construction and API boundaries; enforce 32-byte payload and 16-byte generation |
| GF(256) | No algebra defect found in the reviewed valid-input multiplication/interpolation paths | Independently compare all 65536 products against polynomial long division; check all 255 nonzero inverses, fixed polynomial vectors, valid quorums and every repair coordinate |
| HKDF | Existing SHA-256 extract/expand matched the existing RFC vector | Added RFC cases 2/3, strict types/output limits and empty-output support; accepts only 32-byte Extract PRKs |
| Derivation framing | Environment length could overflow the two-byte frame; malformed types/context produced incidental errors | Fixed: bound canonical-byte input to 1..65535, enforce 32-byte KV/salt, validate UTF-8 and context byte length without echoing secret input |
| PIN distribution | No simple-modulo bias defect found in existing rejection sampling | Preserved mapping; force cutoff/pattern rejection and exhaustion in tests, including leading zeros; 30 forbidden patterns checked |
| Hardware syntax | 12-digit output fits restrictions in official KP200 Quick Start Guide | Documentary comparison only; no device/firmware/lockout testing; full manual fetch failed |
| Environment format | Count/container/AnchorDefinition types were not fully checked | Fixed typed count/ranges and raw sequence rules; descriptive legacy profile constant added. No v0.2 Manifest parser yet |
| Fail-closed demo | assert could disappear under `python -O`; PIN was printed before later checks | Fixed: explicit consistency errors and output only after demo checks; fault injection tests prove no candidate output on detected failures in normal and optimized modes |
| Simulation | NaN/Inf could silently look like total decay; fractional/bool parameters reached unrelated errors | Fixed finite nonnegative rates/time, integer trial/seed/threshold checks, and finite-operand product overflow handling |
| Persistence / verifier | No source persistence of real observations/shares or published enrollment verifier found | No new secret writer or verifier added. Test/demo data are synthetic; private-data ignore patterns expanded. Caller logging/dumps remain a risk |
| Documentation | Optional-electronic-source wording conflicted with the current mandatory two-source protocol | Clarified current architecture in Chinese/English; distinguished detectable errors from undetectable wrong inputs and explicitly deferred v0.2 tools |
| Packaging / CI | Coverage focused on default paths and editable source installation | Added malformed-input/compatibility tests, optimized-mode CI, source/wheel builds and separate-environment wheel smoke tests; modern MIT metadata and source manifest |

## Evidence and reproduction

Locally verified runtime: **Python 3.12.14**, macOS. The supplied baseline's 16 tests passed before changes. The revised 52 tests pass in normal and optimized mode. The local evidence file delivered alongside the project records exact runs, distribution checks and checksums; it contains no demo PIN output.

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python -m edk demo
python -m edk simulate-decay --trials 5000 --seed 2026
```

CI keeps Python 3.11/3.12/3.13. Only 3.12 was run locally; configured matrix coverage is not an assertion that remote CI ran. Local distribution verification uses the installed setuptools backend without network build isolation; CI additionally configures `python -m build`.

Compatibility is tested against three deliberately synthetic PIN vectors captured from the original archive. The underlying `EDK-LAB/v0.1-alpha` domain and valid-input source encoding are unchanged. A package version is distinct from a cryptographic protocol version. The source distribution and wheel are local artifacts, not a published package.

## API compatibility notes

- Existing `Share(index, generation, payload)` construction still means threshold 3. Nondefault shares constructed manually must add the correct threshold; `recover(..., threshold=t)` must match the metadata. Shape validation may raise ValueError earlier than before. There is no stable hardware serialization format.
- Non-32-byte payloads, boolean/float indices and thresholds, text/bytes masquerading as raw observation lists, nonfinite simulation inputs and oversized KDF framing are now rejected. Explicit environment counts still work for integer observation sequences.
- `derive_pin` is a lower-level byte API; a bytes object is not proof that the physical readings are valid or match enrollment. The demo always canonicalizes synthetic observations first.
- Debug output now omits node/share byte material. Dataclass field serialization, direct access, debugger locals, dumps, swaps and privileged host access are not protected by repr redaction.
- HKDF output length zero now returns empty bytes. No PIN derivation calls use this path. SPDX license metadata needs setuptools >=77 at build time; runtime remains Python standard library only.

## Unresolved security and research questions

1. **Exact-quorum corruption remains undetectable.** Three well-formed but altered shares can interpolate another secret. A new regression test intentionally records this limitation; no MAC, authenticated interface or robust secret-sharing scheme has been implemented. Configuration validation must not be represented as adversarial protection.
2. **Changed environment remains undetectable as wrong enrollment.** Missing/ambiguous observations are rejected, but other valid observations can yield another PIN. No verifier hash was added to hide this problem. The CLI has no real-data recovery or hardware submission command.
3. **No physical-entropy evidence.** The encoding space is not an entropy estimate, and HKDF cannot supply missing entropy. No room observations, observer study, entropy assessment, Secure Sketch or Fuzzy Extractor were performed.
4. **No physical death proof.** The unchanged binary independent-hazard simulation does not measure read error, erasure, historical information loss, adversarial recovery, location correlations or maintenance repair. Parameters remain synthetic.
5. **No hardware validation.** SRAM retention, cold readout, zeroization, supplies, automotive temperature safety, spare-node programming and transactional refresh remain open. No BOM price or retention guarantee is offered by this review.
6. **No deployment approval implied.** Authors/contact, repository identity/visibility and remote CI remain pending. No GitHub push, tag or Release was performed.

## References checked

- [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869), particularly SHA-256 Appendix A.1–A.3. Component known-answer tests do not prove this application's security or the entropy of physical inputs.
- [Kingston KP200 Quick Start Guide v1.0](https://media.kingston.com/support/downloads/IKKP200_QSG_EN.pdf): 8–15 digits and exclusion of all-repeated/all-consecutive patterns. This review is limited to syntactic compatibility with that guide, not device acceptance or lockout behavior.

Next implementation target is the v0.2 environment observation research layer specified in the handoff. Its private raw data, aggregate exports and statistical distinctions must be implemented and verified separately; this revision does not claim those capabilities.
