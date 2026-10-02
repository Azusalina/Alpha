# Local self-model v1

This package is an evidence-linked, interpretable starting point—not a digital
replica, clinical instrument, or calibrated choice predictor. It keeps three
independent partitions (`rational`, `emotional`, `crazy`; the last is a user's
input-page name, **not** a diagnosis). All personal parameter values are zero
in the immutable [`baseline.json`](baseline.json); `support=0` and
`observed=false` distinguish unobserved from measured neutral. The active state
is derived from current-model-epoch agreed sources in local SQLite. Raw input is stored at submit
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

Fresh double approval publishes authored candidates for the current source/version;
legacy pending/rejected candidates remain untouched. API: schema_version=1,
contract_revision=2, 30 methods. Guarded typed correction/version review/selected
replay is implemented, not general semantic relabelling ML or a causal graph.
See [frontend handoff](../docs/frontend-contract-handoff.md).

Model-only reset is available through a deliberately confirmed local CLI:
all three parameter partitions return to unobserved zero while translator
vocabulary/correction learning, approvals and history survive. Old sources
cannot automatically rejoin the new model; explicit re-review is required.
This is not a factory reset or a hidden JSON API. See
[`../docs/model-reset.md`](../docs/model-reset.md) for exact scope and commands.

## Setup

Terminal CLI/API processes now print text-free live model status to stderr:
receipt, storage address, dual judgement, committed fit and parameter changes.
Tauri forwards validated records to its launching terminal. Use `--quiet` or
`ALPHA_BRAIN_TRACE=0` to disable; embedded Python defaults remain quiet. See
[`../docs/terminal-tracing.md`](../docs/terminal-tracing.md).

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
whole-input agreement before fitting. Ordinary re-review preserves frozen fits.
The implemented separate reviewed-source typed revision path can
withdraw the current contribution and require renewed `immediate`/`confirm`
consent before fitting the revised interpretation. That path and selected replay
enforce source-version/global revision/epoch guards.
Preserve historical effects and model-reset exclusions, and do not confuse this
semantic revision with F6 text replacement.

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
without depending on a visual representation. Current scope exclusions and
pending work are recorded in [`../docs/TODO.md`](../docs/TODO.md).
The complete active/deferred parameter register is
[`../docs/parameters.md`](../docs/parameters.md).

F6 source governance is available through the application API: edit inactive
sources without retaining their old text-bearing history, or delete any source
and atomically remove its active contribution and source-specific history.
Other inputs' old effects/frozen contexts stay untouched; external files and
backups are not deleted. F13 application access control and encrypted backups
are implemented for API/CLI/evaluation; frontend unlock UI remains pending;
whole-database encryption is outside this round and SQLite remains plaintext.
The gate must cover excerpts, evidence, histories and writes as well as raw text;
it does not prevent direct file access by the same OS user. Recovery must validate
into an explicit fresh target. F6 does not claim secure erasure.
Editing resets confirmation and clears old terms/labels/frozen evidence before
any fresh fit. A non-text internal ever-fitted flag survives editing for held-out
source-overlap checks; it is deleted with the source. See
[`../docs/api.md`](../docs/api.md#source-editing-and-deletion-f6-implemented).
Latest frontend ledger reports capability-based F6 activation and model activity/
epoch handling verified through browser real-Python tests. Native administrative
model-reset/reconnect and physical input/GPU acceptance remain pending.
Linux portable release/runtime and Xvfb DOM F6/paging/persistence passed;
main verified native DOM EOF/invalid-response/timeout faults, including explicit
reconnect, exactly-one-source read recovery and no automatic write retry.
no live reset endpoint/UI exists.

Offline held-out evaluation uses the same pure ranking function as the live
model, reads a consistent SQLite snapshot without writing, separates actual
and retrospectively endorsed choices, and reports coverage plus static
leave-one-value-parameter-out comparisons. See
[`../docs/evaluation.md`](../docs/evaluation.md); the supplied example is synthetic.
No real private held-out material is available this round. Requested work is local
collection templates/readiness tools, delivered and verified, with independent
labels and leakage checks. Real coverage/predictive validity remains unverified;
offline tools do not enable the deferred F14 frontend feedback contract.
