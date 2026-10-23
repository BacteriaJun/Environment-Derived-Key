# Experiments | falsifiable engineering plan

The goal is to discover whether any environmental source satisfies both **repeatable living recovery** and **unattended information decay**. We must publish negative results as readily as positive ones.

## E0 — Physical feature identification

Choose 15–20 physical anchor candidates in a real, irregular room. Public schema records anchor ID, reproducible orientation, discrete rule, and reading order. Secret enrollment readings must **not** be uploaded to a public repository. Do not put addresses, GPS coordinates or identifiable room photos in study data.

Pass conditions (proposed, not observed):

- The reading rule allows an independent person to unambiguously classify the same state.
- No precision measuring instruments needed for normal use.
- Mean reading time per cell and missing/ambiguous event counts measured.
- Document how cleaning, rearrangement, lighting, temperature, and repairs affect observations.

## E1 — Usable recovery under maintenance

For 30 days, repeat blinded/manual readings of the candidate anchors, varying observers and time. Measure per-cell mismatch probabilities, **correlated failures**, erasure rates, read duration, and ability to restore known original states. Publish anonymized aggregates, not secret readings.

The **target** is under 1% read disagreement per reliable anchor and under 5 minutes for the eventual system. These numbers are not validated or binding; report data first, choose parameters second.

## E2 — Adversarial knowledge and conditional entropy

Threat levels: public documentation only; exterior photographs; partial interior photos; brief authorized physical observation; complete original state captured. Derive a defensible lower bound on `H_inf(X0 | W,E)` only if the sampling assumptions are credible.

Do not conflate repeated observation of **one fixed room** with independent samples from a source distribution. Statistical tools such as SP 800-90B assist with noisy-source measurement, but empirical claim strength depends on sampling, independence and attacker priors.

## E3 — Environment decay and death

Make two cohorts of the same physical encoding candidate:

- **Maintained**: periodic human reading and repair of recoverably altered cells.
- **Unmaintained**: similar exposure, no repair.

Across observation periods, record probability of standard decoder success *and separately* posterior uncertainty about initial states. A decoder's bounded-distance failure is NOT proof of information-theoretic death. Test for residual traces recoverable by stronger optical/forensic readers where feasible.

Pre-register environmental conditions (temperature, lighting, moisture) and sample count. Avoid inferring multi-year retention from a short acceleration experiment without a validated physical aging law.

## E4 — Six independent volatile nodes

Start with RAM-only simulation (done). Next, build a single power-backed SRAM testboard, then 6 independent supplies.

For each unit measure: normal-power recovery, USB power-cycle without loss, deep-sleep data retention, brownout behavior, recharge, environmental stress, loss distribution, and post-loss reconstruction failure. **No single-node result proves six-node independence.**

## E5 — 3-of-6 lifecycle

Required test scenarios:

1. Any 3 of 6 intact **same-generation** shares recover the same 256-bit `KV`.
2. Any 0–2 independent shares fail to recover via supported API.
3. Destroyed (confirmed gone) S5 can be replaced at original index without changing `KV`.
4. One duplicated share index is NOT counted twice.
5. Mixed-generation input is rejected.
6. Suspected stolen share triggers a not-yet-implemented coordinated refresh plan rather than repair by copying the old share.
7. A read failure never produces a candidate PIN to send to a real keypad.
8. The environmental source is required, irrespective of how many electronic shares survive.

## E6 — Security review before real keys

Minimum gates: external cryptographic review; measured environmental source entropy and known attack assumptions; robust sketch; secure reader; power electronics tests; side-channel/tamper model; deliberate recovery policy; no offline PIN oracle; verified restrictions of target commercial device.

Release an experimental report with per-measurement uncertainty, raw *non-secret* aggregated results, and a limitations section. No deployment to valuable data until reviews pass.

## Stage-1 review evidence and next observations

The software review adds deterministic GF(256) algebra fixtures, RFC 5869 SHA-256 test cases 2/3, legacy PIN vectors, malformed-input tests and failure-output checks. These are synthetic software tests, not E0–E3 observations. See [REVIEW_STAGE1.md](REVIEW_STAGE1.md).

For v0.2, register normal, ambiguous and unreadable observations separately. Pairwise disagreement alone cannot identify a misread versus a changed physical state; that distinction needs reference readings or controlled experiment labels, and unknown causes must remain unknown. Treat read duration, observer disagreement, erasures, controlled state changes and correlations as distinct measurements. Publish only anonymous aggregates, never raw states, per-anchor public fingerprints of secret states, PINs, share payloads or enrollment verifiers. Private storage and aggregate export are implemented; schema validation cannot certify that humans have avoided sensitive text in public definitions.

The current `environment_recovery_rate` remains a binary synthetic survival event; it does not separately measure read errors, physical erasure, residual historical information or adversarial recoverability. Those are explicit future simulation dimensions, not inferred results of the current model.

## v0.2 tooling now available

The legacy `simulate-decay` retains the model described above for compatibility. The new `simulate-lifecycle` separately tracks read errors, ambiguity, physical unavailability and latent historical loss, along with correlated node faults and maintenance. These are imposed synthetic variables, not measured physical evidence.

Use [OBSERVATION_GUIDE.md](OBSERVATION_GUIDE.md) for private manual collection and aggregate-only repeatability reports. External event labels can help controlled experiments but are not software-confirmed truth. No real E0–E3 study has been performed by this implementation work. [SRAM_ENGINEERING.md](SRAM_ENGINEERING.md) supplies the host writer and pending E4 bench plan; `hardware-demo` uses only in-memory chips. [FORMAL_SPEC.md](FORMAL_SPEC.md) separates conditional theorems, finite model checks and unverified physical assumptions.

The 0.2.0a2 `StudyPolicy` binds a manifest and declared start time to explicit sample/observer/span/reading-quality criteria. `study-accept` rejects predating sessions and exports no identities or raw states; its CLI requires at least five sessions and three anchors. Timestamp declarations are not trusted preregistration. Passing repeatability criteria never validates entropy or approves real derivation. `examples/study-policy.v1.example.json` contains arbitrary illustrative thresholds and a synthetic-era timestamp, not validated experimental limits; choose actual limits before new physical sampling. Public bench acceptance similarly requires distinct preparations, stable backup/status observations and operator-supplied durations, without claiming hardware authenticity or measured lifetime. See [engineering runbook](ENGINEERING_RUNBOOK.zh-CN.md).
