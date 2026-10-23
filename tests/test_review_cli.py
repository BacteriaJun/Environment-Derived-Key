import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from edk.__main__ import main


class ReviewedCLITests(unittest.TestCase):
    def test_invalid_trial_count_is_clean_error(self):
        for trials in ("0", "-1", "nan", "1.5"):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as stopped:
                    main(["simulate-decay", "--trials", trials])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("Traceback", err.getvalue())

    def test_demo_failure_never_prints_candidate_or_exception_secret(self):
        for target, kwargs in (
            ("edk.__main__.derive_pin", dict(side_effect=ValueError("SENSITIVE-SENTINEL"))),
            ("edk.__main__.recover", dict(side_effect=[bytes(32), b"\xff" * 32])),
        ):
            out, err = io.StringIO(), io.StringIO()
            with patch(target, **kwargs), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as stopped:
                    main(["demo"])
            self.assertEqual(stopped.exception.code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("SENSITIVE-SENTINEL", err.getvalue())
            self.assertIsNone(re.search(r"\d{12}", err.getvalue()))

    def test_optimized_mode_preserves_quorum_checks(self):
        script = ("from unittest.mock import patch\n"
                  "from edk.__main__ import main\n"
                  "with patch('edk.__main__.recover', side_effect=[bytes(32), b'\\xff'*32]):\n"
                  "    main(['demo'])\n")
        result = subprocess.run([sys.executable, "-O", "-c", script],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_demo_creates_no_persistent_files(self):
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-m", "edk", "demo"], cwd=directory,
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(len(re.findall(r"\b\d{12}\b", result.stdout)), 1)
            self.assertIn("SIMULATION ONLY", result.stdout)


if __name__ == "__main__":
    unittest.main()
