# Environment-Derived Key · EDK 1.0

[中文](README.md)

**EDK is a concept algorithm studying how physical environments and continued maintenance affect secret recovery. Version 1.0.0 includes the reference algorithm, experiment tools, volatile-node programming and mathematical models. Validation so far is software based; long-term engineering validation has not been performed.**

## Concept

Recovery requires two inputs: state information read from the physical environment, and an independent random secret stored across volatile electronic nodes. Continued maintenance can preserve recovery. After maintenance stops, loss of historical physical information and electronic shares can reduce recovery capability.

The research concerns recovery probability under stated attacker knowledge, equipment, time and resource assumptions. Previously copied information remains available. Decoder failure alone does not establish historical information loss, and the number of representable states does not measure environmental unpredictability.

## Reference algorithm

```text
Physical anchors -> exact observations -> E ---------+
                                                     +-> HKDF-SHA256 -> 12-digit PIN
Six volatile nodes -> 3-of-6 reconstruction -> KV ----+
                      Public manifest, salt and device context
```

Both inputs participate in derivation. Electronic shares provide the second source; the physical environment provides the first. Public room names or locations alone do not supply the intended environmental uncertainty.

The `edk.exact-input/v1` profile implements:

```text
E   = Encode_v1(Manifest, exact_observations)
KV  = ShamirRecover(shares, threshold=3)
PIN = derive_pin(E, KV, salt, device_id)
```

Each anchor defines 2–65536 states. Encoding binds the complete public manifest fingerprint, anchor count and ordered values. Ambiguous or unreadable observations return an error. This profile uses exact input; Secure Sketch/Fuzzy Extractor work remains on the research roadmap.

Manifest names, reading rules, state counts and order affect the encoding. The registered manifest, public salt and device context therefore remain fixed. Observer identity, session ID and timing do not affect derivation. See the [algorithm and API specification](docs/CONCEPT_ALGORITHM.md).

## Run

Python 3.11+; runtime code uses the standard library.

```sh
python -m pip install -e .
edk-lab --version
edk-lab concept-run --seed 2026
python -m unittest discover -s tests -v
```

`concept-run` executes synthetic observations in memory. It checks all 20 threshold combinations, destroyed-share repair, and handling of missing environment, ambiguous/unreadable observations, insufficient shares and mixed generations. Its JSON report contains check results. The seed fixes the synthetic source inputs and derived result; sharing coefficients are randomized separately.

Offline installation from the supplied wheel:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps /path/to/edk_lab-1.0.0-py3-none-any.whl
.venv/bin/edk-lab concept-run --seed 2026
```

The existing `demo` command retains the raw 40×64 input example and displays a synthetic PIN. The new command uses the manifest-bound profile and reports checks.

## Included implementation

| Component | Implementation |
|---|---|
| Algorithm | Exact observation encoding, Shamir 3-of-6, HKDF-SHA256, rejection-sampled decimal mapping |
| Environment studies | Versioned manifests, non-echo collection, local private records, repeatability/missingness/timing/correlated differences |
| Study criteria | Declared sample, observer, span and reading-quality requirements with aggregate assessment |
| Lifecycle model | Independent/correlated faults, stress, maintenance cutoff, read errors, erasures and historical loss |
| Electronic nodes | MCP7940N 64-byte records, Linux I²C transport, readback and destroyed-share replacement |
| Operations | Six-slot configuration, durable intents/receipts, partial-failure status and read-only inspection |
| Mathematics | Threshold properties, conditional erasure model, PIN mapping, commit-order arguments and finite model checks |
| Packaging | Public source export, wheel/sdist checks, sdist rebuild and isolated offline installation |

CRC detects accidental record errors; share and reader authentication remain separate work. The profile encodes exact observations and uses the inherited KDF. It does not estimate source entropy or implement error-tolerant extraction.

## Experiments and hardware

```sh
edk-lab manifest-check examples/anchor-manifest.v1.public.json
edk-lab synthetic-study examples/anchor-manifest.v1.public.json --count 30 --seed 2026 --store .edk-private
edk-lab analyze examples/anchor-manifest.v1.public.json --store .edk-private --output study.aggregate.json
edk-lab simulate-lifecycle --months 36 --trials 1000 --seed 2026 --maintenance-every 1 --output lifecycle.synthetic.json
```

Manual collection uses `collect`. Raw research observations stay in owner-only local storage; public reports contain aggregate statistics. Research records are separate from key enrollment. The maintenance-dependent design has no permanent environmental-secret backup or universal recovery path.

`study-accept` evaluates declared study criteria. `bench-accept` evaluates public-pattern experiment records. Repeatability and low missingness describe usability; environmental security contribution additionally depends on source distribution and attacker knowledge.

The selected reader is Linux/Raspberry Pi I²C with MCP7940N battery-backed SRAM. Each share uses 64 bytes; the six-node workflow currently uses six independent adapters. `hardware-enroll` preflights all nodes, writes intents and readback receipts, then checks every threshold combination. `operation-status` reads receipts; `hardware-inspect` compares current nodes. Partial failures retain uncertainty without automatic resume or distributed rollback.

Actual wiring, supply switching and retention measurements remain to be performed. See the [engineering runbook](docs/ENGINEERING_RUNBOOK.zh-CN.md), [Pi bench guide](docs/RASPBERRY_PI_BENCH.zh-CN.md) and [SRAM analysis](docs/SRAM_ENGINEERING.md).

## Validation and development

Tests cover field arithmetic, threshold sharing, RFC 5869 vectors, the exact-input profile, invalid inputs, interrupted writes, journals and distribution contents. Execution results and test counts ship in `validation.json`.

```sh
python -m pip install "setuptools>=77" wheel
python tools/verify_release.py --output ../edk-1.0.0-candidate
```

There are no long-term environment studies, measured hardware power/retention curves, residual-information experiments or target-keypad integration results yet. Conditional min-entropy evidence, robust recovery, authentication, generation refresh and external mathematical/engineering review are future work. Mathematical statements identify their models and assumptions; software results and physical findings are recorded separately.

## Versioning

`1.0.0` identifies the concept algorithm and reference tools. JSON `/v1`, the `EDK1` record format and the inherited `EDK-LAB/v0.1-alpha` KDF domain have independent compatibility histories. Valid raw-byte API vectors remain unchanged. The new profile encodes environmental input differently and has separate vectors.

This directory contains local release source. GitHub upload, tag and Release status are determined by the actual publication record.

## Documentation

[Algorithm/API](docs/CONCEPT_ALGORITHM.md) · [Architecture](docs/ARCHITECTURE.md) · [Mathematics](docs/FORMAL_SPEC.md) · [Experiments](docs/EXPERIMENTS.md) · [Roadmap](docs/ROADMAP.md) · [Deployment](docs/DEPLOYMENT.md) · [Threat model](docs/THREAT_MODEL.md) · [Security](SECURITY.md) · [Changelog](RELEASE_NOTES.md)

License: [MIT](LICENSE).
