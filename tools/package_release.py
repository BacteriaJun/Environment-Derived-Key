"""Deterministic SOURCE ZIP from explicit public-code/documentation paths only."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import stat
import zipfile

ROOT_FILES = ("README.md", "README.en.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "RELEASE_NOTES.md",
              "pyproject.toml", "MANIFEST.in", ".gitignore")
PUBLIC_TREES = (("src/edk", "*.py"), ("tests", "*.py"), ("docs", "*.md"),
                ("examples", "*.json"), ("tools", "*.py"), (".github/workflows", "*.yml"))


def package_source(root: Path, destination: Path) -> str:
    root = root.resolve()
    files = [root / name for name in ROOT_FILES]
    for directory, pattern in PUBLIC_TREES:
        base = root / directory
        if base.exists():
            files.extend(base.rglob(pattern))
    selected = []
    for path in sorted(set(files)):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("public release input is missing or unsafe")
        relative = path.relative_to(root)
        if (path.name.endswith((".edk-private.json", ".event.json"))
                or any(part.endswith(".edk-operation") for part in relative.parts)):
            raise ValueError("private study or operation record in public release inputs")
        if any(part.startswith(".") and part not in (".github", ".gitignore")
               for part in relative.parts):
            raise ValueError("hidden input inside a public release tree")
        selected.append((path, relative))
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in selected:
            info = zipfile.ZipInfo("environment-derived-key/" + relative.as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(package_source(Path(__file__).resolve().parents[1], args.output))


if __name__ == "__main__":
    main()
