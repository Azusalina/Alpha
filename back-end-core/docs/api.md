# Local API v1, contract revision 2

`python -m core.api --db /absolute/synthetic.sqlite3` from `back-end-core` serves
newline-delimited UTF-8 JSON on stdin/stdout. No network listener. The host selects
the database path. stderr carries diagnostics; `--quiet` disables model traces.
Requests are exactly `{schema_version:1,id,method,params}`; ID is a 1–128 character
string. Success: `{schema_version:1,id,ok:true,result}`. Failure:
`{schema_version:1,id:string|null,ok:false,error:{code,message}}`.
ID is correlation, not idempotency. Do not retry uncertain writes automatically.

## All 30 typed methods

[api.schema.json](api.schema.json) is Draft 2020-12. Root validates requests;
`#/$defs/response` validates envelopes only. Validate successful bodies using
`#/$defs/results/$defs/METHOD`, with METHOD from the retained request, and check ID.
Keep the entire schema/$defs when selecting a ref. Records remain closed using
additionalProperties:false or unevaluatedProperties:false; maps have typed values.
Runtime additionally enforces evidence/span equality, consent/version guards,
UTF-8 byte limits and unique IDs. Shape checks alone do not establish semantics.

Optional params use `?`. Partitions: rational/emotional/crazy. Kinds:
diary/chat/philosophy. Default limit=20, integer 1–100. Chat requires self_speaker.
Nullable optional filters equal omitted filters.

| Method | Params | Result fields/schema type |
| --- | --- | --- |
| health | `{}` | schema_version=1, contract_revision=2, candidate_publication="automatic_double_approval", llm_runtime_configured=false, methods, features, access; model_epoch when unlocked only |
| baseline | `{}` | schema_version=1, partitions, parameters (13 immutable zeros) |
| access_status | `{}` | configured:boolean, locked:boolean |
| unlock | password | configured:boolean, locked:boolean |
| lock | `{}` | configured:boolean, locked:boolean |
| submit | text, partition, kind?="diary", self_speaker?, source_ref?, immediate?=true, exclamation?=false | decisionFields; actual fit fields on exclamation |
| input_get | source_id | inputRecord plus text |
| input_edit | source_id, text, immediate, kind?, self_speaker? | inputRecord, confirmation reset |
| input_delete | source_id | source_id, deleted=true |
| input_list | partition?, status?, limit? | inputRecord[] |
| input_page | partition?, status?, limit?, cursor? | items:inputRecord[], total, next_cursor:string|null, revision:integer |
| preview | source_id | source_id, partition, kind, approvalMetadata, hypothetical=true, effects:previewEffect[], translator_effects, observed_terms, translation, interpretation |
| review | source_id, agree:boolean | decisionFields; source_version must be 0 |
| review_history | source_id | source_id, approvalMetadata, history:reviewEvent[] |
| correction_set | source_id, corrections, expected_revision | source_id, revision, status="pending", corrections |
| correction_history | source_id | source_id, status, revision, corrections, history:correctionRecord[], fit_context:interpretation|null, version_history:versionArchive[] |
| correction_reopen | source_id, corrections, immediate, expected_source_version, expected_revision, expected_epoch | reopenDecision |
| review_version | source_id, agree, expected_source_version, expected_revision, expected_epoch | decisionFields plus source_version, input_revision, model_epoch |
| replay_preview | source_ids | items:replayItem[], input_revision, model_epoch |
| replay_reopen | source_ids, immediate, expected_source_versions, expected_revision, expected_epoch | items:reopenDecision[], input_revision, model_epoch |
| revoke | source_id | decisionFields, status="revoked" |
| state | partition? | partitionState or allState |
| effects | source_id? | committedEffect[] ordered by revision |
| terms | partition, min_documents?=2 | {term,documents,occurrences}[] |
| rank | options | abstain: {status,reason,ranked:[]}; provisional: {status,basis,not_a_probability,used_parameters,ranked:[{id,alignment_score}]} |
| candidate_propose | source_id, claim, evidence | candidate_id, source_id, status="accepted" |
| candidate_review | candidate_id, accept:boolean | candidate record: id, source_id, claim, evidence, status, created_at, resolved_at, source_version |
| candidate_list | partition?, status?, limit? | candidateRow[] |
| memory_list | partition?, limit? | activeMemory[] |
| memory_search | query, partition?, limit? | activeMemory[]; literal claim/evidence search |

approvalMetadata: status, immediate:boolean, confirm:boolean|null,
exclamation:boolean, confirmed_by:manual/exclamation/legacy/null,
reason:immediate_false/confirm_false/user_revoked/null. Pending=true/null;
agreed=true/true; disagreed=first or second false; revoked=explicit withdrawal.
decisionFields adds source_id, partition, effects, translator_effects. Actual
approval adds observed_terms:integer, interpretation, restored_fit:boolean together.
Idempotent review returns the shorter decision with empty effects and no new audit.

inputRecord: source_id, partition, kind, self_speaker, approvalMetadata, reviewed_at,
source_ref, created_at, excerpt, char_count, edited_at, model_active, model_epoch,
source_version. The last three are additive v1 schema fields emitted by this backend.
Excerpt is first 80 Unicode code points, raw plain text. Input detail adds unchanged
text. New text is nonblank, max 1,000,000 code points, no NUL/surrogates. Valid Unicode,
BOM/newlines are not normalized. Nullable fields are specified in the schema.

previewEffect: source_id, partition, action="preview", parameter, before, after,
delta, support_before, support_after, evidence, rule_id, span. committedEffect: parameter, before, after, delta,
support_before, support_after, evidence, rule_id, span, source_id, partition,
action:approve/revoke, revision, created_at, model_epoch and source_version metadata.
translatorEffect: term, documents_before, documents_after, source_id.
Parameter state is {value,support,observed}; no evidence means observed=false.
Zero delta can still add support. Historical effects keep numbers, not current state.
Rank options are 2–100 unique {id,impacts} with finite [-1,1] value.* impacts.
Scores are not probabilities; status explicitly identifies abstention.

candidateRow adds partition, source_status, source_ref to the candidate record above.
Active memories require accepted status, agreed source, matching source version.
reviewEvent: revision, action, before, after, effect_revisions, created_at. Legacy
migration before can be status-only; reopen approval snapshots add source_version
and reopened. correctionRecord: revision, corrections, created_at; archive entries
add source_version. Full nested field types and negative-shape checks are in schema.

## Access and publication

Only health/baseline/access_status/unlock/lock are public. Locked health is config-only,
omits model_epoch and never reads/constructs/migrates SQLite. Unlock itself returns
only config status and does not construct a brain. Authenticated health uses the
gated brain and returns current model_epoch for protected and unprotected sessions.
Missing/empty/invalid protected DB fails MODEL_UNAVAILABLE, never creates replacement.
Every valid-envelope unlock attempt revokes session/cache BEFORE parameter validation,
including empty/wrong-type password or unknown fields. Config changes/removal and
failed authentication revoke access. Private reads/writes recheck authorization.
Denial is generic LOCKED / "access is locked". Passwords are 1–1024 UTF-8 bytes,
without NUL/surrogates, no trimming; never log them or whole requests.
Clients clear private caches and pending operations on lock/reconnect; no auto-unlock.
The gate is application-level; SQLite is plaintext. Backup/restore are offline-only;
see [local-security.md](local-security.md). No JSON setup/backup/restore method.

Immediate defaults true, confirm starts null. Immediate false saves without fitting;
review requires edit to restart immediate. Explicit exclamation=true sets BOTH true
and saves/fits/audits atomically, even if immediate=false; never infer from punctuation.
Manual review can later reject. Fresh double approval automatically publishes up to
16 conservative self-authored exact lexical memories in the fit transaction, no LLM.
New candidate_propose on an agreed source is accepted and current-version-bound.
Migration/startup/idempotent/frozen reapproval never publishes legacy pending/rejected
candidates; explicit candidate_review handles legacy pending candidates and refuses
superseded acceptance. Frozen reapproval restores old interpretation/contributions.
Python-only optional text adapters are not JSON API methods.

## Revision tokens and source lifecycle

All guards are nonnegative integers, not booleans. Source versions start at 0.

| Operation | expected_revision token |
| --- | --- |
| correction_set | Latest correction_history.revision for THIS source, 0 before feedback |
| correction_reopen/review_version/replay_reopen | GLOBAL input_page.revision, replay_preview.input_revision or latest version-result input_revision |

input_page.revision equals reset_info().input_revision even with filters/limit=1.
Get source_version from input_get/page, expected_epoch from unlocked health.model_epoch,
NOT historical row epochs. Health/page are separate snapshots; stale guards fail
atomically. Refresh and resolve consent/conflicts, never automatically retry.
Replay preview gives snapshot revision/epoch and selected versions together.

correction_set replaces the full pending set; [] clears it. Parameter items are
exactly {parameter,sign,evidence,span}; sign -1/0/1, negative for value.* only,
unique known parameter. Typed items are exactly {type,value,sign,evidence,span};
event/intent/tone/candidate, sign 0 suppress/1 retain, exact existing translator
target and authored evidence. Mixed max 64, duplicate targets rejected. Unicode
spans are zero-based/end-exclusive; JS uses Array.from(text).slice(start,end).join('').
Typed labels cannot invent claims or teach general semantics, and do not change
the 13 parameter contributions. Suppression filters fitted interpretation.translation
and memories; preview.translation reflects active corrections. Original source text
and evidence spans are preserved; preview is not the raw translator output.
Context contains correction_revision,
corrections, learned_rules and optional evidence_policy/withheld diagnostics,
translation/memories. Old frozen contexts may omit additive fields. Learned support
has support_source_versions alongside support_source_ids. See [evidence-policy.md](evidence-policy.md).

correction_reopen requires ever-fitted material: archive prior version, withdraw
model/translator support, increment version, clear fit and append corrections in one
transaction. Original body unchanged. Immediate true gives pending, false disagreed;
confirm=null, exclamation=false, confirmed_by=null. Unversioned review refuses ALL
source_version>0, including negative judgements. Guarded review_version grants renewed
second consent. reopenDecision adds source_version, input_revision, model_epoch,
correction_revision, corrections to decisionFields; pending CAN have withdrawal effects.

versionArchive: source_version, model_epoch, created_at, approval, fit_context,
contributions:{parameter,sign,evidence,start_offset,end_offset,rule_id}[], terms map,
corrections. No raw-body duplicate. Replay accepts 1–16 unique IDs. replayItem:
source_id, source_version, eligible, dependencies:{support_source_ids,terms,
dependent_source_ids}, diff:{before,after}, semantic_change. Each diff side contains
contributions, terms, interpretation, memories. Dependencies are lexical support,
not a causal graph. Preview is read-only, including ineligible reset-excluded fits.
Reopen needs selected frozen fits in current epoch; full batch validates/commits
atomically, all item tokens equal final outer tokens. Dependents stay frozen until
separately selected. Fresh review fits revised version; repeat with fresh guards is
idempotent. Old effects are never rewritten.

## Pagination, edit/delete and reset

Page order: created_at DESC, source_id DESC. Pass cursor unchanged with same filters;
limit may change. Total/rows/revision share one snapshot. Bounded integrity-checked
cursor is not authorization/idempotency. Submit/changed review/revoke/edit/delete,
correction/reopen/reset invalidate old cursors globally; no-op reviews do not.
STALE_CURSOR means discard accumulated pages/reload first page. External SQL is outside
contract. Canonical methods exclude legacy store-only sources.

Edit permits pending/disagreed/revoked only; revoke agreed first. It preserves
identity/partition/ref/creation, replaces body, purges old fit/history/candidates/
archives, resets source_version to 0 and resets confirmation. Semantic reopen guards
do not protect queued unversioned reviews across legacy F6 edits; clients must clear
in-flight source operations. Future content-revision guards require a separate
compatible frontend contract. Delete accepts all states
and atomically removes source/support; response carries no effects. Refresh state,
terms/page afterwards. Edit preserves internal ever-fitted held-out exclusion;
delete removes it. Logical purge is not forensic erasure/downstream unlearning and
does not delete original files, external backups or another input's frozen evidence.

Reset is administrative CLI/Python only; no JSON reset method. It advances epoch,
zeroes model partitions and preserves translator/memories/frozen fits. Agreed can be
model_active=false. Reopen/replay cannot re-enlist reset-excluded material. Deliberate
review_version with fresh tokens can restore selected frozen fits; legacy review only
for version 0. Never auto-review or animate history on reconnect. See
[model-reset.md](model-reset.md) and [frontend-contract-handoff.md](frontend-contract-handoff.md).

## Errors and remaining acceptance

Codes: INVALID_REQUEST, UNSUPPORTED_VERSION, METHOD_NOT_FOUND, INVALID_ARGUMENT,
STALE_CURSOR, NOT_FOUND, LOCKED, MODEL_UNAVAILABLE, STORAGE_ERROR, INTERNAL_ERROR.
Sensitive unknown methods are gate-checked before diagnostics. Ordinary errors keep
process alive; startup exits nonzero with type-only stderr. Duplicate JSON keys,
nonfinite numbers, malformed envelopes and unknown fields are refused; oversized
lines are drained. Stdout carries only JSON responses.

Offline evaluation/readiness uses authorized read-only snapshots and independently
labelled strict held-out manifests, not feedback/training API. F14 and real validity
evidence remain pending. Frontend unlock/version/replay UI and native acceptance
belong to their owners; API tests do not establish those results.

Full synthetic tests require `python -m pip install '.[test-schema,security]'` from
back-end-core, including pinned PyNaCl. Do not rely on system crypto dependencies.
The backend workflow installs both extras; pinned Actions/tokenizer refs remain.
Online CI has not been run by this integration worker.
