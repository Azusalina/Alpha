<a id="local-api-v1--revision-5-backend-synthetic-contract-delivered"></a>

# Local API v1 — revision 6 exact-text duplicate hint backend accepted

> 2026-10-06 (Asia/Taipei): schema_version=1 / contract_revision=6 / 35 methods,
> features.exact_text_duplicate_hint=true; prior contrast guarantees unchanged.
> Main session90162 exit0: 620 tests/100.682s/OK/0 skips; independent discovery
> 620 unique IDs/0 loader errors. Aquinas/Tesla/Franklin terminal reviews found
> no blockers. Only the exact-text duplicate hint backend is accepted this phase;
> see [current contract](#oct-6-rev6-exact-text-duplicate-hint) and [full proof](../../frontback-log.md#oct-6-rev6-exact-text-duplicate-hint).
> Earlier [main601](../../frontback-log.md#oct-6-offline-comparisons-and-typed-validation-performance)
> and [rev5 main576](#oct-6-final-rev5-backend-synthetic-contract) retain historical scope.
> P2/P3 overall, frontend/native, general correction/generic replay, actual weights
> and real validity remain pending. Dated proposals/intermediate pending below
> are superseded for current status; rev4 483/rev3 458/411 retain historical scope.
> Root queue has 13 pending items; overall goal ACTIVE/NOT ACHIEVED.

Historical main proof is 396 full-discovery tests (134.672s), then 51 semantic
tests (1.142s) covering the two added tests in a 398-test discovery; all had 0 skips.
Independent backup verification passed 12 (11.220s), 0 skips. This is not a single
398-test run or acceptance of later preference/evaluator edits. See
[current queue and proof](TODO.md#oct-6-rev6-exact-text-duplicate-hint).

`python -m core.api --db /absolute/synthetic.sqlite3` from `back-end-core` serves
newline-delimited UTF-8 JSON on stdin/stdout. No network listener. The host selects
the database path. stderr carries diagnostics; `--quiet` disables model traces.
Requests are exactly `{schema_version:1,id,method,params}`; ID is a 1–128 character
string. Success: `{schema_version:1,id,ok:true,result}`. Failure:
`{schema_version:1,id:string|null,ok:false,error:{code,message}}`.
ID is correlation, not idempotency. Do not retry uncertain writes automatically.

<a id="34-methods--revision-5-synthetic-backend-conformance-verified"></a>

## 35 methods — revision 6 backend conformance accepted

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
| health | `{}` | schema_version=1, contract_revision=6, candidate_publication="automatic_double_approval", llm_runtime_configured=false, methods, features.reviewed_event_groups=true, features.preference_contrast_guard=true, features.exact_text_duplicate_hint=true, access; model_epoch when unlocked only |
| baseline | `{}` | schema_version=1, partitions, parameters (13 immutable zeros) |
| access_status | `{}` | configured:boolean, locked:boolean |
| unlock | password | configured:boolean, locked:boolean |
| lock | `{}` | configured:boolean, locked:boolean |
| submit | text, partition, kind?="diary", self_speaker?, source_ref?, immediate?=true, exclamation?=false | decisionFields; actual fit fields on exclamation |
| input_get | source_id | inputRecord plus text |
| input_duplicates | source_id, limit?=20 | {source_id,source_version,match_kind="exact_text",items:duplicateItem[],total,truncated,input_revision,model_epoch}; [closed metadata contract](#oct-6-rev6-exact-text-duplicate-hint) |
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
| memory_search_semantic | query, partition?, limit?=20, min_score?=0.0 | {mode,score_kind,items:[{memory,score,encoded_text_truncated}],pool_count,pool_truncated} |
| choice_feedback_set | source_id, event_id, domain, options, actual_choice_id:string|null, endorsed_choice_id:string|null, endorsement_partition:string|null, training_consent:boolean, expected_source_version, expected_revision, expected_epoch, reason?:string|null, group_id?:string|null=null, group_reviewed?:boolean=false | feedback record including group_id/group_reviewed, plus input_revision |
| choice_feedback_get | source_id | {source_id,records:feedbackRecord[],input_revision,model_epoch}; all records include normalized group_id/group_reviewed |
| preference_rank | options, target, partition, domain | {status,reason,basis,not_calibrated,target,partition,domain,training_sources,training_groups,used_features,weights,contrast_rank,contrast_basis,ranked,model_epoch,input_revision} |


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

<a id="hybrid-extension-semantics-current-revision-5"></a>

## Hybrid extension semantics (current revision 6)

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
endorsed_choice_id, endorsement_partition, training_consent, group_id,
group_reviewed, reason, source
partition, source_version, model_epoch, body_digest, created_at, model_active.
set additionally returns input_revision; get returns saved records and current
snapshot input_revision/model_epoch. Guarded set fully replaces one source/event,
binds current source version/body/epoch and advances global input revision.
It can save pending feedback; neither set nor get fits. Bounds in source:
32 events/source, 65,536 UTF-8 payload bytes, event IDs 1–128 characters,
reason at most 2048 code points. group_id defaults null and, when nonnull, is
nonblank 1–128 Unicode code points without NUL/surrogates; group_reviewed defaults
false and must be a real boolean. True requires a nonnull group_id. Draft saves
are allowed. Groups belong to feedback events, not entire text files. Old exact
payloads normalize to null/false on read without stored-payload backfill; partial
new/unknown field shapes are rejected. User-reviewed guarded save is required
to make legacy feedback eligible; no automatic grouping/review/consent.

Feedback `model_active` means preference eligibility: agreed source with both
judgements true, explicit training_consent and group_reviewed, matching source_version/partition/
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
settings (revision 5): at least three informative reviewed groups per
target/partition/domain, L2=0.1, damped Newton with
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
groups (insufficient_training_groups), no identifiable preference, unsupported feature contrasts or a top score
gap <=1e-8 can abstain (options_tied_with_learned_weights for the latter).
Feature coverage still does not certify identifiable contrast span; rev5 also
checks every query pair with the span guard below. training_sources
counts actual informative source IDs; training_groups counts informative groups
separately. One source can contain three groups, while many sources in one group
cannot cross the gate. Three reviewed group IDs remain an exploratory count gate,
not proof of independent samples or sufficient data.

For G informative groups and n_g informative events in group g in this axis:
L(w) = -(1/G) sum_g (1/n_g) sum_e log q_e,y_e + (L2/2)||w||².
Each event has loss weight 1/(G*n_g), each group total 1/G: the global mean of
group means. The one group weight unit is before group averaging, not normalized
mass=1. Pure offline callers screen their own provenance and may use source-ID
fallback only when group fields are absent. Explicit unreviewed groups never
fall back; online snapshots always supply group fields and require review.
rank_from_fit rejects huge integer weights with ValueError before float conversion;
there is no JSON endpoint accepting an externally supplied fitted weight vector.
Option-impact validation checks exact int/float types and [-1,1] bounds before
math.isfinite/float conversion. Enormous integers raise controlled ValueError;
API calls return INVALID_ARGUMENT while preserving stored state and process survival.

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
independence. Memory/convergence/numeric base fixes have scoped main/fresh acceptance;
reviewed production groups now have narrow synthetic contract acceptance.
Contrast-span refusal has narrow rev5 synthetic acceptance; same-span utility,
magnitude/convex-hull coverage and real extrapolation validity remain unverified. Worker resource measurements
and their scope are in the [hybrid plan](hybrid-learning-plan.md#oct-5-final-worker-proof--mainfresh-acceptance-pending).

## Rev5 contrast contract

Contrast metadata belongs to `preference_rank`. Legacy `rank` retains its
value-alignment result shape without contrast_rank/contrast_basis fields.

Health declares schema_version=1, contract_revision=5 and 34 methods with
features.preference_contrast_guard=true; reviewed_event_groups=true remains.
The closed preference_rank result requires contrast_rank and contrast_basis in
both provisional and abstain results, alongside the existing weights/used_features,
counts, snapshot tokens and ranked fields. contrast_rank is an integer 0–8
(not bool); contrast_basis has exactly contrast_rank rows (rank0 gives []).
Each row has exactly eight finite numeric coordinates in [-1,1]. Runtime also
validates unit length and mutual orthogonality within 1e-12; schema shape alone
does not certify that geometry. The fixed column order is:

```text
value.autonomy, value.fairness, value.care, value.truth,
value.security, value.growth, value.achievement, value.connection
```

This order comes from VALUE_PARAMETERS, not baseline JSON/catalog iteration.
Fit geometry uses informative eligible option differences per target/partition/
domain; query membership checks EVERY pair (at most 28 for eight options).
unsupported_option_features retains feature-support precedence. Otherwise any
nonzero normalized pair outside the identified span returns status=abstain,
reason=unidentified_option_contrasts and ranked=[]. A query is never projected
into the span to manufacture support; used_features alone cannot establish it.

The deterministic pivoted/twice-reorthogonalized construction converts original
binary floats exactly inside an isolated 80-digit Decimal context before
normalization; only exported basis coordinates become floats. Rank tolerance
1e-10, membership tolerance 1e-12 and orthogonality tolerance 1e-12 are unchanged.
Membership uses the exported validated basis; a direction dropped by rank policy
has no membership exemption, even if it occurred in training. These are engineering
policies, not statistical confidence, calibrated precision, covariance,
parameter-magnitude identification, convex-hull/magnitude coverage or real utility
validity. L2 regularization and same-span membership do not establish those claims.
There is no formal numerical error bound or general SVD-equivalence claim.

The offline P3 evaluator uses the production preference fit/rank guard and reports scalar
contrast_rank per training axis only, without raw contrast_basis, weights or
private internal variables. Public preference_rank still returns contrast_basis
and learned weights under its existing private-access boundary. Neither report
nor preference_rank establishes real predictive validity. The reviewed-group gate applies
only to the eight-weight preference branch; source t/t still updates translator,
13-rule model and memories without choice metadata. preference_rank fits
temporarily at read time without DB/rule/effect/weight writes or encoder training;
feedback_set/get do not fit. Counts and activity meanings remain separate.

## Confirmed next-phase event-group policy (not implemented)

Historical Oct 5 proposal, superseded by the current revision 4 contract above.
The following planned-field/do-not-send implications no longer describe the
backend. Frontend UI/adapter acceptance and exact duplicate hints remain TODO.

Frontend will explicitly provide a user-reviewed event-group ID; `group_id` is
PROPOSED, not a parameter/result field in the current closed JSON contract.
All materials in one reviewed group must share one total training loss mass
within each target/partition/domain fit. Exact-text duplicate hints remain TODO;
backend must not infer same-event membership for distinct texts or grant review.
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
methods above; narrow rev5 synthetic backend contract is delivered. Frontend unlock/version/replay/F14 UI,
administrative reset/native and physical acceptance remain pending. Real validity
and actual encoder weights are unverified; API tests do not establish those results.

Full synthetic tests require `python -m pip install '.[test-schema,security]'` from
back-end-core, including pinned PyNaCl. Do not rely on system crypto dependencies.
The backend workflow installs both extras; pinned Actions/tokenizer refs remain.
Online CI has not been run by this integration worker.

## Oct 5 fresh rev3 baseline proof

Historical recovery sequence: pending/PROPOSED statuses through the pre-final
delivery records are superseded by the current revision 4 contract and final
accepted section below. All counts retain their stated pre-fix/pre-group scope.

Main supplied terminal proof from `back-end-core`:

```sh
TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q
```

458 tests, 181.564s, OK, 0 skips, before the evaluator zero/numeric-impact fix
and rev4 group edits. This verifies the scoped rev3 baseline, including the
then-present evaluator tests, but the recovered duplicate defect prevents P3
tool acceptance. The earlier 411-test proof is retained in TODO/hybrid history.
Old job 97510 lacks terminal proof; fresh job 9839 supersedes its pending result.
The temporary Python 3.14.7/jsonschema 4.26.0 environment inherited PyNaCl and
does not prove hosted CI, Python 3.10 or release dependency provisioning.

Pauli's pending evaluator fix makes omitted impacts and exact `0`/`0.0`/`-0.0`
equivalent and normalizes equal int/float values without rounding distinct
nonzero impacts. Pauli supplied 68 pass = 51 evaluator (47 old + 4 new) + 17 pure
before concurrent partial group edits. Independent Lorentz/fresh antipattern/
quality reviews and settled-code proof remain pending. Main's overlapping
evaluator51 encountered WIP MIN_SOURCES NameError, not acceptance. Do not mark
final P3 or use the pre-group proof to accept group behavior.

## Prospective revision 4 — PROPOSED until owner proof

Descartes has started group implementation after the fresh baseline terminal.
This section is the agreed plan, not the current accepted request/result schema.
Prospective contract_revision=4 retains the same 34 methods.

| Proposed change | Planned semantics |
| --- | --- |
| `choice_feedback_set` optional `group_id: string|null`, `group_reviewed: boolean=false` | Explicit frontend user review per feedback event; draft/unknown records may be saved. Existing flat fields and version/revision/epoch guards remain. |
| Legacy stored payloads | Preserve their exact old field set; normalize missing group metadata to unknown/unreviewed on read. Exclude from online preference eligibility until deliberate guarded user-reviewed save. No silent migration or approval. |
| Online eligibility | Require training_consent, source immediate/confirm both true, current version/body digest/epoch and reviewed group. Group review grants neither source approval nor training consent. |
| Group loss and support | One total loss mass per reviewed group within target/partition/domain. Require at least 3 distinct informative `training_groups`; `training_sources` counts actual source IDs separately. |
| Pure offline fitting | Legacy callers retain responsibility for provenance screening and may fall back to source-ID grouping. This fallback must not bypass the online review gate or create frontend training eligibility. |

Group scope is the feedback event, not the complete diary/chat file. Exact-text
duplicate hints remain TODO; no backend inference of distinct texts as the same
event. Final field placement, signatures and reason enums will be documented
from delivered source/schema and owner proof. Next safe action: reconcile that
delivery, then record fresh fix/group verification with its precise scope.
P2/P3, contrast span, real held-out/calibration/weights/GPU and frontend/native
remain pending.

Oct 5 latest limited acceptance: canonical zero/numeric-copy identity has Pauli's
68 targeted pass and independent Lorentz 51 evaluator/4.258s/0 skips, unchanged
module hashes and eight stable actual/endorsed repro checks. Mill and James static
reviews found no blocker (James supplied no runtime). Only canonicalization is
accepted. The evaluator report's fit['training_groups'] integration still needs
final rerun; main session 37713 is running. Group checkpoint 92 existing/91.197s
and 18 new/7.916s, 0 skips separately, precedes final schema/backup additions and
fresh group reviews. Rev4 remains PROPOSED/unaccepted for frontend handoff;
whole P3, baselines/ablation and real validity remain pending.

### Stable actual rev4 delivery — implemented, awaiting acceptance

This supersedes the preceding PROPOSED implementation status. Owner source and
schema now implement the group contract; main's full suite and three fresh
group reviews must finish before accepted header/health-table switch. Actual
extension to the flat `choice_feedback_set` signature:

```python
reason: str | None = None,
group_id: str | None = None,
group_reviewed: bool = False
```

Group IDs are nonblank 1–128 Unicode code points with no NUL/surrogates; true
group_reviewed requires a nonnull group_id. Every returned feedback record has
group_id/group_reviewed, including normalized legacy null/false; stored legacy
payloads are not backfilled. Health declares revision 4, 34 methods and
features.reviewed_event_groups=true. `training_sources` counts actual informative
source IDs separately from `training_groups`; min3 groups returns
insufficient_training_groups when unmet. Other solver reasons are unchanged.
The pure offline source-ID fallback retains caller responsibility for screening.

The review gate applies only to the eight supervised preference weights.
Whole-source double approval continues updating translator, the 13-rule model
and memories without choice-group metadata. choice_feedback_set/get do not fit;
preference_rank performs temporary recomputation at read/rank time, without
persisting fit weights or training the encoder. inputRecord.model_active and
feedbackRecord.model_active retain their separate rule/eligibility meanings.

Owner new final group20 + schema19 = 39 tests/34.034s/0 skips; existing
92/91.197s/0 skips is earlier scoped proof. Encrypted reviewed/exact legacy
payload backup/DDL/no-backfill tests are in test_preference_groups.py; backup
code/file is unchanged. Groups remain unaccepted pending main/fresh finals.

Limited synthetic P3 tool provision is accepted: report integration now reads
authoritative fit['training_groups'], owner51/4.695s/0 skips and main settled
evaluator51/4.139s/0 skips. Numeric canonicalization is unchanged; earlier
independent51/eight repros/static reviews retain scope. This does not accept
whole P3, baselines/ablation/calibration/real held-out validity or frontend.

Current rev4 group objective (synthetic backend contract accepted): for G informative
groups and n_g informative events in group g within this target/partition/domain,
L(w) = -(1/G) sum_g (1/n_g) sum_e log q_e,y_e + (L2/2)||w||².
Each event has loss weight 1/(G*n_g), each group total 1/G. "One group, one
weight unit" describes the pre-average group contribution, not normalized mass=1.
The source-ID objective/gate in the rev3 baseline above is historical; group IDs
and this min3 gate still do not prove independence or real predictive validity.

## Oct 5 final rev4 backend synthetic contract

Main terminal session 28196, exit 0, from `back-end-core`:

```sh
TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q
```

483 tests, 121.151s, OK, 0 skips, covering final canonicalization, group20,
schema19 and evaluator51 report integration. Lagrange independently passed
51 focused (20 group + 19 schema + 12 backup), 19.543s test/20.215s wall,
0 skips, then 3 inline checks, 7.380s test/8.227s wall, 0 skips: all 54 passed
in two runs. Legacy DB bytes remained identical across two restarts; online
axes stayed isolated, unequal groups matched an independent scalar equal-mass
reference, network calls=0 and all DB connections used temporary paths.
62 tracked-file hashes were stable. Exact focused command from `back-end-core`:

```sh
time env TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest tests.test_preference_groups tests.test_schema_contract tests.test_hybrid_backup -v
```

Meitner quality: no blockers, 8 targeted/7.990s/0 skips, 12 valid-axis mass
checks and all 34 callable required/optional-field/schema parity; hashes stable.
Kant antipattern: no blockers, 5 stable hashes, 9 pure pass and 8 synthetic
API/schema guard cases with network/SQLite blocked. Confirmed no automatic
group/review/consent, no legacy backfill, no live fallback, no persisted fit or
encoder training. These are scoped synthetic proofs, not real-data/GPU/CI proof.
Earlier recovery/proposal/intermediate statuses below dated headings are historical.

Narrow reviewed-group backend contract and synthetic P3 tool provision are
delivered. Whole P2/P3, baselines/ablation, contrast span, duplicate hints,
frontend/native, calibration, actual weights and real held-out validity remain
pending. Next: frontend owner integrates the accepted fields with explicit
review/consent and independent UI tests; contrast span stays a separate task.

## Oct 6 final rev5 backend synthetic contract

2026-10-06 (Asia/Taipei): main accepts only the limited rev5 backend synthetic
contract after the input-bounds repair and all three final review rechecks.
Authoritative main session80693, exit0, from `back-end-core`:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/tmp/alpha-verify-20261005-night.khVPhV /tmp/alpha-verify-20261005-night.khVPhV/bin/python -B -m unittest discover -s tests -q
```

576 tests, 59.590s, OK, 0 skips. The documentation owner records main's terminal
evidence and did not rerun this suite. Previous main574/61.668s is prerepair
history only; quality's duplicate successful574/61.968s is not a main proof.

All three final reviews found no blockers, with distinct scopes:

- Archimedes verification: 161 distinct tests across initial/corrected temporary-URI
  guard runs (not 161 from each run); independent 216 Fraction cases with
  2160 inside/756 outside/2772 normal checks, maximum residual6.939e-17, 0.613s.
  Post-bounds recheck8/1.113s/0 skips.
- Chandrasekhar quality: post-bounds8/1.144s/0 skips. Original exploratory3684
  checks exited1: nine incorrect rank-threshold expectations were independently
  explained as expected rank6/residual6.93855e-11. The complete harness was NOT
  rerun green and is not recorded as passed; final no-blocker status does not
  convert that exploratory exit1 into a successful run.
- Kant antipattern: 13 pure/0.057s/0 skips and post-repair pure1/0.003s/0 skips
  with DB/network denied.

The phase includes the preexisting huge-integer impact-validation edge repair:
bounds precede math.isfinite/float conversion, controlled ValueError/API
INVALID_ARGUMENT preserves stored state/process survival; two new regressions,
owner8+69 pass. Review/test/check counts overlap and are not added to main576
or combined into an invented single-run total. Exact reviewer commands were
not supplied to this documentation owner; none are fabricated.
Numeric owner55/8.020s, benchmark and residual scopes are recorded in the
[hybrid numeric proof](hybrid-learning-plan.md#oct-6-rev5-numeric-proof-and-remaining-scope).

Final source identities (read-only hash check by documentation owner):

| File | SHA-256 |
| --- | --- |
| model/contrast.py | `abf73e8d962a11bced7951c80c15459fd7b4b9483d6320c7eb38010afd239bcd` |
| model/ranking.py | `b9d7e2724728571bad2825337ca1774f10f6e1c73b941c457de292f6167516b2` |
| tests/test_value_order.py | `a17c5ef97aa1b000051ef093de07a2f4c080e5c841e0a85c9a6bafddb04cccbd` |
| model/baseline.json | `7531203bda3cb9c3572e17502d95d68df7a429df2480def9be1592f616c06d7c` |

Contrast remains the stable 80-digit Decimal implementation; ranking reflects
the final bounded validation-order repair. Rev4/483 and all dated proposals/
intermediate pending records above retain their historical scope and are
superseded for current status only. Completed root tasks moved to the
[Oct 6 log](../../frontback-log.md#oct-6-final-rev5-backend-synthetic-contract).
Overall goal remains active: P2/P3, real validity/calibration/parameter selection,
frontend/native, general correction/generic replay, actual weights/GPU and
online CI/Python3.10 remain pending.

## Oct 6 rev6 exact-text duplicate hint

`input_duplicates(source_id: str, *, limit: int = 20) -> dict` is an
authenticated, read-only advisory query for an already stored submit/current
edit. Closed flat params require source_id and allow only optional limit.
Runtime rejects blank/non-string/NUL/surrogate IDs and limits other than exact
int (non-bool) 1..100; JSON Schema integer accepts 1.0 while runtime rejects it,
an existing validator limitation. Shape validation is not semantic proof.
The target must be an application input or returns NOT_FOUND; legacy-only
targets/matches and the target itself are excluded. All statuses, kinds,
partitions and current/old epochs are included. Match CURRENT stored raw text
using SQLite BINARY equality: no trim, casefold, normalization, CRLF conversion,
fuzzy/semantic comparison, hash matching or history matching.

The closed result contains exactly source_id, source_version,
match_kind="exact_text", items, total, truncated, input_revision, model_epoch.
Each closed item contains exactly source_id, partition, kind, status,
source_version, model_epoch, model_active, created_at. Items order by
created_at DESC, source_id DESC; limit bounds output, not full-scan latency.
Target version, total, limited items, GLOBAL input_revision and CURRENT
model_epoch share one BEGIN read snapshot. Item model_active means rule source
agreed in the current epoch, not feedback eligibility. Target source_version
and top-level revision/epoch are snapshot tokens, not guaranteed latest at
return; the frontend must discard stale hints against current guards before use.

No raw text, source refs, excerpts, evidence, hash, labels, weights, group review
or consent are returned. Counts/IDs/statuses remain private: clear hint caches
on LOCKED/reconnect/Reset/edit/delete/version changes. Access is checked before
and after operation; lock/config rotation suppresses metadata. Locked calls
with a missing DB create none; SQLite remains plaintext. The backend does not
invoke the hint inside submit/edit/review or other operations; a frontend may
explicitly request it after save/edit, including its own post-save trigger.
There is no automatic grouping/approval/consent/merge/dedup/block-submit/refit,
and different text does not imply the same event. User-reviewed event groups
remain necessary.

Health now exposes features.exact_text_duplicate_hint=true with rev6/35 methods;
schema_version=1, the closed request/envelope design and prior contrast guarantees
remain unchanged. Frontend negotiation requires BOTH the input_duplicates method
and the feature, plus owner adapter/UI/cache/native acceptance, still pending;
no automatic write retry. Read-only main inspection found Remote.readHealth
permits new fields but API_METHOD has no duplicate method; this is not UI proof.
Main620/100.682s/OK/0 skips and all three terminal reviews accept only this
backend phase; exact command, review scopes and six hashes are in the
[rev6 log](../../frontback-log.md#oct-6-rev6-exact-text-duplicate-hint).
Root13 pending; overall goal ACTIVE/NOT ACHIEVED.

## Oct 6 rev7 semantic label revision (pending acceptance)

typedCorrection accepts an optional `revised_value` (trimmed 1–64 characters, no
control/surrogate characters, different from `value`, only with `sign` 1) when
`health.features.semantic_label_revision` is true. It targets exact existing
translator output as before and replaces only that record's `value` in
`interpretation.translation` and in deterministic memory claims. Raw text, the raw
`preview.translation` report, the 13 rule parameters and learned rules are
unchanged; typed annotations still never teach rules. Already-fitted sources use
`correction_reopen`/`replay_reopen` with the usual source_version/revision/epoch
guards and return to pending/disagreed, so both judgements must be reconfirmed.
Nothing is inferred, propagated to other sources or auto-reviewed. Adding labels
the translator did not produce is not implemented. Local synthetic tests only.

## Oct 6 rev7 manual relations (pending acceptance; 38 methods)

`relation_set` and `relation_list` (health.features.manual_relations) store only
user-reviewed directed edges between two existing sources, kind `semantic` or `causal`.
`relation_set` is guarded by both source versions, global input revision and model
epoch; `reviewed=true` saves/replaces the edge (optional note up to 1024 characters),
`reviewed=false` retracts it (idempotent, `changed=false` when absent; no note). A
source may touch at most 64 edges. Nothing is inferred: the backend never creates,
reviews, consents, fits, replays or rewrites effects because of an edge.

An edge is bound to both source_versions and the model epoch. `relation_list`
(`source_id`, limit 1–100) returns incoming/outgoing edges with `stale=true` once
either source was reopened/versioned or the model was Reset; stale edges are
ignored by the planner and not auto-deleted. F6 edit/delete purge the source's
edges. `dependency_plan` now also follows fresh edges (via_kinds `manual_semantic`/
`manual_causal`); manual-only targets have fit_id=null, provenance_complete=false and
replay_eligible only if they were fitted in the current epoch. Manual edges do not
make `status` partial and are user claims, not proof of causation. Notes and ids are
private: frontends clear them on LOCKED/reconnect/Reset like other private caches.
Replay still requires explicit `replay_reopen` with guards and fresh double
confirmation. Local synthetic tests only; no independent review.
