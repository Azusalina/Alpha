"""SQLite source and candidate memory store for the local brain.

The model is deliberately absent here: a candidate can be supplied by a human,
an extractor, or an import tool. Publishing it to the memory graph is an
explicit, separate operation, so the UI can choose its own review policy.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must contain text")
    return value.strip()


class MemoryStore:
    """One local SQLite database; callers decide when to accept candidates."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Create with restrictive permissions before SQLite ever writes data.
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        os.chmod(self.path, 0o600)
        db = sqlite3.connect(self.path)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA busy_timeout = 5000")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    body TEXT NOT NULL CHECK (length(trim(body)) > 0),
                    origin TEXT NOT NULL CHECK (length(trim(origin)) > 0),
                    source_ref TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(id),
                    claim TEXT NOT NULL CHECK (length(trim(claim)) > 0),
                    evidence TEXT NOT NULL CHECK (length(trim(evidence)) > 0),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'accepted', 'rejected')),
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS candidates_source
                    ON candidates(source_id);
                CREATE INDEX IF NOT EXISTS candidates_status
                    ON candidates(status);
            """)

    def add_source(self, body: str, *, origin: str = "input", source_ref: str | None = None) -> str:
        body = _nonempty(body, "body")
        origin = _nonempty(origin, "origin")
        source_id = uuid4().hex
        with self._connect() as db:
            db.execute(
                "INSERT INTO sources(id, body, origin, source_ref, created_at) VALUES (?, ?, ?, ?, ?)",
                (source_id, body, origin, source_ref, _now()),
            )
        return source_id

    def get_source(self, source_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM sources ORDER BY created_at, id").fetchall()
        return [dict(row) for row in rows]

    def propose(self, source_id: str, claim: str, evidence: str) -> str:
        """Record a candidate only when its evidence occurs in the source."""
        return self.propose_many(source_id, [(claim, evidence)])[0]

    def propose_many(self, source_id: str, items: list[tuple[str, str]]) -> list[str]:
        """Validate and save a model's candidate batch as one transaction."""
        if not isinstance(items, list) or len(items) > 16:
            raise ValueError("items must be a list of at most 16 candidates")
        ids = [uuid4().hex for _ in items]
        with self._connect() as db:
            source = db.execute("SELECT body FROM sources WHERE id = ?", (source_id,)).fetchone()
            if source is None:
                raise KeyError(f"source not found: {source_id}")
            checked = []
            for claim, evidence in items:
                claim = _nonempty(claim, "claim")
                evidence = _nonempty(evidence, "evidence")
                if evidence not in source["body"]:
                    raise ValueError("evidence must be an exact excerpt from the source")
                checked.append((claim, evidence))
            timestamp = _now()
            db.executemany(
                "INSERT INTO candidates(id, source_id, claim, evidence, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                [(item_id, source_id, claim, evidence, timestamp)
                 for item_id, (claim, evidence) in zip(ids, checked)],
            )
        return ids

    def list_candidates(self, *, status: str | None = None) -> list[dict]:
        if status is not None and status not in {"pending", "accepted", "rejected"}:
            raise ValueError("invalid status")
        with self._connect() as db:
            if status is None:
                rows = db.execute("SELECT * FROM candidates ORDER BY created_at, id").fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM candidates WHERE status = ? ORDER BY created_at, id", (status,)
                ).fetchall()
        return [dict(row) for row in rows]

    def resolve(self, candidate_id: str, *, accept: bool) -> dict:
        status = "accepted" if accept else "rejected"
        with self._connect() as db:
            changed = db.execute(
                "UPDATE candidates SET status = ?, resolved_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (status, _now(), candidate_id),
            ).rowcount
            if not changed:
                raise ValueError("candidate not found or already resolved")
            row = db.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
        return dict(row)

    def list_memories(self) -> list[dict]:
        """Accepted candidates form the current graph's node inventory."""
        return self.list_candidates(status="accepted")

    def search_memories(self, query: str, *, limit: int = 20) -> list[dict]:
        """Find accepted claims with their source references.

        This is literal substring retrieval: it works for Chinese and English
        without a tokenizer, but scans accepted claims rather than using FTS.
        """
        query = _nonempty(query, "query")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.id, c.claim, c.evidence, c.source_id, c.created_at, "
                "s.origin, s.source_ref "
                "FROM candidates AS c JOIN sources AS s ON s.id = c.source_id "
                "WHERE c.status = 'accepted' AND "
                "(instr(lower(c.claim), lower(?)) > 0 OR "
                "instr(lower(c.evidence), lower(?)) > 0) "
                "ORDER BY c.created_at, c.id LIMIT ?",
                (query, query, limit),
            ).fetchall()
        return [dict(row) for row in rows]
