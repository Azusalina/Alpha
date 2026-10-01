"""Source governance metadata and purge helpers; no external-file deletion."""

from __future__ import annotations

import sqlite3

from translator.pipeline import MAX_CHARS

from .approvals import metadata as approval_metadata

UNSET = object()
GENERATION_KEY = "input_mutation_generation"
DEPENDENT_TABLES = ("candidates", "brain_effects", "brain_review_history",
                    "brain_corrections", "brain_fit_context", "brain_terms",
                    "brain_contributions")


def validate_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
        raise ValueError(f"text must contain 1 to {MAX_CHARS} characters")
    if "\0" in text:
        raise ValueError("text must not contain U+0000")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("text must not contain surrogate code points") from None


def initialize(db: sqlite3.Connection) -> None:
    """Transactional additive migration; old text/contributions stay untouched."""
    marker = db.execute("SELECT value FROM brain_meta WHERE key='source_schema'").fetchone()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(brain_inputs)")}
    declarations = {"edited_at": "TEXT",
                    "ever_fitted": "INTEGER NOT NULL DEFAULT 0 CHECK (ever_fitted IN (0, 1))"}
    if marker is not None:
        if marker["value"] != "1" or not set(declarations) <= columns:
            raise RuntimeError("unsupported source schema; explicit migration required")
        generation = db.execute("SELECT value FROM brain_meta WHERE key=?", (GENERATION_KEY,)).fetchone()
        if generation is None or not generation[0].isascii() or not generation[0].isdigit():
            raise RuntimeError("input mutation generation unavailable; explicit repair required")
        return
    if columns & set(declarations):
        raise RuntimeError("partial source schema; explicit migration required")
    for name, declaration in declarations.items():
        db.execute(f"ALTER TABLE brain_inputs ADD COLUMN {name} {declaration}")
    db.execute("UPDATE brain_inputs SET ever_fitted=1 WHERE status IN ('agreed','revoked') "
               "OR EXISTS (SELECT 1 FROM brain_fit_context f WHERE f.source_id=brain_inputs.source_id) "
               "OR EXISTS (SELECT 1 FROM brain_contributions c WHERE c.source_id=brain_inputs.source_id) "
               "OR EXISTS (SELECT 1 FROM brain_terms t WHERE t.source_id=brain_inputs.source_id)")
    db.execute("INSERT INTO brain_meta(key,value) VALUES ('source_schema','1')")
    db.execute("INSERT INTO brain_meta(key,value) VALUES (?, '0')", (GENERATION_KEY,))


def bump_generation(db: sqlite3.Connection) -> None:
    # This contains neither source identities nor deleted source text.
    changed = db.execute("UPDATE brain_meta SET value=CAST(value AS INTEGER)+1 WHERE key=?", (GENERATION_KEY,))
    if changed.rowcount != 1:
        raise RuntimeError("input mutation generation unavailable; explicit repair required")


def purge_dependents(db: sqlite3.Connection, source_id: str) -> None:
    for table in DEPENDENT_TABLES:
        db.execute(f"DELETE FROM {table} WHERE source_id=?", (source_id,))


def public_record(row: sqlite3.Row | dict, text: str) -> dict:
    """Return only the established input metadata, never internal fit flags."""
    fields = ("source_id", "partition", "kind", "self_speaker", "reviewed_at",
              "source_ref", "created_at", "edited_at")
    return {**{field: row[field] for field in fields}, **approval_metadata(row),
            "model_active": bool(row["model_active"]), "model_epoch": row["model_epoch"],
            "excerpt": text[:80], "char_count": len(text)}
