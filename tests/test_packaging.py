import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


class PackagingTests(unittest.TestCase):
    def test_deterministic_allowlist_excludes_private_data_and_caches(self):
        path = Path(__file__).resolve().parents[1] / "tools/package_release.py"
        spec = importlib.util.spec_from_file_location("edk_package_tool", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            for name in module.ROOT_FILES:
                (root / name).write_text("public fixture")
            for subdir, name in (("src/edk", "public.py"), ("docs", "public.md"),
                                 ("examples", "public.json"), (".edk-private", "raw.edk-private.json"),
                                 ("src/edk/__pycache__", "cache.pyc")):
                (root / subdir).mkdir(parents=True, exist_ok=True)
                (root / subdir / name).write_text("public" if name.startswith("public") else "SENSITIVE-SENTINEL")
            a, b = Path(directory) / "a.zip", Path(directory) / "b.zip"
            self.assertEqual(module.package_source(root, a), module.package_source(root, b))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with zipfile.ZipFile(a) as archive:
                self.assertFalse(any("private" in n or "__pycache__" in n for n in archive.namelist()))
                self.assertTrue(all(b"SENSITIVE-SENTINEL" not in archive.read(n) for n in archive.namelist()))
            with self.assertRaises(FileExistsError):
                module.package_source(root, a)
            for name in ("raw.edk-private.json", "0000.event.json"):
                record = root / "examples" / name
                record.write_text("SENSITIVE-SENTINEL")
                with self.assertRaises(ValueError):
                    module.package_source(root, Path(directory) / "unsafe.zip")
                record.unlink()


if __name__ == "__main__":
    unittest.main()
