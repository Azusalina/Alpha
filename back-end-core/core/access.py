"""Opt-in local request gate. This does not encrypt SQLite or defend its owner."""

from __future__ import annotations

import json
import os
import re
import stat
import threading
import tempfile
import time
from collections import deque
from pathlib import Path


class AccessError(ValueError):
    """Safe, credential-free error suitable for an integration boundary."""


MAX_PASSWORD_BYTES = 1024
CONFIG_LIMIT = 1024
OPS = 2
MEM = 64 * 1024 * 1024
_VERIFIER = re.compile(r"\$argon2id\$v=19\$m=65536,t=2,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}")
_attempts: dict[str, deque] = {}
_attempt_lock = threading.Lock()


def password_bytes(password: str) -> bytes:
    """Preserve whitespace; reject NUL, surrogates, empty and oversized inputs."""
    if not isinstance(password, str) or not 1 <= len(password) <= MAX_PASSWORD_BYTES or '\x00' in password:
        raise AccessError("invalid password")
    try:
        encoded = password.encode('utf-8', errors='strict')
    except UnicodeError:
        raise AccessError("invalid password") from None
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise AccessError("invalid password")
    return encoded


def crypto():
    # Legacy status/require paths work without the optional dependency.
    try:
        from nacl import pwhash
        return pwhash.argon2id
    except ImportError:
        raise AccessError("install the security optional extra") from None


def config_path(db_path: str | Path) -> Path:
    return Path(str(db_path) + '.access.json')


def absolute_path(path: str | Path) -> Path:
    """Reject symlinks in every existing component and require an existing parent."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise AccessError("an absolute path without symlinks is required")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise AccessError("an absolute path without symlinks is required")
    if not path.parent.is_dir():
        raise AccessError("target parent must already exist")
    return path


def exclusive_file(path: Path):
    """Create only a new regular file, private before any content is written."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, 'wb')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate config key")
        result[key] = value
    return result


def _read_config(path: Path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None, None
    except OSError:
        raise AccessError("access configuration invalid") from None
    try:
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > CONFIG_LIMIT:
                raise ValueError("invalid config file")
            raw = stream.read(CONFIG_LIMIT + 1)
        value = json.loads(raw, object_pairs_hook=_pairs)
        if (not isinstance(value, dict) or set(value) != {'version', 'verifier'}
                or type(value['version']) is not int or value['version'] != 1
                or not isinstance(value['verifier'], str) or not _VERIFIER.fullmatch(value['verifier'])):
            raise ValueError("invalid config")
        fingerprint = (raw, info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
        return value['verifier'].encode('ascii'), fingerprint
    except (OSError, ValueError, UnicodeError):
        raise AccessError("access configuration invalid") from None


def _config_bytes(password: str) -> bytes:
    encoded = password_bytes(password)
    verifier = crypto().str(encoded, opslimit=OPS, memlimit=MEM).decode('ascii')
    if not _VERIFIER.fullmatch(verifier):
        raise AccessError("unsupported password verifier")
    return (json.dumps({'version': 1, 'verifier': verifier}) + '\n').encode('ascii')


def setup_access(db_path: str | Path, password: str) -> Path:
    """Offline explicit setup for an existing Alpha DB; never overwrite a config."""
    from .backup import _sync_directory, validate_database
    path = absolute_path(db_path)
    validate_database(path)
    data = _config_bytes(password)
    target = config_path(path)
    with exclusive_file(target) as stream:
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            # Retain an invalid config on failure: fail closed until explicit repair.
            raise
    _sync_directory(path.parent)
    return target


def password_attempt(scope: str) -> None:
    """At most five KDF attempts per scope per rolling minute in this process."""
    now = time.monotonic()
    with _attempt_lock:
        queue = _attempts.setdefault(scope, deque())
        while queue and queue[0] <= now - 60:
            queue.popleft()
        if len(queue) >= 5:
            raise AccessError("password attempts temporarily limited")
        queue.append(now)


class AccessSession:
    """One process/session gate; require() must precede EVERY sensitive request."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(os.path.abspath(db_path))
        self._fingerprint = None
        self._unlocked = False
        self._configured_ever = False
        self._mutex = threading.RLock()

    def _refresh(self):
        try:
            verifier, fingerprint = _read_config(config_path(self.db_path))
        except AccessError:
            self._unlocked = False
            self._fingerprint = None
            self._configured_ever = True
            raise
        if verifier is not None:
            self._configured_ever = True
        elif self._configured_ever:
            self._unlocked = False
            self._fingerprint = None
            raise AccessError("access configuration missing")
        if fingerprint != self._fingerprint:
            self._unlocked = False
            self._fingerprint = fingerprint
        return verifier

    def status(self) -> dict:
        """Config-only status: never open, stat or initialize the database."""
        with self._mutex:
            verifier = self._refresh()
            return {'configured': verifier is not None,
                    'locked': verifier is not None and not self._unlocked}

    def unlock(self, password: str) -> dict:
        with self._mutex:
            self._unlocked = False
            verifier = self._refresh()
            if verifier is None:
                return self.status()
            password_attempt('access:' + str(self.db_path))
            argon = crypto()
            from nacl.exceptions import CryptoError
            try:
                encoded = password_bytes(password)
                argon.verify(verifier, encoded)
            except (ValueError, UnicodeError, CryptoError):
                raise AccessError("authentication failed") from None
            fingerprint = self._fingerprint
            self._refresh()
            if fingerprint != self._fingerprint:
                raise AccessError("authentication failed")
            self._unlocked = True
            return self.status()

    def lock(self) -> dict:
        with self._mutex:
            self._unlocked = False
            return self.status()

    def require(self) -> None:
        with self._mutex:
            if self._refresh() is not None:
                crypto()
                if not self._unlocked:
                    raise AccessError("access locked")


# Compatibility spelling for workers who used the earlier SessionAccess name.
SessionAccess = AccessSession


def check_authorized(path: str | Path, *, session: AccessSession | None = None) -> None:
    """Noninteractive library gate; an explicit session is needed if configured."""
    expected = Path(os.path.abspath(path))
    if session is None:
        session = AccessSession(expected)
    if not isinstance(session, AccessSession) or session.db_path != expected:
        raise AccessError("access session database mismatch")
    session.require()


def authorize_database(path: str | Path) -> AccessSession:
    """CLI-only getpass authorization, before any DB open or initialization."""
    # Lazy import avoids getpass in library/API paths and any core.api dependency.
    from .security_cli import _prompt
    session = AccessSession(path)
    try:
        configured = session.status()['configured']
        if configured:
            session.unlock(_prompt('Access password: '))
        session.require()
        if configured:
            # CLI construction barrier only: session status/unlock/require never
            # touch the DB. Do not silently initialize a configured replacement.
            info = session.db_path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                raise AccessError("configured database unavailable")
            session.require()
    except Exception:
        raise AccessError("access authorization failed") from None
    return session


def change_password(db_path: str | Path, old_password: str, new_password: str) -> Path:
    """Authenticated OFFLINE rotation; stop clients, then atomically replace config."""
    from .backup import _sync_directory, validate_database
    path = absolute_path(db_path)
    session = AccessSession(path)
    if not session.status()['configured']:
        raise AccessError("access configuration required")
    session.unlock(old_password)
    session.require()
    validate_database(path)
    data = _config_bytes(new_password)
    target = config_path(path)
    with tempfile.TemporaryDirectory(prefix='.alpha-access-', dir=path.parent) as temp:
        os.chmod(temp, 0o700)
        staged = Path(temp) / 'access.json'
        with exclusive_file(staged) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        fingerprint = session._fingerprint
        session.require()
        if session._fingerprint != fingerprint:
            raise AccessError("access configuration changed")
        os.replace(staged, target)
        _sync_directory(path.parent)
    return target
