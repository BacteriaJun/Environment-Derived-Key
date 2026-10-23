"""Offline public-source build, distribution checks and isolated install acceptance.

This executes only synthetic software checks. It performs no device I/O and
cannot establish source entropy, physical retention or cryptographic security.
Requires Python 3.11+, local setuptools >=77, wheel support, venv and ensurepip.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import email
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any
import zipfile


class VerificationError(RuntimeError):
    """A failed check with a safe, static message; command output is withheld."""


def _name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise VerificationError("unsafe archive path")
    return path


def source_snapshot(path: Path) -> dict[str, bytes]:
    """Read a generated public ZIP without extracting links or trusting paths."""
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            parts = _name(member.filename).parts
            mode = member.external_attr >> 16
            if (len(parts) < 2 or parts[0] != "environment-derived-key"
                    or member.is_dir() or stat.S_ISLNK(mode) or member.file_size > 8 * 1024 * 1024):
                raise VerificationError("unexpected public source member")
            relative = "/".join(parts[1:])
            if relative in result:
                raise VerificationError("duplicate source member")
            result[relative] = archive.read(member)
    if not result or sum(map(len, result.values())) > 32 * 1024 * 1024:
        raise VerificationError("unexpected source archive size")
    return result


def expected_version(snapshot: dict[str, bytes]) -> str:
    import tomllib

    project = tomllib.loads(snapshot["pyproject.toml"].decode("utf-8"))["project"]
    if project["name"] != "edk-lab" or project.get("dependencies", []) != []:
        raise VerificationError("unexpected project or runtime dependencies")
    version = project["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:(?:a|b|rc)[0-9]+)?", version):
        raise VerificationError("unsupported release version")
    tree = ast.parse(snapshot["src/edk/__init__.py"].decode("utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if versions != [version]:
        raise VerificationError("project and package versions differ")
    return version


def readme_contract(snapshot: dict[str, bytes]) -> tuple[bytes, str]:
    """Check both distributed READMEs and resolve the declared package description."""
    import tomllib

    for name in ("README.md", "README.en.md"):
        if name not in snapshot or not snapshot[name].decode("utf-8").strip():
            raise VerificationError("both public language READMEs are required")
    project = tomllib.loads(snapshot["pyproject.toml"].decode("utf-8"))["project"]
    declared = project.get("readme")
    if isinstance(declared, str):
        name, content_type = declared, "text/markdown"
    elif isinstance(declared, dict) and set(declared) == {"file", "content-type"}:
        name, content_type = declared["file"], declared["content-type"]
    else:
        raise VerificationError("a public README file must supply the package description")
    if name not in ("README.md", "README.en.md") or content_type != "text/markdown":
        raise VerificationError("unexpected README metadata contract")
    description = snapshot[name]
    if not description.endswith(b"\n"):
        description += b"\n"  # setuptools terminates the metadata description with a newline.
    return description, content_type


def _metadata(data: bytes, version: str, snapshot: dict[str, bytes]) -> None:
    metadata = email.message_from_bytes(data)
    if (metadata.get_all("Name") != ["edk-lab"] or metadata.get_all("Version") != [version]
            or metadata.get_all("License-Expression") != ["MIT"]
            or metadata.get_all("Requires-Dist")):
        raise VerificationError("unexpected distribution metadata")
    description, content_type = readme_contract(snapshot)
    if (metadata.get_all("Description-Content-Type") != [content_type]
            or metadata.get_payload(decode=True) != description):
        raise VerificationError("distribution description differs from its public README")


def verify_wheel(path: Path, snapshot: dict[str, bytes], version: str) -> None:
    expected = {name.removeprefix("src/"): data for name, data in snapshot.items()
                if name.startswith("src/edk/") and name.endswith(".py")}
    metadata_root = f"edk_lab-{version}.dist-info/"
    extras = {metadata_root + name for name in (
        "METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "licenses/LICENSE")}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names) or set(names) != set(expected) | extras:
            raise VerificationError("unexpected wheel contents")
        for item in archive.infolist():
            _name(item.filename)
            if stat.S_ISLNK(item.external_attr >> 16):
                raise VerificationError("wheel contains a link")
        if any(archive.read(name) != data for name, data in expected.items()):
            raise VerificationError("wheel code differs from public source")
        if archive.read(metadata_root + "licenses/LICENSE") != snapshot["LICENSE"]:
            raise VerificationError("wheel license differs from public source")
        _metadata(archive.read(metadata_root + "METADATA"), version, snapshot)
        parser = configparser.ConfigParser()
        parser.read_string(archive.read(metadata_root + "entry_points.txt").decode("utf-8"))
        if parser.sections() != ["console_scripts"] or dict(parser["console_scripts"]) != {"edk-lab": "edk.__main__:main"}:
            raise VerificationError("unexpected wheel entry points")


def verify_sdist(path: Path, snapshot: dict[str, bytes], version: str) -> dict[str, bytes]:
    """Allow only the public snapshot and known build-generated metadata files."""
    prefix = f"edk_lab-{version}"
    generated = {"PKG-INFO", "setup.cfg"} | {
        "src/edk_lab.egg-info/" + name for name in (
            "PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "top_level.txt")}
    directories = {prefix}
    for relative in set(snapshot) | generated:
        directories.update(str(parent) for parent in PurePosixPath(prefix, relative).parents
                           if str(parent) != ".")
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            parts = _name(member.name).parts
            if parts[0] != prefix or member.name in seen or not (member.isfile() or member.isdir()):
                raise VerificationError("unexpected sdist member")
            seen.add(member.name)
            if member.isdir():
                if member.name not in directories:
                    raise VerificationError("sdist contains a nonpublic directory")
                continue
            if len(parts) < 2 or member.size > 8 * 1024 * 1024:
                raise VerificationError("unexpected sdist file")
            relative = "/".join(parts[1:])
            if relative not in snapshot and relative not in generated:
                raise VerificationError("sdist contains a nonpublic file")
            stream = archive.extractfile(member)
            if stream is None:
                raise VerificationError("unreadable sdist member")
            files[relative] = stream.read()
    if set(files) != set(snapshot) | generated or any(files[name] != data for name, data in snapshot.items()):
        raise VerificationError("sdist differs from public source")
    if sum(map(len, files.values())) > 32 * 1024 * 1024:
        raise VerificationError("unexpected sdist size")
    _metadata(files["PKG-INFO"], version, snapshot)
    _metadata(files["src/edk_lab.egg-info/PKG-INFO"], version, snapshot)
    return files


def _materialize(files: dict[str, bytes], root: Path) -> None:
    root.mkdir()
    for name, data in files.items():
        target = root.joinpath(*_name(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)


def _run(args: list[str | Path], *, cwd: Path, pythonpath: Path | None = None,
         timeout: int = 240) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INDEX="1", PIP_NO_CACHE_DIR="1")
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    try:
        result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, capture_output=True,
                                text=True, timeout=timeout, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        raise VerificationError("verification command unavailable or timed out") from None
    if result.returncode:
        raise VerificationError("verification command failed; output withheld")
    return result


def _tests(root: Path, *, optimized: bool = False) -> int:
    result = _run([sys.executable, *(["-O"] if optimized else []), "-m", "unittest", "discover",
                   "-s", "tests", "-v"], cwd=root, pythonpath=root / "src")
    count = re.search(r"Ran ([0-9]+) tests? in", result.stderr)
    if count is None or int(count[1]) < 16:
        raise VerificationError("test runner did not report a complete test suite")
    return int(count[1])


def _build(root: Path, output: Path, *, sdist: bool) -> None:
    code = "import setuptools.build_meta as b; b.build_wheel(" + repr(str(output)) + ")"
    if sdist:
        code += "; b.build_sdist(" + repr(str(output)) + ")"
    _run([sys.executable, "-c", code], cwd=root)


def _package_source(root: Path, destination: Path) -> str:
    spec = importlib.util.spec_from_file_location("edk_public_source_packager", Path(__file__).with_name("package_release.py"))
    if spec is None or spec.loader is None:
        raise VerificationError("source packager is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.package_source(root, destination)


def concept_summary(stdout: str, version: str) -> dict[str, Any]:
    """Accept only the public synthetic workflow contract; never retain raw output."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise VerificationError("duplicate concept report field")
            result[key] = value
        return result

    if not isinstance(stdout, str) or len(stdout) > 1024 * 1024:
        raise VerificationError("unexpected concept report size")
    try:
        report = json.loads(stdout, object_pairs_hook=pairs)
    except (ValueError, RecursionError):
        raise VerificationError("invalid concept report JSON") from None
    required = {"schema_version", "mode", "source", "software_version", "profile", "seed", "anchors",
                "verified_quorums", "checks"}
    if type(report) is not dict or set(report) != required:
        raise VerificationError("unexpected concept report fields")
    if (report["schema_version"] != "edk.concept-run/v1" or report["mode"] != "concept_simulation"
            or report["source"] != "synthetic" or report["software_version"] != version
            or report["profile"] != "edk.exact-input/v1"
            or type(report["seed"]) is not int or report["seed"] != 2026
            or type(report["anchors"]) is not int or not 1 <= report["anchors"] <= 512
            or type(report["verified_quorums"]) is not int or report["verified_quorums"] != 20
            or type(report["checks"]) is not dict or not report["checks"]
            or any(type(value) is not bool or not value for value in report["checks"].values())):
        raise VerificationError("installed concept workflow did not satisfy its declared contract")
    return {"passed": True, "mode": "concept_simulation", "source": "synthetic",
            "profile": "edk.exact-input/v1", "seed": 2026, "anchors": report["anchors"],
            "verified_quorums": 20, "all_checks_passed": True, "raw_output_retained": False}


def verify_release(root: Path, output: Path) -> dict[str, Any]:
    root, output = root.resolve(), output.absolute()
    if output.resolve().is_relative_to(root):
        relative = output.resolve().relative_to(root)
        if not relative.parts or relative.parts[0] in {"src", "tests", "docs", "examples", "tools", ".github"}:
            raise VerificationError("release output must be outside public input trees")
    output.mkdir(mode=0o755)  # Refuse overwriting or resuming an earlier output directory.
    report: dict[str, Any] = {
        "schema_version": "edk.software-release-validation/v1", "status": "failed",
        "runtime": sys.version.split()[0], "platform": sys.platform, "checks": {},
        "physical_io_executed": False, "physical_environment_measurements": False,
        "independent_security_or_proof_audit": False, "published": False,
        "scope": "Offline synthetic software verification; no target-hardware or cryptographic-security certification.",
    }
    failure: BaseException | None = None
    stage = "build_prerequisites"
    try:
        setuptools_version = importlib.metadata.version("setuptools")
        if int(setuptools_version.split(".", 1)[0]) < 77:
            raise VerificationError("local setuptools >=77 required")
        report["setuptools"] = setuptools_version
        stage = "public_source_export"
        source_zip = output / "environment-derived-key-source.zip"
        _package_source(root, source_zip)
        snapshot = source_snapshot(source_zip)
        version = expected_version(snapshot)
        readme_contract(snapshot)
        report["revision"] = version
        with tempfile.TemporaryDirectory(prefix="edk-release-check-") as directory:
            temporary = Path(directory)
            source = temporary / "public-source"
            _materialize(snapshot, source)
            reproduced = temporary / "reproduced.zip"
            if _package_source(source, reproduced) != hashlib.sha256(source_zip.read_bytes()).hexdigest():
                raise VerificationError("source ZIP did not reproduce from exported contents")
            report["checks"][stage] = {"passed": True, "files": len(snapshot), "reproducible_zip": True}
            stage = "source_tests"
            ordinary, optimized = _tests(source), _tests(source, optimized=True)
            if ordinary != optimized:
                raise VerificationError("ordinary and optimized test counts differ")
            report["checks"][stage] = {"passed": True, "ordinary": ordinary, "optimized": optimized}
            stage = "distribution_build"
            dist = output / "distributions"
            dist.mkdir()
            _build(source, dist, sdist=True)
            wheels, sdists = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
            if len(wheels) != 1 or len(sdists) != 1 or len(list(dist.iterdir())) != 2:
                raise VerificationError("unexpected build products")
            verify_wheel(wheels[0], snapshot, version)
            sdist_files = verify_sdist(sdists[0], snapshot, version)
            report["checks"][stage] = {"passed": True, "wheel_code_matches_source": True,
                                        "sdist_matches_public_snapshot": True,
                                        "readme_languages_in_source": ["README.md", "README.en.md"],
                                        "metadata_description_matches_declared_readme": True}
            stage = "sdist_rebuild"
            sdist_source = temporary / "sdist-source"
            _materialize(sdist_files, sdist_source)
            sdist_count = _tests(sdist_source)
            if sdist_count != ordinary:
                raise VerificationError("sdist test count differs from public source")
            rebuilt_dist = temporary / "sdist-rebuilt-dist"
            rebuilt_dist.mkdir()
            _build(sdist_source, rebuilt_dist, sdist=False)
            rebuilt = list(rebuilt_dist.glob("*.whl"))
            if len(rebuilt) != 1:
                raise VerificationError("sdist wheel rebuild failed")
            verify_wheel(rebuilt[0], snapshot, version)
            report["checks"][stage] = {"passed": True, "tests": sdist_count,
                                        "rebuilt_wheel_code_matches_source": True}
            stage = "isolated_wheel_install"
            venv = temporary / "venv"
            _run([sys.executable, "-m", "venv", venv], cwd=temporary)
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            executable = venv / ("Scripts/edk-lab.exe" if os.name == "nt" else "bin/edk-lab")
            _run([python, "-m", "pip", "install", "--no-index", "--no-deps", wheels[0]], cwd=temporary)
            outside = temporary / "outside-source"
            outside.mkdir()
            if _run([executable, "--version"], cwd=outside).stdout.strip() != version:
                raise VerificationError("installed CLI version differs")
            installed = _run([python, "-c", "import edk; print(edk.__file__)"], cwd=outside).stdout.strip()
            if not Path(installed).resolve().is_relative_to(venv.resolve()):
                raise VerificationError("installed import came from outside the new virtual environment")
            for command in ("bench-demo", "hardware-demo", "verify-models"):
                _run([executable, command], cwd=outside)
            concept = _run([executable, "concept-run", "--seed", "2026"], cwd=outside)
            report["checks"]["installed_concept_workflow"] = concept_summary(concept.stdout, version)
            if list(outside.iterdir()):
                raise VerificationError("synthetic smoke commands unexpectedly wrote files")
            report["checks"][stage] = {"passed": True, "source_tree_on_pythonpath": False,
                                        "smoke_commands": ["--version", "bench-demo", "hardware-demo", "verify-models",
                                                           "concept-run --seed 2026"]}
        report["status"] = "passed"
    except BaseException as error:
        failure = error
        report["failed_stage"] = stage
        report["checks"][stage] = {"passed": False}
        report["failure"] = "Verification stopped. Inspect this stage locally; command output was not exported."
    finally:
        artifacts = []
        for path in sorted(output.rglob("*")):
            if path.is_file():
                artifacts.append({"name": path.relative_to(output).as_posix(), "bytes": path.stat().st_size,
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        report["artifacts"] = artifacts
        validation = output / "validation.json"
        validation.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files = [output / item["name"] for item in artifacts] + [validation]
        checksums = "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  "
                            + path.relative_to(output).as_posix() + "\n" for path in sorted(files))
        (output / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
    if failure is not None:
        if isinstance(failure, KeyboardInterrupt):
            raise failure
        raise VerificationError("release verification failed; validation.json records the failed stage") from None
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new output directory; never overwrite")
    args = parser.parse_args()
    try:
        report = verify_release(Path(__file__).resolve().parents[1], args.output)
    except KeyboardInterrupt:
        parser.exit(130, "verification interrupted; existing output is not an accepted release\n")
    except (VerificationError, OSError, ValueError):
        parser.exit(1, "release verification failed; inspect validation.json if created\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
