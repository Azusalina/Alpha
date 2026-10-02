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
            self.assertEqual(self.call("health")["error"],
                             {"code": "MODEL_UNAVAILABLE", "message": "protected database unavailable"})
            response = self.call("submit", {"text": "我重视公平。", "partition": "rational"})
            self.assertEqual(response["error"], {"code": "MODEL_UNAVAILABLE", "message": "protected database unavailable"})
            if invalid is None:
                self.assertFalse(self.path.exists())
            else:
                self.assertEqual(self.path.read_bytes(), invalid)

    def test_authenticated_health_exposes_current_epoch_then_lock_omits_it(self):
        self.assertNotIn("model_epoch", self.call("health")["result"])
        self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
        self.assertIsNone(self.api._brain)  # Unlock itself reads no database.
        self.assertEqual(self.call("health")["result"]["model_epoch"], 0)
        info = self.api.brain.model.reset_info()
        self.api.brain.model.reset_model(confirmation="RESET_MODEL",
                                       expected_epoch=info["model_epoch"],
                                       expected_revision=info["input_revision"])
        self.assertEqual(self.call("health")["result"]["model_epoch"], 1)
        self.call("lock")
        with patch("core.api.BrainCore", side_effect=AssertionError("database accessed")):
            self.assertNotIn("model_epoch", self.call("health")["result"])
        self.assertIsNone(self.api._brain)

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

    def test_malformed_unlock_attempts_revoke_authorization_and_cached_brain(self):
        for params in ({"password": ""}, {"password": True}, {}, [],
                       {"password": self.password, "unknown": True}):
            with self.subTest(params_type=type(params).__name__):
                self.assertTrue(self.call("unlock", {"password": self.password})["ok"])
                self.assertTrue(self.call("state")["ok"])
                self.assertIsNotNone(self.api._brain)
                self.assertEqual(self.call("unlock", params)["error"]["code"], "INVALID_ARGUMENT")
                self.assertIsNone(self.api._brain)
                self.assertTrue(self.call("access_status")["result"]["locked"])
                self.assertEqual(self.call("state")["error"]["code"], "LOCKED")

    def test_cli_config_change_after_authorization_prevents_construction_and_trace(self):
        import core.cli as store_cli
        import model.__main__ as model_cli
        from core.access import AccessSession
        original_config = config_path(self.path).read_bytes()
        before = self.path.read_bytes()
        for module, constructor, action in ((store_cli, "MemoryStore", "list-sources"),
                                             (model_cli, "BrainModel", "state"),
                                             (model_cli, "BrainModel", "reset-info")):
            config_path(self.path).write_bytes(original_config)
            session = AccessSession(self.path)
            session.unlock(self.password)
            def changed_after_auth(_path):
                config_path(self.path).write_bytes(b"corrupted after authorization")
                return session
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(module, "authorize_database", side_effect=changed_after_auth), \
                    patch.object(module, constructor) as construct, \
                    patch.object(sys, "argv", ["alpha", "--db", str(self.path), action]), \
                    contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                with self.assertRaises(SystemExit):
                    module.main()
            construct.assert_not_called()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(errors.getvalue(), "access is locked\n")
            self.assertEqual(self.path.read_bytes(), before)

    def test_cli_config_change_during_construction_blocks_sensitive_branch(self):
        import core.cli as store_cli
        import model.__main__ as model_cli
        from core.access import AccessSession
        from unittest.mock import Mock
        original_config = config_path(self.path).read_bytes()
        for module, constructor, action, operation in (
                (store_cli, "MemoryStore", "list-sources", "list_sources"),
                (model_cli, "BrainModel", "state", "state")):
            config_path(self.path).write_bytes(original_config)
            session = AccessSession(self.path)
            session.unlock(self.password)
            instance = Mock()
            def change_in_constructor(*args, **kwargs):
                config_path(self.path).write_bytes(b"changed during construction")
                return instance
            with patch.object(module, "authorize_database", return_value=session), \
                    patch.object(module, constructor, side_effect=change_in_constructor), \
                    patch.object(sys, "argv", ["alpha", "--db", str(self.path), action]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    module.main()
            getattr(instance, operation).assert_not_called()
            if module is store_cli:
                instance.initialize.assert_not_called()

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
