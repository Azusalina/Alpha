# Local self-model v1

This package is an evidence-linked, interpretable starting point—not a digital
replica, clinical instrument, or calibrated choice predictor. It keeps three
independent partitions (`rational`, `emotional`, `crazy`; the last is a user's
input-page name, **not** a diagnosis). All personal parameter values are zero
in the immutable [`baseline.json`](baseline.json); `support=0` and
`observed=false` distinguish unobserved from measured neutral. The active state
is derived from agreed sources in local SQLite. Raw input is stored at submit
time; a single whole-input boolean is applied later with `review`.

An agreed rational source updates only the rational partition. An agreed
emotional/"crazy" source updates only its own partition and never becomes
evidence that the corresponding *choice* was rationally endorsed. A disagreed
source remains in the database but does not train either the model or
translator. `revoke` removes an agreed source's contributions from the active
fit while retaining the source and effect history.

## Setup

The one external tool is [jieba](https://github.com/fxsjy/jieba), MIT licensed,
cloned at `../../ext-refs/jieba` (reviewed commit
`67fa2e36e72f69d9134b8a1037b83fbb070b9775`). It is used locally
for Chinese word segmentation. No user text is sent over the network. Clone if
this ignored reference directory is absent. From the repository root:

```bash
git clone --depth 1 https://github.com/fxsjy/jieba.git ext-refs/jieba
```

Then run from `back-end-core`:

```bash
python -m model --db data/brain.sqlite3 baseline
python -m model --db data/brain.sqlite3 submit --partition rational --kind philosophy --text '我重视公平和自由。'
python -m model --db data/brain.sqlite3 review SOURCE_ID --agree
python -m model --db data/brain.sqlite3 state --partition rational
python -m model --db data/brain.sqlite3 effects --source-id SOURCE_ID
python -m model --db data/brain.sqlite3 terms --partition rational
python -m model --db data/brain.sqlite3 revoke SOURCE_ID
python -m unittest discover -s tests -v
```

Use `--file /path/to/entry.md` or `.txt` instead of `--text` for a local file.
For `--kind chat`, use `--self-speaker NAME` and `NAME: message` lines. Source
text and SQLite data must not be committed to Git.

## What is actually learned

- Value parameters (autonomy, fairness, care, truth, security, growth,
  achievement, connection) move only on explicit first-person importance
  statements—or on `kind=philosophy` statements the user agreed to. Diary topic
  mentions alone do not count. Negative importance statements can move a value
  below zero. A source counts at most once per parameter.
- Textual emotion and reduced-contact cues from `translator` update expression
  parameters in the source's own partition. They do not diagnose a condition.
- jieba splits Chinese text. Agreed inputs add token and adjacent-phrase counts
  to a partition-local lexicon; phrases seen in at least two documents become
  segmentation hints on later inputs. This is personal vocabulary adaptation,
  **not** supervised semantic learning.
- A parameter score is `(positive evidence - negative evidence) / (support + 4)`.
  The `4` is fixed prior shrinkage, not a personal trait. Scores are not
  psychometric scales, probabilities, or comparable across people.
- `rank_options` accepts structured value impacts and may give provisional
  value-alignment order after enough rational evidence. It abstains otherwise;
  it cannot yet predict the user's most likely choice or define the objectively
  best choice. Retrospectively endorsed choice labels are a future requirement.

Each effect records old/new score, support, exact source excerpt and character
span, source ID, partition, and revision. The frontend can consume this JSON
without depending on a visual representation. MMPI report import is deferred in
[`../docs/TODO.md`](../docs/TODO.md).
The complete active/deferred parameter register is
[`../docs/parameters.md`](../docs/parameters.md).
