"""Explicit feedback validation and scoped, exact-clause correction memory."""

from __future__ import annotations

import json
import sqlite3

from translator.learning import own_chat_ranges

from .catalog import PARAMETERS
from .evidence import Contribution, authored_segments


def validate_corrections(text: str, kind: str, self_speaker: str | None,
                         corrections: list[dict]) -> list[dict]:
    if not isinstance(corrections, list) or len(corrections) > len(PARAMETERS):
        raise ValueError("corrections must be an array with at most one item per parameter")
    checked, seen = [], set()
    author_ranges = own_chat_ranges(text, self_speaker) if kind == "chat" else [(0, len(text))]
    for item in corrections:
        if not isinstance(item, dict) or set(item) != {"parameter", "sign", "evidence", "span"}:
            raise ValueError("each correction needs parameter, sign, evidence and span")
        parameter, sign, evidence, span = (item[field] for field in ("parameter", "sign", "evidence", "span"))
        if not isinstance(parameter, str) or parameter not in PARAMETERS or parameter in seen:
            raise ValueError("correction parameter must be known and unique")
        if type(sign) is not int or sign not in (-1, 0, 1):
            raise ValueError("correction sign must be -1, 0 or 1")
        if sign == -1 and not parameter.startswith("value."):
            raise ValueError("non-value cues support only sign 0 or 1")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("correction evidence must contain text")
        if (not isinstance(span, list) or len(span) != 2 or any(type(v) is not int for v in span)
                or not 0 <= span[0] < span[1] <= len(text) or text[span[0]:span[1]] != evidence):
            raise ValueError("correction span must select its exact evidence in the source")
        if not any(start <= span[0] and span[1] <= end for start, end in author_ranges):
            raise ValueError("chat correction must belong to the self speaker")
        checked.append({"parameter": parameter, "sign": sign, "evidence": evidence,
                        "span": list(span)})
        seen.add(parameter)
    return checked


def latest_corrections(db: sqlite3.Connection, source_id: str) -> tuple[int, list[dict]]:
    row = db.execute("SELECT revision, payload FROM brain_corrections WHERE source_id = ? "
                     "ORDER BY revision DESC LIMIT 1", (source_id,)).fetchone()
    return (row["revision"], json.loads(row["payload"])) if row else (0, [])


def learned_rules(db: sqlite3.Connection, row: sqlite3.Row
                  ) -> tuple[dict[tuple[str, str, str], int | None], list[dict]]:
    """Only explicit feedback teaches a label; inferred examples never do."""
    segments = {(segment, row["body"][offset + len(segment):offset + len(segment) + 1])
                for segment, offset in authored_segments(row["body"], row["kind"], row["self_speaker"])}
    examples = db.execute(
        "SELECT c.source_id, c.payload, i.kind, i.self_speaker, s.body "
        "FROM brain_corrections c JOIN brain_inputs i ON i.source_id = c.source_id "
        "JOIN sources s ON s.id = c.source_id "
        "WHERE i.status = 'agreed' AND i.partition = ? AND i.kind = ? "
        "AND c.revision = (SELECT MAX(other.revision) FROM brain_corrections other "
        "WHERE other.source_id = c.source_id)", (row["partition"], row["kind"]),
    ).fetchall()
    pool = {}
    for example in examples:
        complete = {(segment, offset, offset + len(segment)) for segment, offset in
                    authored_segments(example["body"], example["kind"], example["self_speaker"])}
        for correction in json.loads(example["payload"]):
            phrase = correction["evidence"]
            end = correction["span"][1]
            boundary = example["body"][end:end + 1]
            if (phrase, boundary) not in segments or (phrase, *correction["span"]) not in complete:
                continue  # Short excerpts are local corrections, not reusable rules.
            pool.setdefault((correction["parameter"], phrase, boundary), []).append(
                (correction["sign"], example["source_id"]))
    rules, metadata = {}, []
    for (parameter, phrase, boundary), items in sorted(pool.items()):
        labels = {sign for sign, _ in items}
        sources = sorted({source for _, source in items})
        status = "conflict" if len(labels) > 1 else "active" if len(sources) >= 2 else "insufficient"
        if status == "conflict":
            rules[(parameter, phrase, boundary)] = None
        elif status == "active":
            rules[(parameter, phrase, boundary)] = next(iter(labels))
        metadata.append({"parameter": parameter, "evidence": phrase, "boundary": boundary, "status": status,
                         "sign": next(iter(labels)) if len(labels) == 1 else None,
                         "support_source_ids": sources, "support": len(sources)})
    return rules, metadata


def apply_local(contributions: list[Contribution], corrections: list[dict]) -> list[Contribution]:
    overridden = {item["parameter"] for item in corrections}
    result = [item for item in contributions if item.parameter not in overridden]
    result.extend(Contribution(item["parameter"], item["sign"], item["evidence"],
                               *item["span"], "user_correction")
                  for item in corrections if item["sign"])
    return sorted(result, key=lambda item: (item.start, item.parameter))
