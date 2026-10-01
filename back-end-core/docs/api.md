# Local backend API v1

`core.brain.BrainCore` is the application entry point. `core.api` exposes it as
a persistent local process with newline-delimited UTF-8 JSON. A desktop host
starts it once, matches responses by `id`, and closes stdin to end the process.
There is no network listener. A Tauri `brain_call` host is now implemented in
`src-tauri`; React Transport is now wired. The frontend reports browser/real-Python
and Xvfb native-window smoke acceptance in `front-back-communicate.md`; native
fault/restart acceptance and release runtime packaging remain pending.
See [desktop-bridge.md](desktop-bridge.md) for invocation and host settings.

From `back-end-core`:

```bash
python -m core.api --db data/brain.sqlite3
```

The host selects the database path; requests cannot change it or read arbitrary
file paths. For a user-selected `.txt`/`.md` file, send its decoded UTF-8 content
as `text` and its display filename as `source_ref`. The existing model CLI also
supports local `--file` import. Schema version 1 is defined in
[`api.schema.json`](api.schema.json); the API validates method fields at runtime.
The root schema validates requests; `$defs.response` validates only the response
envelope. All 23 method result bodies are defined under
`$defs.results.$defs[METHOD]`, referenced as `#/$defs/results/$defs/METHOD`.
Validate a successful `result` against the method of the corresponding request;
the wire response has no method field. Validating just the envelope or the
`results` definition container does **not** validate the result body.
`$defs.translation` defines the lexical
report returned in `preview.translation`; `$defs.approvalMetadata` defines the
dual-judgement metadata shared by inputs and decisions.
`$defs.inputRecord` defines list rows; `$defs.inputPage` defines paginated results.
`$defs.interpretation` defines correction provenance and versioned value-rule
diagnostics, including older frozen contexts without the newer diagnostics.
Optional conformance checks in `tests/test_schema_contract.py` require the
`test-schema` extra; see `../README.md`. Thirteen tests cover live method bodies,
negative shapes, lifecycle/ranking/candidate variants, legacy migration and
serialized process responses. These shape checks do not prove cross-field
source/span equality, matching IDs or semantic correctness; runtime/behavior
tests enforce the applicable relationships. Backend CI is configured, not yet
verified by an online run.

For a Draft 2020-12 validator, keep the complete schema document (including
`$defs`) when selecting an entry point. In the Python test suite:

```python
envelope_validator = Draft202012Validator({**schema, "$ref": "#/$defs/response"})
body_validator = Draft202012Validator({**schema, "$ref": f"#/$defs/results/$defs/{request['method']}"})
envelope_validator.validate(response)
if response["ok"]:
    body_validator.validate(response["result"])
```

Use a method from the locally retained, validated request, not a field supplied
by an untrusted response. Confirm the response ID matches that request.
`state` has a partition-only or three-partition shape: choose `partitionState`
for a non-null requested partition, otherwise `allState`, if checking scope too.
`unevaluatedProperties` is used to close composed records; validators must
support Draft 2020-12 rather than silently using an older draft.

## Envelope

One request occupies one line. `id` is a nonempty string up to 128 characters;
it is for correlating responses, **not an idempotency key**. Retrying `submit`
creates another source. Re-review is allowed; repeating the same decision is a
no-op, returning no new effects and writing no duplicate audit event.

Fresh fitting returns `observed_terms`, `interpretation` and `restored_fit`
together. A repeat same-decision review returns the shorter decision shape,
without these fields and with empty effect arrays; their absence is not a
failure or a new unobserved fit. `review_history` migration events preserve a
status-only legacy `before`, while new review/revoke events carry full approval
snapshots. See `decisionFields` and `reviewEvent` in the schema.

```json
{"schema_version":1,"id":"entry-1","method":"submit","params":{"text":"我重视公平。","partition":"rational","kind":"diary","source_ref":"diary.md"}}
```

```json
{"schema_version":1,"id":"entry-1","ok":true,"result":{"source_id":"...","partition":"rational","status":"pending","immediate":true,"confirm":null,"exclamation":false,"confirmed_by":null,"reason":null,"effects":[],"translator_effects":[]}}
```

```json
{"schema_version":1,"id":"entry-2","ok":false,"error":{"code":"NOT_FOUND","message":"input or candidate not found"}}
```

Unknown fields/methods, duplicate JSON keys, non-finite numbers, and string
values such as `"false"` in boolean fields are rejected. Invalid JSON yields
`id=null`; a following valid request can still be processed. Stdout carries
responses only; any dependency diagnostics go to stderr.

## Methods

Optional fields are marked `?`. Defaults are shown where applicable.

| Method | `params` | Result |
| --- | --- | --- |
| `health` | `{}` | API version, available methods, `features`, manual candidate publication policy, LLM runtime status |
| `baseline` | `{}` | Immutable zero model definition |
| `submit` | `text`, `partition`, `kind?="diary"`, `self_speaker?`, `source_ref?`, `immediate?=true`, `exclamation?=false` | Source, approval metadata, effects; explicit exclamation can fit immediately |
| `input_get` | `source_id` | Original `text`, metadata, partition, kind, review status |
| `input_edit` | `source_id`, `text`, `immediate`, `kind?`, `self_speaker?` | New `inputRecord`; inactive source only, clears old source history and resets confirmation |
| `input_delete` | `source_id` | `{source_id, deleted:true}`; any state, atomically removes fit and all this source's records |
| `input_list` | `partition?`, `status?`, `limit?=20` | Array of metadata and summaries, newest first; no full original text |
| `input_page` | `partition?`, `status?`, `limit?=20`, `cursor?=null` | `{items, total, next_cursor, revision}`; bounded pages of the same summary rows |
| `preview` | `source_id` | Inactive-source translation and hypothetical effects; no fitting |
| `review` | `source_id`, `agree` (boolean) | Set second judgement; actual approval/removal effects |
| `review_history` | `source_id` | Current approval metadata and decision history since the last edit |
| `correction_set` | `source_id`, `corrections`, `expected_revision` | Append a complete pending correction set; no fitting |
| `correction_history` | `source_id` | Current correction revision/history and frozen fit context, cleared by edit/delete |
| `revoke` | `source_id` | Revocation and reversal effects |
| `state` | `partition?` | Current parameter values, support, observed flags |
| `effects` | `source_id?` | Ordered actual parameter effect history |
| `terms` | `partition`, `min_documents?=2` | Approved personal vocabulary counts |
| `rank` | `options` | Provisional alignment ranking or abstention |
| `candidate_propose` | `source_id`, `claim`, `evidence` | Pending candidate ID; requires an agreed source and exact evidence |
| `candidate_review` | `candidate_id`, `accept` (boolean) | Explicit acceptance/rejection of a pending candidate |
| `candidate_list` | `partition?`, `status?`, `limit?=20` | Candidate history, including source status |
| `memory_list` | `partition?`, `limit?=20` | Accepted memories whose sources remain agreed |
| `memory_search` | `query`, `partition?`, `limit?=20` | Literal search of active memory claims/evidence |

- Partitions: `rational`, `emotional`, `crazy`. Each input belongs to one.
- Input kinds: `diary`, `chat`, `philosophy`. `chat` requires `self_speaker`;
  the current format is one `speaker: content` line per message. Chat memory
  evidence must come from that speaker; optional model extraction receives
  only that speaker's message content.
- Input statuses: `pending`, `agreed`, `disagreed`, `revoked`.
- Candidate statuses: `pending`, `accepted`, `rejected`. An accepted candidate
  from a revoked source remains in history but is absent from active memories.
- `limit` is an integer from 1 to 100; filters apply before this limit.
- Input text is limited to 1,000,000 Unicode characters. Blank text and U+0000
  anywhere in new submit/edit text are `INVALID_ARGUMENT`; no silent stripping.
  Existing legacy text is not rewritten by migration.
- Surrogate code points in text fields are rejected as `INVALID_ARGUMENT`.
  Valid Unicode text is stored without BOM/newline normalization; `input_get`
  returns the same code-point sequence (and therefore the same UTF-8 encoding).
  File decoding/BOM removal is the client's responsibility before submission.
- `rank.options` uses the existing structured format, e.g.
  `[{"id":"A","impacts":{"value.autonomy":0.5}}, {"id":"B","impacts":{"value.autonomy":-0.2}}]`.
  Impacts are finite numbers in `[-1,1]` on value parameters only.

## Review and client state

`submit → preview → review` uses one `source_id`. A preview is hypothetical and
can become stale after another input changes the model. Render actual changes
from the review response and refresh `state`. Pending preview effects have no
revision number; committed effects carry a revision and timestamp.

Only whole-input agreement enables model/vocabulary fitting. Candidate memory
review is currently separate and explicit. A configured Python text adapter
can be injected through `BrainCore.extract_memories`; no LLM extraction method
or runtime is exposed by the JSON API.

### Dual judgements (F1-F4 implemented)

- `immediate` is the first whole-input judgement at submit. Defaults to true
  for legacy clients; new clients should always send it explicitly. `confirm`
  starts null and is set by `review(agree=...)`; do not send confirm to submit.
- Only both true are eligible for fitting. `immediate=false` saves raw text as
  `disagreed`, `reason="immediate_false"`, confirm=null, without parameter,
  vocabulary or semantic-rule learning. Either review value is invalid until
  `input_edit` can change immediate and restart confirmation.
- Explicit `exclamation=true` **sets both judgements true**, including when the
  submitted immediate was false, following the user's updated rule. Saving,
  fitting and audit commit in one transaction. Failure rolls everything back.
  It is a user-supplied boolean, never inferred from emphatic language or `!`.
  The submit response includes actual effects/translator_effects and
  `confirmed_by="exclamation"`; clients must render these without calling review
  or preview again. Ordinary confirmation uses `confirmed_by="manual"`.
- `pending`: immediate=true, confirm=null. `agreed`: both true. `disagreed`:
  immediate=false, or manual confirm=false (`reason="confirm_false"`). `revoked`
  is an explicit removal of a previously agreed source: confirm=false,
  `reason="user_revoked"`. This historical status takes precedence over disagreed.
- `review(false)` on agreed removes its active parameter/vocabulary/rule support
  and hides accepted memories; it returns reversal effects with action=revoke
  but input status=disagreed. `review(true)` may accept a previously rejected
  source or restore a revoked/previously fitted source. Restore reuses saved
  contributions, terms and fit context, not today's extraction; support is never
  counted twice. Previously accepted memories become visible again; pending
  candidates are not auto-published. `restored_fit=true` identifies restoration.
- After later manual review, `exclamation` remains the historical submit flag;
  it does not continuously force both true. The latest confirmed_by/reason and
  review history explain subsequent manual rejection or re-approval.
- All decisions return source_id, partition, status, immediate, confirm,
  exclamation, confirmed_by, reason, effects and translator_effects. Input
  get/list return real JSON booleans, not SQLite integers. Vocabulary effects
  identify crossing the two-document learning threshold in either direction.
- `review_history.history` contains revision, action (`submit`, `review`,
  `revoke`, `migrate`), before, after, effect_revisions and created_at. Even a
  decision with no parameter effect is audited. Revision is an opaque global
  integer. It is not a raw-text edit history or an authentication mechanism.
- On opening legacy v1 data, an atomic metadata migration sets immediate=true,
  maps existing status to confirm/reason, and marks prior judgements `legacy`:
  it does not invent manual consent, re-fit, change prior scores or duplicate
  effect history. Earlier fits without context retain stored contributions and
  use `legacy_context_unavailable=true`. Restart does not repeat migration.
- `health.features.two_judgements`, `exclamation_sets_both_true`,
  `repeat_review`, `preview_untrained`, `source_edit`, `source_delete` are true.
  New fields require a matching backend; schema_version remains 1 because old
  requests are still accepted. Never assume these features solely from version.

Preview now supports pending/disagreed/revoked, including immediate=false, but
never trains or authorizes a review. For previously fitted sources it projects
restoration of frozen evidence. Only pending interpretation corrections remain
editable; repeat review alone does not reset raw text or its correction history.

### Input summaries and pagination (F5 implemented)

Both list methods return `excerpt` (the first 80 Unicode code points),
`char_count` (the full original text's code-point length), `edited_at` (null until
edited, then the last edit's UTC timestamp), and the dual-judgement fields. `input_get` adds
the same summary fields to the full-text detail. No normalization, trimming,
HTML/Markdown rendering or ellipsis is applied; excerpts can include line
breaks, combining marks and legacy NUL. Excerpts are **raw user text**, not semantic
summaries or sanitized markup. Render as plain text; future access protection
must cover excerpts as well as full text. No password gate exists yet.

`input_list` still returns an array, preserving existing adapters. The current
RemoteBrainAdapter's excerpt hydration should now skip extra input_get calls;
it does not automatically gain paging. Add `input_page` consumption separately.
Use `health.methods` and `features.input_summary/input_pagination` to detect support.

```json
{"schema_version":1,"id":"page-1","method":"input_page","params":{"partition":"rational","status":"pending","limit":20}}
```

- Results are ordered by `(created_at DESC, source_id DESC)`, including ties.
  Each page has 1–100 as its requested limit, at most that many items, total
  matching canonical inputs (not just the remaining count), and next_cursor.
  Empty/end pages have next_cursor=null; an empty dataset has total=0, items=[].
  Legacy store-only sources are excluded. Filters apply before count/limit.
- Pass next_cursor unchanged with the same partition/status filters for the
  next page. Missing/null filters are equivalent; limit may change. Do not
  construct/decode cursor positions in the client or send cursor to input_list.
- The cursor is bounded to 2,048 characters, database-bound and integrity-checked;
  it contains sort/filter/revision metadata, not raw text or the signing key.
  It is not encryption, an access token, a password gate or an idempotency key.
  It survives reopening the same database without intervening input changes.
- Each call reads total, rows, summaries and revision in one SQLite snapshot.
  Revision combines the review sequence high-water mark and a source mutation
  generation (not a timestamp or personal parameter); purging history cannot
  reuse a prior revision. Supported submit, changed review, revoke, edit or delete invalidates older cursors, even
  in another partition. A mutation cannot silently mix old and new pages:
  `STALE_CURSOR` requires discarding accumulated pages and querying page 1 again.
  No-op reviews, pending correction labels and legacy-only writes do not
  change input-list metadata or invalidate its cursor. External SQL edits are outside
  the API contract; revision does not detect arbitrary manual database changes.
- Invalid, altered, wrong-database or filter-mismatched cursors return
  INVALID_ARGUMENT. Paging is read-only and cannot authorize material fitting.
  Cursor generation keys are local database metadata, not personal parameters.

Canonical input/candidate/memory methods exclude legacy `core.cli add-source`
records. Those records are preserved and remain available through the old CLI.
`memory_list`/`memory_search` return partition and source status so the client
can keep state contexts distinct. They search literal text, not embeddings.

`span=[start,end]` refers to zero-based Unicode code points in the original
input, with an exclusive end. JavaScript UTF-16 offsets differ for some
characters; use `Array.from(text).slice(start,end).join("")` for evidence checks.
`observed=false` means no supporting evidence. Parameter scores are not choice
probabilities; use `rank.status` to handle abstention explicitly.

The lexical `translation` report has `schema_version`, `kind`, `self_speaker`,
`cues`, `candidates`, `skipped`, and `limitations`. A philosophy source uses the
diary lexical pipeline, so its outer `kind` is `philosophy` but
`translation.kind` is `diary`. Cue/candidate status is an extraction label,
not the input's review status. Corrections affect `interpretation` and fitted
`effects`; they do not rewrite this raw lexical report.

New interpretation contexts carry `evidence_policy="assertion-guards-v2"`,
`withheld_values` (at most 64 base value-rule omissions, each with reason,
parameters and exact evidence/span), `withheld_count` and `withheld_truncated`.
Quotation, questions, reported/hypothetical frames and ambiguous negation are
not automatically endorsed values. V2 also withholds bounded familiar-actor
value frames with `reason="other_subject_value"`, without discarding the user's
own concern for another person or their emotion/intent reaction. Raw lexical cues remain visible. These
diagnostics are not an exhaustive account of missing effects; explicit local
or learned corrections can override the base omission. Old frozen contexts
may carry `assertion-guards-v1` or omit all four fields: do not fabricate a policy
version on restore. The schema accepts both versions, but the new reason is
only valid with v2. Existing fitted contributions and diagnostics stay frozen.
See [`evidence-policy.md`](evidence-policy.md) for examples and frontend semantics.

Zero parameter effects means no extracted parameter contribution, not
`rank.status="abstain"`. Vocabulary may still be updated on agreement. An effect
with `delta=0` can still add support, so do not infer training solely from delta.

## Pending interpretation corrections

First fetch `correction_history` (`revision=0` if no feedback exists). Then send
the whole replacement set with that `expected_revision`:

```json
{"schema_version":1,"id":"correct-1","method":"correction_set","params":{"source_id":"...","expected_revision":0,"corrections":[{"parameter":"value.fairness","sign":0,"evidence":"我重视公平吗","span":[0,6]}]}}
```

- Only `pending` inputs can be corrected. This saves feedback but changes
  neither model state nor vocabulary. Preview again, then review the whole input.
- Each item needs exactly `parameter`, `sign`, `evidence`, `span`. The parameter
  must be known and unique within the set (at most 13 items).
- `sign=1` adds support; `sign=-1` adds opposition for `value.*` only;
  `sign=0` removes that parameter's contribution from this whole input. This is
  a source-level parameter override, not a score or a phrase-only deletion.
- Evidence must exactly equal the raw source slice. In chat it must lie within
  the selected speaker's message. JSON schema cannot validate this relationship;
  runtime validates it before writing anything.
- Each call replaces the current set; `[]` resets it. History remains. Revision
  tokens are opaque, database-wide integers; do not assume increments of one.
  A stale token returns `INVALID_ARGUMENT`; refresh and resolve the conflict.
- `preview.interpretation` and an agreed `review.interpretation` contain
  `correction_revision`, `corrections`, and `learned_rules`. `correction_history`
  returns `source_id`, `status`, `revision`, `corrections`, `history` (each entry
  has `revision`, `corrections`, `created_at`), and `fit_context` (null until fit).
  An agreed fit freezes this context; reviewed inputs cannot be corrected again.
- Reuse is deliberately narrow: two distinct agreed sources with consistent
  explicit labels can teach an exact complete authored clause, including its
  following separator, in the same partition and input kind. Short excerpts
  remain local. Metadata includes `parameter`, `evidence`, `boundary`, `status`
  (`active`, `insufficient`, `conflict`), `sign`, `support_source_ids`, `support`.
  Conflicting labels abstain for that parameter; inferred results never become
  training labels. This is not general semantic understanding or neural training.
- Rejection never teaches a label. Revocation removes future teaching support,
  but does not silently reinterpret already committed dependent sources; their
  fit contexts remain recorded. Deleting or editing a teaching source likewise
  removes its future support, without rewriting other inputs' frozen fits.
  General dependent-fit replay is still pending.

## Source editing and deletion (F6 implemented)

`input_edit` requires new text and an explicit boolean immediate. It is allowed
for pending/disagreed/revoked sources only; agreed sources must first be revoked
or reviewed false. Identity, partition, source_ref and created_at stay unchanged.
An omitted kind retains the current kind. For chat, an omitted self_speaker
retains the current speaker; changing to chat requires a valid resolved speaker,
and explicit null is invalid for chat. A non-chat result clears self_speaker.

Every edit, even identical text, clears this source's previous effect/review/
correction history, vocabulary contributions, parameter contributions, frozen fit
context and all candidate memories. It does not retain the previous body. It sets
confirm=null, exclamation=false, confirmed_by=null, reviewed_at=null and edited_at
to UTC now. Immediate true produces pending; false produces disagreed with
reason=immediate_false. The result is inputRecord, not full text or a decision
with effects. No edit trains. Review history is initially empty for this version;
later reviews append normally. Preview/review now interpret the new body, never
restore the purged old fit. Fetch fresh correction_history before new corrections.

`input_delete` accepts all four statuses. Within one transaction it deactivates
an agreed source's parameter/vocabulary support, deletes its candidates and all
the source-specific records listed above, then deletes the input and source.
There is no tombstone, retained revoke event or raw-data backup created by this
operation. Other inputs' historical effect values and frozen contexts remain
unchanged. Return `{source_id, deleted:true}` only; refresh state/terms/list after
success, not an old effect log as a replacement for current state. Subsequent
source queries/deletes return NOT_FOUND, not an idempotent success. A failure
rolls back removal and deletion together. Neither method accepts file paths,
partition changes, backup targets, exclamation or a password field.

An additive metadata migration records last edit time and a non-text internal
ever-fitted flag. Editing retains that flag to prevent old training sources being
misclassified as independent held-out samples; deletion removes it with the row.
The flag is not a frontend field. Zero baseline and existing fits are untouched
by migration. Earlier text-bearing histories are not preserved after edit/delete.

**Privacy boundary:** hard deletion means removing this source's records from
the current application's database, not forensic secure erasure or deleting all
copies. It does not delete original txt/md files, manual backups, system snapshots,
frontend caches/reports or evidence already present in other inputs' frozen
contexts. It is not complete downstream unlearning. No password gate or encryption
exists; the client must explain irreversibility and obtain deletion confirmation.
F13 and the error code LOCKED are deferred, not implemented by F6.

## Remaining frontend extensions (not implemented)

### Model-only reset metadata

The local administrative reset preserves translator learning while starting a
new zero-state model epoch. API methods remain 23 and schema_version remains 1;
there is no JSON reset method. See [model-reset.md](model-reset.md) for CLI
confirmation, optimistic checks, stop-client requirement and retained history.
`health.model_epoch` identifies the current model. Input records add
`model_active` and `model_epoch`; formal effects add their originating
`model_epoch`. These are optional schema extensions for older v1 compatibility.

After reset, `status=agreed` can coexist with `model_active=false`: approval
still supports translator vocabulary/corrections and memories, but no longer
contributes to personalized parameters. Explicit `review(...,agree=true)` may
re-enlist that source's frozen fit; same-epoch repetition remains a no-op.
Never auto-review on reconnect. `preview` still excludes agreed inputs; no
post-reset preview extension is introduced. Read current `state`, not old effects.
Clear stale caches and pending operations and reload health/state/page 1 after
administrative reset. Frontend support of these distinctions remains pending.

The frontend may enable its existing proposedMethods adapter option after
health advertises input_edit/input_delete and source_edit/source_delete=true.
Use the final F6 contract above, not the obsolete non-agreed-only delete proposal.
Clear stale source detail/preview/effects/correction caches and reload state and
page 1 after either mutation; invalidate pending old-source operations too.
All 23 results are typed; schema_version stays 1. Frontend acceptance of these new
methods, original-text access protection and future choice-feedback remain pending.

## Errors and host lifecycle

| Code | Meaning |
| --- | --- |
| `INVALID_REQUEST` | Invalid JSON or envelope, request too large, invalid ID |
| `UNSUPPORTED_VERSION` | Unsupported schema version |
| `METHOD_NOT_FOUND` | Method outside the allowlist |
| `INVALID_ARGUMENT` | Invalid fields/values, wrong review state, or invalid evidence |
| `STALE_CURSOR` | Input metadata changed between pages; discard pages and restart input_page without cursor |
| `NOT_FOUND` | Canonical input/candidate missing |
| `MODEL_UNAVAILABLE` | Model dependency or runtime operation unavailable |
| `STORAGE_ERROR` | Local storage operation failed |
| `INTERNAL_ERROR` | Unexpected backend failure |

Startup failure exits nonzero and reports its error type to stderr. An ordinary
request error returns one JSON response and keeps the process alive. The host
must handle EOF, process exit, timeouts, and stderr independently. Do not retry
mutations automatically after an uncertain process failure: first inspect the
source/candidate status. Restarting the process reloads committed SQLite state.
Data editing/deletion, authentication, encryption, and semantic generalization
beyond exact-clause feedback remain pending; this protocol does not implement them.
