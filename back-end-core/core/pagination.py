"""Opaque, bounded, database-bound input-list cursors (not authentication)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3

from model.sources import GENERATION_KEY

MAX_CURSOR_CHARS = 2048
_TOKEN = re.compile(r"[A-Za-z0-9_-]+\.[0-9a-f]{64}\Z")
_FIELDS = {"version", "revision", "partition", "status", "created_at", "source_id"}


class StaleCursor(ValueError):
    """Supported input mutations changed the list; restart from its first page."""


def initialize(db: sqlite3.Connection) -> None:
    db.execute("INSERT OR IGNORE INTO brain_meta(key, value) VALUES ('input_cursor_key', ?)",
               (secrets.token_hex(32),))


def key(db: sqlite3.Connection) -> bytes:
    row = db.execute("SELECT value FROM brain_meta WHERE key='input_cursor_key'").fetchone()
    if row is None or not re.fullmatch(r"[0-9a-f]{64}", row["value"]):
        raise RuntimeError("input cursor key unavailable; explicit repair required")
    return bytes.fromhex(row["value"])


def revision(db: sqlite3.Connection) -> int:
    """Monotonic even when a source's complete audit (including max ID) is purged."""
    sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='brain_review_history'").fetchone()
    generation = db.execute("SELECT value FROM brain_meta WHERE key=?", (GENERATION_KEY,)).fetchone()
    if generation is None or not generation[0].isdigit():
        raise RuntimeError("input mutation generation unavailable; explicit repair required")
    return (sequence[0] if sequence else 0) + int(generation[0])


def encode(secret: bytes, *, revision: int, partition: str | None, status: str | None,
           created_at: str, source_id: str) -> str:
    payload = json.dumps({"version": 1, "revision": revision, "partition": partition,
                          "status": status, "created_at": created_at, "source_id": source_id},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    token = body + "." + signature
    if len(token) > MAX_CURSOR_CHARS:
        raise RuntimeError("input sort key exceeds cursor size limit")
    return token


def decode(token: str, secret: bytes, *, revision: int, partition: str | None,
           status: str | None) -> dict:
    if not isinstance(token, str) or len(token) > MAX_CURSOR_CHARS or not _TOKEN.fullmatch(token):
        raise ValueError("invalid input cursor")
    body, signature = token.split(".")
    expected = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("invalid input cursor")
    try:
        payload = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
        record = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid input cursor") from None
    if (not isinstance(record, dict) or set(record) != _FIELDS
            or type(record["version"]) is not int or record["version"] != 1
            or type(record["revision"]) is not int or record["revision"] < 0
            or any(not isinstance(record[field], str) or not record[field]
                   for field in ("created_at", "source_id"))):
        raise ValueError("invalid input cursor")
    try:
        record["created_at"].encode("utf-8")
        record["source_id"].encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid input cursor") from None
    if record["partition"] != partition or record["status"] != status:
        raise ValueError("input cursor filters changed; restart from the first page")
    if record["revision"] != revision:
        raise StaleCursor("input list changed; discard accumulated pages and restart from the first page")
    return record
