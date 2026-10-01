"""Local personal vocabulary learner backed by the cloned jieba tokenizer.

Learning here means updating token/phrase counts and reusing recurrent phrases
as segmentation hints. It does not learn semantic labels from a single boolean.
"""

from __future__ import annotations

import importlib
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

JIEBA_ROOT = Path(__file__).resolve().parents[2] / "ext-refs" / "jieba"
_TERM = re.compile(r"(?:[\u3400-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_-]{2,31})\Z")
_CHINESE = re.compile(r"[\u3400-\u9fff]{2,8}\Z")
_CHAT_LINE = re.compile(r"^\s*([^:：\s]{1,32})\s*[:：]\s*(.*)$")


def _jieba():
    if (JIEBA_ROOT / "jieba" / "__init__.py").is_file():
        root = str(JIEBA_ROOT)
        sys.path.insert(0, root)
        try:
            return importlib.import_module("jieba")
        finally:
            sys.path.remove(root)
    try:
        # For an installed wheel, jieba may be installed from that same clone.
        return importlib.import_module("jieba")
    except ImportError as error:
        raise RuntimeError(
            "jieba missing; clone https://github.com/fxsjy/jieba to ext-refs/jieba "
            "or install that clone into the Python environment"
        ) from error


@lru_cache(maxsize=16)
def _tokenizer(personal_phrases: tuple[str, ...]):
    tokenizer = _jieba().Tokenizer()
    for phrase in personal_phrases:
        if _CHINESE.fullmatch(phrase):
            tokenizer.add_word(phrase)
    tokenizer.initialize()
    return tokenizer


def learnable_terms(text: str, *, personal_phrases: tuple[str, ...] = ()) -> dict[str, int]:
    """Return per-source counts for words and adjacent Chinese word-pairs."""
    tokens = [(word, start, end) for word, start, end in
              _tokenizer(tuple(sorted(set(personal_phrases)))).tokenize(text, HMM=False)
              if _TERM.fullmatch(word)]
    counts: Counter[str] = Counter(word.lower() if word.isascii() else word
                                   for word, _, _ in tokens)
    for (left, _start, middle), (right, next_start, _end) in zip(tokens, tokens[1:]):
        phrase = left + right
        if middle == next_start and _CHINESE.fullmatch(phrase):
            counts[phrase] += 1
    return dict(counts)


def own_chat_text(text: str, self_speaker: str) -> str:
    """Exclude other speakers from personal vocabulary learning."""
    return "\n".join(text[start:end] for start, end in own_chat_ranges(text, self_speaker))


def own_chat_ranges(text: str, self_speaker: str) -> list[tuple[int, int]]:
    """Original character ranges for the selected speaker's message bodies."""
    result, offset = [], 0
    for line in text.splitlines(keepends=True):
        match = _CHAT_LINE.match(line.rstrip("\r\n"))
        if match is not None and match.group(1) == self_speaker:
            result.append((offset + match.start(2), offset + match.end(2)))
        offset += len(line)
    return result
