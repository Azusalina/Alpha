# Local API v1 — revision 3 working contract (final acceptance pending)

> 2026-10-04: source declares schema_version=1 / contract_revision=3 / 34 methods.
> Oct 2 revision 2 / 30 methods is the accepted historical baseline. New hybrid
> methods below describe current source, not completed full-suite/frontend/native
> acceptance. Main's final verification is pending; do not enable by health alone.
> New-table access/backup compatibility was reproduced and repaired in an owner
> patch; owner tests and main review are intermediate evidence, not full acceptance.

Historical main proof is 396 full-discovery tests (134.672s), then 51 semantic
tests (1.142s) covering the two added tests in a 398-test discovery; all had 0 skips.
Independent backup verification passed 12 (11.220s), 0 skips. This is not a single
398-test run or acceptance of later preference/evaluator edits. See
[current queue and proof](TODO.md#current-implementation-continuation--awaiting-mains-new-proof).

`python -m core.api --db /absolute/synthetic.sqlite3` from `back-end-core` serves
newline-delimited UTF-8 JSON on stdin/stdout. No network listener. The host selects
the database path. stderr carries diagnostics; `--quiet` disables model traces.
Requests are exactly `{schema_version:1,id,method,params}`; ID is a 1–128 character
string. Success: `{schema_version:1,id,ok:true,result}`. Failure:
`{schema_version:1,id:string|null,ok:false,error:{code,message}}`.
ID is correlation, not idempotency. Do not retry uncertain writes automatically.

## 34 declared methods — final conformance pending

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
| health | `{}` | schema_version=1, contract_revision=3, candidate_publication="automatic_double_approval", llm_runtime_configured=false, methods, features, access; model_epoch when unlocked only |
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
| memory_search_semantic | query, partition?, limit?=20, min_score?=0.0 | {mode,score_kind,items:[{memory,score,encoded_text_truncated}],pool_count,pool_truncated}; working extension |
| choice_feedback_set | source_id, event_id, domain, options, actual_choice_id:string|null, endorsed_choice_id:string|null, endorsement_partition:string|null, training_consent:boolean, expected_source_version, expected_revision, expected_epoch, reason?:string|null | feedback record plus input_revision; working extension |
| choice_feedback_get | source_id | {source_id,records:feedbackRecord[],input_revision,model_epoch}; working extension |
| preference_rank | options, target, partition, domain | {status,reason,basis,not_calibrated,target,partition,domain,training_sources,used_features,weights,ranked,model_epoch,input_revision}; working extension |


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

## Hybrid extension semantics (current source; main acceptance pending)

JSON params are closed and flat. There is no nested `feedback` dictionary.
Targets: actual/endorsed; domains: daily/study/relationships; partitions retain
rational/emotional/crazy. Options are explicit unique IDs with eight finite [-1,1]
value.* impacts; frontend supplies them and the user reviews them. Labels are
independent: actual_choice_id records what occurred, endorsed_choice_id records
rational retrospective endorsement. A nonnull label must identify an option;
nonnull endorsed_choice_id requires an explicit valid endorsement_partition;
only "rational" endorsement contributes to the endorsed preference target. No endorsed
label requires endorsement_partition=null. Missing labels use explicit null.
Whole-source approval/exclamation never supplies labels, impacts or training_consent.

feedbackRecord contains source_id, event_id, domain, options, actual_choice_id,
endorsed_choice_id, endorsement_partition, training_consent, reason, source
partition, source_version, model_epoch, body_digest, created_at, model_active.
set additionally returns input_revision; get returns saved records and current
snapshot input_revision/model_epoch. Guarded set fully replaces one source/event,
binds current source version/body/epoch and advances global input revision.
It can save pending feedback; neither set nor get fits. Bounds in source:
32 events/source, 65,536 UTF-8 payload bytes, event IDs 1–128 characters,
reason at most 2048 code points. Final schema conformance remains with main.

Feedback `model_active` means preference eligibility: agreed source with both
judgements true, explicit training_consent, matching source_version/partition/
body_digest and feedback epoch equal to current epoch. It is distinct from
inputRecord.model_active, which describes rule-fit participation. An inactive old
rule fit does not itself forbid deliberately saved current-epoch feedback.
Reset excludes old feedback; a new explicit guarded feedback save can re-enlist it.
Rule re-review alone does not re-enlist old feedback. F6 edit/delete purge feedback;
revoke/reopen/version/body changes invalidate its eligibility.

preference_rank reads a bounded authorized eligible snapshot, releases its DB
transaction, temporarily fits a CPU pure-Python L2 multinomial logistic baseline,
then ranks. It calls fit_preferences; it is not inference on persistent weights.
It writes no DB/rule state/effects/weights and never trains the encoder. Current
settings (Oct 5 source and final worker proof; main/fresh acceptance pending):
three distinct source IDs with informative events, L2=0.1, damped Newton with
a pure-Python Cholesky solve, at most 64 steps and 32 backtracks per step.
Returned weights must have gradient infinity norm <=1e-11. Backtracking starts
at 1, halves the step and uses Armijo coefficient 0.01; loss-roundoff slack is
bounded by 8 ulps and additionally requires residual reduction. Nonfinite
objectives abstain with nonfinite_fit; exhausted/failed convergence abstains
with fit_not_converged. The old 400 fixed steps/step=0.2 are historical.
At most 1000 current-epoch
records are screened; overflow/invalid snapshots abstain rather than fit a prefix.
Actual isolates source partition/domain; endorsed fits rational/domain from explicit
rational endorsement. Returned tokens describe the fitted snapshot, which may
be superseded by concurrent writes. Clients handle stale results deliberately.

ranked items contain id, score, model_probability and eight feature contributions.
basis="personal_choice_feedback_multinomial_logistic", not_calibrated=true.
Softmax is a model output, not a validated personal choice probability. Insufficient
sources, no identifiable preference, unsupported feature contrasts or a top score
gap <=1e-8 can abstain (options_tied_with_learned_weights for the latter).
Feature coverage still does not certify identifiable contrast span. Three IDs
are an exploratory count gate, not established independent sample sufficiency.
rank_from_fit rejects huge integer weights with ValueError before float conversion;
there is no JSON endpoint accepting an externally supplied fitted weight vector.

Screening caches only bounded source status/version/partition metadata and body
digests; it materializes one eligible source body at a time, hashing in 65,536-
character chunks, and streams feedback rows. Fit records omit source body,
nontraining reason and option labels. This does not make all fitting memory
constant: options/events remain bounded by the snapshot/payload limits.

memory_search_semantic validates query (1–2048 nonblank code points, no NUL/
surrogates), limit 1–100, min_score finite [-1,1]. It screens accepted/agreed/
matching-source-version memories and partition before selecting the latest bounded
pool of 1000, ranks that pool then applies limit. pool_count/pool_truncated expose
this bound. With no configured encoder it explicitly returns mode=lexical_fallback,
score_kind=none, score=null. Configured path/provider/load/encode failures return
MODEL_UNAVAILABLE; they do not fall back. Semantic mode returns cosine scores,
original memory/evidence and encoded_text_truncated. No persistent embeddings.
Global input revision is rechecked after encoding; API rechecks authorization,
including failure paths. Similarity neither verifies facts nor publishes candidates.

References: core/api.py METHODS/handle, core/brain.py memory_search_semantic,
model/preferences.py _public/set_feedback/rank_preferences, translator/semantic.py.
Actual weights, zero-network dependency execution, semantic quality, CPU performance
and real predictive validity remain unverified. Distinct IDs do not prove sample
independence. Memory/convergence/numeric fixes have final worker evidence, while
new main/fresh acceptance remains pending; production groups and contrast-subspace
extrapolation remain unimplemented acceptance work. Worker resource measurements
and their scope are in the [hybrid plan](hybrid-learning-plan.md#oct-5-final-worker-proof--mainfresh-acceptance-pending).

## Confirmed next-phase event-group policy (not implemented)

Frontend will explicitly provide a user-reviewed event-group ID; `group_id` is
PROPOSED, not a parameter/result field in the current closed JSON contract.
All materials in one reviewed group must share one total training loss mass
within each target/partition/domain fit. Backend may hint at exact-text duplicates
only; it must not infer same-event membership for distinct texts or grant review.
The next-phase review gate must exclude current feedback with legacy/unknown
groups until its group is user-reviewed. This is a future eligibility requirement,
not current runtime behavior or an automatic migration. Goodall completes the
base fixes first; a fresh owner implements group integration afterward. Field/
review/update semantics and frontend acceptance remain pending. Offline manifest
groups do not implement this live gate; contrast-span acceptance is still open.

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
| correction_reopen/review_version/replay_reopen/choice_feedback_set | GLOBAL input_page.revision, replay_preview.input_revision or latest version-result input_revision |

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
labelled strict held-out manifests. F14 development is authorized and has the working
methods above; final backend acceptance, frontend unlock/version/replay/F14 UI,
administrative reset/native and physical acceptance remain pending. Real validity
and actual encoder weights are unverified; API tests do not establish those results.

Full synthetic tests require `python -m pip install '.[test-schema,security]'` from
back-end-core, including pinned PyNaCl. Do not rely on system crypto dependencies.
The backend workflow installs both extras; pinned Actions/tokenizer refs remain.
Online CI has not been run by this integration worker.
