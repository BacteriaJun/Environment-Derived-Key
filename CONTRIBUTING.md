# Contributing

Suggestions, critiques and reproducible negative results are welcome. Please keep the project empirical and careful about security claims.

1. Propose the precise hypothesis and attacker model before offering a new source of physical entropy.
2. If introducing cryptographic primitives, cite formal references and add deterministic known-answer tests and malformed-input tests.
3. Keep real secrets and personal spatial data out of commits/issues. Only synthetic demonstrations belong in the repo.
4. Run `python -m unittest discover -s tests -v` and CLI smoke tests before a PR.
5. Document false-positive recovery, erroneous PIN output, and irreversible-loss risks rather than hiding them.

The maintainers do not currently accept production-security guarantees, or claims that Shamir alone makes this an environment-derived system.
