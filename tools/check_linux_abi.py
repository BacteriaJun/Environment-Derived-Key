"""Run on the target Linux host; --require makes unavailable checks fail."""
import argparse
import json

from edk.native_abi import check_native_abi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require", action="store_true")
    args = parser.parse_args()
    result = check_native_abi()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["checked"] and not result["matches"]:
        raise SystemExit(1)
    if args.require and not result["checked"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
