"""Conservative Chinese text cues and interpretations with exact source spans.

Rules are intentionally auditable. They do not claim to understand arbitrary
grammar or spoken tone. A later NLP/model adapter can replace individual stages
without changing the evidence-and-review contract.
"""

from __future__ import annotations

import re
from collections import Counter
from .discourse import AssertionGuards

MAX_CHARS = 1_000_000
_CHAT_LINE = re.compile(r"^\s*([^:：\s]{1,32})\s*[:：]\s*(.*)$")
_SEGMENT = re.compile(r"[^。！？!?；;]+")

# Cue names are an internal, versioned vocabulary, not the product taxonomy.
_CUE_RULES = (
    ("event_word", "cancellation", re.compile(r"取消|放鴿子|放鸽子")),
    ("frequency_word", "claimed_repetition", re.compile(r"又|總是|总是|每次")),
    ("contrast_word", "contrast", re.compile(r"但(?:是)?|不過|不过|其實|其实")),
    ("uncertainty_word", "hedge", re.compile(r"可能|也許|也许|或許|或许|大概")),
    ("emotion_word", "disappointment", re.compile(r"失望")),
    ("emotion_word", "sadness", re.compile(r"難過|难过|傷心|伤心")),
    ("emotion_word", "happiness", re.compile(r"開心|开心|高興|高兴")),
    ("emotion_word", "anger", re.compile(r"生氣|生气|憤怒|愤怒")),
)
_NEGATION = re.compile(r"(?:不|沒|没|沒有|没有|無|无|未)\s{0,2}$")
_THIRD_PERSON = re.compile(r"(?:他|她|別人|别人|朋友|同事|阿[^\s，,。；;]{1,3}).{0,12}$")
_REPORTED = re.compile(r"(?:他|她|別人|别人|朋友|同事).{0,6}(?:說|说|表示).{0,12}$")
_LESS_CONTACT = re.compile(
    r"(?:不會|不会|不想|不再|少|減少|减少).{0,6}(?:主動|主动)|"
    r"(?:主動|主动).{0,6}(?:不會|不会|不想|不再|少|減少|减少)"
)
_CONTACT_VERB = re.compile(r"約|约|聯繫|联系|找")


def _parts(text: str, kind: str, self_speaker: str | None) -> tuple[list[tuple[str, int, str]], list[dict]]:
    parts: list[tuple[str, int, str]] = []
    skipped: list[dict] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        if kind == "chat":
            match = _CHAT_LINE.match(bare)
            if match is None:
                if bare.strip():
                    skipped.append({"span": [offset, offset + len(bare)], "reason": "unlabeled_chat_line"})
                offset += len(line)
                continue
            speaker, content = match.groups()
            if speaker != self_speaker:
                offset += len(line)
                continue
            base = offset + match.start(2)
        else:
            content, base = bare, offset
        for segment in _SEGMENT.finditer(content):
            value = segment.group().strip()
            if value:
                leading = len(segment.group()) - len(segment.group().lstrip())
                parts.append((value, base + segment.start() + leading, self_speaker or "author"))
        offset += len(line)
    return parts, skipped


def translate(text: str, *, kind: str = "diary", self_speaker: str | None = None) -> dict:
    """Return cues and reviewable interpretations; never mutate or send input.

    Spans are Python Unicode character offsets into the original string.
    Chat accepts one `speaker: content` message per line. Only exact speaker
    matches are analyzed; unlabeled lines are reported as skipped.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must contain content")
    if len(text) > MAX_CHARS:
        raise ValueError(f"text exceeds {MAX_CHARS} characters")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("text must not contain surrogate code points") from None
    if kind not in {"diary", "chat"}:
        raise ValueError("kind must be diary or chat")
    if kind == "chat" and (not isinstance(self_speaker, str) or not self_speaker.strip()):
        raise ValueError("chat requires self_speaker")
    if self_speaker is not None and (not isinstance(self_speaker, str) or not self_speaker.strip()):
        raise ValueError("self_speaker must contain text")

    parts, skipped = _parts(text, kind, self_speaker)
    guards = AssertionGuards(text, kind, self_speaker)
    cues: list[dict] = []
    candidates: list[dict] = []
    for segment, start, speaker in parts:
        hedged = bool(re.search(r"可能|也許|也许|或許|或许|大概", segment))
        for category, value, pattern in _CUE_RULES:
            for match in pattern.finditer(segment):
                # Existing subject/negation patterns have bounded lookbehind;
                # don't repeatedly copy a long paragraph's entire prefix.
                before = segment[max(0, match.start() - 32):match.start()]
                negated = category == "emotion_word" and bool(_NEGATION.search(before))
                span = [start + match.start(), start + match.end()]
                cues.append({
                    "category": category, "value": value, "evidence": match.group(),
                    "span": span, "speaker": speaker, "negated": negated,
                })
                if category != "emotion_word" or negated:
                    continue
                clause_start, clause_end = guards.clause_span(start + match.start(), start, start + len(segment))
                if guards.reason(clause_start, clause_end):
                    continue
                # Quoted/reported feelings are not evidence of the writer's mood.
                clause = re.split(r"[，,、]", before)[-1]
                first_person_object = bool(re.search(r"我(?:對|对).{0,8}$", clause))
                if _REPORTED.search(clause) or (_THIRD_PERSON.search(clause) and not first_person_object):
                    continue
                candidates.append({
                    "type": "textual_emotion", "value": value,
                    "evidence": match.group(), "span": span, "speaker": speaker,
                    "certainty": "hedged" if hedged else "explicit_word",
                    "status": "pending_review",
                })
        intent = _LESS_CONTACT.search(segment)
        if intent:
            intent_start, intent_end = guards.clause_span(start + intent.start(), start, start + len(segment))
            intent_text = text[intent_start:intent_end]
        if intent and _CONTACT_VERB.search(intent_text) and not guards.reason(intent_start, intent_end):
            # Only explicit first-person language can create an intention cue.
            if (re.search(r"我|自己", intent_text)
                    and not re.search(r"(?:他|她).{0,8}(?:主動|主动)", intent_text)
                    and not _REPORTED.search(intent_text[:start + intent.start() - intent_start])):
                candidates.append({
                    "type": "contact_intention", "value": "less_initiative",
                    "evidence": intent_text, "span": [intent_start, intent_end],
                    "speaker": speaker, "certainty": "hedged" if hedged else "explicit_word",
                    "status": "pending_review",
                })
    return {
        "schema_version": 1, "kind": kind, "self_speaker": self_speaker,
        "cues": cues, "candidates": candidates, "skipped": skipped,
        "limitations": ["lexical_rules_only", "no_trait_or_diagnosis", "non_assertive_candidates_withheld"],
    }


def summarize(reports: list[dict]) -> dict:
    """Count candidates across independent inputs; do not infer a trait/trend."""
    if not isinstance(reports, list) or any(not isinstance(r, dict) for r in reports):
        raise ValueError("reports must be a list of translation reports")
    counts: Counter[tuple[str, str]] = Counter()
    for report in reports:
        if report.get("schema_version") != 1 or not isinstance(report.get("candidates"), list):
            raise ValueError("invalid translation report")
        # One document counts once per candidate kind/value, regardless of repeats.
        seen = {(item["type"], item["value"]) for item in report["candidates"]}
        counts.update(seen)
    return {
        "input_count": len(reports),
        "cross_document_counts": [
            {"type": kind, "value": value, "document_count": count}
            for (kind, value), count in sorted(counts.items())
        ],
        "interpretation": "occurrence_counts_only; not a stable tendency, trend, or diagnosis",
    }
