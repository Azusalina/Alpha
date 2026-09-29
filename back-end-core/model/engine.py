"""Local, auditable model updates from whole-input agreement feedback.

This is an interpretable statistical state model, not a pretrained LLM. Each
partition starts from the same immutable zero baseline and learns only from
inputs that the user agreed to. Effect logs make every update reversible.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.store import MemoryStore
from translator.learning import learnable_terms, own_chat_text
from translator.pipeline import MAX_CHARS

from .catalog import BASELINE, BASELINE_PATH, PARAMETERS, PARTITIONS, PRIOR_STRENGTH, zero_state
from .evidence import extract_contributions


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _score(net: int, support: int) -> float:
    return net / (support + PRIOR_STRENGTH)


class BrainModel:
    """One SQLite-backed active model; `baseline.json` is never rewritten."""

    def __init__(self, path: str | Path):
        self.store = MemoryStore(path)
        self.store.initialize()
        baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
        if BASELINE.get("schema_version") != 1 or any(value != 0 for value in BASELINE["parameters"].values()):
            raise RuntimeError("baseline schema must have all numeric parameters at zero")
        with self.store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS brain_meta (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS brain_inputs (
                    source_id TEXT PRIMARY KEY REFERENCES sources(id),
                    partition TEXT NOT NULL CHECK (partition IN ('rational', 'emotional', 'crazy')),
                    kind TEXT NOT NULL CHECK (kind IN ('diary', 'chat', 'philosophy')),
                    self_speaker TEXT,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'agreed', 'disagreed', 'revoked')),
                    reviewed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS brain_state (
                    partition TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    value REAL NOT NULL,
                    support INTEGER NOT NULL,
                    net INTEGER NOT NULL,
                    PRIMARY KEY (partition, parameter)
                );
                CREATE TABLE IF NOT EXISTS brain_contributions (
                    source_id TEXT NOT NULL REFERENCES brain_inputs(source_id),
                    parameter TEXT NOT NULL,
                    sign INTEGER NOT NULL CHECK (sign IN (-1, 1)),
                    evidence TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    rule_id TEXT NOT NULL,
                    PRIMARY KEY (source_id, parameter)
                );
                CREATE TABLE IF NOT EXISTS brain_terms (
                    source_id TEXT NOT NULL REFERENCES brain_inputs(source_id),
                    term TEXT NOT NULL,
                    occurrences INTEGER NOT NULL,
                    PRIMARY KEY (source_id, term)
                );
                CREATE TABLE IF NOT EXISTS brain_effects (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES brain_inputs(source_id),
                    partition TEXT NOT NULL,
                    parameter TEXT NOT NULL,
                    before_value REAL NOT NULL,
                    after_value REAL NOT NULL,
                    before_support INTEGER NOT NULL,
                    after_support INTEGER NOT NULL,
                    evidence TEXT NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    rule_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (action IN ('approve', 'revoke')),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS brain_effects_source ON brain_effects(source_id);
                CREATE INDEX IF NOT EXISTS brain_inputs_partition ON brain_inputs(partition, status);
            """)
            stored = db.execute("SELECT value FROM brain_meta WHERE key = 'baseline_sha256'").fetchone()
            if stored is not None and stored["value"] != baseline_hash:
                raise RuntimeError("baseline changed; migrate the active model explicitly")
            db.execute("INSERT OR IGNORE INTO brain_meta(key, value) VALUES ('baseline_sha256', ?)",
                       (baseline_hash,))
            db.executemany(
                "INSERT OR IGNORE INTO brain_state(partition, parameter, value, support, net) "
                "VALUES (?, ?, 0, 0, 0)",
                [(partition, parameter) for partition in PARTITIONS for parameter in PARAMETERS],
            )

    @staticmethod
    def baseline() -> dict:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    def submit(self, text: str, *, partition: str, kind: str = "diary",
               self_speaker: str | None = None, source_ref: str | None = None) -> str:
        """Save original text immediately; do not translate or train yet."""
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError(f"text must contain 1 to {MAX_CHARS} characters")
        if partition not in PARTITIONS:
            raise ValueError("invalid partition")
        if kind not in {"diary", "chat", "philosophy"}:
            raise ValueError("invalid kind")
        if kind == "chat" and (not isinstance(self_speaker, str) or not self_speaker.strip()):
            raise ValueError("chat requires self_speaker")
        source_id = uuid4().hex
        with self.store._connect() as db:
            db.execute("INSERT INTO sources(id, body, origin, source_ref, created_at) "
                       "VALUES (?, ?, ?, ?, ?)",
                       (source_id, text, kind, source_ref, _now()))
            db.execute("INSERT INTO brain_inputs(source_id, partition, kind, self_speaker) "
                       "VALUES (?, ?, ?, ?)",
                       (source_id, partition, kind, self_speaker))
        return source_id

    def _term_counts(self, db: sqlite3.Connection, partition: str) -> dict[str, int]:
        rows = db.execute(
            "SELECT t.term, COUNT(*) AS documents FROM brain_terms t "
            "JOIN brain_inputs i ON i.source_id = t.source_id "
            "WHERE i.partition = ? AND i.status = 'agreed' GROUP BY t.term",
            (partition,),
        ).fetchall()
        return {row["term"]: row["documents"] for row in rows}

    def _recompute(self, db: sqlite3.Connection, partition: str, parameter: str,
                   source_id: str, evidence: str, start: int, end: int,
                   rule_id: str, action: str) -> dict:
        before = db.execute(
            "SELECT value, support FROM brain_state WHERE partition = ? AND parameter = ?",
            (partition, parameter),
        ).fetchone()
        aggregate = db.execute(
            "SELECT COUNT(*) AS support, COALESCE(SUM(c.sign), 0) AS net "
            "FROM brain_contributions c JOIN brain_inputs i ON i.source_id = c.source_id "
            "WHERE i.partition = ? AND i.status = 'agreed' AND c.parameter = ?",
            (partition, parameter),
        ).fetchone()
        support, net = aggregate["support"], aggregate["net"]
        after_value = _score(net, support)
        db.execute("UPDATE brain_state SET value = ?, support = ?, net = ? "
                   "WHERE partition = ? AND parameter = ?",
                   (after_value, support, net, partition, parameter))
        timestamp = _now()
        cursor = db.execute(
            "INSERT INTO brain_effects(source_id, partition, parameter, before_value, "
            "after_value, before_support, after_support, evidence, start_offset, "
            "end_offset, rule_id, action, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (source_id, partition, parameter, before["value"], after_value,
             before["support"], support, evidence, start, end, rule_id, action, timestamp),
        )
        return {
            "revision": cursor.lastrowid, "source_id": source_id,
            "partition": partition, "parameter": parameter,
            "before": before["value"], "after": after_value,
            "delta": after_value - before["value"],
            "support_before": before["support"], "support_after": support,
            "evidence": evidence, "span": [start, end], "rule_id": rule_id,
            "action": action, "created_at": timestamp,
        }

    def review(self, source_id: str, *, agree: bool) -> dict:
        """Apply one whole-source boolean; true updates only its own partition."""
        if type(agree) is not bool:
            raise ValueError("agree must be a boolean")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT i.*, s.body FROM brain_inputs i JOIN sources s ON s.id = i.source_id "
                "WHERE i.source_id = ?", (source_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"brain input not found: {source_id}")
            if row["status"] != "pending":
                raise ValueError("brain input already reviewed")
            partition = row["partition"]
            if not agree:
                db.execute("UPDATE brain_inputs SET status = 'disagreed', reviewed_at = ? "
                           "WHERE source_id = ?", (_now(), source_id))
                return {"source_id": source_id, "status": "disagreed", "effects": [],
                        "translator_effects": []}

            before_terms = self._term_counts(db, partition)
            personal_phrases = tuple(sorted(term for term, n in before_terms.items() if n >= 2))
            learner_text = (own_chat_text(row["body"], row["self_speaker"])
                            if row["kind"] == "chat" else row["body"])
            terms = learnable_terms(learner_text, personal_phrases=personal_phrases)
            contributions = extract_contributions(row["body"], kind=row["kind"],
                                                  self_speaker=row["self_speaker"])
            db.executemany(
                "INSERT INTO brain_terms(source_id, term, occurrences) VALUES (?, ?, ?)",
                [(source_id, term, count) for term, count in terms.items()],
            )
            db.executemany(
                "INSERT INTO brain_contributions(source_id, parameter, sign, evidence, "
                "start_offset, end_offset, rule_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(source_id, item.parameter, item.sign, item.evidence, item.start, item.end,
                  item.rule_id)
                 for item in contributions],
            )
            db.execute("UPDATE brain_inputs SET status = 'agreed', reviewed_at = ? "
                       "WHERE source_id = ?", (_now(), source_id))
            effects = [self._recompute(db, partition, item.parameter, source_id,
                                       item.evidence, item.start, item.end,
                                       item.rule_id, "approve")
                       for item in contributions]
            after_terms = self._term_counts(db, partition)
            translator_effects = [
                {"term": term, "documents_before": before_terms.get(term, 0),
                 "documents_after": after_terms[term], "source_id": source_id}
                for term in sorted(terms) if before_terms.get(term, 0) < 2 <= after_terms[term]
            ]
            return {"source_id": source_id, "status": "agreed", "partition": partition,
                    "effects": effects, "translator_effects": translator_effects,
                    "observed_terms": len(terms)}

    def revoke(self, source_id: str) -> dict:
        """Remove an agreed source from the active fit; retain audit history."""
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT partition, status FROM brain_inputs WHERE source_id = ?",
                             (source_id,)).fetchone()
            if row is None:
                raise KeyError(f"brain input not found: {source_id}")
            if row["status"] != "agreed":
                raise ValueError("only agreed sources can be revoked")
            items = db.execute("SELECT * FROM brain_contributions WHERE source_id = ? "
                               "ORDER BY start_offset, parameter", (source_id,)).fetchall()
            db.execute("UPDATE brain_inputs SET status = 'revoked', reviewed_at = ? "
                       "WHERE source_id = ?", (_now(), source_id))
            effects = [self._recompute(db, row["partition"], item["parameter"], source_id,
                                       item["evidence"], item["start_offset"],
                                       item["end_offset"], item["rule_id"], "revoke")
                       for item in items]
            return {"source_id": source_id, "status": "revoked", "effects": effects}

    def state(self, partition: str | None = None) -> dict:
        if partition is not None and partition not in PARTITIONS:
            raise ValueError("invalid partition")
        with self.store._connect() as db:
            rows = db.execute("SELECT partition, parameter, value, support FROM brain_state "
                              "ORDER BY partition, parameter").fetchall()
        result = zero_state()
        for row in rows:
            result[row["partition"]][row["parameter"]] = {
                "value": row["value"], "support": row["support"],
                "observed": row["support"] > 0,
            }
        return result[partition] if partition else result

    def effects(self, *, source_id: str | None = None) -> list[dict]:
        with self.store._connect() as db:
            if source_id is None:
                rows = db.execute("SELECT * FROM brain_effects ORDER BY revision").fetchall()
            else:
                rows = db.execute("SELECT * FROM brain_effects WHERE source_id = ? "
                                  "ORDER BY revision", (source_id,)).fetchall()
        return [{
            "revision": row["revision"], "source_id": row["source_id"],
            "partition": row["partition"], "parameter": row["parameter"],
            "before": row["before_value"], "after": row["after_value"],
            "delta": row["after_value"] - row["before_value"],
            "support_before": row["before_support"],
            "support_after": row["after_support"],
            "evidence": row["evidence"],
            "span": [row["start_offset"], row["end_offset"]],
            "rule_id": row["rule_id"], "action": row["action"],
            "created_at": row["created_at"],
        } for row in rows]

    def learned_terms(self, *, partition: str, min_documents: int = 2) -> list[dict]:
        if partition not in PARTITIONS:
            raise ValueError("invalid partition")
        if type(min_documents) is not int or min_documents < 1:
            raise ValueError("min_documents must be a positive integer")
        with self.store._connect() as db:
            rows = db.execute(
                "SELECT t.term, COUNT(*) AS documents, SUM(t.occurrences) AS occurrences "
                "FROM brain_terms t JOIN brain_inputs i ON i.source_id = t.source_id "
                "WHERE i.partition = ? AND i.status = 'agreed' GROUP BY t.term "
                "HAVING COUNT(*) >= ? ORDER BY documents DESC, occurrences DESC, t.term",
                (partition, min_documents),
            ).fetchall()
        return [dict(row) for row in rows]

    def rank_options(self, options: list[dict]) -> dict:
        """Rank structured options by rational value alignment, never as probability."""
        if not isinstance(options, list) or len(options) < 2:
            raise ValueError("provide at least two options")
        ids = []
        for option in options:
            if not isinstance(option, dict) or not isinstance(option.get("id"), str) or not option["id"]:
                raise ValueError("each option needs a nonempty id")
            impacts = option.get("impacts")
            if not isinstance(impacts, dict):
                raise ValueError("each option needs impacts")
            for parameter, value in impacts.items():
                if parameter not in PARAMETERS or not parameter.startswith("value."):
                    raise ValueError(f"unknown or non-value parameter: {parameter}")
                if type(value) not in (int, float) or not math.isfinite(value) or not -1 <= value <= 1:
                    raise ValueError("impacts must be finite numbers from -1 to 1")
            ids.append(option["id"])
        if len(set(ids)) != len(ids):
            raise ValueError("option ids must be distinct")
        rational = self.state("rational")
        usable = {key: item["value"] for key, item in rational.items()
                  if key.startswith("value.") and item["support"] >= 2}
        if not usable or not any(any(key in usable and impact != 0
                                     for key, impact in option["impacts"].items())
                                 for option in options):
            return {"status": "abstain", "reason": "insufficient_confirmed_value_evidence",
                    "ranked": []}
        ranked = sorted(
            ({"id": option["id"],
              "alignment_score": sum(usable.get(key, 0) * value
                                     for key, value in option["impacts"].items())}
             for option in options),
            key=lambda item: (-item["alignment_score"], item["id"]),
        )
        if all(item["alignment_score"] == ranked[0]["alignment_score"] for item in ranked):
            return {"status": "abstain", "reason": "options_indistinguishable_with_current_evidence",
                    "ranked": []}
        return {"status": "provisional", "basis": "confirmed_value_alignment_only",
                "not_a_probability": True, "used_parameters": sorted(usable), "ranked": ranked}
