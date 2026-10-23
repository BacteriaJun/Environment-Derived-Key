"""Executable bounded models, not a general theorem prover or hardware proof."""

from __future__ import annotations

from collections import Counter
import itertools
from fractions import Fraction
from typing import Any

from .shamir import Share
from .sram import COMMIT, decode_share, encode_share


def verify_models() -> dict[str, Any]:
    """Exhaust the declared finite models; raise on an invariant violation."""
    states = transitions = 0
    # Node repair cannot cross upward from an unavailable quorum; lost history
    # cannot become true. Environment must be readable and history must survive.
    for live_tuple in itertools.product((False, True), repeat=6):
        live = tuple(live_tuple)
        for history, readable in itertools.product((False, True), repeat=2):
            available = sum(live) >= 3
            eligible = available and history and readable
            if eligible and (not available or not history or not readable):
                raise RuntimeError("dual-source gate invariant violated")
            repaired = (True,) * 6 if available else live
            restored_readable = True if history else readable
            if not available and sum(repaired) >= 3:
                raise RuntimeError("maintenance created a quorum")
            if available and not (sum(repaired) >= 3):
                raise RuntimeError("maintenance lost a quorum")
            # Every single-node loss is a transition; no loss can restore quorum.
            for index in range(6):
                failed = list(live)
                failed[index] = False
                if sum(failed) > sum(live):
                    raise RuntimeError("node loss created availability")
                transitions += 1
            if history and not restored_readable:
                raise RuntimeError("toy restoration invariant violated")
            states += 1

    # GF(7), t=3, six nonzero coordinates. Every possible coefficient vector,
    # secret, and observation of zero/one/two shares is enumerated.
    privacy_views = reconstruction_cases = 0
    for size in (0, 1, 2):
        for coordinates in itertools.combinations(range(1, 7), size):
            views = []
            for secret in range(7):
                distributions: Counter[tuple[int, ...]] = Counter()
                for a, b in itertools.product(range(7), repeat=2):
                    distributions[tuple((secret + a * x + b * x * x) % 7 for x in coordinates)] += 1
                views.append(distributions)
            if any(view != views[0] for view in views):
                raise RuntimeError("finite-field privacy model violated")
            privacy_views += 1
    for secret, a, b in itertools.product(range(7), repeat=3):
        for coordinates in itertools.combinations(range(1, 7), 3):
            recovered = 0
            for x in coordinates:
                weight = 1
                for other in coordinates:
                    if other != x:
                        weight = weight * (-other) * pow(x - other, -1, 7) % 7
                recovered = (recovered + (secret + a * x + b * x * x) * weight) % 7
            if recovered != secret:
                raise RuntimeError("finite-field reconstruction model violated")
            reconstruction_cases += 1

    # Byte-prefix interruption model for invalidate/body/commit programming.
    old = encode_share(Share(1, b"A" * 16, b"B" * 32))
    new = encode_share(Share(1, b"C" * 16, b"D" * 32))
    writes = [(60 + i, 0) for i in range(4)]
    writes += list(enumerate(new[:60])) + [(60 + i, value) for i, value in enumerate(COMMIT)]
    prefixes = 0
    for initial in (bytes(64), old):
        for length in range(len(writes) + 1):
            image = bytearray(initial)
            for offset, value in writes[:length]:
                image[offset] = value
            try:
                decoded = decode_share(bytes(image))
            except ValueError:
                pass
            else:
                if decoded not in (decode_share(old), decode_share(new)):
                    raise RuntimeError("interrupted write accepted an unrelated record")
                if length not in (0, len(writes)):
                    raise RuntimeError("partial byte-prefix write was accepted")
            prefixes += 1
    # Independent binary erasure example, n=4, p_survival=1/2. The view
    # includes the public erasure mask; parity is a one-bit helper string.
    plain: dict[tuple, Counter] = {}
    helper: dict[tuple, Counter] = {}
    for original in itertools.product((0, 1), repeat=4):
        for mask in itertools.product((0, 1), repeat=4):
            retained = tuple(original[i] for i in range(4) if mask[i])
            view = (mask, retained)
            plain.setdefault(view, Counter())[original] += 1
            helper.setdefault((view, sum(original) % 2), Counter())[original] += 1
    guessing = Fraction(sum(max(c.values()) for c in plain.values()), 256)
    with_helper = Fraction(sum(max(c.values()) for c in helper.values()), 256)
    if guessing != Fraction(3, 4)**4 or with_helper > 2 * guessing:
        raise RuntimeError("finite erasure/helper leakage model violated")
    return {"schema_version": "edk.bounded-verification/v1", "all_invariants_hold": True,
            "gate_states": states, "single_node_loss_transitions": transitions,
            "gf7_private_coordinate_sets": privacy_views,
            "gf7_reconstruction_cases": reconstruction_cases, "sram_write_prefixes": prefixes,
            "binary_erasure_guess_probability": str(guessing),
            "binary_erasure_with_parity_guess_probability": str(with_helper),
            "scope": "Exhaustive within stated finite models; no physical entropy, attacker or device proof."}
