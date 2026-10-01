"""Dual approval metadata, transactional legacy migration and decision audit."""

from __future__ import annotations

import json
import sqlite3


FIELDS = ("status", "immediate", "confirm", "exclamation", "confirmed_by", "reason")


def metadata(row: sqlite3.Row | dict) -> dict:
    result = {field: row[field] for field in FIELDS}
    result["immediate"] = bool(result["immediate"])
    result["exclamation"] = bool(result["exclamation"])
    if result["confirm"] is not None:
        result["confirm"] = bool(result["confirm"])
    return result


def record(db: sqlite3.Connection, source_id: str, action: str, before: dict | None,
           after: dict, effects: list[dict], timestamp: str) -> None:
    db.execute(
        "INSERT INTO brain_review_history(source_id, action, before_payload, after_payload, "
        "effect_revisions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, action, json.dumps(before, ensure_ascii=False),
         json.dumps(after, ensure_ascii=False), json.dumps([item["revision"] for item in effects]),
         timestamp),
    )


def initialize(db: sqlite3.Connection, timestamp: str) -> None:
    """Run inside BEGIN IMMEDIATE; never re-fit or rewrite legacy evidence."""
    marker = db.execute("SELECT value FROM brain_meta WHERE key='approval_schema'").fetchone()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(brain_inputs)")}
    declarations = {
        "immediate": "INTEGER NOT NULL DEFAULT 1 CHECK (immediate IN (0, 1))",
        "confirm": "INTEGER CHECK (confirm IN (0, 1))",
        "exclamation": "INTEGER NOT NULL DEFAULT 0 CHECK (exclamation IN (0, 1))",
        "confirmed_by": "TEXT CHECK (confirmed_by IN ('manual', 'exclamation', 'legacy'))",
        "reason": "TEXT CHECK (reason IN ('immediate_false', 'confirm_false', 'user_revoked'))",
    }
    if marker is not None:
        if marker["value"] != "1" or not set(declarations) <= columns:
            raise RuntimeError("unsupported approval schema; explicit migration required")
        return
    if columns & set(declarations):
        raise RuntimeError("partial approval schema; explicit migration required")
    for name, declaration in declarations.items():
        db.execute(f"ALTER TABLE brain_inputs ADD COLUMN {name} {declaration}")
    db.execute("CREATE TABLE brain_review_history ("
               "revision INTEGER PRIMARY KEY AUTOINCREMENT, "
               "source_id TEXT NOT NULL REFERENCES brain_inputs(source_id), "
               "action TEXT NOT NULL CHECK (action IN ('submit', 'review', 'revoke', 'migrate')), "
               "before_payload TEXT NOT NULL, after_payload TEXT NOT NULL, "
               "effect_revisions TEXT NOT NULL, created_at TEXT NOT NULL)")
    db.execute("CREATE INDEX brain_review_history_source ON brain_review_history(source_id, revision)")
    for old in db.execute("SELECT source_id, status FROM brain_inputs").fetchall():
        status = old["status"]
        confirm = None if status == "pending" else int(status == "agreed")
        reason = {"disagreed": "confirm_false", "revoked": "user_revoked"}.get(status)
        db.execute("UPDATE brain_inputs SET confirm=?, confirmed_by=?, reason=? WHERE source_id=?",
                   (confirm, None if status == "pending" else "legacy", reason, old["source_id"]))
        if status in ("agreed", "revoked"):
            # Early v1 fits predate correction provenance. Preserve their stored
            # terms/contributions rather than re-extracting or inventing feedback.
            db.execute("INSERT OR IGNORE INTO brain_fit_context(source_id, payload) VALUES (?, ?)",
                       (old["source_id"], json.dumps({"correction_revision": 0, "corrections": [],
                                                    "learned_rules": [], "legacy_context_unavailable": True})))
        row = db.execute("SELECT * FROM brain_inputs WHERE source_id=?", (old["source_id"],)).fetchone()
        record(db, old["source_id"], "migrate", {"status": status}, metadata(row), [], timestamp)
    # Enforce the eligibility boundary even for accidental internal SQL writes.
    valid = """(
        (NEW.status='pending' AND NEW.immediate=1 AND NEW.confirm IS NULL
            AND NEW.reason IS NULL AND NEW.confirmed_by IS NULL)
        OR (NEW.status='agreed' AND NEW.immediate=1 AND NEW.confirm=1
            AND NEW.reason IS NULL AND NEW.confirmed_by IS NOT NULL)
        OR (NEW.status='disagreed' AND NEW.immediate=0 AND NEW.confirm IS NULL
            AND NEW.reason='immediate_false' AND NEW.confirmed_by IS NULL)
        OR (NEW.status='disagreed' AND NEW.immediate=1 AND NEW.confirm=0
            AND NEW.reason='confirm_false' AND NEW.confirmed_by IS NOT NULL)
        OR (NEW.status='revoked' AND NEW.immediate=1 AND NEW.confirm=0
            AND NEW.reason='user_revoked' AND NEW.confirmed_by IS NOT NULL)
    )"""
    for event in ("INSERT", "UPDATE"):
        db.execute(f"CREATE TRIGGER brain_approval_{event.lower()} BEFORE {event} ON brain_inputs "
                   f"WHEN COALESCE({valid}, 0)=0 BEGIN "
                   "SELECT RAISE(ABORT, 'invalid dual approval state'); END")
    db.execute("INSERT INTO brain_meta(key, value) VALUES ('approval_schema', '1')")
