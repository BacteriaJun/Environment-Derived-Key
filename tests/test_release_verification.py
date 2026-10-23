import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


TOOL = Path(__file__).resolve().parents[1] / "tools/verify_release.py"
SPEC = importlib.util.spec_from_file_location("edk_verify_release_test_tool", TOOL)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


VERSION = "1.0.0"


def snapshot():
    return {
        "pyproject.toml": b'[project]\nname="edk-lab"\nversion="1.0.0"\nreadme="README.md"\n',
        "src/edk/__init__.py": b'__version__ = "1.0.0"\n',
        "src/edk/__main__.py": b"def main(): pass\n",
        "LICENSE": b"MIT fixture\n",
        "README.md": "# EDK 中文说明\n".encode("utf-8"),
        "README.en.md": b"# EDK English description\n",
    }


def metadata(extra=b""):
    return b"Metadata-Version: 2.4\nName: edk-lab\nVersion: 1.0.0\nLicense-Expression: MIT\nDescription-Content-Type: text/markdown\n" + extra + b"\n" + snapshot()["README.md"]


def wheel_files():
    data = snapshot()
    prefix = "edk_lab-1.0.0.dist-info/"
    files = {name.removeprefix("src/"): body for name, body in data.items() if name.startswith("src/")}
    files.update({prefix + "METADATA": metadata(), prefix + "WHEEL": b"Wheel-Version: 1.0\n",
                  prefix + "entry_points.txt": b"[console_scripts]\nedk-lab = edk.__main__:main\n",
                  prefix + "top_level.txt": b"edk\n", prefix + "RECORD": b"",
                  prefix + "licenses/LICENSE": data["LICENSE"]})
    return files


def write_wheel(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)


def sdist_files():
    data = snapshot()
    data.update({"PKG-INFO": metadata(), "setup.cfg": b"[egg_info]\n",
                 "src/edk_lab.egg-info/PKG-INFO": metadata(),
                 "src/edk_lab.egg-info/SOURCES.txt": b"",
                 "src/edk_lab.egg-info/dependency_links.txt": b"\n",
                 "src/edk_lab.egg-info/entry_points.txt": b"[console_scripts]\n",
                 "src/edk_lab.egg-info/top_level.txt": b"edk\n"})
    return data


def write_sdist(path, files, *, link=None):
    with tarfile.open(path, "w:gz") as archive:
        for name, body in files.items():
            member = tarfile.TarInfo("edk_lab-1.0.0/" + name)
            member.size = len(body)
            archive.addfile(member, io.BytesIO(body))
        if link is not None:
            member = tarfile.TarInfo("edk_lab-1.0.0/link")
            member.type = tarfile.SYMTYPE
            member.linkname = link
            archive.addfile(member)


class ReleaseVerificationTests(unittest.TestCase):
    def test_version_must_match_package_and_have_no_runtime_dependencies(self):
        self.assertEqual(release.expected_version(snapshot()), VERSION)
        data = snapshot()
        data["src/edk/__init__.py"] = b'__version__ = "0.2.0a1"\n'
        with self.assertRaises(release.VerificationError):
            release.expected_version(data)
        data = snapshot()
        data["pyproject.toml"] += b'dependencies=["new-runtime-library"]\n'
        with self.assertRaises(release.VerificationError):
            release.expected_version(data)

    def test_bilingual_readmes_and_declared_metadata_description_are_checked(self):
        self.assertEqual(release.readme_contract(snapshot()), (snapshot()["README.md"], "text/markdown"))
        data = snapshot()
        del data["README.en.md"]
        with self.assertRaises(release.VerificationError):
            release.readme_contract(data)
        data = snapshot()
        data["README.en.md"] = b"  \n"
        with self.assertRaises(release.VerificationError):
            release.readme_contract(data)
        data = snapshot()
        data["pyproject.toml"] = data["pyproject.toml"].replace(b'readme="README.md"', b'readme="README.en.md"')
        self.assertEqual(release.readme_contract(data), (data["README.en.md"], "text/markdown"))
        with self.assertRaises(release.VerificationError):
            release._metadata(metadata(), VERSION, data)
        with self.assertRaises(release.VerificationError):
            release._metadata(metadata().replace(snapshot()["README.md"], b"changed description\n"), VERSION, snapshot())

    def test_concept_workflow_summary_retains_only_safe_contract_fields(self):
        data = {"schema_version": "edk.concept-run/v1", "mode": "concept_simulation", "source": "synthetic",
                "software_version": VERSION, "profile": "edk.exact-input/v1", "seed": 2026,
                "anchors": 40, "verified_quorums": 20, "checks": {"arbitrary_check_name": True}}
        summary = release.concept_summary(json.dumps(data), VERSION)
        self.assertTrue(summary["passed"])
        self.assertEqual(summary["source"], "synthetic")
        self.assertEqual(summary["verified_quorums"], 20)
        self.assertFalse(summary["raw_output_retained"])
        self.assertNotIn("checks", summary)
        variants = (("source", "physical_io"), ("mode", "production"), ("seed", True),
                    ("software_version", "0.2.0a2"), ("verified_quorums", 19),
                    ("checks", {"check": False}), ("checks", {"check": 1}), ("checks", {}),
                    ("pin", "SYNTHETIC-SENTINEL"))
        for key, value in variants:
            changed = dict(data, **{key: value})
            with self.assertRaises(release.VerificationError) as caught:
                release.concept_summary(json.dumps(changed), VERSION)
            self.assertNotIn("SYNTHETIC-SENTINEL", str(caught.exception))
        duplicate = json.dumps(data).replace('"seed": 2026', '"seed": 2026, "seed": 2026')
        with self.assertRaises(release.VerificationError):
            release.concept_summary(duplicate, VERSION)

    def test_source_zip_rejects_duplicate_escaping_and_link_members(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("environment-derived-key/LICENSE", b"MIT")
            self.assertEqual(release.source_snapshot(path), {"LICENSE": b"MIT"})
            for name in ("../escape", "/absolute", "environment-derived-key/../escape"):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(name, b"SYNTHETIC-SENTINEL")
                with self.assertRaises(release.VerificationError):
                    release.source_snapshot(path)
            with zipfile.ZipFile(path, "w") as archive:
                member = zipfile.ZipInfo("environment-derived-key/link")
                member.external_attr = 0o120777 << 16
                archive.writestr(member, b"/target")
            with self.assertRaises(release.VerificationError):
                release.source_snapshot(path)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("environment-derived-key/LICENSE", b"MIT")
                    archive.writestr("environment-derived-key/LICENSE", b"changed")
            with self.assertRaises(release.VerificationError):
                release.source_snapshot(path)

    def test_wheel_requires_exact_code_metadata_license_and_entry_point(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wheel.whl"
            write_wheel(path, wheel_files())
            release.verify_wheel(path, snapshot(), VERSION)
            mutations = (
                ("edk/__main__.py", b"changed code"),
                ("edk/private.edk-private.json", b"SYNTHETIC-SENTINEL"),
                ("edk_lab-1.0.0.dist-info/METADATA", metadata(b"Requires-Dist: added-library\n")),
                ("edk_lab-1.0.0.dist-info/licenses/LICENSE", b"other license"),
                ("edk_lab-1.0.0.dist-info/entry_points.txt", b"[console_scripts]\nother = edk:main\n"),
            )
            for name, value in mutations:
                data = wheel_files()
                data[name] = value
                write_wheel(path, data)
                with self.assertRaises(release.VerificationError):
                    release.verify_wheel(path, snapshot(), VERSION)

    def test_sdist_rejects_private_data_links_missing_and_changed_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.tar.gz"
            write_sdist(path, sdist_files())
            self.assertEqual(release.verify_sdist(path, snapshot(), VERSION), sdist_files())
            for change in ("extra", "changed", "missing", "link"):
                data = sdist_files()
                if change == "extra":
                    data[".edk-private/raw.edk-private.json"] = b"SYNTHETIC-SENTINEL"
                elif change == "changed":
                    data["LICENSE"] = b"changed"
                elif change == "missing":
                    del data["src/edk/__main__.py"]
                write_sdist(path, data, link="/outside" if change == "link" else None)
                with self.assertRaises(release.VerificationError):
                    release.verify_sdist(path, snapshot(), VERSION)
            write_sdist(path, sdist_files())
            with tarfile.open(path, "r:gz") as archive:
                # An unknown empty directory is still outside the public manifest.
                members = [(member, archive.extractfile(member).read()) for member in archive]
            with tarfile.open(path, "w:gz") as archive:
                for member, body in members:
                    archive.addfile(member, io.BytesIO(body))
                private = tarfile.TarInfo("edk_lab-1.0.0/.edk-private")
                private.type = tarfile.DIRTYPE
                archive.addfile(private)
            with self.assertRaises(release.VerificationError):
                release.verify_sdist(path, snapshot(), VERSION)

    def test_failed_prerequisite_records_failure_and_no_sensitive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            with patch.object(release.importlib.metadata, "version", return_value="76.0"):
                with self.assertRaises(release.VerificationError):
                    release.verify_release(Path(directory), output)
            report = json.loads((output / "validation.json").read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failed_stage"], "build_prerequisites")
            self.assertFalse(report["physical_io_executed"])
            self.assertFalse(report["published"])
            self.assertTrue((output / "CHECKSUMS.sha256").exists())
            self.assertNotIn("76.0", json.dumps(report))

    def test_existing_output_and_public_tree_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "existing"
            existing.mkdir()
            (existing / "keep.txt").write_text("preserve")
            with self.assertRaises(FileExistsError):
                release.verify_release(root, existing)
            self.assertEqual((existing / "keep.txt").read_text(), "preserve")
            for destination in (root, root / "docs/output", root / "src/output"):
                with self.assertRaises(release.VerificationError):
                    release.verify_release(root, destination)

    def test_failed_subprocess_never_exports_output(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(release.VerificationError) as caught:
                release._run([release.sys.executable, "-c",
                              "import sys; print('SYNTHETIC-SENTINEL'); sys.exit(1)"], cwd=Path(directory))
            self.assertNotIn("SYNTHETIC-SENTINEL", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
