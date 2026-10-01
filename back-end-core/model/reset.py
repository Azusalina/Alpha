"""Model-only epochs. Approval, translator learning and source history survive."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from . import sources
from .catalog import BASELINE_PATH

CONFIRMATION = "RESET_MODEL"
EPOCH_KEY = "model_epoch"


def verify_existing(path: Path) -> None:
    """CLI guard: never initialize an absent or unrelated database by mistake."""
    if not path.is_absolute() or not path.is_file():
        raise ValueError("reset requires --db pointing to an existing absolute database path")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            row = db.execute("SELECT value FROM brain_meta WHERE key='baseline_sha256'").fetchone()
            if row is None or row[0] != hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest():
                raise ValueError("reset target is not an Alpha model with the current baseline")
    except sqlite3.Error:
        raise ValueError("reset target is not a readable Alpha model database") from None


def epoch(db: sqlite3.Connection) -> int:
    row = db.execute("SELECT value FROM brain_meta WHERE key=?", (EPOCH_KEY,)).fetchone()
    if row is None or not row[0].isascii() or not row[0].isdigit():
        raise RuntimeError("model epoch unavailable; explicit repair required")
    return int(row[0])


def revision(db: sqlite3.Connection) -> int:
    sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name='brain_review_history'").fetchone()
    generation = db.execute("SELECT value FROM brain_meta WHERE key=?", (sources.GENERATION_KEY,)).fetchone()
    return (sequence[0] if sequence else 0) + int(generation[0])


def initialize(db: sqlite3.Connection) -> None:
    """Add epochs transactionally without touching previous fits or baseline."""
    marker = db.execute("SELECT value FROM brain_meta WHERE key='reset_schema'").fetchone()
    columns = {table: {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
               for table in ('brain_inputs', 'brain_effects')}
    if marker is not None:
        if marker[0] != '1' or any('model_epoch' not in names for names in columns.values()):
            raise RuntimeError("unsupported reset schema; explicit migration required")
        epoch(db)
        return
    if any('model_epoch' in names for names in columns.values()):
        raise RuntimeError("partial reset schema; explicit migration required")
    for table in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN model_epoch INTEGER NOT NULL DEFAULT 0 "
                   "CHECK (model_epoch >= 0)")
    db.execute("INSERT INTO brain_meta(key,value) VALUES (?, '0')", (EPOCH_KEY,))
    db.execute("INSERT INTO brain_meta(key,value) VALUES ('reset_schema','1')")


def info(db: sqlite3.Connection) -> dict:
    current = epoch(db)
    active = db.execute("SELECT COUNT(*) FROM brain_inputs WHERE status='agreed' AND model_epoch=?",
                        (current,)).fetchone()[0]
    return {"model_epoch": current, "input_revision": revision(db),
            "active_model_inputs": active, "translator_preserved": True}


def perform(db: sqlite3.Connection, *, confirmation: str, expected_epoch: int,
            expected_revision: int) -> dict:
    """Caller owns BEGIN IMMEDIATE: optimistic checks and zeroing are atomic."""
    if confirmation != CONFIRMATION:
        raise ValueError("explicit RESET_MODEL confirmation required")
    if any(type(value) is not int or value < 0 for value in (expected_epoch, expected_revision)):
        raise ValueError("expected epoch and revision must be nonnegative integers")
    before = info(db)
    if expected_epoch != before['model_epoch'] or expected_revision != before['input_revision']:
        raise ValueError("model changed; refresh reset-info before resetting")
    current = before['model_epoch'] + 1
    db.execute("UPDATE brain_meta SET value=? WHERE key=?", (str(current), EPOCH_KEY))
    db.execute("UPDATE brain_state SET value=0, support=0, net=0")
    sources.bump_generation(db)
    return {**info(db), "reset": True, "previous_epoch": before['model_epoch'],
            "previous_active_model_inputs": before['active_model_inputs']}
