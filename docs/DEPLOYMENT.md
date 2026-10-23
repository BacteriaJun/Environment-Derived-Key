# Install, verify and package EDK 1.0

Version 1.0.0 packages the concept algorithm, reference implementation and experiment tools. Software verification is available; long-term engineering validation has not been performed. Observation collection targets macOS/Linux POSIX; physical MCP7940N I/O targets Linux. The tools run as local commands without a daemon or network service. The selected hardware path is a Linux/Raspberry Pi host; see [engineering runbook](ENGINEERING_RUNBOOK.zh-CN.md) and [台架指南](RASPBERRY_PI_BENCH.zh-CN.md).

## Local installation

Install Python 3.11+ and create a project-local virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/edk-lab --version
.venv/bin/edk-lab concept-run --seed 2026
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -O -m unittest discover -s tests -v
.venv/bin/edk-lab verify-models
.venv/bin/edk-lab hardware-demo
```

There are no third-party runtime dependencies. Building from source requires setuptools >=77, which the installer can fetch in an isolated build. For offline installation use the supplied wheel:

```sh
.venv/bin/python -m pip install --no-index --no-deps /path/to/edk_lab-1.0.0-py3-none-any.whl
```

Keep raw research data outside synced/public folders. `.edk-private` is created relative to the working directory with owner-only access; existing unsafe storage is rejected. Do not install the project into a shared server just to collect personal room observations.

## Reproduce a study and synthetic lifecycle reports

Use a dedicated empty working directory or separate store for each synthetic seed/study. Run from the source folder after installation:

```sh
edk-lab manifest-check examples/anchor-manifest.v1.public.json
edk-lab synthetic-study examples/anchor-manifest.v1.public.json --store .edk-private --count 30 --seed 2026
edk-lab analyze examples/anchor-manifest.v1.public.json --store .edk-private --output study.aggregate.json
edk-lab simulate-lifecycle --months 36 --trials 1000 --seed 2026 --output decay.synthetic.json
edk-lab simulate-lifecycle --months 36 --trials 1000 --seed 2026 --maintenance-every 1 --output maintained.synthetic.json
edk-lab simulate-lifecycle --months 36 --trials 1000 --seed 2026 --maintenance-every 1 --maintenance-stop-after 12 --output stopped.synthetic.json
```

Reports distinguish immediate normal recovery, electronic quorum, survival of modeled environmental history, exact present reads and modeled system recoverability. Misread, ambiguity, physical erasure and history-loss fractions are separate. Maintenance cannot restore a missing quorum or genuinely lost history. Location shocks, per-node hazards, vehicle stress and a fallible continuously powered S5 are synthetic assumptions printed in the report. The CLI is a subset of the full typed Python configuration API. There are no attacker-success estimates or measured retention times.

Output paths must be new files. Existing files and duplicate synthetic session IDs are not overwritten. `collect` requires a real interactive terminal; pipelines/stdin files do not silently echo secret readings or create imports for real PIN generation. See [observation workflow](OBSERVATION_GUIDE.md).

## Package and verify

```sh
python -m pip install "setuptools>=77" wheel
python tools/verify_release.py --output ../edk-1.0.0-candidate
```

The source ZIP uses an explicit public-tree allowlist, sorted files and fixed archive metadata, and refuses overwriting. It excludes arbitrary private directories, bytecode, Git history and build products. Deterministic ZIP packaging does not mean physical measurements or random cryptographic enrollment are deterministic. Inspect the selected public content before publication; no allowlist can recognize secrets a person manually pasted into source or documentation.

The verification tool installs the wheel in a fresh environment and runs commands from a directory outside the source tree, verifies exact public source/metadata correspondence in wheel/sdist, reruns tests from the sdist and rebuilds its wheel. Verify the supplied checksums as well. CI configures Python 3.11/3.12/3.13 tests, optimized-mode tests, synthetic study/model/SRAM smoke checks and the same artifact acceptance. The local validation record identifies which runtime actually ran; configuration is not proof that remote CI completed. Build-time prerequisites must already be installed for a completely offline run; no third-party runtime dependency is added.

## Supported rollback and incident behavior

Retain the prior source/package archive to roll back software. Do not roll back by copying real master keys or all environment secrets into a permanent fallback. Raw study records are research data and must not be reused as production key backups.

On a malformed or unreadable record, unsafe permissions, device error or power-failure status, stop and investigate. New initialization uses `hardware-enroll` with a new operation directory and strict topology; diagnose using `operation-status` and read-only `hardware-inspect`. An intent without receipt is uncertain, including when a device committed before a disk failure. Partial six-node provisioning has no automatic resume or distributed rollback. Legacy provisioning/repair APIs lack this journal. Replacing destroyed slots preserves the old polynomial and does not revoke copied shares. The package has no unattended real-PIN recovery command.

## Further engineering work

Further work covers source entropy and attacker knowledge, robust recovery/helper leakage, share/reader authentication, physical power/retention/residual-information measurements, coordinated refresh, target-device testing and external mathematical review. The Linux reader uses host I²C rather than a separate MCU firmware image. See [formal specification](FORMAL_SPEC.md), [hardware engineering](SRAM_ENGINEERING.md) and [roadmap](ROADMAP.md). GitHub upload, tag and Release publication remain a separate owner-authorized operation.
