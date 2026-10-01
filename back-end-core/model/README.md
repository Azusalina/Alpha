# Local self-model v1

This package is an evidence-linked, interpretable starting point—not a digital
replica, clinical instrument, or calibrated choice predictor. It keeps three
independent partitions (`rational`, `emotional`, `crazy`; the last is a user's
input-page name, **not** a diagnosis). All personal parameter values are zero
in the immutable [`baseline.json`](baseline.json); `support=0` and
`observed=false` distinguish unobserved from measured neutral. The active state
is derived from agreed sources in local SQLite. Raw input is stored at submit
time; two whole-input judgements (`immediate`, `confirm`) gate fitting. Both must
be true. An explicit `exclamation` at submit sets both true and fits atomically;
otherwise `review` sets confirm later. See [`../docs/api.md`](../docs/api.md).

An agreed rational source updates only the rational partition. An agreed
emotional/"crazy" source updates only its own partition and never becomes
evidence that the corresponding *choice* was rationally endorsed. A disagreed
source remains in the database but does not train either the model or
translator. `revoke` removes an agreed source's contributions from the active
fit while retaining the source and effect history.
Manual re-review can reject an agreed source or restore an inactive one using
its frozen fit, without duplicate support. Decision history is retained.

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
python -m model --db data/brain.sqlite3 preview SOURCE_ID
python -m model --db data/brain.sqlite3 review SOURCE_ID --agree
python -m model --db data/brain.sqlite3 state --partition rational
python -m model --db data/brain.sqlite3 effects --source-id SOURCE_ID
python -m model --db data/brain.sqlite3 terms --partition rational
python -m model --db data/brain.sqlite3 revoke SOURCE_ID
python -m model --db data/brain.sqlite3 review-history SOURCE_ID
python -m unittest discover -s tests -v
```

Use `--file /path/to/entry.md` or `.txt` instead of `--text` for a local file.
For `--kind chat`, use `--self-speaker NAME` and `NAME: message` lines. Source
text and SQLite data must not be committed to Git.
Use `--no-immediate` to record a first false judgement, or `--exclamation` to
explicitly set both true and fit at submission. The flag is not inferred from text.

`preview` is read-only after `submit`: it returns translator observations and
hypothetical parameter/lexicon effects with source spans, but no effects are
logged and no state is fitted by preview. Without exclamation, fitting waits for
`review --agree`. Inactive disagreed/revoked sources can also be previewed.
A preview can become stale
if another source is approved or revoked before review; the review result is
authoritative. The JSON API now provides `correction_set` and
`correction_history` for pending interpretation feedback; see
[`../docs/api.md`](../docs/api.md). Corrections preserve raw text and require
whole-input agreement before fitting. Already reviewed inputs remain frozen.

## What is actually learned

- Value parameters (autonomy, fairness, care, truth, security, growth,
  achievement, connection) move only on explicit first-person importance
  statements—or on `kind=philosophy` statements the user agreed to. Diary topic
  mentions alone do not count. Negative importance statements can move a value
  below zero. A source counts at most once per parameter.
- New base value extraction withholds questions, quotation, hypothetical and
  reported frames, hedges and ambiguous negation/comparisons. Bounded reason/
  evidence diagnostics accompany the interpretation. Explicit corrections
  may override base guards; old fits are not recomputed. See
  [`../docs/evidence-policy.md`](../docs/evidence-policy.md).
- Textual emotion and reduced-contact cues from `translator` update expression
  parameters in the source's own partition. They do not diagnose a condition.
- jieba splits Chinese text. Agreed inputs add token and adjacent-phrase counts
  to a partition-local lexicon; phrases seen in at least two documents become
  segmentation hints on later inputs. This is personal vocabulary adaptation,
  **not** supervised semantic learning.
- Explicit pending corrections can override one parameter per source. Two
  agreed sources with consistent full-clause labels can teach exact-clause
  reuse in the same partition/kind and following-separator context. Conflicting
  labels abstain; short excerpts remain local, and inferred labels never teach.
  This narrow feedback memory is separate from jieba vocabulary adaptation.
  Revocation removes future support, not already committed dependent fits.
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

F6 source governance is available through the application API: edit inactive
sources without retaining their old text-bearing history, or delete any source
and atomically remove its active contribution and source-specific history.
Other inputs' old effects/frozen contexts stay untouched; external files and
backups are not deleted. There is no password gate or secure-erasure claim.
Editing resets confirmation and clears old terms/labels/frozen evidence before
any fresh fit. A non-text internal ever-fitted flag survives editing for held-out
source-overlap checks; it is deleted with the source. See
[`../docs/api.md`](../docs/api.md#source-editing-and-deletion-f6-implemented).

Offline held-out evaluation uses the same pure ranking function as the live
model, reads a consistent SQLite snapshot without writing, separates actual
and retrospectively endorsed choices, and reports coverage plus static
leave-one-value-parameter-out comparisons. See
[`../docs/evaluation.md`](../docs/evaluation.md); the supplied example is synthetic.
