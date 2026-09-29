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

`learning.py` uses the locally cloned [jieba](https://github.com/fxsjy/jieba)
source at `../../ext-refs/jieba` for partition-local vocabulary adaptation in
`model/`. Approved inputs add token/phrase counts; recurrent phrases become
future segmentation hints. A single whole-input boolean cannot train semantic
extraction rules without more targeted correction feedback.

Future interface boundary: targeted corrections can train semantic extraction;
validated state changes can later feed visual effects. A language model can
replace individual rules for ambiguous sentences only if measured examples
show it is needed.
