# Security and validation status

EDK 1.0.0 is a concept and algorithm release for maintenance-dependent environment-derived keys. It includes executable algorithms, research tools, Linux SRAM programming and engineering workflows. Long-duration environmental studies, physical hardware validation and an independent security audit have not been completed. The version number identifies the software release; validation results are recorded separately in [the validation report](docs/VALIDATION_V1.md).

## Implemented behavior and software validation

- The exact-input reference API composes manifest-bound environmental encoding, a 3-of-6 volatile secret, HKDF-SHA256 and rejection sampling for a 12-digit PIN. The `concept-run` command exercises that profile with synthetic input and emits check results. The only command that displays a PIN is the synthetic legacy `demo`; collection and hardware commands remain separate from calculation and automatic keypad submission.
- Input schemas reject malformed observations, missing or ambiguous readings, duplicate share indices, mixed generations and incompatible thresholds. Extra supplied shares are checked for polynomial consistency. Synthetic tests exercise the field arithmetic, RFC test vectors, legacy outputs and failure paths.
- SRAM writes use invalidation, body readback, a commit tag and final readback. Journaled enrollment persists a write intent before each node write and records readback receipts. Tests cover interrupted writes, partial provisioning, intent and receipt failures, and read-only inspection.
- Public-source packaging, wheel and source-distribution checks, clean installation and ordinary/optimized test execution have automated acceptance tooling. These checks validate software artifacts. The execution record states the platform and checks actually run; CI configuration alone is not a completed CI run.

## Model assumptions

The [formal specification](docs/FORMAL_SPEC.md) gives conditional mathematical arguments and executable finite-model checks. Shamir confidentiality assumes correctly sampled independent coefficients and fewer than the threshold number of shares. Environmental security depends on the conditional unpredictability of the physical observations given the attacker's knowledge. The number of representable physical states does not establish their entropy.

The environmental erasure model assumes the stated source distribution, loss process, helper-data leakage and attacker information. A previous copy of the original environment or shares remains usable after later physical decay. Decoder failure and synthetic recovery rates do not establish physical information loss. Thermodynamic entropy and conditional information entropy describe different quantities.

The SRAM commit model assumes one writer, ordered writes and the specified interruption behavior. Journal durability assumes the filesystem and storage honor `fsync`. Neither model covers arbitrary physical faults, hostile devices or forged local records. The arguments have not received a complete machine-checked proof or independent review of the physical system.

## Remaining engineering work and concrete risks

- **Environmental recovery:** real-source conditional min-entropy, repeatability and long-term maintenance behavior remain unmeasured. Secure Sketch/Fuzzy Extractor recovery is not implemented. A valid but changed observation can produce a different PIN.
- **Share integrity:** generation, threshold, CRC32 and commit tags are unauthenticated. A correctly formatted corrupted threshold-sized quorum can reconstruct a different secret. Extra-share checks and all-20-quorum agreement establish algebraic consistency, not identity or authenticity.
- **Physical nodes:** Raspberry Pi I²C transfers, supply switching, backfeed, temperature behavior, retention, forensic recovery and six-node physical independence require measurements. MCP7940N SRAM is physically readable; it is not a secure element. Logical expiration does not establish secure erasure.
- **Power events:** share operations stop when backup is disabled or a power-failure flag is recorded. The public-pattern bench preserves recorded flags. Enabling backup writes RTCWKDAY, which clears the flag and can race a new event; flag checks alone do not prove the power history.
- **Initialization:** an `EDK1` header is protected from overwrite even if the record checksum is damaged. If the header itself is corrupted, software cannot reliably distinguish an old secret-bearing record from unused SRAM. Explicit unknown-record initialization therefore depends on the operator confirming that the hardware is new or expendable; it is not a recovery action.
- **Node lifecycle:** provisioning is not atomic across devices. A missing receipt leaves the slot uncertain, including when the write actually committed. The software has no automatic enrollment resume or rollback. Safe authenticated refresh and revocation after theft or copying remain unimplemented; replacing a destroyed share does not revoke another copy.
- **Host memory:** Python arithmetic is variable-time, and KV/share payloads temporarily exist in ordinary process memory. Reliable zeroization is not implemented. Debuggers, memory dumps, tracebacks with locals, direct field access and caller-added logging can expose them despite redacted object representations.
- **PIN guessing:** twelve decimal digits carry at most about 39.86 bits. A PIN used as the sole key for offline-decryptable data limits the search to that space. Public hashes, authenticated ciphertext or other correctness checks can become offline guessing verifiers. Device-enforced online attempt limits do not automatically apply to that attack model.

These unresolved items define the work needed to validate use with real secrets and security hardware. Current PIN exercises use synthetic data.

## Local data and public artifacts

Raw observation studies use owner-only local storage: directory mode 0700, file mode 0600, final-component symlink and hard-link checks, and no overwrites. These records are research measurements, not a permanent environment-secret backup mechanism. Filesystem permissions do not provide encryption or protect against the same user, administrators, ACL changes, sync services or backups.

Enrollment journals contain grouping and operation metadata, not KV, share payloads or secret hashes. They are local, unauthenticated receipts. Topology labels and timing can reveal deployment relationships and belong outside public source packages. Inspection reports current consistency without adding historical success receipts or changing device data/control registers.

Aggregate exports exclude raw states and individual identifiers. They do not provide differential privacy; repeated releases may reveal information through comparison. Investigator event labels and `manual`/`physical_io` labels are declarations, not authenticated evidence. Synthetic records and measurements are analyzed separately. Public `EDKT` bench patterns contain no secrets and are reconstructible from their public token.

The packager excludes private record formats and working files. Allowed source and documentation still need content review because manually pasted secrets cannot be detected by filename rules. Public material should contain synthetic examples and redacted evidence, with real observations, credentials, access coordinates, shares and PINs kept local.

## Reporting a security issue

If the repository enables GitHub **Report a vulnerability**, use that private channel for sensitive findings. A maintainer email has not been designated. If no private channel is available, open a sanitized issue requesting a contact method; include the affected version and component without exploit details that expose a deployment.

A useful report contains reproduction steps using synthetic inputs, expected and observed behavior, and the relevant platform. Redact real secrets, personal locations, precise physical-access details and identifying photographs. Non-sensitive design questions can be discussed in public issues.
