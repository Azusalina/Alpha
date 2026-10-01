"""Application entry point for the reviewed local self-model and memory store."""

from __future__ import annotations

from pathlib import Path

from model import BrainModel
from model.approvals import metadata as approval_metadata
from model.catalog import PARTITIONS

from .extraction import TextModel, extract_candidates
from . import pagination


class BrainCore:
    """One source identity and review flow for every client-facing operation.

    Legacy store-only sources stay accessible via the old CLI, but are not
    included in this application's inputs, candidates, or active memories.
    Candidate publication keeps the existing explicit review policy.
    """

    def __init__(self, path: str | Path):
        self.model = BrainModel(path)
        self.store = self.model.store
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            pagination.initialize(db)

    @staticmethod
    def _partition(partition: str | None) -> None:
        if partition is not None and partition not in PARTITIONS:
            raise ValueError("invalid partition")

    @staticmethod
    def _limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")

    def submit(self, text: str, *, partition: str, kind: str = "diary",
               self_speaker: str | None = None, source_ref: str | None = None,
               immediate: bool = True, exclamation: bool = False) -> dict:
        return self.model.submit_result(text, partition=partition, kind=kind,
                                        self_speaker=self_speaker, source_ref=source_ref,
                                        immediate=immediate, exclamation=exclamation)

    def input_get(self, source_id: str) -> dict:
        with self.store._connect() as db:
            row = db.execute(
                "SELECT i.*, s.body AS text, s.source_ref, s.created_at "
                "FROM brain_inputs i JOIN sources s ON s.id = i.source_id "
                "WHERE i.source_id = ?", (source_id,),
            ).fetchone()
        if row is None:
            raise KeyError("brain input not found")
        return {**dict(row), **approval_metadata(row), **self._summary(row["text"])}

    @staticmethod
    def _summary(text: str) -> dict:
        # SQLite length/substr stop at embedded NUL; Python preserves every
        # Unicode code point, including CRLF, combining marks and emoji.
        return {"excerpt": text[:80], "char_count": len(text), "edited_at": None}

    def _input_filters(self, partition: str | None, status: str | None, limit: int
                       ) -> tuple[list[str], list[str]]:
        self._partition(partition)
        self._limit(limit)
        if status is not None and status not in ("pending", "agreed", "disagreed", "revoked"):
            raise ValueError("invalid input status")
        clauses, values = [], []
        for column, value in (("partition", partition), ("status", status)):
            if value is not None:
                clauses.append(f"i.{column} = ?")
                values.append(value)
        return clauses, values

    @staticmethod
    def _input_rows(db, clauses: list[str], values: list, limit: int) -> list:
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return db.execute(
            "SELECT i.*, s.source_ref, s.created_at FROM brain_inputs i "
            "JOIN sources s ON s.id=i.source_id" + where +
            " ORDER BY s.created_at DESC, i.source_id DESC LIMIT ?", (*values, limit),
        ).fetchall()

    def _input_summaries(self, db, rows: list) -> list[dict]:
        if not rows:
            return []
        # Only sort small metadata rows. Read selected bodies in one batch,
        # iterating instead of accumulating up to 100 full journals in memory.
        summaries = {}
        placeholders = ",".join("?" for _ in rows)
        for source in db.execute(f"SELECT id, body FROM sources WHERE id IN ({placeholders})",
                                 [row["source_id"] for row in rows]):
            summaries[source["id"]] = self._summary(source["body"])
        return [{**dict(row), **approval_metadata(row), **summaries[row["source_id"]]} for row in rows]

    def input_list(self, *, partition: str | None = None, status: str | None = None,
                   limit: int = 20) -> list[dict]:
        clauses, values = self._input_filters(partition, status, limit)
        with self.store._connect() as db:
            db.execute("BEGIN")
            return self._input_summaries(db, self._input_rows(db, clauses, values, limit))

    def input_page(self, *, partition: str | None = None, status: str | None = None,
                   limit: int = 20, cursor: str | None = None) -> dict:
        clauses, values = self._input_filters(partition, status, limit)
        with self.store._connect() as db:
            db.execute("BEGIN")  # Total, eligibility, metadata and text share one read snapshot.
            revision = db.execute("SELECT COALESCE(MAX(revision), 0) FROM brain_review_history").fetchone()[0]
            secret = pagination.key(db)
            where = " WHERE " + " AND ".join(clauses) if clauses else ""
            total = db.execute("SELECT COUNT(*) FROM brain_inputs i" + where, values).fetchone()[0]
            if cursor is not None:
                after = pagination.decode(cursor, secret, revision=revision, partition=partition, status=status)
                anchor = db.execute("SELECT 1 FROM brain_inputs i JOIN sources s ON s.id=i.source_id "
                                    "WHERE i.source_id=? AND s.created_at=?",
                                    (after["source_id"], after["created_at"])).fetchone()
                if anchor is None:
                    raise ValueError("input cursor anchor unavailable; restart from the first page")
                clauses.append("(s.created_at < ? OR (s.created_at = ? AND i.source_id < ?))")
                values.extend((after["created_at"], after["created_at"], after["source_id"]))
            rows = self._input_rows(db, clauses, values, limit + 1)
            selected, next_cursor = rows[:limit], None
            if len(rows) > limit:
                last = selected[-1]
                next_cursor = pagination.encode(secret, revision=revision, partition=partition, status=status,
                                                created_at=last["created_at"], source_id=last["source_id"])
            return {"items": self._input_summaries(db, selected), "total": total,
                    "next_cursor": next_cursor, "revision": revision}

    def preview(self, source_id: str) -> dict:
        return self.model.preview(source_id)

    def review(self, source_id: str, *, agree: bool) -> dict:
        return self.model.review(source_id, agree=agree)

    def review_history(self, source_id: str) -> dict:
        return self.model.review_history(source_id)

    def correction_set(self, source_id: str, *, corrections: list[dict], expected_revision: int) -> dict:
        return self.model.correction_set(source_id, corrections=corrections, expected_revision=expected_revision)

    def correction_history(self, source_id: str) -> dict:
        return self.model.correction_history(source_id)

    def revoke(self, source_id: str) -> dict:
        return self.model.revoke(source_id)

    def state(self, partition: str | None = None) -> dict:
        return self.model.state(partition)

    def effects(self, *, source_id: str | None = None) -> list[dict]:
        if source_id is not None:
            self.input_get(source_id)
        return self.model.effects(source_id=source_id)

    def terms(self, *, partition: str, min_documents: int = 2) -> list[dict]:
        return self.model.learned_terms(partition=partition, min_documents=min_documents)

    def rank(self, options: list[dict]) -> dict:
        return self.model.rank_options(options)

    def candidate_propose(self, source_id: str, claim: str, evidence: str) -> dict:
        self.input_get(source_id)
        candidate_id = self.store.propose(source_id, claim, evidence)
        return {"candidate_id": candidate_id, "source_id": source_id, "status": "pending"}

    def extract_memories(self, source_id: str, model: TextModel) -> list[str]:
        """Optional Python-only adapter; no text model is configured by the API."""
        self.input_get(source_id)
        return extract_candidates(self.store, source_id, model)

    def candidate_review(self, candidate_id: str, *, accept: bool) -> dict:
        with self.store._connect() as db:
            row = db.execute(
                "SELECT c.id FROM candidates c JOIN brain_inputs i "
                "ON i.source_id = c.source_id WHERE c.id = ?", (candidate_id,),
            ).fetchone()
        if row is None:
            raise KeyError("brain candidate not found")
        return self.store.resolve(candidate_id, accept=accept)

    def _memories(self, *, active: bool, partition: str | None, status: str | None,
                  query: str | None, limit: int) -> list[dict]:
        self._partition(partition)
        self._limit(limit)
        clauses, values = [], []
        if active:
            clauses.extend(("c.status = 'accepted'", "i.status = 'agreed'"))
        elif status is not None:
            if status not in ("pending", "accepted", "rejected"):
                raise ValueError("invalid candidate status")
            clauses.append("c.status = ?")
            values.append(status)
        if partition is not None:
            clauses.append("i.partition = ?")
            values.append(partition)
        if query is not None:
            if not isinstance(query, str) or not query.strip():
                raise ValueError("query must contain text")
            clauses.append("(instr(lower(c.claim), lower(?)) > 0 "
                           "OR instr(lower(c.evidence), lower(?)) > 0)")
            values.extend((query.strip(), query.strip()))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.store._connect() as db:
            rows = db.execute(
                "SELECT c.*, i.partition, i.status AS source_status, s.source_ref "
                "FROM candidates c JOIN brain_inputs i ON i.source_id = c.source_id "
                "JOIN sources s ON s.id = c.source_id" + where +
                " ORDER BY c.created_at, c.id LIMIT ?", (*values, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def candidate_list(self, *, partition: str | None = None, status: str | None = None,
                       limit: int = 20) -> list[dict]:
        return self._memories(active=False, partition=partition, status=status,
                              query=None, limit=limit)

    def memory_list(self, *, partition: str | None = None, limit: int = 20) -> list[dict]:
        return self._memories(active=True, partition=partition, status=None,
                              query=None, limit=limit)

    def memory_search(self, query: str, *, partition: str | None = None,
                      limit: int = 20) -> list[dict]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must contain text")
        return self._memories(active=True, partition=partition, status=None,
                              query=query, limit=limit)
