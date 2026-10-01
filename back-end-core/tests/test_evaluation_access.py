"""Snapshot authorization checks using only fresh synthetic databases."""

import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from core.access import AccessError, AccessSession, setup_access
from model.engine import BrainModel
from model.evaluation import evaluate_database, main, read_snapshot

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "synthetic-test-password"


class EvaluationAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "PRIVATE_DB_CANARY.sqlite3"
        BrainModel(self.path)
        self.manifest = json.loads((ROOT / "docs/evaluation.example.json").read_text(encoding="utf-8"))

    def configure(self):
        # Real foundation contract, not a mocked verifier/config.
        setup_access(self.path, PASSWORD)
        return AccessSession(self.path)

    def test_unconfigured_existing_library_callers_stay_compatible(self):
        before = self.path.read_bytes()
        self.assertIn("fingerprint", read_snapshot(self.path))
        self.assertEqual(evaluate_database(self.path, self.manifest)["status"], "offline_experiment")
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(Path(str(self.path) + ".access.json").exists())

    def test_protected_locked_wrong_or_mismatched_sessions_fail_before_sqlite(self):
        session = self.configure()
        before = self.path.read_bytes()
        with patch("sqlite3.connect", side_effect=AssertionError("must authorize before database open")):
            for selected in (None, session, AccessSession(self.path.with_name("other.sqlite3"))):
                with self.subTest(session=selected), self.assertRaises(AccessError):
                    read_snapshot(self.path, access_session=selected)
                with self.assertRaises(AccessError):
                    evaluate_database(self.path, self.manifest, access_session=selected)
            with self.assertRaises(AccessError):
                session.unlock("wrong-synthetic-password")
            with self.assertRaises(AccessError):
                read_snapshot(self.path, access_session=session)
        self.assertEqual(before, self.path.read_bytes())

    def test_unlocked_snapshot_and_evaluation_are_read_only_and_relock_is_enforced(self):
        session = self.configure()
        before = {path.name: path.read_bytes() for path in self.path.parent.iterdir()}
        session.unlock(PASSWORD)
        snapshot = read_snapshot(self.path, access_session=session)
        result = evaluate_database(self.path, self.manifest, access_session=session)
        self.assertEqual(snapshot, result["snapshot"])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.path.parent.iterdir()})
        session.lock()
        with patch("sqlite3.connect", side_effect=AssertionError("relocked database must not open")), self.assertRaises(AccessError):
            read_snapshot(self.path, access_session=session)

    def test_cli_prompts_via_authorize_helper_then_passes_unlocked_session(self):
        self.configure()
        stdout = io.StringIO()
        cases_path = ROOT / "docs/evaluation.example.json"
        real_connect = sqlite3.connect
        prompted = []

        def prompt(label):
            prompted.append(label)
            return PASSWORD

        def connect(*args, **kwargs):
            self.assertEqual(len(prompted), 1, "prompt must precede all DB reads")
            return real_connect(*args, **kwargs)

        before = self.path.read_bytes()
        with patch.object(sys, "argv", ["model.evaluation", "--db", str(self.path), "--cases", str(cases_path)]), \
             patch("core.security_cli._prompt", side_effect=prompt), \
             patch("sqlite3.connect", side_effect=connect), redirect_stdout(stdout):
            main()
        self.assertEqual(json.loads(stdout.getvalue())["status"], "offline_experiment")
        self.assertEqual(before, self.path.read_bytes())
        self.assertNotIn(PASSWORD, stdout.getvalue())

    def test_cli_access_failure_is_generic_no_raw_exception_or_snapshot(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["model.evaluation", "--db", str(self.path), "--cases", str(ROOT / "docs/evaluation.example.json")]), \
             patch("model.evaluation.authorize_database", side_effect=AccessError("PRIVATE_EXCEPTION_CANARY")), \
             patch("sqlite3.connect", side_effect=AssertionError("denied database must not open")), \
             redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "evaluation access denied; no snapshot was read\n")

    def test_protected_cli_without_terminal_fails_safely(self):
        self.configure()
        result = subprocess.run([sys.executable, "-m", "model.evaluation", "--db", str(self.path),
                                 "--cases", str(ROOT / "docs/evaluation.example.json")],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, cwd=ROOT, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("PRIVATE_DB_CANARY", result.stderr)
        self.assertIn("evaluation access denied", result.stderr)


if __name__ == "__main__":
    unittest.main()
