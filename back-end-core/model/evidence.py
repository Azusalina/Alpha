"""Bounded, evidence-only observations for model updates.

This intentionally under-extracts ambiguous prose. A missing update is safer
than treating a topic mention, quotation, or another person's value as the
user's endorsed principle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from translator import translate

from .catalog import VALUE_WORDS

_BOUNDARY = re.compile(r"[。！？!?；;，,\n]|但(?:是)?|不(?:过|過)|而(?:是)?|却|卻")
_CHAT_LINE = re.compile(r"^\s*([^:：\s]{1,32})\s*[:：]\s*(.*)$")
_FIRST_PERSON = re.compile(r"我(?:也|仍然|一直)?(?:不|没|沒有|没有)?(?:认为|認為|觉得|覺得|相信|重视|重視|看重|珍惜|坚持|堅持)|(?:对|對)我来[说說]")
_DIRECT = re.compile(r"我(?:也|仍然|一直)?(?:不|没|沒有|没有)?(?:重视|重視|看重|珍惜|坚持|堅持)")
_IMPORTANCE = re.compile(r"重要|优先|優先|值得")
_NORMATIVE = re.compile(r"(?:应该|應該|应当|應當|必须|必須)(?:[^。！？!?；;，,]{0,3})")
_NEGATIVE = re.compile(r"(?:不|没|沒有|没有)(?:重视|重視|看重|珍惜)|我不(?:认为|認為|觉得|覺得|相信)|不重要|不太重要|没那么重要|沒有那麼重要")
_NEGATIVE_NORMATIVE = re.compile(r"不(?:应该|應該|应当|應當|必須|必须)")
_ANTI = re.compile(r"反对|反對|拒绝|拒絕|排斥")
_REPORTED = re.compile(r"(?:他|她|有人|朋友|阿[\u3400-\u9fff]{1,3})(?:说|說|觉得|覺得|认为|認為|重视|重視)")


@dataclass(frozen=True)
class Contribution:
    parameter: str
    sign: int
    evidence: str
    start: int
    end: int
    rule_id: str


def _word_positions(segment: str, parameter: str) -> list[int]:
    return [match.start() for word in VALUE_WORDS[parameter]
            for match in re.finditer(re.escape(word), segment)]


def _split_segments(text: str, base: int):
    start = 0
    for boundary in _BOUNDARY.finditer(text):
        piece = text[start:boundary.start()]
        if piece.strip():
            leading = len(piece) - len(piece.lstrip())
            yield piece.strip(), base + start + leading
        start = boundary.end()
    piece = text[start:]
    if piece.strip():
        leading = len(piece) - len(piece.lstrip())
        yield piece.strip(), base + start + leading


def _value_segments(text: str, kind: str, self_speaker: str | None):
    if kind != "chat":
        yield from _split_segments(text, 0)
        return
    offset = 0
    for line in text.splitlines(keepends=True):
        match = _CHAT_LINE.match(line.rstrip("\r\n"))
        if match is not None and match.group(1) == self_speaker:
            content = match.group(2)
            yield from _split_segments(content, offset + match.start(2))
        offset += len(line)


def extract_contributions(text: str, *, kind: str, self_speaker: str | None = None) -> list[Contribution]:
    """At most one contribution per parameter per source, or none on conflict."""
    if kind not in {"diary", "chat", "philosophy"}:
        raise ValueError("kind must be diary, chat, or philosophy")
    translated = translate(text, kind="diary" if kind == "philosophy" else kind,
                           self_speaker=self_speaker)
    pool: dict[str, list[Contribution]] = {}

    # Chat claims use only the self speaker's labeled lines.
    for segment, offset in _value_segments(text, kind, self_speaker):
        if not segment or _REPORTED.search(segment):
            continue
        explicit = bool(_FIRST_PERSON.search(segment) or _DIRECT.search(segment))
        if not explicit and kind != "philosophy":
            continue
        if not (_DIRECT.search(segment) or _IMPORTANCE.search(segment)
                or (kind == "philosophy" and _NORMATIVE.search(segment))):
            continue
        if kind == "philosophy" and _NORMATIVE.search(segment) and (
                _NEGATIVE_NORMATIVE.search(segment) or _ANTI.search(segment)):
            # Nested negation and normative opposition need deeper semantics.
            continue
        # Comparative statements are handled only when the left-hand value
        # can be identified unambiguously. Other comparisons are skipped.
        comparative = "比" in segment
        if comparative and (_NEGATIVE.search(segment) or _NEGATIVE_NORMATIVE.search(segment)):
            continue
        winner = segment.split("比", 1)[0] if comparative else None
        for parameter in VALUE_WORDS:
            positions = _word_positions(segment, parameter)
            if not positions:
                continue
            if comparative and not _word_positions(winner or "", parameter):
                continue
            sign = (-1 if (_NEGATIVE.search(segment) or _NEGATIVE_NORMATIVE.search(segment))
                    and not comparative else 1)
            rule_id = ("comparative_value_preference" if comparative else
                       "negated_value_statement" if sign < 0 else
                       "explicit_value_statement")
            pool.setdefault(parameter, []).append(
                Contribution(parameter, sign, segment, offset, offset + len(segment), rule_id)
            )

    emotion_map = {
        "disappointment": "affect.disappointment", "sadness": "affect.sadness",
        "happiness": "affect.happiness", "anger": "affect.anger",
    }
    for item in translated["candidates"]:
        parameter = (emotion_map.get(item["value"]) if item["type"] == "textual_emotion"
                     else "expression.less_initiative" if item["type"] == "contact_intention" else None)
        if parameter is not None:
            rule_id = ("textual_emotion_cue" if item["type"] == "textual_emotion"
                       else "contact_intention_cue")
            pool.setdefault(parameter, []).append(
                Contribution(parameter, 1, item["evidence"], *item["span"], rule_id)
            )

    result = []
    for parameter, items in pool.items():
        # Contradictory claims in one source do not move a parameter.
        if {item.sign for item in items} == {-1, 1}:
            continue
        result.append(items[0])
    return sorted(result, key=lambda item: (item.start, item.parameter))
