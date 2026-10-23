# v0.2 observation research workflow

This tool can collect real laboratory observations. It does not enroll a real PIN, drive a keypad, certify entropy or use approximate readings for recovery. Raw study records must never be reused as a secret backup for a production enrollment.

## Public definitions

Start from `examples/anchor-manifest.v1.public.json`, a fictional, unvalidated sample. Provide an explicit physical legend for every real study anchor. Review all free text before publishing: schema checks cannot discover a private address hidden in a reading rule.

The strict object has only `schema_version`, `manifest_id` and ordered `anchors`. Each anchor has `anchor_id`, `location_hint`, `reading_rule`, `state_count` (2..65536). Public IDs use ASCII letters/digits/underscore/hyphen, beginning with a letter. There are 1..512 anchors. Unknown fields, duplicate JSON keys, control characters, wrong types, duplicate IDs and unsupported versions are rejected. A manifest fingerprint hashes **only these public definitions**, not a secret observation. Changing state counts, rules or order changes the fingerprint and invalidates old-study comparisons.

The older `anchor-manifest.public.json` remains a legacy illustration and is deliberately not silently accepted as the new schema.

```sh
edk-lab manifest-check examples/anchor-manifest.v1.public.json
```

## Manual collection and protected storage

Run in an interactive terminal:

```sh
edk-lab collect examples/anchor-manifest.v1.public.json --observer observer-1
edk-lab sessions
```

For each anchor enter an integer, `?` for ambiguous, or `-` for unreadable. Input is hidden. A duration is measured around the actual reading prompt. Invalid input, EOF or interruption aborts input collection; it is not rounded or replaced by a guessed state. `--annotate` also asks for an externally assigned event label: `unknown` (default), `none`, `misread`, `state_change`, `physical_erasure`, or `history_loss`. Such labels are investigator assertions, not independently verified physical facts. A claim of historical information loss needs additional evidence.

The default directory is `.edk-private` relative to the current directory. It must be owned by the current user with mode 0700. Records and the internal deny-all `.gitignore` have mode 0600. The store refuses broad existing permissions, final-component symlinks, nonregular or hard-linked record files, wrong owners and overwrites. It never runs Git. Use `--store` to select an existing private parent location; parents are not recursively created or silently repermissioned. Automated synthetic creation is not atomic as a whole; interrupted batches may contain a saved prefix.

Current raw collection/storage targets **POSIX macOS and Linux**. Unsupported platforms stop rather than silently writing unprotected records. File modes are not encryption or an ACL audit. Same-user software, administrators, sync, backups, process dumps and disk recovery remain outside this protection. Use a trusted local, nonsynchronized storage location. Research records deliberately contain raw states for analysis, so none may be placed in public source/examples, submitted to Git, or treated as a production recovery backup.

`exact_observation_bytes` supplies the versioned, manifest-bound encoding used by the 1.0 `edk.exact-input/v1` concept profile. It rejects ambiguous/missing states. The in-memory `derive_observation_pin` API composes that encoding with threshold recovery and the inherited KDF. Collection and analysis commands remain separate; `concept-run` generates its own synthetic input. See [algorithm/API](CONCEPT_ALGORITHM.md).

## Compare repeats and export aggregates

Collect at least five sessions over at least three anchors, then:

```sh
edk-lab analyze examples/anchor-manifest.v1.public.json --output study.aggregate.json
```

Use `--sessions ID ...` to choose specific records; otherwise all IDs in the selected store are used. Different manifests, duplicate sessions, incompatible ordering and mixing synthetic/manual sessions are rejected. The output is a new file; existing files are not overwritten.

The report explicitly includes normal/ambiguous/unreadable counts, operational erasure fraction, normal-read pairwise disagreement, external event-label counts, annotated misread fraction, and reading-time sum/mean/median/p95. Pairwise normal comparisons use every unordered session pair per anchor. Mismatches cannot by themselves identify a misread or a real state change; unknown causes remain unknown. An annotated misread fraction is not an estimated population error rate with verified ground truth.

Correlation uses mismatch indicators relative to the chronologically first session, only paired normal readings, at least three repeats, and the phi coefficient where both margins vary. It exports only a summary across anchor pairs. Undefined coefficients are not set to zero. With more than 64 anchors correlation is explicitly omitted to bound work; the other statistics still cover every anchor. Baseline errors, sample size and temporal dependence can bias these exploratory statistics.

Exports omit raw values, per-anchor identities/distributions, manifest IDs/fingerprints, timestamps, observer codes, session IDs, PINs and share payloads. Minimum sample checks reduce obviously tiny exports but are not a privacy theorem. Repeated releases, differencing, external knowledge and study counts can still leak information. There is no differential privacy or automatic disclosure clearance.

## Reproducible synthetic study

```sh
edk-lab synthetic-study examples/anchor-manifest.v1.public.json --count 30 --seed 2026 --store .edk-private
edk-lab analyze examples/anchor-manifest.v1.public.json --output synthetic.aggregate.json
```

The seeded generator uses noncryptographic randomness, artificial durations and a fixed synthetic epoch. Seed, manifest and session count reproduce the same records and aggregate on the tested runtime. Repeat-seed IDs are rejected rather than overwriting. These samples demonstrate the pipeline; they are not observations of a room or estimates of physical entropy. Corresponding example aggregates are shipped as synthetic JSON only; raw generated records are excluded from the source package.
