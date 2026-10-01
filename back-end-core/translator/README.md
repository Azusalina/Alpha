# Translator v1 (local preview)

The rule-first preview does **not** call an LLM, contact a service, store
source text, diagnose a mental condition, or infer a stable personality trait.
The newer `model/` package consumes its evidence-linked candidates, while the
older `core.extraction` candidate-memory path and frontend remain separate.
Cues are observable words; candidates are reviewable interpretations. All
`span` pairs are zero-based Unicode character
offsets into the *original* input (end-exclusive), and `evidence` is exact text.

Run from `back-end-core`:

```bash
python -m translator --kind diary --text '阿明又临时取消。我说没事，但其实很失望；下次我可能不会主动约他了。'
python -m translator --kind diary --file /path/to/diary.md
python -m translator --kind chat --self-speaker 我 --file /path/to/chat.txt
python -m translator --kind diary --file /path/to/entry1.md --file /path/to/entry2.md
python -m unittest discover -s translator -p 'test_*.py' -v
```

Chat input must have one `speaker: content` or `speaker：content` message per
line. Only exact matches to `--self-speaker` are analyzed. Unlabeled lines are
listed as skipped; other speakers' lines are not interpreted as the user's
feelings. This v1 does not parse timestamps or multiline exports. Diary text
is treated as written by the user, but quoted/third-person language is only
handled by conservative heuristics; review every candidate.

Rules currently recognize a *small example vocabulary*: cancellation,
repetition words, contrast, hedges, four emotion words, and explicit
first-person reduced-contact intentions. `又` is a claim of repetition, not
proof of previous events. A negated emotion word is recorded as a cue but
cannot become an emotion candidate. `没事` is not a positive emotion marker.
The multi-file summary counts occurrences in separate inputs; it does not
calculate direction, stability, clinical scores, or animation parameters.

`discourse.py` now guards questions, quotation/code/Markdown quotation and
reported/hypothetical frames before producing emotion/intent candidates.
Lexical cues still show those words. Model value extraction also withholds
hedged values and ambiguous negation/comparisons, with bounded diagnostics in
`interpretation`; this is not a general parser. Explicit corrections can
override base value guards. Existing fits retain their frozen evidence.
Assertion-guards-v2 also distinguishes bounded familiar-actor value statements
from the user's own values and explicit self viewpoints; it does not suppress
the user's own feelings merely because they respond to someone else's values.
Arbitrary names and complex mixed ownership still require review.
See [`../docs/evidence-policy.md`](../docs/evidence-policy.md).

`learning.py` uses the locally cloned [jieba](https://github.com/fxsjy/jieba)
source at `../../ext-refs/jieba` for partition-local vocabulary adaptation in
`model/`. Approved inputs add token/phrase counts; recurrent phrases become
future segmentation hints. A single whole-input boolean cannot train semantic
extraction rules without more targeted correction feedback.

The model JSON API now accepts targeted pending corrections, preserves their
history, and reuses consistent full-clause labels from at least two agreed
sources in the same partition/kind and following-separator context. Short
excerpts only override the current source. This is exact feedback memory, not
general semantic learning. Standalone `translate()` still returns raw lexical
observations; corrections are visible in model `interpretation` and `effects`.
See [`../docs/api.md`](../docs/api.md) for the contract. Broader generalization
and a local language-model adapter remain candidates to evaluate with corrected
examples, not prerequisites.

Read-only extraction benchmarking is now available as
`python -m translator.evaluation --cases /path/to/labelled-corpus.json`.
Human `label_scope` prevents unchecked parameters being treated as negative labels;
source-group/split checks prevent obvious duplicate leakage. Reports separate
parameter/sign metrics from strict evidence-window matches; `--details` opts
into opaque case IDs and error kinds/positions, never source text. No database,
personal correction rules, vocabulary fitting or training is used. See
[`../docs/translator-evaluation.md`](../docs/translator-evaluation.md).
