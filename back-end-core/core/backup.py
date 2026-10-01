"""Versioned, bounded encrypted SQLite snapshots and fresh-target recovery."""

from __future__ import annotations

import os
import hashlib
import sqlite3
import stat
import struct
import tempfile
import time
from contextlib import closing
from pathlib import Path

from .access import (AccessError, AccessSession, MEM, OPS, _config_bytes,
                     absolute_path, config_path, crypto, exclusive_file,
                     password_attempt, password_bytes)

CHUNK = 64 * 1024
MAX_DATABASE = 1024 * 1024 * 1024
MAX_BACKUP = MAX_DATABASE + (MAX_DATABASE // CHUNK + 1) * 21 + 128
MAGIC = b'ALPHABK1'
# Magic/version, Argon2id ops and memory, chunk size, plaintext length, salt,
# secretstream header. All 68 bytes are authenticated as AD on every record.
HEADER = struct.Struct('>8sIIIQ16s24s')
LENGTH = struct.Struct('>I')


class BackupError(ValueError):
    """Credential-free backup/restore failure."""


def _bindings():
    crypto()
    from nacl import bindings
    return bindings


def _regular(path: Path, limit: int) -> None:
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise BackupError("invalid file or size limit exceeded")


def _schema(db):
    tables = [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    result = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        result[table] = (list(db.execute(f'PRAGMA table_info({quoted})')),
                         list(db.execute(f'PRAGMA foreign_key_list({quoted})')))
    return result


def _schema_objects(db):
    """Include exact DDL: constraints, indexes and production consent triggers."""
    return list(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master "
                           "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"))


def validate_database(path: str | Path) -> None:
    """Read-only integrity/FK/current schema check; no initialization or migration."""
    path = absolute_path(path)
    _regular(path, MAX_DATABASE)
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise BackupError("database integrity check failed")
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise BackupError("database foreign key check failed")
            actual = _schema(db)
            actual_objects = _schema_objects(db)
            model_database = any(name.startswith('brain_') for name in actual)
            if model_database:
                from model.catalog import BASELINE_PATH
                row = db.execute("SELECT value FROM brain_meta WHERE key='baseline_sha256'").fetchone()
                if row != (hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest(),):
                    raise BackupError("model baseline fingerprint does not match")
            db.rollback()
        # Derive the actual current schema from production initializers ONLY in a
        # throwaway synthetic database. Never initialize or migrate the input.
        with tempfile.TemporaryDirectory(prefix='alpha-schema-') as temp:
            reference = Path(temp) / 'reference.sqlite3'
            if model_database:
                from model.reset import verify_existing
                verify_existing(path)  # Existing read-only baseline verification.
                from model.engine import BrainModel
                BrainModel(reference)
            else:
                from .store import MemoryStore
                MemoryStore(reference).initialize()
            with closing(sqlite3.connect(reference)) as db:
                expected = _schema(db)
                expected_objects = _schema_objects(db)
        if actual != expected or actual_objects != expected_objects:
            raise BackupError("unsupported Alpha database schema")
    except (sqlite3.Error, RuntimeError, ValueError) as error:
        if isinstance(error, BackupError):
            raise
        raise BackupError("not a valid current Alpha database") from None


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _snapshot(source: Path, target: Path) -> None:
    with exclusive_file(target):
        pass
    deadline = time.monotonic() + 60
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            page_size = src.execute('PRAGMA page_size').fetchone()[0]
            def progress(status, remaining, total):
                if total * page_size > MAX_DATABASE or time.monotonic() > deadline:
                    raise BackupError("snapshot size or time limit exceeded")
            src.backup(dst, pages=256, progress=progress, sleep=0.01)
            dst.execute('PRAGMA journal_mode=DELETE')
    _regular(target, MAX_DATABASE)


def create_backup(db_path: str | Path, output_path: str | Path, password: str,
                  *, session: AccessSession) -> Path:
    source, output = absolute_path(db_path), absolute_path(output_path)
    if session.db_path != source:
        raise AccessError("access session database mismatch")
    session.require()
    encoded = password_bytes(password)
    validate_database(source)
    b = _bindings()
    created = False
    try:
        with exclusive_file(output) as stream:
            created = True
            with tempfile.TemporaryDirectory(prefix='.alpha-backup-', dir=output.parent) as temp:
                os.chmod(temp, 0o700)
                snapshot = Path(temp) / 'snapshot.sqlite3'
                _snapshot(source, snapshot)
                validate_database(snapshot)
                session.require()
                size = snapshot.stat().st_size
                salt = os.urandom(16)
                key = crypto().kdf(b.crypto_secretstream_xchacha20poly1305_KEYBYTES,
                                   encoded, salt, opslimit=OPS, memlimit=MEM)
                state = b.crypto_secretstream_xchacha20poly1305_state()
                stream_header = b.crypto_secretstream_xchacha20poly1305_init_push(state, key)
                del key
                header = HEADER.pack(MAGIC, OPS, MEM, CHUNK, size, salt, stream_header)
                stream.write(header)
                with snapshot.open('rb') as plain:
                    remaining = size
                    while remaining:
                        data = plain.read(min(CHUNK, remaining))
                        if not data:
                            raise BackupError("incomplete snapshot")
                        remaining -= len(data)
                        tag = (b.crypto_secretstream_xchacha20poly1305_TAG_FINAL if not remaining
                               else b.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE)
                        ciphertext = b.crypto_secretstream_xchacha20poly1305_push(state, data, header, tag)
                        stream.write(LENGTH.pack(len(ciphertext)))
                        stream.write(ciphertext)
                session.require()
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(output.parent)
        return output
    except BaseException:
        if created:
            output.unlink()
        raise


def _exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise BackupError("backup authentication failed")
    return data


def _decrypt(source: Path, destination: Path, password: str) -> None:
    encoded = password_bytes(password)
    b = _bindings()
    from nacl.exceptions import CryptoError
    password_attempt('restore:' + str(source))
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not HEADER.size < info.st_size <= MAX_BACKUP:
                raise BackupError("invalid backup size")
            header = _exact(stream, HEADER.size)
            magic, ops, mem, chunk, size, salt, stream_header = HEADER.unpack(header)
            if (magic != MAGIC or ops != OPS or mem != MEM or chunk != CHUNK
                    or not 0 < size <= MAX_DATABASE):
                raise BackupError("unsupported backup header")
            key = crypto().kdf(b.crypto_secretstream_xchacha20poly1305_KEYBYTES,
                               encoded, salt, opslimit=ops, memlimit=mem)
            state = b.crypto_secretstream_xchacha20poly1305_state()
            b.crypto_secretstream_xchacha20poly1305_init_pull(state, stream_header, key)
            del key
            with exclusive_file(destination) as plain:
                remaining = size
                while remaining:
                    length = LENGTH.unpack(_exact(stream, LENGTH.size))[0]
                    expected = min(chunk, remaining)
                    if length != expected + b.crypto_secretstream_xchacha20poly1305_ABYTES:
                        raise BackupError("backup authentication failed")
                    data, tag = b.crypto_secretstream_xchacha20poly1305_pull(
                        state, _exact(stream, length), header)
                    remaining -= len(data)
                    expected_tag = (b.crypto_secretstream_xchacha20poly1305_TAG_FINAL if not remaining
                                    else b.crypto_secretstream_xchacha20poly1305_TAG_MESSAGE)
                    if len(data) != expected or tag != expected_tag:
                        raise BackupError("backup authentication failed")
                    plain.write(data)
                if stream.read(1):
                    raise BackupError("backup authentication failed")
                plain.flush()
                os.fsync(plain.fileno())
    except (ValueError, RuntimeError, CryptoError) as error:
        if isinstance(error, (BackupError, AccessError)):
            raise
        raise BackupError("backup authentication failed") from None


def restore_backup(backup_path: str | Path, target_path: str | Path,
                   password: str, new_password: str) -> Path:
    """Never overwrite: install a NEW verifier before publishing a validated DB."""
    source, target = absolute_path(backup_path), absolute_path(target_path)
    access = config_path(target)
    for path in (target, access, Path(str(target) + '-wal'), Path(str(target) + '-shm'),
                 Path(str(target) + '-journal')):
        if os.path.lexists(path):
            raise BackupError("restore requires a fresh target and access configuration")
    # Validate and generate the mandatory new password before exposing plaintext.
    config = _config_bytes(new_password)
    published_config = published_db = False
    try:
        with tempfile.TemporaryDirectory(prefix='.alpha-restore-', dir=target.parent) as temp:
            os.chmod(temp, 0o700)
            staged = Path(temp) / 'database.sqlite3'
            _decrypt(source, staged, password)
            validate_database(staged)
            staged_config = Path(temp) / 'access.json'
            with exclusive_file(staged_config) as stream:
                stream.write(config)
                stream.flush()
                os.fsync(stream.fileno())
            # Hard links are exclusive (EEXIST), same filesystem, never replace.
            os.link(staged_config, access, follow_symlinks=False)
            published_config = True
            _sync_directory(target.parent)
            os.link(staged, target, follow_symlinks=False)
            published_db = True
            _sync_directory(target.parent)
        return target
    except BaseException:
        # Remove DB first; if removal fails, keep its gate rather than expose it.
        if published_db:
            target.unlink()
        if published_config:
            access.unlink()
        raise
