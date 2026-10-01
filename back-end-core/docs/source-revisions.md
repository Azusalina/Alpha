# Source revisions, publication and explicit replay

These Python contracts are additive to schema version 1. The shared API/schema
integration is owned separately; this document describes the model implementation.
BrainCore and BrainModel expose the same signatures:

```python
correction_reopen(source_id: str, *, corrections: list[dict], immediate: bool,
                  expected_source_version: int, expected_revision: int,
                  expected_epoch: int) -> dict
review_version(source_id: str, *, agree: bool, expected_source_version: int,
               expected_revision: int, expected_epoch: int) -> dict
replay_preview(source_ids: list[str]) -> dict
replay_reopen(source_ids: list[str], *, immediate: bool,
              expected_source_versions: dict[str, int], expected_revision: int,
              expected_epoch: int) -> dict
```

`expected_revision` means **global `reset_info().input_revision`**, not the
per-source correction revision from `correction_history`. `expected_epoch` means
`reset_info().model_epoch`. All numeric guards require nonnegative integers, never
booleans. Source versions start at 0. Input get/list/page summaries always include
`source_version`. Guards are checked against one snapshot and checked again inside
BEGIN IMMEDIATE. Concurrent or stale operations fail without changing anything.
Any fitted source excluded by model-only reset is refused by correction/replay
reopening even when the caller supplies the current epoch. Explicit review_version
can deliberately re-enlist the selected source with fresh guards, preserving its
frozen fit. Legacy explicit frozen reapproval remains available for version 0.

## Reviewed corrections and renewed consent

`correction_reopen` requires an ever-fitted source. Validate the complete correction
batch before withdrawing support. Archive the old approval, contributions, terms,
fit context and corrections with their source version and model epoch; do not make
a second copy of the raw body. Withdraw this source's model and translator support,
increment its version, clear its frozen fit, and append the new corrections in one
transaction. `immediate=True` creates pending/confirm-null; False creates
disagreed/immediate-false/confirm-null. Exclamation and confirmed_by are cleared.
The original source body does not change. Existing effects keep their numbers;
withdrawal adds effects, never rewrites another source's history.

The reopen result contains existing decision fields (`source_id`, `partition`,
`status`, `immediate`, `confirm`, `exclamation`, `confirmed_by`, `reason`, `effects`,
`translator_effects`) plus `source_version`, `input_revision`, `model_epoch`,
`correction_revision`, and `corrections`. **Pending reopen results may contain
withdrawal effects**, unlike ordinary pending submission results.

`review_version` returns existing decision fields plus `source_version`,
`input_revision`, `model_epoch`. A non-idempotent approval also returns the existing
`observed_terms`, `interpretation`, and `restored_fit`. It requires immediate true
and a fresh second judgement; successful renewed approval fits the new version.
The old unversioned `review` refuses every source with version greater than 0,
including negative judgements and later reapprovals. Thus an old in-flight review
cannot approve a reopened version. Normal version-0 revoke/reapprove keeps its
frozen interpretation. Pending `correction_set` keeps its existing correction
revision guard; changing corrections also invalidates global input revision.

`correction_history` adds `version_history` (always an array, empty when no archive).
Entries contain `source_version`, `model_epoch`, `created_at`, `approval`,
`fit_context` (object or null), `contributions` (same six-field shape as replay),
`terms` (term/count object), and `corrections` (array of revision/corrections/
created_at/source_version objects). No raw source body copy is returned.

## Typed evidence annotations: deliberately narrow

Legacy parameter corrections remain `{parameter, sign, evidence, span}`, where
parameter is one of the 13 model parameters. New items have exactly:

```json
{"type": "tone", "value": "happiness", "sign": 0,
 "evidence": "开心", "span": [2, 4]}
```

`type` is event, intent, tone, or candidate; sign is integer 0 (suppress) or 1
(retain). Value, evidence and Unicode span must exactly match existing translator
output, with author ownership checked. Event targets event_word cues; intent targets
contact_intention candidates; tone targets textual_emotion candidates; candidate
targets any translator candidate. Duplicate targets are refused. Maximum total
batch size is 64. These annotations are local and never teach parameter rules.
They cannot add events, invent intent or tone labels, bypass assertion guards,
create arbitrary claims, or claim generalized NLP/retraining. Retain never turns a
raw event cue into an accepted personal memory. Suppression filters the fitted
translation and automatic memory extraction; parameter suppression also blocks
automatic memory evidence from the same clause. Typed annotations do not alter
the 13 model parameter contributions.

New fit context adds `translation` (the translator report with local suppressions)
and `memories: [{claim, evidence, span}]`. Learned rule provenance adds
`support_source_versions: {source_id: integer}` alongside support_source_ids.
Old frozen contexts are retained as stored and can lack these additive fields.

## Deterministic automatic memory publication

First approval of a fresh fit extracts up to 16 memories from translator candidates
and inserts accepted candidates in the same transaction as fitting. It calls no
LLM. Only exact self-authored spans in explicit first-person assertions pass. The
existing assertion guards exclude quotes, questions, hypotheses, hedges and
reported speech. An additional conservative clause filter excludes negation and
other-actor words. This can miss valid observations (including explicitly negative
intentions); under-extraction is intentional. Bare emotion words without explicit
first-person language and raw lexical event cues never produce accepted memories.
Claims are lexical observation labels (`textual_emotion: happiness`, for example),
not inferred traits, durable facts, diagnoses, or clinical interpretations.

New `candidate_propose` calls against an agreed source are accepted immediately
and bound to its current version. Their supplied claim remains manually authored;
exact source evidence and chat self-speaker checks remain required. Explicit text
model adapters are still optional Python calls, never part of automatic extraction.
Legacy standalone store proposals stay pending. Migration, startup, idempotent
approval and frozen reapproval never silently publish legacy pending/rejected
candidates or generate replacement memories. `candidate_review` remains available
for legacy pending candidates; superseded version acceptance is refused. Memory
list/search require agreement and matching current source version, so old accepted
memories cannot resurface after a revised source is approved. Model-only reset
preserves agreed translator/memory material under its existing contract.

## Explicit replay

Preview accepts 1–16 unique source ids. It uses a read snapshot, performs no fit or
publication, and returns `{items, input_revision, model_epoch}`. Each item has
`source_id`, `source_version`, `eligible`, `dependencies`, `diff`, `semantic_change`.
Dependencies contain `support_source_ids`, `terms` (strings), and
`dependent_source_ids`. These describe frozen learned-rule support and vocabulary;
they do not claim a generalized causal/NLP dependency graph. Dependent source fits
and effects stay frozen until separately selected for replay.

Diff is `{before, after}`. Each side contains:

- `contributions`: objects with parameter, sign, evidence, start_offset, end_offset,
  rule_id;
- `terms`: a term-to-occurrence-count object;
- `interpretation`: frozen/fresh fit context;
- `memories`: claim/evidence/span objects.

Semantic change compares contributions, terms, lexical translation and generated
memories; support metadata is separately visible in interpretation. Eligibility
requires a stored fit in the current model epoch. Preview may display an ineligible
source, but cannot authorize its replay. A fitted source's own corrections remain
the explicit local labels during replay.

`replay_reopen` requires exactly one expected version per selected source. The
entire bounded batch is validated before any mutation and revalidated under the
write lock. It archives/withdraws/reopens only those selected sources, retaining
their explicit corrections. It always requires renewed double consent, including
when semantic_change is false; no preview agreement is implied. It returns
`{items, input_revision, model_epoch}`, where items are correction_reopen results
and all carry the final batch revision. No source is automatically approved,
no dependent is automatically replayed, and no old reset input is re-enlisted.
Fresh extraction takes place on subsequent guarded approval, using then-current
support. Any intervening support change invalidates the preview/global revision.

## Privacy and compatibility

Source deletion purges new version archives as well as all prior dependent tables.
F6 input replacement purges archives, corrections, candidates, fit/context, terms,
contributions and effects, resets source_version to 0, preserves ever_fitted and
the existing reset exclusion contract, and retains no prior text-bearing records.
These are logical database purges under the existing contract, not a forensic
secure-erasure guarantee for SQLite pages or external backups. Source_ref files and
external backups are untouched. New fields are additive; selected publication
changes candidate_propose's truthful status to accepted. API integration must update
the v1 result schema/expectations rather than returning a fictitious pending status.
Privacy/access protection belongs to the shared private API gate, not this extractor.
