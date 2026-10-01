"""Local, auditable model updates from whole-input agreement feedback.

This is an interpretable statistical state model, not a pretrained LLM. Each
partition starts from the same immutable zero baseline and learns only from
inputs that the user agreed to. Effect logs make every update reversible.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.store import MemoryStore
from translator import translate
from translator.learning import learnable_terms, own_chat_text
from translator.discourse import POLICY_VERSION

from .catalog import BASELINE, BASELINE_PATH, PARAMETERS, PARTITIONS, PRIOR_STRENGTH, zero_state
from .approvals import initialize as initialize_approvals, metadata as approval_metadata, record as record_review
from .corrections import apply_local, latest_corrections, learned_rules, validate_corrections
from .evidence import Contribution, extract_contributions
from .ranking import rank_from_state
from . import sources


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
                CREATE TABLE IF NOT EXISTS brain_corrections (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES brain_inputs(source_id),
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS brain_corrections_source
                    ON brain_corrections(source_id, revision);
                CREATE TABLE IF NOT EXISTS brain_fit_context (
                    source_id TEXT PRIMARY KEY REFERENCES brain_inputs(source_id),
                    payload TEXT NOT NULL
                );
            """)
            db.execute("BEGIN IMMEDIATE")
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
            initialize_approvals(db, _now())
            sources.initialize(db)

    @staticmethod
    def baseline() -> dict:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    def submit(self, text: str, *, partition: str, kind: str = "diary",
               self_speaker: str | None = None, source_ref: str | None = None,
               immediate: bool = True, exclamation: bool = False) -> str:
        """Compatibility Python entry point returning only the source identity."""
        return self.submit_result(text, partition=partition, kind=kind, self_speaker=self_speaker,
                                  source_ref=source_ref, immediate=immediate,
                                  exclamation=exclamation)["source_id"]

    def submit_result(self, text: str, *, partition: str, kind: str = "diary",
                      self_speaker: str | None = None, source_ref: str | None = None,
                      immediate: bool = True, exclamation: bool = False) -> dict:
        """Store and, only on explicit exclamation, fit in the same transaction."""
        sources.validate_text(text)
        if partition not in PARTITIONS:
            raise ValueError("invalid partition")
        if kind not in {"diary", "chat", "philosophy"}:
            raise ValueError("invalid kind")
        if kind == "chat" and (not isinstance(self_speaker, str) or not self_speaker.strip()):
            raise ValueError("chat requires self_speaker")
        if type(immediate) is not bool or type(exclamation) is not bool:
            raise ValueError("immediate and exclamation must be booleans")
        # User-confirmed product rule: explicit exclamation overrides immediate=false.
        immediate = immediate or exclamation
        source_id = uuid4().hex
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO sources(id, body, origin, source_ref, created_at) "
                       "VALUES (?, ?, ?, ?, ?)",
                       (source_id, text, kind, source_ref, _now()))
            db.execute("INSERT INTO brain_inputs(source_id, partition, kind, self_speaker, "
                       "immediate, exclamation, status, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (source_id, partition, kind, self_speaker, int(immediate), int(exclamation),
                        "pending" if immediate else "disagreed", None if immediate else "immediate_false"))
            row = self._input(db, source_id)
            record_review(db, source_id, "submit", None, approval_metadata(row), [], _now())
            if exclamation:
                return self._review(db, row, agree=True, confirmed_by="exclamation")
            return self._decision_result(row)

    @staticmethod
    def _input(db: sqlite3.Connection, source_id: str) -> sqlite3.Row:
        row = db.execute("SELECT i.*, s.body, s.source_ref, s.created_at FROM brain_inputs i JOIN sources s ON s.id=i.source_id "
                         "WHERE i.source_id=?", (source_id,)).fetchone()
        if row is None:
            raise KeyError("brain input not found")
        return row

    def input_edit(self, source_id: str, text: str, immediate: bool, *,
                   kind=sources.UNSET, self_speaker=sources.UNSET) -> dict:
        """Replace an inactive source, purging its old text-bearing history."""
        sources.validate_text(text)
        if type(immediate) is not bool:
            raise ValueError("immediate must be a boolean")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._input(db, source_id)
            if row["status"] == "agreed":
                raise ValueError("revoke the agreed source before editing")
            new_kind = row["kind"] if kind is sources.UNSET else kind
            if not isinstance(new_kind, str) or new_kind not in {"diary", "chat", "philosophy"}:
                raise ValueError("invalid kind")
            if self_speaker is not sources.UNSET and self_speaker is not None:
                if not isinstance(self_speaker, str) or not self_speaker.strip():
                    raise ValueError("self_speaker must contain text")
                try:
                    self_speaker.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError("self_speaker must not contain surrogate code points") from None
            speaker = row["self_speaker"] if self_speaker is sources.UNSET else self_speaker
            if new_kind == "chat":
                if not isinstance(speaker, str) or not speaker.strip():
                    raise ValueError("chat requires self_speaker")
                try:
                    speaker.encode("utf-8")
                except UnicodeEncodeError:
                    raise ValueError("self_speaker must not contain surrogate code points") from None
            else:
                speaker = None  # No stale chat identity after changing kind.
            sources.purge_dependents(db, source_id)
            timestamp = _now()
            db.execute("UPDATE sources SET body=?, origin=? WHERE id=?", (text, new_kind, source_id))
            db.execute("UPDATE brain_inputs SET kind=?, self_speaker=?, immediate=?, confirm=NULL, "
                       "exclamation=0, confirmed_by=NULL, reason=?, status=?, reviewed_at=NULL, "
                       "edited_at=? WHERE source_id=?",
                       (new_kind, speaker, int(immediate), None if immediate else "immediate_false",
                        "pending" if immediate else "disagreed", timestamp, source_id))
            sources.bump_generation(db)
            updated = self._input(db, source_id)
            return sources.public_record(updated, text)

    def input_delete(self, source_id: str) -> dict:
        """Atomically deactivate and hard-delete this source's application records."""
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._input(db, source_id)
            if row["status"] == "agreed":
                # Reuse aggregate/vocabulary removal, then purge even this temporary audit.
                self._deactivate(db, row, status="revoked", reason="user_revoked",
                                 confirmed_by=row["confirmed_by"], action="revoke")
            sources.purge_dependents(db, source_id)
            db.execute("DELETE FROM brain_inputs WHERE source_id=?", (source_id,))
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))
            sources.bump_generation(db)
            return {"source_id": source_id, "deleted": True}

    @staticmethod
    def _decision_result(row: sqlite3.Row, effects: list[dict] | None = None,
                         translator_effects: list[dict] | None = None) -> dict:
        return {"source_id": row["source_id"], "partition": row["partition"],
                **approval_metadata(row), "effects": effects or [],
                "translator_effects": translator_effects or []}

    def review_history(self, source_id: str) -> dict:
        with self.store._connect() as db:
            db.execute("BEGIN")
            row = self._input(db, source_id)
            history = db.execute("SELECT * FROM brain_review_history WHERE source_id=? ORDER BY revision",
                                 (source_id,)).fetchall()
        return {"source_id": source_id, **approval_metadata(row), "history": [
            {"revision": item["revision"], "action": item["action"],
             "before": json.loads(item["before_payload"]), "after": json.loads(item["after_payload"]),
             "effect_revisions": json.loads(item["effect_revisions"]), "created_at": item["created_at"]}
            for item in history]}

    def _term_counts(self, db: sqlite3.Connection, partition: str) -> dict[str, int]:
        rows = db.execute(
            "SELECT t.term, COUNT(*) AS documents FROM brain_terms t "
            "JOIN brain_inputs i ON i.source_id = t.source_id "
            "WHERE i.partition = ? AND i.status = 'agreed' GROUP BY t.term",
            (partition,),
        ).fetchall()
        return {row["term"]: row["documents"] for row in rows}

    def _observations(self, db: sqlite3.Connection, row: sqlite3.Row
                      ) -> tuple[dict[str, int], dict[str, int], list[Contribution], dict]:
        """Use identical extraction inputs for a pending preview and approval."""
        before_terms = self._term_counts(db, row["partition"])
        personal_phrases = tuple(sorted(term for term, n in before_terms.items() if n >= 2))
        learner_text = (own_chat_text(row["body"], row["self_speaker"])
                        if row["kind"] == "chat" else row["body"])
        terms = learnable_terms(learner_text, personal_phrases=personal_phrases)
        rules, semantic_feedback = learned_rules(db, row)
        revision, corrections = latest_corrections(db, row["source_id"])
        diagnostics = {}
        contributions = extract_contributions(row["body"], kind=row["kind"],
                                              self_speaker=row["self_speaker"], semantic_rules=rules,
                                              diagnostics=diagnostics)
        contributions = apply_local(contributions, corrections)
        context = {"correction_revision": revision, "corrections": corrections,
                   "learned_rules": semantic_feedback, "evidence_policy": POLICY_VERSION, **diagnostics}
        return before_terms, terms, contributions, context

    def correction_set(self, source_id: str, *, corrections: list[dict], expected_revision: int) -> dict:
        """Append pending feedback; whole-input agreement still gates fitting."""
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT i.*, s.body FROM brain_inputs i JOIN sources s "
                             "ON s.id = i.source_id WHERE i.source_id = ?", (source_id,)).fetchone()
            if row is None:
                raise KeyError("brain input not found")
            if row["status"] != "pending":
                raise ValueError("only pending inputs can be corrected")
            revision, _ = latest_corrections(db, source_id)
            if revision != expected_revision:
                raise ValueError("correction revision changed; refresh correction_history")
            checked = validate_corrections(row["body"], row["kind"], row["self_speaker"], corrections)
            cursor = db.execute("INSERT INTO brain_corrections(source_id, payload, created_at) VALUES (?, ?, ?)",
                                (source_id, json.dumps(checked, ensure_ascii=False), _now()))
            return {"source_id": source_id, "revision": cursor.lastrowid,
                    "status": "pending", "corrections": checked}

    def correction_history(self, source_id: str) -> dict:
        with self.store._connect() as db:
            db.execute("BEGIN")
            source = db.execute("SELECT status FROM brain_inputs WHERE source_id = ?", (source_id,)).fetchone()
            if source is None:
                raise KeyError("brain input not found")
            history = db.execute("SELECT revision, payload, created_at FROM brain_corrections "
                                 "WHERE source_id = ? ORDER BY revision", (source_id,)).fetchall()
            context = db.execute("SELECT payload FROM brain_fit_context WHERE source_id = ?", (source_id,)).fetchone()
        records = [{"revision": item["revision"], "corrections": json.loads(item["payload"]),
                    "created_at": item["created_at"]} for item in history]
        return {"source_id": source_id, "status": source["status"],
                "revision": records[-1]["revision"] if records else 0,
                "corrections": records[-1]["corrections"] if records else [], "history": records,
                "fit_context": json.loads(context["payload"]) if context else None}

    def preview(self, source_id: str) -> dict:
        """Preview any inactive source; restore frozen evidence if previously fitted."""
        with self.store._connect() as db:
            db.execute("BEGIN")  # Keep terms and scores in one read snapshot.
            row = db.execute(
                "SELECT i.*, s.body FROM brain_inputs i JOIN sources s ON s.id = i.source_id "
                "WHERE i.source_id = ?", (source_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"brain input not found: {source_id}")
            if row["status"] == "agreed":
                raise ValueError("agreed brain inputs cannot be previewed")
            before_terms, terms, contributions, context = self._fit_observations(db, row)
            projected = []
            for item in contributions:
                current = db.execute(
                    "SELECT value, support, net FROM brain_state "
                    "WHERE partition = ? AND parameter = ?",
                    (row["partition"], item.parameter),
                ).fetchone()
                after = _score(current["net"] + item.sign, current["support"] + 1)
                projected.append({
                    "source_id": source_id, "partition": row["partition"],
                    "parameter": item.parameter, "before": current["value"],
                    "after": after, "delta": after - current["value"],
                    "support_before": current["support"],
                    "support_after": current["support"] + 1,
                    "evidence": item.evidence, "span": [item.start, item.end],
                    "rule_id": item.rule_id, "action": "preview",
                })
            translator_effects = [
                {"term": term, "documents_before": before_terms.get(term, 0),
                 "documents_after": before_terms.get(term, 0) + 1,
                 "source_id": source_id}
                for term in sorted(terms) if before_terms.get(term, 0) == 1
            ]
            translation = translate(row["body"],
                                    kind="diary" if row["kind"] == "philosophy" else row["kind"],
                                    self_speaker=row["self_speaker"])
        return {
            "source_id": source_id, **approval_metadata(row), "partition": row["partition"],
            "kind": row["kind"], "hypothetical": True,
            "effects": projected, "translator_effects": translator_effects,
            "observed_terms": len(terms), "translation": translation,
            "interpretation": context,
        }

    def _fit_observations(self, db: sqlite3.Connection, row: sqlite3.Row
                          ) -> tuple[dict[str, int], dict[str, int], list[Contribution], dict]:
        context = db.execute("SELECT payload FROM brain_fit_context WHERE source_id=?",
                             (row["source_id"],)).fetchone()
        if context is None:
            return self._observations(db, row)
        terms = {item["term"]: item["occurrences"] for item in db.execute(
            "SELECT term, occurrences FROM brain_terms WHERE source_id=?", (row["source_id"],))}
        contributions = [Contribution(item["parameter"], item["sign"], item["evidence"],
                                      item["start_offset"], item["end_offset"], item["rule_id"])
                         for item in db.execute("SELECT * FROM brain_contributions WHERE source_id=? "
                                                "ORDER BY start_offset, parameter", (row["source_id"],))]
        return self._term_counts(db, row["partition"]), terms, contributions, json.loads(context["payload"])

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
        """Set the second whole-source judgement, including explicit re-review."""
        if type(agree) is not bool:
            raise ValueError("agree must be a boolean")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._review(db, self._input(db, source_id), agree=agree, confirmed_by="manual")

    def _review(self, db: sqlite3.Connection, row: sqlite3.Row, *, agree: bool,
                confirmed_by: str) -> dict:
        if not row["immediate"]:
            raise ValueError("immediate=false cannot be reviewed; source editing is not yet supported")
        if (agree and row["status"] == "agreed") or (not agree and row["confirm"] == 0):
            return self._decision_result(row)  # Same decision: no duplicate fit or audit event.
        if not agree:
            return self._deactivate(db, row, status="disagreed", reason="confirm_false",
                                    confirmed_by=confirmed_by, action="review")

        source_id, partition = row["source_id"], row["partition"]
        before_terms, terms, contributions, context = self._fit_observations(db, row)
        frozen = db.execute("SELECT 1 FROM brain_fit_context WHERE source_id=?", (source_id,)).fetchone()
        if frozen is None:
            db.execute("INSERT INTO brain_fit_context(source_id, payload) VALUES (?, ?)",
                       (source_id, json.dumps(context, ensure_ascii=False)))
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
        timestamp = _now()
        db.execute("UPDATE brain_inputs SET status='agreed', confirm=1, ever_fitted=1, confirmed_by=?, "
                   "reason=NULL, reviewed_at=? WHERE source_id=?", (confirmed_by, timestamp, source_id))
        effects = [self._recompute(db, partition, item.parameter, source_id,
                                   item.evidence, item.start, item.end, item.rule_id, "approve")
                   for item in contributions]
        after_terms = self._term_counts(db, partition)
        translator_effects = [
            {"term": term, "documents_before": before_terms.get(term, 0),
             "documents_after": after_terms[term], "source_id": source_id}
            for term in sorted(terms) if before_terms.get(term, 0) < 2 <= after_terms[term]
        ]
        updated = self._input(db, source_id)
        record_review(db, source_id, "review", approval_metadata(row), approval_metadata(updated),
                      effects, timestamp)
        return {**self._decision_result(updated, effects, translator_effects),
                "observed_terms": len(terms), "interpretation": context,
                "restored_fit": frozen is not None}

    def _deactivate(self, db: sqlite3.Connection, row: sqlite3.Row, *, status: str,
                    reason: str, confirmed_by: str, action: str) -> dict:
        source_id, partition = row["source_id"], row["partition"]
        active = row["status"] == "agreed"
        before_terms = self._term_counts(db, partition) if active else {}
        items = db.execute("SELECT * FROM brain_contributions WHERE source_id=? "
                           "ORDER BY start_offset, parameter", (source_id,)).fetchall() if active else []
        timestamp = _now()
        db.execute("UPDATE brain_inputs SET status=?, confirm=0, confirmed_by=?, reason=?, "
                   "reviewed_at=? WHERE source_id=?", (status, confirmed_by, reason, timestamp, source_id))
        effects = [self._recompute(db, partition, item["parameter"], source_id,
                                   item["evidence"], item["start_offset"], item["end_offset"],
                                   item["rule_id"], "revoke") for item in items]
        after_terms = self._term_counts(db, partition) if active else {}
        translator_effects = [
            {"term": item["term"], "documents_before": before_terms.get(item["term"], 0),
             "documents_after": after_terms.get(item["term"], 0), "source_id": source_id}
            for item in db.execute("SELECT term FROM brain_terms WHERE source_id=? ORDER BY term", (source_id,))
            if before_terms.get(item["term"], 0) >= 2 > after_terms.get(item["term"], 0)
        ] if active else []
        updated = self._input(db, source_id)
        record_review(db, source_id, action, approval_metadata(row), approval_metadata(updated),
                      effects, timestamp)
        return self._decision_result(updated, effects, translator_effects)

    def revoke(self, source_id: str) -> dict:
        """Remove an agreed source from the active fit; retain audit history."""
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._input(db, source_id)
            if row["status"] != "agreed":
                raise ValueError("only agreed sources can be revoked")
            return self._deactivate(db, row, status="revoked", reason="user_revoked",
                                    confirmed_by=row["confirmed_by"], action="revoke")

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
        return rank_from_state(options, self.state("rational"))
