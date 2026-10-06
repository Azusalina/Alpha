"""User-reviewed semantic/causal source relations; never inferred or auto-applied.

An edge says the user judged that one source bears on another. It is bound to
both source versions and the model epoch, so edits, reopened versions and model
Resets make it stale. It never fits, replays, reviews or changes any effect.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from . import reset, sources

KINDS = ("semantic", "causal")
MAX_NOTE = 1024
MAX_PER_SOURCE = 64
MAX_LIST = 100


def initialize(db: sqlite3.Connection) -> None:
    """Add only this table, idempotently; caller owns migration transaction."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS brain_relations (
            from_source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            to_source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('semantic','causal')),
            from_source_version INTEGER NOT NULL CHECK (from_source_version >= 0),
            to_source_version INTEGER NOT NULL CHECK (to_source_version >= 0),
            model_epoch INTEGER NOT NULL CHECK (model_epoch >= 0),
            note TEXT CHECK (note IS NULL OR length(note) <= 1024),
            created_at TEXT NOT NULL,
            PRIMARY KEY (from_source_id, to_source_id, kind),
            CHECK (from_source_id <> to_source_id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS brain_relations_to ON brain_relations(to_source_id)")


def exists(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brain_relations'").fetchone() is not None


def _id(value: object, name: str) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 128 or "\0" in value
            or any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)):
        raise ValueError(f"{name} must contain 1 to 128 characters without NUL or surrogates")
    return value


def _int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _input(db: sqlite3.Connection, source_id: str) -> sqlite3.Row:
    row = db.execute("SELECT source_id, source_version FROM brain_inputs WHERE source_id=?",
                     (source_id,)).fetchone()
    if row is None:
        raise KeyError("brain input not found")
    return row


def _public(row: sqlite3.Row, versions: dict[str, int], epoch: int, source_id: str | None = None) -> dict:
    stale = (versions.get(row["from_source_id"]) != row["from_source_version"]
             or versions.get(row["to_source_id"]) != row["to_source_version"]
             or row["model_epoch"] != epoch)
    result = {"from_source_id": row["from_source_id"], "to_source_id": row["to_source_id"],
              "kind": row["kind"], "from_source_version": row["from_source_version"],
              "to_source_version": row["to_source_version"], "model_epoch": row["model_epoch"],
              "note": row["note"], "created_at": row["created_at"], "stale": stale}
    if source_id is not None:
        result["direction"] = "outgoing" if row["from_source_id"] == source_id else "incoming"
    return result


def set_relation(store, from_source_id, to_source_id, kind, reviewed, expected_from_source_version,
                 expected_to_source_version, expected_revision, expected_epoch, note=None) -> dict:
    """Save (reviewed=true, replacing the same edge) or retract (reviewed=false) one edge."""
    _id(from_source_id, "from_source_id")
    _id(to_source_id, "to_source_id")
    if from_source_id == to_source_id:
        raise ValueError("a relation needs two different sources")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("kind must be semantic or causal")
    if type(reviewed) is not bool:
        raise ValueError("reviewed must be an explicit boolean")
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE or "\0" in note
                             or any(0xD800 <= ord(ch) <= 0xDFFF for ch in note)):
        raise ValueError("note must be text of at most 1024 characters")
    if note is not None and not reviewed:
        raise ValueError("a retraction cannot carry a note")
    for name, value in (("expected_from_source_version", expected_from_source_version),
                        ("expected_to_source_version", expected_to_source_version),
                        ("expected_revision", expected_revision), ("expected_epoch", expected_epoch)):
        _int(value, name)
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        source, target = _input(db, from_source_id), _input(db, to_source_id)
        epoch = reset.epoch(db)
        if (source["source_version"] != expected_from_source_version
                or target["source_version"] != expected_to_source_version
                or reset.revision(db) != expected_revision or epoch != expected_epoch):
            raise ValueError("relation sources/revision/epoch changed; refresh before saving")
        key = (from_source_id, to_source_id, kind)
        present = db.execute("SELECT 1 FROM brain_relations WHERE from_source_id=? AND to_source_id=? "
                             "AND kind=?", key).fetchone() is not None
        if reviewed:
            if not present:
                for endpoint in (from_source_id, to_source_id):
                    if db.execute("SELECT COUNT(*) FROM brain_relations WHERE from_source_id=? "
                                  "OR to_source_id=?", (endpoint, endpoint)).fetchone()[0] >= MAX_PER_SOURCE:
                        raise ValueError("at most 64 relations per source")
            created = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            db.execute("INSERT INTO brain_relations(from_source_id,to_source_id,kind,from_source_version,"
                       "to_source_version,model_epoch,note,created_at) VALUES (?,?,?,?,?,?,?,?) "
                       "ON CONFLICT(from_source_id,to_source_id,kind) DO UPDATE SET "
                       "from_source_version=excluded.from_source_version, "
                       "to_source_version=excluded.to_source_version, model_epoch=excluded.model_epoch, "
                       "note=excluded.note, created_at=excluded.created_at",
                       (*key, source["source_version"], target["source_version"], epoch, note, created))
        elif present:
            db.execute("DELETE FROM brain_relations WHERE from_source_id=? AND to_source_id=? AND kind=?", key)
        if reviewed or present:
            sources.bump_generation(db)
        return {"from_source_id": from_source_id, "to_source_id": to_source_id, "kind": kind,
                "reviewed": reviewed, "changed": reviewed or present,
                "from_source_version": source["source_version"], "to_source_version": target["source_version"],
                "model_epoch": epoch, "input_revision": reset.revision(db)}


def list_relations(store, source_id, limit: int = MAX_LIST) -> dict:
    _id(source_id, "source_id")
    if type(limit) is not int or not 1 <= limit <= MAX_LIST:
        raise ValueError("limit must be an integer from 1 to 100")
    with store._connect() as db:
        db.execute("BEGIN")
        _input(db, source_id)
        epoch = reset.epoch(db)
        rows = db.execute("SELECT * FROM brain_relations WHERE from_source_id=? OR to_source_id=? "
                          "ORDER BY from_source_id, to_source_id, kind LIMIT ?",
                          (source_id, source_id, limit + 1)).fetchall()
        ids = {r[k] for r in rows[:limit] for k in ("from_source_id", "to_source_id")}
        versions = {r["source_id"]: r["source_version"] for r in db.execute(
            "SELECT source_id, source_version FROM brain_inputs WHERE source_id IN (%s)"
            % ",".join("?" for _ in ids), tuple(ids))} if ids else {}
        return {"source_id": source_id, "relations": [_public(r, versions, epoch, source_id) for r in rows[:limit]],
                "truncated": len(rows) > limit, "input_revision": reset.revision(db), "model_epoch": epoch}


def fresh_edges(db: sqlite3.Connection, cap: int) -> tuple[list[sqlite3.Row], bool]:
    """Edges whose both source versions and epoch are still current (bounded)."""
    if not exists(db):
        return [], False
    rows = db.execute(
        "SELECT r.from_source_id, r.to_source_id, r.kind FROM brain_relations r "
        "JOIN brain_inputs a ON a.source_id=r.from_source_id AND a.source_version=r.from_source_version "
        "JOIN brain_inputs b ON b.source_id=r.to_source_id AND b.source_version=r.to_source_version "
        "WHERE r.model_epoch=? ORDER BY r.from_source_id, r.to_source_id, r.kind LIMIT ?",
        (reset.epoch(db), cap + 1)).fetchall()
    return rows[:cap], len(rows) > cap
