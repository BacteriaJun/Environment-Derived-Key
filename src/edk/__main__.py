"""EDK concept algorithm, physical observation and volatile-node tools."""

from __future__ import annotations

import argparse
import secrets
from collections.abc import Sequence
from . import __version__
from .derivation import derive_pin
from .environment import canonicalize
from .shamir import split, recover, repair_share
from .volatile import VolatileNode, NodeUnavailable
from .simulation import survival_probability


def demo() -> None:
    # Artificial uniform 40-cell input; does not establish room entropy.
    environment = canonicalize([secrets.randbelow(64) for _ in range(40)])
    secret = secrets.token_bytes(32)
    salt = secrets.token_bytes(32)  # public enrollment parameter in an actual system
    nodes = [VolatileNode.provision(share) for share in split(secret)]
    def pin(indices: tuple[int, ...], observed: bytes = environment) -> str:
        q = [nodes[i-1].read() for i in indices]
        return derive_pin(observed, recover(q), salt=salt, device_id="demo-device")
    first = pin((1, 2, 3))
    second = pin((2, 4, 6))
    if first != second:
        raise RuntimeError("inconsistent demo quorums")
    changed = bytearray(environment)
    changed[0] ^= 1
    changed_pin = derive_pin(bytes(changed), secret, salt=salt, device_id="demo-device")
    nodes[4].expire()
    replacement = repair_share([nodes[0].read(), nodes[1].read(), nodes[2].read()], missing_index=5)
    nodes[4].reprovision(replacement)
    if pin((1, 4, 5)) != first:
        raise RuntimeError("inconsistent demo repair")
    for i in (0, 1, 2, 3):
        nodes[i].expire()
    try:
        _ = pin((1, 5, 6))
    except (NodeUnavailable, ValueError):
        pass
    else:
        raise RuntimeError("quorum should not be available")
    # Emit the synthetic PIN only after the entire demo has passed its checks.
    # Explicit checks remain active under python -O; no real recovery command exists.
    print(f"EDK {__version__} | SIMULATION ONLY | synthetic inputs")
    print(f"3-of-6 reconstruction: {first} (synthetic PIN)")
    print("different independent quorums yield identical PIN: YES")
    print("modified environmental observation yields different PIN:", changed_pin != first)
    print("destroyed node S5 replaced from three healthy nodes: True")
    print("only two live nodes remain: recovery BLOCKED")
    print("Input profile: legacy raw bytes; exact observations; no error correction.")


def simulate(trials: int, seed: int) -> None:
    print("Synthetic independent exponential hazard model")
    print("months  quorum_success  environment_success  combined_success")
    for months in (0, 1, 3, 6, 12, 24, 36):
        r = survival_probability(months, trials=trials, seed=seed)
        print(f"{months:>6}  {r['node_recovery_rate']*100:>13.1f}%"
              f"  {r['environment_recovery_rate']*100:>18.1f}%"
              f"  {r['combined_recovery_rate']*100:>14.1f}%")


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a positive integer") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="EDK concept algorithm and physical secret lifecycle tools")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="ephemeral end-to-end 3-of-6 and environment demo")
    decay = sub.add_parser("simulate-decay", help="synthetic unmaintained-lifetime experiment")
    decay.add_argument("--trials", type=_positive_int, default=5000)
    decay.add_argument("--seed", type=int, default=2026)
    from .research_cli import add_research_commands
    add_research_commands(sub)
    args = parser.parse_args(argv)
    try:
        if getattr(args, "handler", None) is not None:
            args.handler(args)
        elif args.command == "demo":
            demo()
        else:
            simulate(args.trials, args.seed)
    except (ValueError, NodeUnavailable, RuntimeError, OSError, EOFError, Warning):
        # Never echo exception data: errors can originate in secret-handling code.
        parser.error("operation stopped: invalid input, unsafe storage, unavailable I/O or inconsistent state; no PIN released")
    except KeyboardInterrupt:
        parser.exit(130, "operation interrupted; no automatic recovery or retry performed\n")


if __name__ == "__main__":
    main()
