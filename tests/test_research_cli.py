import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from edk.__main__ import main
from edk.jsonio import encode_document
from test_observations import manifest


class ResearchCLITests(unittest.TestCase):
    def run_cli(self, *args, cwd):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
                   PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "edk", *map(str, args)],
                              cwd=cwd, env=env, capture_output=True, text=True, timeout=30)

    @unittest.skipUnless(os.name == "posix", "POSIX study storage")
    def test_full_synthetic_study_pipeline_and_anonymous_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "manifest.json"
            public.write_bytes(encode_document(manifest().to_dict()))
            commands = [("manifest-check", public),
                        ("synthetic-study", public, "--count", "10", "--store", root / ".edk-private"),
                        ("analyze", public, "--store", root / ".edk-private", "--output", root / "report.json")]
            for command in commands:
                result = self.run_cli(*command, cwd=root)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('"value"', result.stdout)
            report = json.loads((root / "report.json").read_text())
            self.assertEqual(report["sessions"], 10)
            self.assertEqual(report["declared_source"], "synthetic")
            listed = self.run_cli("sessions", "--store", root / ".edk-private", cwd=root)
            self.assertEqual(len(listed.stdout.splitlines()), 10)
            again = self.run_cli(*commands[1], cwd=root)
            self.assertEqual(again.returncode, 2)
            self.assertEqual(len(list((root / ".edk-private").glob("*.edk-private.json"))), 10)

    def test_noninteractive_collection_aborts_without_secret_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "manifest.json"
            public.write_bytes(encode_document(manifest().to_dict()))
            result = self.run_cli("collect", public, "--store", root / ".edk-private", cwd=root)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((root / ".edk-private").exists())
            self.assertNotIn("Traceback", result.stderr)

    @unittest.skipUnless(os.name == "posix", "real POSIX terminal echo check")
    def test_real_terminal_collection_disables_echo(self):
        import pty
        import select
        import signal
        import termios
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "manifest.json"
            public.write_bytes(encode_document(manifest().to_dict()))
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
                       PYTHONDONTWRITEBYTECODE="1")
            pid, fd = pty.fork()
            if pid == 0:
                os.execve(sys.executable, [sys.executable, "-m", "edk", "collect", str(public),
                                          "--store", str(root / ".edk-private")], env)
            status, output = None, b""
            try:
                deadline = time.monotonic() + 10
                for index in range(3):
                    while output.count(b"ambiguous, - unreadable: ") < index + 1:
                        self.assertLess(time.monotonic(), deadline, "terminal prompt timed out")
                        if select.select([fd], [], [], 0.1)[0]:
                            output += os.read(fd, 65536)
                    self.assertFalse(termios.tcgetattr(fd)[3] & termios.ECHO)
                    os.write(fd, b"00001\n")
                while time.monotonic() < deadline:
                    if select.select([fd], [], [], 0.05)[0]:
                        try:
                            output += os.read(fd, 65536)
                        except OSError:
                            pass  # Terminal returns EIO after child exit on some hosts.
                    done, child_status = os.waitpid(pid, os.WNOHANG)
                    if done:
                        status = child_status
                        break
                self.assertIsNotNone(status, "terminal collection did not exit")
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                self.assertNotIn(b"\r\n00001\r\n", output)
                self.assertEqual(len(list((root / ".edk-private").glob("*.edk-private.json"))), 1)
            finally:
                os.close(fd)
                if status is None:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)

    def test_mocked_non_echo_collection_and_input_error_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public = root / "manifest.json"
            public.write_bytes(encode_document(manifest().to_dict()))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    patch("sys.stdin.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True), \
                    patch("edk.research_cli.getpass.getpass", side_effect=["1", "?", "-"]):
                main(["collect", str(public), "--store", str(root / ".edk-private")])
            self.assertIn("Private session saved", out.getvalue())
            self.assertNotIn('"value"', out.getvalue())
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    patch("sys.stdin.isatty", return_value=True), patch("sys.stderr.isatty", return_value=True), \
                    patch("edk.research_cli.getpass.getpass", return_value="SENSITIVE-SENTINEL"):
                with self.assertRaises(SystemExit) as result:
                    main(["collect", str(public), "--store", str(root / "not-created")])
            self.assertEqual(result.exception.code, 2)
            self.assertNotIn("SENSITIVE-SENTINEL", err.getvalue())
            self.assertFalse((root / "not-created").exists())

    def test_synthetic_lifecycle_models_and_sram_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            for command in (("hardware-demo",), ("verify-models",),
                            ("simulate-lifecycle", "--months", "3", "--trials", "10",
                             "--maintenance-every", "1", "--output", Path(directory) / "lifecycle.json")):
                result = self.run_cli(*command, cwd=directory)
                self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(directory) / "lifecycle.json").read_text())
            self.assertTrue(report["synthetic_assumptions_only"])

    def test_physical_operation_without_lab_scope_opens_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        with patch("edk.linux_i2c.os.open") as opened, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as stopped:
                main(["hardware-probe", "--bus", "/dev/i2c-1"])
        self.assertEqual(stopped.exception.code, 2)
        opened.assert_not_called()
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
