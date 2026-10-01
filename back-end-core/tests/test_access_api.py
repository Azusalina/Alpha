"""Synthetic process-boundary access tests; no live database or credentials."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.access import AccessError, config_path, setup_access
from core.api import BrainAPI, METHODS, PUBLIC_METHODS, serve


class AccessAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "protected.sqlite3"
        self.password = "synthetic gate password"
        BrainAPI(self.path)
        setup_access(self.path, self.password)
        self.api = BrainAPI(self.path, trace=True)

    def call(self, method, params=None):
        return self.api.handle({"schema_version": 1, "id": "gate-test", "method": method,
                                "params": {} if params is None else params})

    def test_locked_startup_and_public_methods_never_open_database(self):
        before = self.path.read_bytes()
        self.assertIsNone(self.api._brain)

        with patch("core.api.BrainCore", side_effect=AssertionError("database accessed")):
            health = self.call("health")["result"]
            self.assertNotIn("model_epoch", health)
            self.assertEqual(health["access"], {"configured": True, "locked": True})
            self.assertEqual(set(health["methods"]), set(METHODS))
            self.assertTrue(self.call("baseline")["ok"])
            self.assertTrue(self.call("access_status")["ok"])
            self.assertTrue(self.call("lock")["ok"])
            self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
            self.assertIsNone(self.api._brain)
        self.assertEqual(self.path.read_bytes(), before)

    def test_configured_missing_invalid_or_empty_db_never_initializes_replacement(self):
        self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
        self.path.unlink()
        for invalid in (None, b"", b"synthetic unrelated database"):
            if invalid is not None:
                self.path.write_bytes(invalid)
            self.assertTrue(self.call("health")["ok"])
            self.assertNotIn("model_epoch", self.call("health")["result"])
            response = self.call("submit", {"text": "我重视公平。", "partition": "rational"})
            self.assertEqual(response["error"], {"code": "MODEL_UNAVAILABLE", "message": "protected database unavailable"})
            if invalid is None:
                self.assertFalse(self.path.exists())
            else:
                self.assertEqual(self.path.read_bytes(), invalid)

    def test_corrupt_config_health_is_static_and_removal_does_not_disable_gate(self):
        before = self.path.read_bytes()
        self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
        config_path(self.path).unlink()
        self.assertEqual(self.call("state")["error"]["code"], "LOCKED")
        self.assertEqual(self.call("health")["result"]["access"], {"configured": True, "locked": True})
        self.assertEqual(self.path.read_bytes(), before)
        config_path(self.path).write_bytes(b"invalid config")
        api = BrainAPI(self.path)
        health = api.handle({"schema_version": 1, "id": "corrupt", "method": "health", "params": {}})
        self.assertTrue(health["ok"])
        self.assertNotIn("model_epoch", health["result"])
        self.assertEqual(health["result"]["access"], {"configured": True, "locked": True})

    def test_every_sensitive_method_fails_locked_before_parameter_validation(self):
        before = self.path.read_bytes()
        with patch("core.api.BrainCore", side_effect=AssertionError("database accessed")):
            for method in set(METHODS) - PUBLIC_METHODS:
                for params in ({}, {"password": self.password, "unexpected": "private"}, []):
                    with self.subTest(method=method, params_type=type(params).__name__):
                        response = self.call(method, params)
                        self.assertEqual(response["error"], {"code": "LOCKED", "message": "access is locked"})
        self.assertEqual(self.path.read_bytes(), before)

    def test_unlock_lock_restart_and_configuration_change_revoke_access(self):
        self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
        submitted = self.call("submit", {"text": "我重视公平。", "partition": "rational"})
        self.assertTrue(submitted["ok"], submitted)
        source = submitted["result"]["source_id"]
        self.assertTrue(self.call("input_get", {"source_id": source})["ok"])
        self.assertTrue(self.call("lock")["result"]["locked"])
        self.assertIsNone(self.api._brain)
        self.assertEqual(self.call("input_get", {"source_id": source})["error"]["code"], "LOCKED")
        restarted = BrainAPI(self.path)
        self.assertTrue(restarted.access.status()["locked"])
        self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
        config_path(self.path).write_bytes(b"invalid synthetic access config")
        response = self.call("input_get", {"source_id": source})
        self.assertEqual(response["error"]["code"], "LOCKED")
        self.assertIsNone(self.api._brain)

    def test_password_types_bounds_unicode_and_failures_never_echo(self):
        for password in (True, 1, None, [], "", "\0", "\ud800", "x" * 1025, "😀" * 257):
            response = self.call("unlock", {"password": password})
            self.assertEqual(response["error"], {"code": "INVALID_ARGUMENT", "message": "invalid password"})
        secret = "not the synthetic gate password"
        stderr = io.StringIO()
        output = io.StringIO()
        request = {"schema_version": 1, "id": "wrong", "method": "unlock", "params": {"password": secret}}
        with contextlib.redirect_stderr(stderr):
            serve(self.api, io.StringIO(json.dumps(request) + "\n"), output)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "LOCKED")
        self.assertNotIn(secret, stderr.getvalue() + output.getvalue())
        with patch.object(self.api.access, "unlock", side_effect=AccessError(secret)):
            self.assertNotIn(secret, json.dumps(self.call("unlock", {"password": secret})))

    def test_cli_entry_points_reject_noninteractive_protected_access_without_db_touch(self):
        before = self.path.read_bytes()
        root = Path(__file__).resolve().parents[1]
        for module, action in (("core.cli", "init"), ("model", "state"), ("model", "reset-info")):
            process = subprocess.run([sys.executable, "-m", module, "--db", str(self.path), action],
                                     cwd=root, input=self.password + "\n", capture_output=True,
                                     text=True, timeout=10)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(process.stdout, "")
            self.assertNotIn(self.password, process.stderr)
            self.assertIn("access is locked", process.stderr)
            self.assertEqual(self.path.read_bytes(), before)

    def test_cli_uses_authorized_getpass_session_before_initialization(self):
        from core.cli import main
        with patch("core.security_cli._prompt", return_value=self.password) as prompt:
            with patch.object(sys, "argv", ["alpha-brain", "--db", str(self.path), "init"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    main()
        prompt.assert_called_once()
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
