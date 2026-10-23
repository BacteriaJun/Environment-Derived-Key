# EDK: formal model, conditional theorems and limits

Version: 1.0 concept algorithm and reference implementation. This document gives mathematical arguments with explicit assumptions and executable finite-model checks. Lean/Coq verification, external review and empirical validation of the physical source remain separate work. Each statement identifies its scope.

## 1. Objects and the meaning of environmental dependence

Let X0 be enrollment environment state, Xt the present physical evidence, C public protocol context, W any future public reconstruction helper, and A the adversary's side information. KV is an independent, uniformly generated 256-bit volatile secret. The intended future environment reconstruction is KE = Rec(Xt, W). The current `edk.exact-input/v1` profile uses exact manifest-bound environmental encoding E; the legacy raw-byte demo also uses exact input. Neither implements Rec for noisy observations. The synthetic command's public deterministic KV fixture is a test convention; the ideal uniform-KV assumption concerns the scheme and normal random enrollment, not that fixture.

The composition is schematically K = KDF(KE, KV, C), PIN = Map12(K). This notation does not establish a new two-source extractor theorem. The current implementation uses the inherited HKDF construction; no claim of security for arbitrary correlated or adversarially chosen sources follows from concatenation.

Define guessing probability for a discrete secret Z and side information Y:

```text
Pguess(Z | Y) = Σ_y Pr[Y=y] max_z Pr[Z=z | Y=y]
H̃∞(Z | Y) = -log2(Pguess(Z | Y)).
```

Two useful research requirements, currently **unmeasured**, are positive justified bounds on:

```text
CE = H̃∞(PIN | KV, C, W, A)     environmental contribution after KV disclosure
CV = H̃∞(PIN | KE, C, W, A)     electronic contribution after KE disclosure.
```

These quantities are not additive, and each is bounded by the PIN output space. If KE is public or predictable enough, CE can be zero even though an API requires nonempty environment bytes. Rejecting empty input proves a protocol gate, not physical unpredictability. The project's distinctive research question concerns maintained physical information and its lifecycle; existing cryptographic constructions retain their usual mathematical limits. No novelty or priority claim is made here.

## 2. Gate invariant and maintenance model

Use state s = (L, H, R), where L is a six-element live-share bitmap, H says the model retains all required historical environmental information, and R says the present read can recover the original environment exactly. The operational model gate is:

```text
Eligible(s) ⇔ popcount(L) ≥ 3 ∧ H ∧ R.
```

Loss changes selected live bits from 1 to 0; historical loss changes H from 1 to 0. Maintenance can replace missing shares only when popcount(L) ≥ 3, and can restore physical readability only when the relevant history survives. Maintenance does not change H from 0 to 1 and does not create a missing quorum. These are **model rules**, not evidence that real physical maintenance meets them.

**Invariant.** Along transitions restricted to losses, quorum availability cannot increase. Maintenance cannot recover from fewer than three surviving shares without another information source.

**Proof.** A loss sets bits to zero, so popcount cannot increase. By definition the maintenance transition leaves L unchanged below threshold; therefore a below-threshold state cannot become above threshold through that transition. Induction on the length of any such transition sequence establishes the invariant for all finite sequences. Similarly, if every transition preserves H=0 once reached, no sequence can reverse historical loss. This proves the abstract rule's behavior, not its adequacy as a physical model. ∎

The implementation's `verify-models` exhausts 256 gate states and 1536 single-node-loss transitions. Eligibility is a statement about the modeled original state; the real unauthenticated API cannot know H or recognize every wrong-but-well-formed input. No CLI bridges collected observations or hardware shares into a real PIN recovery operation.

An engineering metric is the **restoration gap**:

```text
G(t) = P(system recoverable in the stated model at t) - P(normal exact recovery at t).
```

The simulator enforces normal recovery as a subset of modeled recoverability, so G(t) ≥ 0. A positive gap identifies modeled recoverability that may require repair or a better read. It is not evidence of security or physical death. This is a project-specific operational definition, not a new cryptographic primitive.

## 3. Shamir reconstruction, repair and privacy

These are established properties of polynomial secret sharing, restated to expose the implementation assumptions. See [Shamir, 1979](https://web.mit.edu/6.857/OldStuff/Fall03/ref/Shamir-HowToShareASecret.pdf). The reference is not a certification of this Python code.

For one byte, work in F = GF(256). Pick independent uniform coefficients a1,...,a(t-1) in F, let f(x) = S + Σ_j aj x^j, and store f(xi) at distinct nonzero coordinates. This is repeated independently for 32 bytes. Coefficients are allowed to be zero; forcing nonzero leading coefficients would change the distribution.

**Reconstruction theorem.** Any t correct points determine S uniquely.

**Proof.** If two degree-at-most-(t-1) polynomials fit the same t distinct points, their difference has t distinct roots. A nonzero polynomial of degree at most t-1 cannot have t roots over a field, so the difference is zero. Lagrange interpolation evaluates that unique polynomial at zero. ∎

**Repair theorem.** Evaluation at the missing coordinate reconstructs its original share and preserves S, under the same correct-point assumptions.

**Proof.** Uniqueness above identifies the original f, so evaluating f at that coordinate gives precisely the original value. ∎

This does not revoke stolen copies; reproducing a share intentionally leaves that copied value valid. Malicious or mixed-polynomial points are outside the hypotheses.

**Privacy theorem.** For r < t observed distinct shares, their payload distribution is independent of S in the ideal scheme.

**Proof.** For fixed S, r observations impose a linear system on t-1 uniform coefficients. Its matrix has entries xi^j for j=1,...,t-1. The first r columns have rank r: divide row i by nonzero xi to obtain a square Vandermonde matrix over distinct coordinates. Hence every observation vector has exactly |F|^(t-1-r) coefficient preimages out of |F|^(t-1), giving probability |F|^(-r), independent of S. Independent byte-wise sampling extends this argument to 32-byte payloads. Independent public grouping metadata does not change the result. ∎

The software checks the complete GF(256) multiplication table against independent polynomial reduction and checks all nonzero inverses. A separate GF(7), t=3 model enumerates all coefficient vectors, 22 coordinate sets of size 0–2, and 6860 reconstruction cases. The GF(7) enumeration is an illustration and bounded check; the field argument above supplies the general reasoning. Side channels, host copies, malicious shares and faulty random generation remain outside the ideal privacy theorem.

## 4. Conditional physical-erasure theorem: a falsifiable toy source

First, a general data-processing boundary: if X0 → Xt → X(t+1) is Markov conditional on fixed W,A, then I(X0; X(t+1) | W,A) ≤ I(X0; Xt | W,A). Expanding I(X0; Xt,X(t+1) | W,A) in the two orders proves this: the forward additional term is zero by the Markov property, and the reverse additional term is nonnegative. This gives nonincrease, not strict decay or physical irreversibility. Invertible evolution may preserve all information. New observations, historical copies or maintenance informed by external memory can violate the required Markov/side-information assumptions. Thermodynamic entropy growth alone is not this hypothesis.

Assume, for this theorem only:

1. X0 consists of n independent, uniform symbols of alphabet size Q.
2. Each original symbol survives independently with probability p(t); a lost symbol leaves no recoverable trace. The erasure mask is public and independent of X0.
3. The adversary learns surviving values but has no historical copy or other side information correlated with lost values.
4. Any helper W has at most 2^ell possible values. It may depend on X0; this is an alphabet-size leakage bound, not an entropy measurement.

Let Zt denote the erasure mask and retained values. Then:

```text
Pguess(X0 | Zt) = [p(t) + (1-p(t))/Q]^n.
Pguess(X0 | Zt, W) ≤ min(1, 2^ell [p(t) + (1-p(t))/Q]^n).
```

**Proof.** Conditional on L lost positions, the Q^L compatible originals are uniform, so one exact-original guess succeeds with probability Q^(-L). Since L is binomial with loss probability 1-p(t), averaging with the binomial theorem gives the first equality. For each fixed Zt, conditioning on W partitions the compatible original set into at most 2^ell nonempty classes. The sum over helper values of the largest joint probability is therefore at most 2^ell/Q^L. Average over Zt and cap at one. ∎

For at most B distinct guesses of X0, an average union bound gives:

```text
P(success in B exact-original guesses | Zt, W)
  ≤ min(1, B 2^ell [p(t) + (1-p(t))/Q]^n).
```

The B-guess statement uses an average conditional guessing measure. It is not a worst-case claim for every observed helper string and is not a PIN lockout theorem.

If p(t)=exp(-λt), λ>0, the unassisted exact-original guessing probability strictly decreases with time for n>0 and Q>1; it approaches Q^(-n), not mathematical impossibility. Under the same assumptions the Shannon uncertainty is H(X0|Zt) = n(1-p(t)) log2 Q. This concerns uncertainty about the original, not thermodynamic entropy.

The bounded binary example n=4, p=1/2 yields Pguess=81/256. With a one-bit parity helper it yields 73/128 ≤ 2×81/256. These exact rational results are enumerated by `verify-models`.

**Applicability limit.** No implemented room source has been shown to satisfy these assumptions. Natural states may be biased, correlated or photographable, and apparent erasure may leave forensic traces. If A contains X0, guessing probability is one for every t. A failed decoder does not establish an erasure model. None of these formulas is reported as a measured EDK lifetime.

## 5. PIN mapping and compositional limits

Let M=10^12, N=2^64, T=floor(N/M)M. A uniform integer U in [0,N) is accepted only if U<T; each residue modulo M has exactly T/M preimages. Rejecting the 30 fixed repeated/cyclic 12-digit patterns leaves a uniform accepted set of size M-30 under the pseudorandom-output assumption. The implementation uses successive domain-separated HKDF counters and raises after 10000 rejected candidates.

This is a mapping argument, not an unconditional proof that HKDF outputs from weak environment input are uniform. The accepted PIN space has at most log2(M-30), approximately 39.86 bits. Different source inputs may collide; input dependence is not injectivity. The source-erasure bound above concerns reconstructing X0, and cannot be substituted for a PIN-guessing bound: truncation/collisions and offline verification change that problem. [RFC 5869](https://www.rfc-editor.org/rfc/rfc5869) does not supply entropy missing from a physical source.

## 6. SRAM commit invariant under a byte-prefix interruption model

Assume exclusive ordered writes to a fixed SRAM image, interruption after any byte, no spontaneous bit changes, and trustworthy reads. The writer clears the 4-byte nonzero commit tag, verifies that clearing, writes and verifies the 60-byte body, then writes the 4-byte tag and reads the record again.

**Claim.** Starting from a blank image, no interrupted proper prefix of this sequence is accepted as committed. In the more general image-format model starting from a valid old image, only the untouched old record or fully committed new record is accepted.

**Proof.** Before clearing starts, the blank image is invalid (or the untouched old image remains valid). The first clearing byte makes the tag invalid. After clearing, any body prefix leaves the all-zero tag. During tag writing, every proper prefix leaves at least one zero tag byte, whereas every byte of `DONE` is nonzero. Only after all tag bytes are written can the previously verified new body pass the tag/checksum decoder. ∎

The executable model checks 69 prefixes for each of two initial images; a fault-injected driver test checks all 68 interrupted blank-image prefixes. The application refuses overwriting an existing committed share, so this does not implement an update/refresh protocol. CRC32 detects accidental errors and is forgeable; arbitrary torn reads, device faults, attacks, reorderings, unauthorized writers and distributed six-node atomicity are not proven. Physical retention and secure erasure need separate tests.

## 7. Journal ordering invariant

The engineering enrollment workflow assumes a local filesystem honors file and directory `fsync`, a single writer follows the protocol, and ordered I/O is not forged. Let I_i be the durable intent for slot i, W_i the first device data write, R_i the durable readback receipt, and C the durable completion event. The code orders I_i < W_i < R_i and requires all six R_i plus final six-record and 20-quorum checks before C. The parent directory entry for the new operation and the initial plan are synced before device access.

**Claim.** Under these assumptions, a protocol write cannot occur without a prior durable intent; absence of a receipt cannot justify treating a slot as untouched. A completed journal has passed the stated software checks at that execution time.

**Proof.** The only call that starts a slot write is dominated by a successful intent append. That append returns only after file and directory sync; failure exits before the write. A receipt append occurs after the device writer's verified return, but may itself fail or be interrupted after the device commit. Therefore an intent without a receipt is compatible with both an untouched and a fully committed slot, and must be classified uncertain. The replay transition system permits completion only after receipts 1 through 6, and the implementation appends completion only after final comparisons. Induction on the event sequence preserves these order constraints. ∎

This is a conditional ordering argument, not a proof of physical disk/chip durability, authenticated receipts, or cross-device atomicity. A crash can leave malformed final JSON; such a journal is rejected rather than interpreted as evidence of no write. Current read-only inspection does not change historical completion and cannot establish that a consistent polynomial is the original one. No payload hash is persisted as a verifier. Fault tests exercise each failed node, intent/receipt storage failures, interrupts and read-only replay; they are not a machine-checked proof.

## 8. Required next evidence

- Independent mathematical/cryptographic review of these statements and any future robust extraction/authentication protocol.
- Physical source repeatability, attacker knowledge and residual-trace experiments.
- Board-level I²C/power/retention tests, then independent-node and shared-location failure tests.
- A suitable authenticated record/reader design before hostile physical deployment.
- A separately justified helper-data/verification design before approximate observations are accepted for real recovery.

The novel research model must survive negative results. No proof may assume the physical property it is presented as establishing.
