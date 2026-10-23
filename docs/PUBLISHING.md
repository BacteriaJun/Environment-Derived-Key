# Publishing EDK 1.0.0

Version **1.0.0** is the concept and algorithm release of Environment-Derived Key. The package contains the dual-source derivation example, observation research tools, conditional mathematical arguments, lifecycle simulation, Linux MCP7940N programming and journaled engineering workflows. Long-duration environmental and hardware engineering validation remains outstanding. The release description should state both the implemented scope and this validation status directly.

The candidate is prepared locally. GitHub upload, tags and Release publication remain separate actions requiring the project owner's explicit authorization. This document does not perform or authorize those actions.

## Repository presentation

Suggested repository name: **environment-derived-key**

Suggested description:

> Concept and algorithm implementation for maintenance-dependent environment-derived keys, with observation research tools and Linux SRAM programming.

Suggested topics: `cryptography`, `security-research`, `secret-sharing`, `embedded-systems`, `sram`, `hardware-security`, `physical-entropy`.

Describe Secure Sketch/Fuzzy Extractor, authenticated hardware and long-term environmental behavior as remaining work. The release contains mathematical arguments under specified assumptions and finite-model checks; physical entropy, secure erasure and the complete real system have not been proven. Claims of novelty, patentability or external review require their own evidence.

## Prepare and verify the candidate

- [ ] Set the project metadata, package version, release notes and current documentation to `1.0.0`. Preserve earlier validation records as historical results.
- [ ] Run the public-source acceptance tool in a new output directory:

  ```sh
  python tools/verify_release.py --output ../edk-1.0.0-candidate
  ```

- [ ] Review `validation.json`: require `status: passed` and inspect the recorded source tests, optimized tests, distribution rebuild and isolated installation results. Check `CHECKSUMS.sha256` against the actual candidate files.
- [ ] Record the platforms actually tested. The configured Linux CI matrix covers Python 3.11, 3.12 and 3.13; attach remote results only after those jobs execute. Native ABI, I²C, electrical and long-term tests retain their own status.
- [ ] Review the exported source, documentation and examples for real observations, shares, PINs, credentials, identifying serial numbers and physical-access details. Review the actual staged file list and diff before committing.
- [ ] Keep raw studies, local topology, operation journals, credentials and build working directories outside the public snapshot. Filename exclusions cannot detect a secret pasted into an allowed file.
- [ ] Confirm MIT licensing, contributor attribution and the intended security-reporting channel.
- [ ] Present the reviewed candidate, artifact hashes and release text to the owner for publication authorization.

The verifier produces software-delivery evidence. Hardware measurements, entropy studies and independent review are separate results and should be linked when available.

## Import into the existing repository

Use the verified public source ZIP as the import snapshot. Extract it into a clean review directory and compare it with the existing repository before applying changes. Preserve repository history. An input archive without `.git` does not establish that no remote repository exists.

Stage the reviewed public changes explicitly rather than the entire research workspace. Keep the acceptance record and artifact hashes associated with the exact candidate that was reviewed. A later code or packaging change requires fresh acceptance for the changed candidate.

## Release text

The following describes the intended 1.0.0 scope; update links and execution evidence to match the accepted candidate:

> EDK 1.0.0 publishes the project's concept, algorithms and research engineering tools. Recovery is designed to require both physical environmental information and a 3-of-6 volatile electronic secret. The implementation includes observation studies, synthetic lifecycle models, conditional mathematical arguments, Linux SRAM programming and journaled enrollment. Long-duration environmental and hardware engineering validation has not been completed. The accompanying validation record lists the automated software checks actually run.

Attach the accepted source package, wheel/source distribution, validation record and checksums when publication is authorized. Use the approved repository and tag `v1.0.0`; keep version numbering separate from claims about physical or cryptographic validation. No GitHub upload, tag or Release is performed by preparing these local artifacts.
