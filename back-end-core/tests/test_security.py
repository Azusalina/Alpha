"""Security foundations: synthetic text and temporary databases ONLY."""

import io
import json
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch

from core import access, backup, security_cli
from core.access import AccessError, AccessSession, check_authorized, config_path, setup_access
from core.backup import BackupError, create_backup, restore_backup, validate_database
from core.store import MemoryStore


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'synthetic.sqlite3'
        self.store = MemoryStore(self.db)
        self.store.initialize()
        self.store.add_source('synthetic security fixture only')
        self.password = ' synthetic access password '
        self.backup_password = 'synthetic backup password'
        self.new_password = 'synthetic restored password'
        self.output = self.root / 'snapshot.alpha'
        self.target = self.root / 'restored.sqlite3'
        with access._attempt_lock:
            access._attempts.clear()

    def configured(self):
        setup_access(self.db, self.password)
        session = AccessSession(self.db)
        session.unlock(self.password)
        return session

    def make_backup(self):
        return create_backup(self.db, self.output, self.backup_password,
                             session=AccessSession(self.db))

    def restore(self, source=None):
        return restore_backup(source or self.output, self.target,
                              self.backup_password, self.new_password)

    def test_status_no_database_touch_and_legacy_without_dependency(self):
        missing = self.root / 'never-created.sqlite3'
        with patch('sqlite3.connect', side_effect=AssertionError('DB touched')), \
                patch('core.access.crypto', side_effect=AccessError('missing dependency')):
            session = AccessSession(missing)
            self.assertEqual(session.status(), {'configured': False, 'locked': False})
            session.require()
            check_authorized(missing)
            self.assertEqual(session.lock(), session.status())
            access.authorize_database(missing)
        self.assertFalse(missing.exists())

    def test_configured_initial_locked_status_no_database_touch(self):
        setup_access(self.db, self.password)
        with patch('sqlite3.connect', side_effect=AssertionError('DB touched')):
            session = AccessSession(self.db)
            self.assertEqual(session.status(), {'configured': True, 'locked': True})
            with self.assertRaises(AccessError):
                session.require()
            session.unlock(self.password)
            session.require()
            self.assertTrue(session.lock()['locked'])
        self.assertEqual(config_path(self.db).stat().st_mode & 0o777, 0o600)

    def test_wrong_password_generic_and_whitespace_preserved(self):
        setup_access(self.db, self.password)
        session = AccessSession(self.db)
        for password in ('wrong synthetic password', self.password.strip(), 'nul\x00pw', '\ud800'):
            with self.assertRaisesRegex(AccessError, '^authentication failed$'):
                session.unlock(password)
            self.assertTrue(session.status()['locked'])
        session.unlock(self.password)
        session.require()

    def test_password_limits(self):
        for value in ('', 'x' * 1025, '界' * 342, '\x00', '\udfff', None):
            with self.subTest(value=repr(value)[:20]), self.assertRaises(AccessError):
                access.password_bytes(value)
        self.assertEqual(access.password_bytes(' '), b' ')
        self.assertEqual(len(access.password_bytes('x' * 1024)), 1024)

    def test_refresh_changed_credentials_revokes_session(self):
        session = self.configured()
        path = config_path(self.db)
        path.unlink()
        setup_access(self.db, self.new_password)
        self.assertTrue(session.status()['locked'])
        with self.assertRaises(AccessError):
            session.require()
        session.unlock(self.new_password)
        session.require()
        # Even replacement with identical bytes invalidates an existing session.
        raw = path.read_bytes()
        path.unlink()
        with access.exclusive_file(path) as stream:
            stream.write(raw)
        with self.assertRaises(AccessError):
            session.require()

    def test_malformed_config_fails_closed_and_revokes(self):
        session = self.configured()
        path = config_path(self.db)
        valid = path.read_bytes()
        invalid = [b'{', b'null', b'{}', b'x' * 1025,
                   b'{"version":1,"version":1,"verifier":"x"}',
                   valid.replace(b'65536', b'99999'),
                   valid.replace(b'"version": 1', b'"version": true'),
                   valid.replace(b'$argon2id$', b'$argon2i$')]
        for data in invalid:
            with self.subTest(data=data[:25]):
                path.write_bytes(data)
                with self.assertRaises(AccessError):
                    session.status()
                with self.assertRaises(AccessError):
                    session.require()
        path.write_bytes(valid)
        self.assertTrue(session.status()['locked'])
        path.chmod(0o644)
        with self.assertRaises(AccessError):
            session.require()

    def test_symlink_and_nonregular_config_fail_closed(self):
        path = config_path(self.db)
        path.symlink_to(self.root / 'missing-config')
        with self.assertRaises(AccessError):
            AccessSession(self.db).status()
        path.unlink()
        os.mkfifo(path, 0o600)
        with self.assertRaises(AccessError):
            AccessSession(self.db).status()

    def test_configured_missing_dependency_fails_closed(self):
        session = self.configured()
        with patch('core.access.crypto', side_effect=AccessError('install security extra')):
            self.assertTrue(AccessSession(self.db).status()['locked'])
            with self.assertRaises(AccessError):
                session.require()
            with self.assertRaises(AccessError):
                AccessSession(self.db).unlock(self.password)

    def test_config_removal_locked_and_unlocked_sessions_fail_closed(self):
        unlocked = self.configured()
        locked = AccessSession(self.db)
        locked.status()
        config_path(self.db).unlink()
        for session in (locked, unlocked):
            for operation in (session.status, session.require, session.lock,
                              lambda: session.unlock(self.password)):
                with self.subTest(locked=session is locked), self.assertRaises(AccessError):
                    operation()
        # A fresh process/session cannot infer a deleted sidecar existed.
        AccessSession(self.db).require()

    def test_password_rotation_authenticated_atomic_and_revokes_sessions(self):
        session = self.configured()
        before = config_path(self.db).read_bytes()
        with self.assertRaises(AccessError):
            access.change_password(self.db, 'wrong old password', self.new_password)
        self.assertEqual(config_path(self.db).read_bytes(), before)
        access.change_password(self.db, self.password, self.new_password)
        self.assertEqual(config_path(self.db).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(AccessError):
            session.require()
        session.unlock(self.new_password)
        session.require()
        self.assertEqual(list(self.root.glob('.alpha-access-*')), [])

    def test_rotation_rechecks_fingerprint_and_does_not_overwrite_change(self):
        self.configured()
        real_config = access._config_bytes
        path = config_path(self.db)
        changed = path.read_bytes() + b'\n'
        def change_during_kdf(password):
            result = real_config(password)
            path.write_bytes(changed)
            return result
        with patch('core.access._config_bytes', side_effect=change_during_kdf):
            with self.assertRaises(AccessError):
                access.change_password(self.db, self.password, self.new_password)
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(list(self.root.glob('.alpha-access-*')), [])

    def test_rotation_unconfigured_or_invalid_new_password_never_enables_gate(self):
        with self.assertRaises(AccessError):
            access.change_password(self.db, self.password, self.new_password)
        self.assertFalse(config_path(self.db).exists())
        self.configured()
        before = config_path(self.db).read_bytes()
        with self.assertRaises(AccessError):
            access.change_password(self.db, self.password, '\x00')
        self.assertEqual(config_path(self.db).read_bytes(), before)

    def test_rate_limit_shared_across_sessions(self):
        setup_access(self.db, self.password)
        for _ in range(5):
            with self.assertRaisesRegex(AccessError, '^authentication failed$'):
                AccessSession(self.db).unlock('wrong password')
        with self.assertRaisesRegex(AccessError, 'temporarily limited'):
            AccessSession(self.db).unlock(self.password)

    def test_cli_helper_prompts_only_configured_and_sanitizes_errors(self):
        with patch('core.security_cli._prompt', side_effect=AssertionError('unexpected prompt')):
            access.authorize_database(self.db).require()
        setup_access(self.db, self.password)
        with patch('core.security_cli._prompt', return_value=self.password) as prompt:
            session = access.authorize_database(self.db)
            session.require()
            prompt.assert_called_once()
        with patch('core.security_cli._prompt', side_effect=RuntimeError('do not expose credentials')):
            with self.assertRaisesRegex(AccessError, '^access authorization failed$'):
                access.authorize_database(self.db)

    def test_configured_cli_missing_empty_or_nonregular_db_never_grants(self):
        setup_access(self.db, self.password)
        self.db.unlink()
        with patch('core.security_cli._prompt', return_value=self.password):
            with self.assertRaisesRegex(AccessError, '^access authorization failed$'):
                access.authorize_database(self.db)
            self.assertFalse(self.db.exists())
            self.db.touch()
            with self.assertRaises(AccessError):
                access.authorize_database(self.db)
            self.db.unlink()
            self.db.mkdir()
            with self.assertRaises(AccessError):
                access.authorize_database(self.db)
        missing = self.root / 'unconfigured.sqlite3'
        access.authorize_database(missing).require()
        self.assertFalse(missing.exists())

    def test_cli_rejects_non_tty_and_getpass_fallback(self):
        with patch('sys.stdin.isatty', return_value=False):
            with self.assertRaises(AccessError):
                security_cli._prompt('Synthetic password: ')
        with patch('sys.stdin.isatty', return_value=True), \
                patch('getpass.getpass', side_effect=security_cli.getpass.GetPassWarning('fallback')):
            with self.assertRaises(AccessError):
                security_cli._prompt('Synthetic password: ')

    def test_noninteractive_library_gate_and_db_mismatch(self):
        session = self.configured()
        with self.assertRaises(AccessError):
            check_authorized(self.db)
        check_authorized(self.db, session=session)
        with self.assertRaises(AccessError):
            check_authorized(self.root / 'other.sqlite3', session=session)
        session.lock()
        with self.assertRaises(AccessError):
            check_authorized(self.db, session=session)

    def test_setup_requires_existing_absolute_valid_db_exclusive(self):
        for path in (Path('relative.sqlite3'), self.root / 'missing.sqlite3'):
            with self.assertRaises((AccessError, OSError)):
                setup_access(path, self.password)
            self.assertFalse(config_path(path).exists())
        foreign = self.root / 'foreign.sqlite3'
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute('CREATE TABLE unrelated(value TEXT)')
        with self.assertRaises(BackupError):
            setup_access(foreign, self.password)
        setup_access(self.db, self.password)
        before = config_path(self.db).read_bytes()
        with self.assertRaises(FileExistsError):
            setup_access(self.db, self.new_password)
        self.assertEqual(config_path(self.db).read_bytes(), before)

    def test_roundtrip_fresh_gate_permissions_and_no_restored_verifier(self):
        session = self.configured()
        create_backup(self.db, self.output, self.backup_password, session=session)
        self.restore()
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(config_path(self.target).stat().st_mode & 0o777, 0o600)
        restored = AccessSession(self.target)
        self.assertTrue(restored.status()['locked'])
        with self.assertRaises(AccessError):
            restored.unlock(self.password)
        restored.unlock(self.new_password)
        self.assertNotEqual(config_path(self.db).read_bytes(), config_path(self.target).read_bytes())
        self.assertEqual(MemoryStore(self.target).list_sources(), self.store.list_sources())
        self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_locked_backup_and_existing_output_do_not_overwrite(self):
        setup_access(self.db, self.password)
        with self.assertRaises(AccessError):
            create_backup(self.db, self.output, self.backup_password, session=AccessSession(self.db))
        self.assertFalse(self.output.exists())
        session = AccessSession(self.db)
        session.unlock(self.password)
        self.output.write_bytes(b'synthetic sentinel')
        with self.assertRaises(FileExistsError):
            create_backup(self.db, self.output, self.backup_password, session=session)
        self.assertEqual(self.output.read_bytes(), b'synthetic sentinel')

    def test_backup_snapshot_failure_cleans_output_and_staging(self):
        with patch('core.backup._snapshot', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.make_backup()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_wrong_backup_password_and_invalid_new_password_leave_no_target(self):
        self.make_backup()
        with self.assertRaisesRegex(BackupError, 'authentication failed'):
            restore_backup(self.output, self.target, 'wrong synthetic pw', self.new_password)
        with self.assertRaises(AccessError):
            restore_backup(self.output, self.target, self.backup_password, '\x00')
        self.assertFalse(self.target.exists())
        self.assertFalse(config_path(self.target).exists())
        self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_tamper_truncate_trailing_and_header_bounds_cleanup(self):
        self.make_backup()
        raw = self.output.read_bytes()
        variants = [raw[:-1], raw[:backup.HEADER.size], raw + b'trailing',
                    raw[:backup.HEADER.size + 9] + bytes([raw[backup.HEADER.size + 9] ^ 1])
                    + raw[backup.HEADER.size + 10:],
                    b'UNKNOWN1' + raw[8:],
                    raw[:8] + struct.pack('>I', 0xffffffff) + raw[12:],
                    raw[:backup.HEADER.size] + struct.pack('>I', 0xffffffff) + raw[backup.HEADER.size + 4:]]
        for index, data in enumerate(variants):
            damaged = self.root / f'damaged-{index}.alpha'
            damaged.write_bytes(data)
            with self.subTest(index=index), self.assertRaises(BackupError):
                self.restore(damaged)
            self.assertFalse(self.target.exists())
            self.assertFalse(config_path(self.target).exists())
            self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def encrypted_fixture(self, data, tags=None):
        """Produce authenticated malformed content/end tags, using synthetic bytes."""
        b = backup._bindings()
        salt = os.urandom(16)
        key = access.crypto().kdf(32, self.backup_password.encode(), salt,
                                  opslimit=access.OPS, memlimit=access.MEM)
        state = b.crypto_secretstream_xchacha20poly1305_state()
        sh = b.crypto_secretstream_xchacha20poly1305_init_push(state, key)
        header = backup.HEADER.pack(backup.MAGIC, access.OPS, access.MEM, backup.CHUNK,
                                    len(data), salt, sh)
        stream = io.BytesIO(header)
        stream.seek(0, io.SEEK_END)
        parts = [data[i:i + backup.CHUNK] for i in range(0, len(data), backup.CHUNK)]
        for index, part in enumerate(parts):
            tag = tags[index] if tags else (3 if index == len(parts) - 1 else 0)
            encrypted = b.crypto_secretstream_xchacha20poly1305_push(state, part, header, tag)
            stream.write(backup.LENGTH.pack(len(encrypted)))
            stream.write(encrypted)
        damaged = self.root / 'crafted.alpha'
        damaged.write_bytes(stream.getvalue())
        return damaged

    def test_authenticated_missing_final_tag_and_early_final_rejected(self):
        for data, tags in ((self.db.read_bytes(), [0]),
                           (b'x' * (backup.CHUNK + 1), [3, 3])):
            damaged = self.encrypted_fixture(data, tags)
            with self.assertRaisesRegex(BackupError, 'authentication failed'):
                self.restore(damaged)
            self.assertFalse(self.target.exists())
            self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_authenticated_non_alpha_payload_rejected_and_cleaned(self):
        foreign = self.root / 'unrelated.sqlite3'
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute('CREATE TABLE foreign_data(value TEXT)')
        damaged = self.encrypted_fixture(foreign.read_bytes())
        with self.assertRaises(BackupError):
            self.restore(damaged)
        self.assertFalse(self.target.exists())
        self.assertFalse(config_path(self.target).exists())
        self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_restore_existing_db_config_or_sidecar_not_overwritten(self):
        self.make_backup()
        for path in (self.target, config_path(self.target), Path(str(self.target) + '-wal')):
            path.write_bytes(b'synthetic sentinel')
            with self.assertRaises(BackupError):
                self.restore()
            self.assertEqual(path.read_bytes(), b'synthetic sentinel')
            path.unlink()

    def test_symlink_targets_and_parent_rejected(self):
        self.make_backup()
        self.target.symlink_to(self.root / 'nonexistent')
        with self.assertRaises(AccessError):
            self.restore()
        self.assertFalse((self.root / 'nonexistent').exists())
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(AccessError):
            restore_backup(self.output, alias / 'target.sqlite3', self.backup_password, self.new_password)

    def test_restore_publication_failure_keeps_no_unprotected_database(self):
        self.make_backup()
        real_link = os.link
        def fail_database(src, dst, **kwargs):
            if Path(dst) == self.target:
                raise OSError('synthetic publication failure')
            return real_link(src, dst, **kwargs)
        with patch('core.backup.os.link', side_effect=fail_database):
            with self.assertRaises(OSError):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assertFalse(config_path(self.target).exists())
        self.assertEqual(list(self.root.glob('.alpha-*')), [])

    def test_postpublication_failure_removes_database_before_config(self):
        self.make_backup()
        real_sync = backup._sync_directory
        def fail_after_db(path):
            if self.target.exists():
                raise OSError('synthetic durability failure')
            real_sync(path)
        with patch('core.backup._sync_directory', side_effect=fail_after_db):
            with self.assertRaises(OSError):
                self.restore()
        self.assertFalse(self.target.exists())
        self.assertFalse(config_path(self.target).exists())

    def test_failed_database_cleanup_retains_gate(self):
        self.make_backup()
        real_sync = backup._sync_directory
        real_unlink = Path.unlink
        def fail_after_db(path):
            if self.target.exists():
                raise OSError('synthetic fsync failure')
            real_sync(path)
        def fail_unlink(path, *args, **kwargs):
            if path == self.target:
                raise OSError('synthetic unlink failure')
            return real_unlink(path, *args, **kwargs)
        with patch('core.backup._sync_directory', side_effect=fail_after_db), \
                patch.object(Path, 'unlink', fail_unlink):
            with self.assertRaises(OSError):
                self.restore()
        self.assertTrue(self.target.exists())
        self.assertTrue(config_path(self.target).exists())
        with self.assertRaises(AccessError):
            AccessSession(self.target).require()

    def test_multichunk_roundtrip_randomized_ciphertext(self):
        self.store.add_source('synthetic chunk ' * 10000)
        self.make_backup()
        second = self.root / 'second.alpha'
        create_backup(self.db, second, self.backup_password, session=AccessSession(self.db))
        self.assertNotEqual(self.output.read_bytes(), second.read_bytes())
        self.restore()
        self.assertEqual(MemoryStore(self.target).list_sources(), self.store.list_sources())

    def test_format_file_limits_reject_before_derivation(self):
        with patch('core.backup.MAX_DATABASE', 1):
            with self.assertRaises(BackupError):
                validate_database(self.db)
        self.make_backup()
        bindings = backup._bindings()
        with patch('core.backup.MAX_BACKUP', 1), \
                patch('core.backup.crypto', side_effect=AssertionError('KDF before bound')):
            # _bindings consults dependency before file parsing, but no KDF.
            with patch('core.backup._bindings', return_value=bindings):
                with self.assertRaises(BackupError):
                    backup._decrypt(self.output, self.root / 'bounded.sqlite3', self.backup_password)
        self.assertFalse((self.root / 'bounded.sqlite3').exists())

    def test_wal_snapshot_includes_committed_excludes_uncommitted(self):
        with closing(sqlite3.connect(self.db)) as writer, writer:
            writer.execute('PRAGMA journal_mode=WAL')
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute("INSERT INTO sources VALUES ('wal', 'synthetic WAL commit', 'input', NULL, 'now')")
            writer.commit()
            self.assertTrue(Path(str(self.db) + '-wal').exists())
            writer.execute("INSERT INTO sources VALUES ('uncommitted', 'synthetic not committed', 'input', NULL, 'now')")
            self.make_backup()
            writer.rollback()
            self.restore()
        ids = {row['id'] for row in MemoryStore(self.target).list_sources()}
        self.assertIn('wal', ids)
        self.assertNotIn('uncommitted', ids)

    def test_model_schema_and_baseline_roundtrip(self):
        from model.engine import BrainModel
        BrainModel(self.db)
        validate_database(self.db)
        self.make_backup()
        self.restore()
        validate_database(self.target)
        with closing(sqlite3.connect(self.target)) as db, db:
            db.execute("UPDATE brain_meta SET value='synthetic wrong baseline' WHERE key='baseline_sha256'")
        with self.assertRaises(BackupError):
            validate_database(self.target)

    def test_integrity_foreign_key_and_schema_guards(self):
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("INSERT INTO candidates VALUES ('dangling', 'missing', 'claim', 'evidence', 'pending', 'now', NULL)")
        with self.assertRaises(BackupError):
            validate_database(self.db)
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute('DELETE FROM candidates')
            db.execute('ALTER TABLE sources ADD COLUMN unexpected TEXT')
        with self.assertRaises(BackupError):
            validate_database(self.db)
        broken = self.root / 'broken.sqlite3'
        broken.write_bytes(b'synthetic corrupt database')
        with self.assertRaises(BackupError):
            validate_database(broken)

    def test_cli_status_subprocess_and_no_password_argument(self):
        missing = self.root / 'missing.sqlite3'
        run = subprocess.run([sys.executable, '-m', 'core.security_cli', 'status', '--db', str(missing)],
                             capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(run.stdout), {'configured': False, 'locked': False})
        self.assertFalse(missing.exists())
        run = subprocess.run([sys.executable, '-m', 'core.security_cli', 'setup', '--db', str(self.db)],
                             input='', capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(config_path(self.db).exists())


if __name__ == '__main__':
    unittest.main()
