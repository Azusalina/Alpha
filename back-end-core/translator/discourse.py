"""Bounded quotation and non-assertion guards; not general grammar parsing."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right

from .learning import own_chat_ranges

POLICY_VERSION = "assertion-guards-v2"
_PAIRS = {"“": "”", "‘": "’", "「": "」", "『": "』", "《": "》", '"': '"', "'": "'"}
_FENCE = re.compile(r"`+|~{3,}")
_MARKDOWN_QUOTE = re.compile(r"(?m)^[ \t]{0,3}>[^\r\n]*")
_QUESTION = re.compile(r"吗|嗎|么|麼|是否|是不是|会不会|會不會|要不要|难道|難道|为何|為何|为什么|為什麼")
_HYPOTHESIS = re.compile(r"如果|假如|假设|假設|假若|倘若|要是|即使|假使")
_HEDGE = re.compile(r"可能|也许|也許|或许|或許|大概|似乎|未必")
_REPORTED = re.compile(r"(?:他|她|有人|别人|別人|朋友|同事|老师|老師|父母|阿[\u3400-\u9fff]{1,3})"
                       r"(?:说|說|表示|觉得|覺得|认为|認為|重视|重視)")
_HARD_BOUNDARY = re.compile(r"[。！？!?；;\r\n]")
_FOLLOWING_SPACE = re.compile(r"[ \t\r]*")
_SOFT_BOUNDARY = re.compile(r"[，,]|但(?:是)?|不(?:过|過)|而(?:是)?|却|卻")
_OTHER_ACTOR = (r"(?:他们|她们|他們|她們|你们|你們|他人|别人|別人|某人|有人|"
                r"朋友|同事|同学|同學|老师|老師|父母|爸妈|爸媽|他|她|你|阿[\u3400-\u9fff]{1,3})")
_ACTOR_QUALIFIER = (r"(?:也|很|更|最|非常|特别|特別|一直|其实|其實|最近|经常|經常|"
                    r"并不|並不|不|没|沒|没有|沒有|未必|可能|只是){0,3}")
_OTHER_VALUE = re.compile(
    _OTHER_ACTOR + _ACTOR_QUALIFIER
    + r"(?:认为|認為|觉得|覺得|相信|重视|重視|看重|珍惜|坚持|堅持)"
    + r"|" + _OTHER_ACTOR + _ACTOR_QUALIFIER + r"(?:把|将|將)[^。！？!?；;，,\r\n]{0,32}?"
    + r"(?:看得|看作|看成|视为|視為|当作|當作|放在)[^。！？!?；;，,\r\n]{0,6}?"
    + r"(?:重要|优先|優先|首位|第一|核心)"
    + r"|(?:对|對)" + _OTHER_ACTOR + r"[来來][说說]"
    + r"|(?:在|从|從)" + _OTHER_ACTOR + r"(?:的)?(?:眼[里裡中]|心[里裡中]|看来|看來)"
    + r"|" + _OTHER_ACTOR + r"(?:的)?(?:眼[里裡中]|心[里裡中])"
)
_OWN_VALUE_VIEW = re.compile(r"(?:对|對)我[来來][说說]|(?:在|从|從)我(?:的)?(?:眼[里裡中]|看来|看來)")


def protected_ranges(text: str, kind: str, self_speaker: str | None) -> list[tuple[int, int, str]]:
    """Return quoted/code spans; chat quotation state never crosses speakers."""
    ranges = own_chat_ranges(text, self_speaker) if kind == "chat" else [(0, len(text))]
    result = []
    for start, end in ranges:
        stack, index = [], start
        while index < end:
            char = text[index]
            fence = _FENCE.match(text, index, end) if char in "`~" else None
            token = fence.group() if fence else char
            if stack and stack[-1][2] == "code_text":
                if token == stack[-1][1]:
                    opened, _, reason = stack.pop()
                    result.append((opened, index + len(token), reason))
                index += len(token)
                continue
            if char == "'" and index > start and index + 1 < end and (
                    text[index - 1].isascii() and text[index - 1].isalpha()
                    and text[index + 1].isascii() and text[index + 1].isalpha()):
                index += 1  # Apostrophes inside Latin words aren't quotation marks.
                continue
            if stack and token == stack[-1][1]:
                opened, _, reason = stack.pop()
                if not stack:
                    result.append((opened, index + len(token), reason))
            elif fence:
                stack.append((index, token, "code_text"))
            elif char in _PAIRS:
                stack.append((index, _PAIRS[char], "quoted_text"))
            index += len(token)
        if stack:
            opened, _, reason = stack[0]
            result.append((opened, end, reason))  # Unclosed quote is uncertain, not an assertion.
        for quote in _MARKDOWN_QUOTE.finditer(text[start:end]):
            result.append((start + quote.start(), start + quote.end(), "markdown_quote"))
    merged = []
    for left, right, reason in sorted(result):
        if merged and left < merged[-1][1]:
            prior_left, prior_right, prior_reason = merged[-1]
            merged[-1] = (prior_left, max(prior_right, right),
                          reason if prior_reason == "quoted_text" else prior_reason)
        else:
            merged.append((left, right, reason))
    return merged


class AssertionGuards:
    """Index once, then query clauses without repeatedly scanning prior text."""

    def __init__(self, text: str, kind: str, self_speaker: str | None):
        self.text = text
        self.protected = protected_ranges(text, kind, self_speaker)
        self.protected_ends = [right for _, right, _ in self.protected]
        self.hard_ends = [match.end() for match in _HARD_BOUNDARY.finditer(text)]
        self.frames = {"reported_speech": [(m.start(), m.end()) for m in _REPORTED.finditer(text)],
                       "hypothetical": [(m.start(), m.end()) for m in _HYPOTHESIS.finditer(text)],
                       "other_subject_value": [(m.start(), m.end()) for m in _OTHER_VALUE.finditer(text)]}
        self.frame_starts = {reason: [start for start, _ in spans] for reason, spans in self.frames.items()}
        self.frame_ends = {reason: [end for _, end in spans] for reason, spans in self.frames.items()}
        self.own_views = []
        for match in _OWN_VALUE_VIEW.finditer(text):
            protected = bisect_right(self.protected_ends, match.start())
            if protected >= len(self.protected) or self.protected[protected][0] >= match.end():
                self.own_views.append((match.start(), match.end()))
        self.own_view_ends = [end for _, end in self.own_views]
        self.author_ranges = own_chat_ranges(text, self_speaker) if kind == "chat" else [(0, len(text))]
        self.author_starts = [start for start, _ in self.author_ranges]
        self.soft = [(m.start(), m.end()) for m in _SOFT_BOUNDARY.finditer(text)]
        self.soft_starts = [start for start, _ in self.soft]
        self.soft_ends = [end for _, end in self.soft]
        self._span_cache, self._reason_cache = {}, {}

    def _scope_start(self, start: int) -> int:
        author = bisect_right(self.author_starts, start) - 1
        scope_start = self.author_ranges[author][0] if author >= 0 else 0
        hard = bisect_right(self.hard_ends, start) - 1
        return max(scope_start, self.hard_ends[hard] if hard >= 0 else 0)

    def self_value_view(self, start: int, end: int) -> bool:
        """An unquoted own viewpoint can carry across commas, not sentences/chat lines."""
        view = bisect_right(self.own_view_ends, end) - 1
        return view >= 0 and self.own_views[view][0] >= self._scope_start(start)

    def clause_span(self, position: int, region_start: int, region_end: int) -> tuple[int, int]:
        before = bisect_right(self.soft_ends, position) - 1
        after = bisect_right(self.soft_starts, position)
        left = max(region_start, self.soft[before][1] if before >= 0 else region_start)
        right = min(region_end, self.soft[after][0] if after < len(self.soft) else region_end)
        key = (left, right)
        if key in self._span_cache:
            return self._span_cache[key]
        raw = self.text[left:right]
        result = left + len(raw) - len(raw.lstrip()), right - len(raw) + len(raw.rstrip())
        if len(self._span_cache) >= 256:
            self._span_cache.clear()
        self._span_cache[key] = result
        return result

    def reason(self, start: int, end: int, *, include_hedges: bool = False,
               quoted_terms: frozenset[str] = frozenset()) -> str | None:
        key = (start, end, include_hedges, quoted_terms)
        if key not in self._reason_cache:
            if len(self._reason_cache) >= 256:
                self._reason_cache.clear()
            self._reason_cache[key] = self._reason(start, end, include_hedges, quoted_terms)
        return self._reason_cache[key]

    def _reason(self, start: int, end: int, include_hedges: bool, quoted_terms: frozenset[str]) -> str | None:
        text = self.text
        index = bisect_right(self.protected_ends, start)
        while index < len(self.protected) and self.protected[index][0] < end:
            left, right, reason = self.protected[index]
            if (reason == "quoted_text" and left < start and right == start + 1
                    and text[start] in _PAIRS.values()):
                index += 1  # A prior sentence's closing mark isn't a new quotation.
                continue
            if not (reason == "quoted_text" and text[left:left + 1] != "《"
                    and start <= left and right <= end and right - left <= 16
                    and text[left + 1:right - 1] in quoted_terms):
                return reason
            index += 1
        clause = text[start:end]
        following = _FOLLOWING_SPACE.match(text, end).end()
        if (following < len(text) and text[following] in ("?", "？")) or _QUESTION.search(clause):
            return "question"
        scope_start = self._scope_start(start)
        for reason, spans in self.frames.items():
            if reason == "other_subject_value":
                # Value ownership is not the same as mood/intent ownership.
                # Describing her values may precede the author's own reaction.
                if not include_hedges:
                    continue
                index = bisect_right(self.frame_ends[reason], end) - 1
                if index < 0 or spans[index][0] < scope_start:
                    continue
                view = bisect_right(self.own_view_ends, end) - 1
                if view >= 0 and self.own_views[view][0] >= spans[index][1]:
                    continue  # Explicitly switching to "对我来说" reclaims own values.
                return reason
            index = bisect_left(self.frame_starts[reason], scope_start)
            if index < len(spans) and spans[index][1] <= end:
                return reason
        if include_hedges and _HEDGE.search(clause):
            return "hedged_value"
        return None
