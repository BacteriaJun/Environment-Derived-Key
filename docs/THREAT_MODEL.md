# Threat model | draft v0.1

**Not a security claim; open to peer review.**

## Assets

- Original environmental secret `X0` / recovered `KE`.
- Independent volatile random secret `KV`, split 3-of-6.
- Final 12-digit PIN (for a rate-limited keypad device profile, once verified).
- The ciphertext and the non-secret public parameter manifest.

## Adversarial access

| Adversary | Intended question | Current answer |
|---|---|---|
| Knows complete source code, manifest, salts, device identity | Does public algorithm itself leak secret? | Design as public; not a demonstrated proof |
| Sees photos of part of a room | How much conditional environment min-entropy remains? | Unknown; field experiment required |
| Gets one or two distinct Shamir shares | Can `KV` be learned from those shares alone? | Ideal Shamir says no; devices physically unsecured |
| Gets three shares | Can `KV` be recovered? | Yes, but original PIN still requires environment; if environment is guessable, risk rises |
| Gets exact original room observation and three shares | Can PIN be recovered? | Yes; this is an explicit failure of secrecy |
| Can save copies before later physical decay | Does future decay revoke copies? | NO |
| Compromises the reader/computer during derivation | Can capture shares, environment, PIN? | YES in v0.1 |
| Alters share payloads or helper data | Can force denial of service / wrong key? | YES; integrity and robust recovery unresolved |
| Controls three locations at once | Can reconstruct `KV`? | If they contain three distinct live shares, YES |
| Can test candidate PINs offline via a MAC/tag or hash | Can do better than ten attempts? | YES; online limit cannot be assumed |
| Applies forensic low-temp/side-channel methods after power loss | Is volatile state proven unrecoverable? | NO; empirical validation needed |

## Deployment note: correlated locations

The originally proposed S2 (home drawer), S3 (home wardrobe), and S5 (permanently powered home corner) all share one home failure and access domain. Under 3-of-6, a single visitor with successful readout of those three nodes may reconstruct `KV`. Geographic placement needs reassessment; **more devices does not mean more independent security domains**.

If S6 is a byte-for-byte copy of S2, it is **not** a sixth mathematically independent share. V0.1 treats each node as a distinct share index; deliberate duplicate shares are rejected.

## PIN security profiles

- **Online-limited 12-digit keypad PIN:** the lockout mechanism must be independently verified for the exact device/mode. Failure after repeated entries can destroy data. Experimental software must not auto-submit any candidate.
- **Offline ciphertext key:** a 12-digit PIN is not an acceptable stand-in for a full-length high-entropy encryption key. A future data-key design must be analyzed separately, including offline AEAD authenticity checks as verification oracles.
- Avoid publishing a `SHA256(PIN)`/`SHA256(X0)` or other known-answer verifier; such an oracle can enable offline candidate testing after partial leaks.

## Security goals vs non-goals

Goals: controlled environmental dependence; reproducible recovery in a maintained regime; failure upon missing required physical information; quantifiable lifetime experiments.

Non-goals (current version): tamper-resistant key storage; secure erasure guarantees; proof of sufficient environmental entropy; physical unclonability; protection from a privileged attacker on the reading host; identity verification by simply being plugged into power; prevention of copied shares surviving later decay.

## Stage-1 review clarification

Fail-closed behavior applies to **detected** invalid inputs. It is impossible for this unauthenticated sharing implementation to reliably distinguish a corrupted three-share quorum from another valid polynomial solely from those three points. A regression test intentionally demonstrates the wrong-output limitation. Additional consistent shares and public metadata do not constitute a cryptographic authenticity proof. Changed, well-formed environmental bytes also remain undetectable as the wrong enrollment state.

Do not bridge the low-level API to a real keypad on the strength of these checks. The CLI accepts only generated synthetic inputs for its PIN demo. On an observed demo failure it emits no PIN, including under `python -O`. There is no automatic PIN submission path.

The node representation no longer includes payload/generation bytes. This reduces accidental debugging exposure, but serialization, direct memory access, crash dumps and host compromise remain outside that protection. No real observations or shares were used in review fixtures, and no public verifier was added.

Kingston's [KP200 Quick Start Guide v1.0](https://media.kingston.com/support/downloads/IKKP200_QSG_EN.pdf) lists 8–15 digits and excludes all-repeated and all-consecutive sequences. The demo's 12-digit policy is consistent with those documented syntactic restrictions; it also rejects descending cyclic runs. This is a document comparison, **not device/firmware validation**. The full manual download was unavailable to the review browser. Lockout, Admin/User mode, PIN history and firmware-specific behavior have not been tested.

## v0.2 surfaces

Manual study records are intentionally sensitive local data. Mode checks do not defend against ACL grants, sync/backup services, same-user malware, root or recovered disks. Public manifests have free text; strict shape checks cannot prevent a person from embedding an address or credential. Aggregate reports can still leak through small samples, repeated release or auxiliary knowledge; the export floor is not a privacy proof. Do not reuse study states as actual enrolled KE.

The physical host I²C writer has no authenticated chip identity, encrypted bus or tamper barrier. CRC32 is not authentication. A malicious reader can copy shares; a malicious chip can return plausible data. Advisory adapter locks do not exclude other masters. PWRFAIL/backup flags are not voltage attestation. Partial provisioning cannot be rolled back atomically across six nodes. The CLI exposes no raw share dump or real-PIN derivation path, but privileged code can inspect memory.

The [formal source-erasure theorem](FORMAL_SPEC.md) assumes independent uniform symbols, real loss of traces and absence of historical copies. It does not show that a room satisfies those assumptions, and it bounds exact-source guessing rather than truncated PIN guessing. An innovative lifecycle model cannot waive those assumptions or increase the finite PIN space.

## Engineering operation evidence

The journaled enrollment path records metadata-only intent before each write and readback receipts afterward. Incomplete receipts cause uncertainty, not an inference that no write occurred. A local actor can forge journals and source labels; all-six consistency cannot authenticate the original polynomial. Host filesystem durability, exclusive cooperative access and physical adapter identity remain assumptions. Topology failure-domain labels do not prove independent geography or power. Quality acceptance and artifact verification provide operational evidence without resolving environmental unpredictability, hardware authentication or erasure. See [ADR 0004](adr/0004-journaled-laboratory-operations.md).
