"""Strict optional feedback schemas; synthetic temporary databases only."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import backup
from core.access import AccessError, AccessSession, config_path, setup_access
from core.api import BrainAPI
from core.backup import BackupError, create_backup, restore_backup, validate_database
from core.store import MemoryStore
from model import preferences
from model.engine import BrainModel


class HybridBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alpha-hybrid-backup-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.sqlite3"
        self.password = "synthetic access password"
        self.backup_password = "synthetic backup password"
        self.new_password = "synthetic restored password"

    @staticmethod
    def call(api, method, **params):
        return api.handle({"schema_version": 1, "id": "synthetic-backup-test",
                           "method": method, "params": params})

    @staticmethod
    def dump(path):
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            return tuple(db.iterdump())

    @staticmethod
    def fingerprint(path):
        info = path.stat()
        return path.read_bytes(), info.st_mtime_ns, info.st_mode

    def populated_api(self):
        api = BrainAPI(self.path)
        result = self.call(api, "submit", text="Synthetic choice source.",
                           partition="rational", exclamation=True)
        self.assertTrue(result["ok"], result)
        source_id = result["result"]["source_id"]
        info = api.brain.model.reset_info()
        feedback = self.call(
            api, "choice_feedback_set", source_id=source_id, event_id="synthetic-event",
            domain="daily", options=[
                {"id": "actual", "impacts": {"value.fairness": 1}},
                {"id": "endorsed", "impacts": {"value.fairness": -1}}],
            actual_choice_id="actual", endorsed_choice_id="endorsed",
            endorsement_partition="rational", training_consent=True,
            reason="Synthetic reviewed feedback only.",
            expected_source_version=api.brain.input_get(source_id)["source_version"],
            expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])
        self.assertTrue(feedback["ok"], feedback)
        return api, source_id

    def execute(self, path, *statements):
        with closing(sqlite3.connect(path)) as db, db:
            for statement in statements:
                db.execute(statement)

    def rejected_unchanged(self, path, message=None):
        before = self.fingerprint(path)
        if message is None:
            with self.assertRaises(BackupError):
                validate_database(path)
        else:
            with self.assertRaisesRegex(BackupError, message):
                validate_database(path)
        self.assertEqual(self.fingerprint(path), before)

    def test_hybrid_validation_uses_production_initializer_only_on_reference(self):
        self.populated_api()
        before = self.fingerprint(self.path)
        children = set(self.root.iterdir())
        initialized = []
        initialize = preferences.initialize
        connect = sqlite3.connect
        input_connections = []

        def reference_only(db):
            target = Path(db.execute("PRAGMA database_list").fetchone()[2])
            self.assertNotEqual(target, self.path)
            initialized.append(target)
            initialize(db)

        def read_only_input(database, *args, **kwargs):
            if str(database).startswith(self.path.as_uri()):
                self.assertEqual(database, self.path.as_uri() + "?mode=ro")
                self.assertTrue(kwargs.get("uri"))
                input_connections.append(database)
            elif str(database) == str(self.path):
                self.fail("input opened without read-only URI")
            return connect(database, *args, **kwargs)

        with patch("model.preferences.initialize", side_effect=reference_only), \
                patch("sqlite3.connect", side_effect=read_only_input):
            validate_database(self.path)
        self.assertEqual(len(initialized), 1)
        self.assertTrue(input_connections)
        self.assertFalse(initialized[0].exists())
        self.assertEqual(self.fingerprint(self.path), before)
        self.assertEqual(set(self.root.iterdir()), children)

    def test_protected_api_setup_and_locked_feedback_access(self):
        _, source_id = self.populated_api()
        before = self.fingerprint(self.path)
        setup_access(self.path, self.password)
        self.assertEqual(self.fingerprint(self.path), before)
        self.assertEqual(config_path(self.path).stat().st_mode & 0o777, 0o600)
        api = BrainAPI(self.path)
        self.assertIsNone(api._brain)
        denied = self.call(api, "choice_feedback_get", source_id=source_id)
        self.assertEqual(denied["error"]["code"], "LOCKED")
        with patch("core.api.BrainCore", side_effect=AssertionError("locked DB access")):
            self.assertTrue(self.call(api, "health")["result"]["access"]["locked"])
            self.assertTrue(self.call(api, "unlock", password=self.password)["ok"])
        self.assertEqual(self.fingerprint(self.path), before)
        feedback = self.call(api, "choice_feedback_get", source_id=source_id)
        self.assertTrue(feedback["ok"], feedback)
        self.assertEqual(feedback["result"]["records"][0]["actual_choice_id"], "actual")
        self.assertTrue(self.call(api, "lock")["ok"])
        self.assertEqual(self.call(api, "choice_feedback_get", source_id=source_id)
                         ["error"]["code"], "LOCKED")

    def test_hybrid_encrypted_roundtrip_preserves_feedback_and_fresh_gate(self):
        api, source_id = self.populated_api()
        # Historical feedback must survive reset without becoming current again.
        info = api.brain.model.reset_info()
        api.brain.model.reset_model(confirmation="RESET_MODEL",
                                   expected_epoch=info["model_epoch"],
                                   expected_revision=info["input_revision"])
        expected = self.call(api, "choice_feedback_get", source_id=source_id)["result"]
        self.assertFalse(expected["records"][0]["model_active"])
        before = self.fingerprint(self.path)
        setup_access(self.path, self.password)
        session = AccessSession(self.path)
        output = self.root / "snapshot.alpha"
        target = self.root / "restored.sqlite3"
        with self.assertRaises(AccessError):
            create_backup(self.path, output, self.backup_password, session=session)
        self.assertFalse(output.exists())
        session.unlock(self.password)
        self.assertEqual(create_backup(self.path, output, self.backup_password,
                                       session=session), output)
        self.assertEqual(restore_backup(output, target, self.backup_password,
                                       self.new_password), target)
        validate_database(target)
        self.assertEqual(self.fingerprint(self.path), before)
        self.assertEqual(self.dump(target), self.dump(self.path))
        restored = BrainAPI(target)
        self.assertEqual(self.call(restored, "choice_feedback_get", source_id=source_id)
                         ["error"]["code"], "LOCKED")
        self.assertFalse(self.call(restored, "unlock", password=self.password)["ok"])
        self.assertTrue(self.call(restored, "unlock", password=self.new_password)["ok"])
        self.assertEqual(self.call(restored, "choice_feedback_get", source_id=source_id)
                         ["result"], expected)
        self.assertNotEqual(config_path(target).read_bytes(), config_path(self.path).read_bytes())
        for path in (output, target, config_path(target)):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        published = self.fingerprint(target), config_path(target).read_bytes()
        with self.assertRaisesRegex(BackupError, "fresh target"):
            restore_backup(output, target, self.backup_password, self.new_password)
        self.assertEqual((self.fingerprint(target), config_path(target).read_bytes()), published)

    def test_old_model_and_standalone_store_roundtrip_without_preferences(self):
        for kind in ("model", "store"):
            with self.subTest(kind=kind):
                path = self.root / (kind + ".sqlite3")
                if kind == "model":
                    BrainModel(path).submit("Synthetic legacy model source.",
                                            partition="rational", exclamation=True)
                else:
                    store = MemoryStore(path)
                    store.initialize()
                    store.add_source("Synthetic standalone source.")
                before = self.fingerprint(path)
                with patch("model.preferences.initialize",
                           side_effect=AssertionError("legacy preferences migration")):
                    validate_database(path)
                    setup_access(path, self.password)
                    session = AccessSession(path)
                    session.unlock(self.password)
                    output = self.root / (kind + ".alpha")
                    target = self.root / (kind + "-restored.sqlite3")
                    create_backup(path, output, self.backup_password, session=session)
                    restore_backup(output, target, self.backup_password, self.new_password)
                    validate_database(target)
                self.assertEqual(self.fingerprint(path), before)
                self.assertEqual(self.dump(target), self.dump(path))
                with closing(sqlite3.connect(target)) as db:
                    self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master "
                                                 "WHERE name='brain_choice_feedback'").fetchone())

    def test_optional_table_requires_exact_production_ddl(self):
        replacements = (
            ("length(event_id) BETWEEN 1 AND 128", "length(event_id) BETWEEN 1 AND 129"),
            ("source_version >= 0", "source_version >= -1"),
            ("model_epoch >= 0", "model_epoch >= -1"),
            ("length(body_digest) = 64", "length(body_digest) = 63"),
            ("<= 65536", "<= 65537"),
            ("ON DELETE CASCADE", "ON DELETE RESTRICT"),
            ("REFERENCES sources(id)", "REFERENCES sources(body)"),
            ("source_version INTEGER", "source_version TEXT"),
            ("PRIMARY KEY (source_id, event_id)", "PRIMARY KEY (event_id, source_id)"),
        )
        for number, (old, new) in enumerate(replacements):
            with self.subTest(replacement=new):
                path = self.root / f"ddl-{number}.sqlite3"
                BrainAPI(path)
                with closing(sqlite3.connect(path)) as db, db:
                    ddl = db.execute("SELECT sql FROM sqlite_master "
                                     "WHERE name='brain_choice_feedback'").fetchone()[0]
                    self.assertIn(old, ddl)
                    db.execute("DROP TABLE brain_choice_feedback")
                    db.execute(ddl.replace(old, new))
                    db.execute("CREATE INDEX brain_choice_feedback_epoch "
                               "ON brain_choice_feedback(model_epoch,source_id,event_id)")
                self.rejected_unchanged(path)

    def test_missing_changed_and_extra_indexes_rejected(self):
        variants = (
            None,
            "CREATE INDEX brain_choice_feedback_epoch ON "
            "brain_choice_feedback(source_id,model_epoch,event_id)",
            "CREATE INDEX brain_choice_feedback_epoch ON "
            "brain_choice_feedback(model_epoch,source_id,event_id) WHERE model_epoch=0",
            "CREATE UNIQUE INDEX brain_choice_feedback_epoch ON "
            "brain_choice_feedback(model_epoch,source_id,event_id)",
        )
        for number, ddl in enumerate(variants):
            with self.subTest(ddl=ddl):
                path = self.root / f"index-{number}.sqlite3"
                BrainAPI(path)
                self.execute(path, "DROP INDEX brain_choice_feedback_epoch")
                if ddl:
                    self.execute(path, ddl)
                self.rejected_unchanged(path, "unsupported Alpha database schema")

    def test_unknown_tables_views_indexes_and_triggers_rejected(self):
        variants = (
            "CREATE TABLE brain_choice_feedback_extra (value TEXT)",
            "CREATE TABLE unexpected (value TEXT)",
            "ALTER TABLE brain_choice_feedback ADD COLUMN unexpected TEXT",
            "CREATE VIEW unexpected AS SELECT * FROM brain_choice_feedback",
            "CREATE INDEX feedback_extra ON brain_choice_feedback(event_id)",
            "CREATE TRIGGER feedback_extra AFTER INSERT ON brain_choice_feedback "
            "BEGIN DELETE FROM brain_choice_feedback; END",
        )
        for number, ddl in enumerate(variants):
            with self.subTest(ddl=ddl):
                path = self.root / f"extra-{number}.sqlite3"
                BrainAPI(path)
                self.execute(path, ddl)
                self.rejected_unchanged(path, "unsupported Alpha database schema")

    def test_missing_and_tampered_base_consent_trigger_rejected(self):
        for tampered in (False, True):
            with self.subTest(tampered=tampered):
                path = self.root / f"trigger-{tampered}.sqlite3"
                BrainAPI(path)
                with closing(sqlite3.connect(path)) as db, db:
                    name, table = db.execute("SELECT name,tbl_name FROM sqlite_master "
                                             "WHERE type='trigger' ORDER BY name LIMIT 1").fetchone()
                    db.execute(f'DROP TRIGGER "{name}"')
                    if tampered:
                        db.execute(f'CREATE TRIGGER "{name}" AFTER INSERT ON "{table}" '
                                   'BEGIN SELECT 1; END')
                self.rejected_unchanged(path, "unsupported Alpha database schema")

    def test_optional_index_without_table_and_standalone_extension_rejected(self):
        BrainModel(self.path)
        self.execute(self.path, "CREATE INDEX brain_choice_feedback_epoch ON sources(id)")
        self.rejected_unchanged(self.path, "unsupported Alpha database schema")
        standalone = self.root / "standalone-extension.sqlite3"
        MemoryStore(standalone).initialize()
        with closing(sqlite3.connect(standalone)) as db, db:
            preferences.initialize(db)
        self.rejected_unchanged(standalone)

    def test_feedback_foreign_key_violation_rejected_without_repair(self):
        self.populated_api()
        self.execute(self.path, "UPDATE brain_choice_feedback SET source_id='synthetic-missing'")
        self.rejected_unchanged(self.path, "foreign key check failed")
        with self.assertRaises(BackupError):
            setup_access(self.path, self.password)
        self.assertFalse(config_path(self.path).exists())

    def test_hybrid_baseline_tampering_rejected(self):
        self.populated_api()
        self.execute(self.path, "UPDATE brain_meta SET value='synthetic wrong baseline' "
                     "WHERE key='baseline_sha256'")
        self.rejected_unchanged(self.path, "baseline fingerprint")

    def test_authenticated_tampered_schema_restore_never_publishes(self):
        self.populated_api()
        self.execute(self.path, "DROP INDEX brain_choice_feedback_epoch")
        before = self.fingerprint(self.path)
        with self.assertRaises(BackupError):
            setup_access(self.path, self.password)
        self.assertFalse(config_path(self.path).exists())
        output = self.root / "invalid-schema.alpha"
        # Manufacture an authenticated invalid fixture, bypassing ONLY the
        # producer's validation; restore must still validate the decrypted DB.
        with patch.object(backup, "validate_database"):
            create_backup(self.path, output, self.backup_password,
                          session=AccessSession(self.path))
        target = self.root / "never-published.sqlite3"
        with self.assertRaisesRegex(BackupError, "unsupported Alpha database schema"):
            restore_backup(output, target, self.backup_password, self.new_password)
        self.assertFalse(target.exists())
        self.assertFalse(config_path(target).exists())
        self.assertEqual(self.fingerprint(self.path), before)
        self.assertFalse(list(self.root.glob(".alpha-restore-*")))


if __name__ == "__main__":
    unittest.main()
