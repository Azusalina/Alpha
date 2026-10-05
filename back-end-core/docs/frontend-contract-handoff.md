# Frontend contract handoff: v1 — revision 5 backend synthetic contract delivered

> 2026-10-06 (Asia/Taipei): schema_version=1 / contract_revision=5 / 34 methods,
> features.preference_contrast_guard=true, narrowly accepted by main session80693
> exit0: 576/59.590s/OK/0 skips, all three final reviews no blockers.
> [Current contract/proof](api.md#oct-6-final-rev5-backend-synthetic-contract).
> Frontend adapters/UI/group review/unlock/cache/native, overall P2/P3, actual
> weights and real validity remain pending. Dated proposal/do-not-send/pending
> records below are historical and superseded for current contract status.

Oct 2 backend exposed 30 accepted methods; current source declares 34; [api.md](api.md) and [api.schema.json](api.schema.json)
document current rev5 params/results (synthetic backend conformance verified). Detect negotiated
health.contract_revision plus methods/features,
not schema_version alone. UI/TypeScript adapters and Rust validation belong to their
owners. Frontend hardcoded method tests need owner updates to the accepted negotiated set;
23/30-method assumptions must not silently enable the working extension. This handoff
does not claim physical native acceptance or implement frontend F13 unlock UI.

## Access and token acquisition

1. Call health/access_status. Locked health is static, never reads SQLite and omits
   model_epoch. baseline remains public. All other data methods return generic LOCKED.
2. Prompt locally and send unlock(password). It returns configured/locked only;
   no SQLite construction or metadata. Do not log/retain credentials or auto-unlock.
   Every valid-envelope unlock attempt, even malformed params, revokes prior access.
3. After success, call health for CURRENT model_epoch and input_page (limit=1 is
   sufficient) for GLOBAL revision. Page revision equals reset_info.input_revision;
   filters do not narrow its scope. Get source_version from input_get/page rows.
   A row's model_epoch can be historic and must not be expected_epoch.
4. Send review_version/correction_reopen using expected_source_version,
   expected_revision=page.revision and expected_epoch=health.model_epoch. These reads
   can race; stale guards return INVALID_ARGUMENT without mutation. Refresh, show
   conflict and obtain deliberate consent; no automatic mutation retry.

correction_set is different: expected_revision=correction_history.revision for THAT
source. It saves pending feedback and changes the global page token too. Do not
substitute correction revision into a version operation, or vice versa.
Replay preview supplies source versions, input_revision and model_epoch in one
snapshot; use these with an exact source-to-version map for replay_reopen. Batch item
tokens equal final outer tokens, not intermediate transaction values.

On lock/LOCKED/config replacement/reconnect, discard private detail/excerpt/preview/
state/effect/correction/memory caches and queued UI operations. Authorization does
not persist on reconnect. Authenticated health can fail MODEL_UNAVAILABLE for a
missing/invalid protected DB; never create a replacement or infer epoch=0. Frontend
unlock/cache UI acceptance is pending; the backend gate is implemented.

## Publication and version consent

Fresh whole-source double approval publishes conservative exact lexical memories
atomically, no LLM. candidate_propose on agreed material returns accepted. Separate
candidate_review is for legacy pending records; migration/startup/frozen reapproval
never publishes old pending/rejected candidates. Active memory requires agreed source
and matching source_version. Refresh memories after source mutations.

Reviewed correction/replay increments source_version, archives prior interpretation,
withdraws support and restarts confirmation. Pending responses CAN contain withdrawal
effects; display actual effects and refresh state. Old review rejects every reopened
version, even negative decisions; use guarded review_version. Reopen immediate false
does not grant second consent. Typed suppress/retain labels match existing authored
translator evidence, not arbitrary semantics. Raw body stays unchanged.

Administrative model-only reset preserves translator/memories/archives but excludes
old fits from active model. Show agreed + model_active=false distinctly. Reopen/replay
cannot bypass exclusion. A deliberate guarded review_version can restore a selected
frozen fit (legacy review only at version 0). Never auto-review, auto-replay or animate
historical effects. Reset, backup/restore and evaluation are not JSON API methods.

Legacy F6 input_edit replaces body/purges history and resets source_version=0.
Semantic reopen guards do not prevent an old queued unversioned review across F6;
clear in-flight source operations on edit/reconnect. Future content-revision guards
need a separately agreed compatible frontend contract, not an implicit API break.

## Host and verification handoff

Rust trace whitelist includes review_version/correction_reopen/replay_reopen;
main's final 16 Rust tests passed, retaining event field/path/size validation.
Batch tracing uses one commit receipt followed by per-source records after all commit;
no new events or sensitive payload fields. Coordinate through main; no Rust edits
were made by this integration worker.

Synthetic verification from back-end-core:

```sh
python -m unittest tests.test_schema_contract tests.test_api tests.test_access_api tests.test_tracing -q
```

All fixtures use temporary databases. Main runs final full discovery after worker
completion. Full test environments install `.[test-schema,security]` from back-end-core;
system PyNaCl must not mask missing CI dependencies. Online CI was not run here.
Readiness/offline evaluations remain separate authorized read-only
contracts; real held-out validity evidence and frontend/native acceptance remain
pending. F14 development is authorized; working backend signatures are below. No private DB, Git, PNG, frontend or shared TODO edits are
part of this integration handoff.

## F14 and semantic extension handoff (current revision 5)

New methods: memory_search_semantic, choice_feedback_set, choice_feedback_get,
preference_rank. Current flat params/results are in api.md; no feedback dictionary.
domain is daily/study/relationships, target is actual/endorsed. The source's
partition and explicit rational endorsement serve different purposes.

Frontend records options and user-reviewed finite value.* impacts, independent
actual_choice_id/endorsed_choice_id (explicit null when unknown), rational
endorsement_partition for nonnull endorsed labels, and separate training_consent.
Material double approval, exclamation, unlock, preview or rank never imply consent
or labels. choice_feedback_set requires fresh source_version/GLOBAL input revision/
CURRENT unlocked health epoch; conflict handling is deliberate, with no write retry.
Set also accepts optional group_id:string|null=null and group_reviewed:boolean=false.
True review requires a nonblank 1–128 code point group ID without NUL/surrogates.
Drafts may be saved; every returned feedback record contains both group fields.
Legacy null/false normalization never backfills stored payloads or grants review.
Health exposes contract_revision=5, features.reviewed_event_groups=true and
features.preference_contrast_guard=true.

Feedback record model_active is preference eligibility (approved + consent + group_reviewed +
matching version/body/partition + feedback current epoch); input model_active is
rule-fit participation. Display these independently. Reset feedback exclusion is
lifted by explicit guarded feedback save; rule re-review does not reactivate it.
A deliberate current-epoch save may be eligible even when the old rule fit is inactive.
This gate affects only the eight supervised preference weights. Whole-source
double approval still updates translator, the 13-rule model and memories without
choice group metadata. Never conflate input.model_active with feedback.model_active.

preference_rank temporarily CPU-fits on the approved eligible read-only snapshot
then ranks; it writes no DB or weights and does not train the encoder. set/get do
not fit. Show returned model_epoch/input_revision and handle concurrent stale
results; no persistent fit endpoint exists. Report provisional/abstain,
not_calibrated=true; model_probability is uncalibrated, not actual behavior likelihood.
training_sources counts actual informative source IDs, separately from
training_groups. At least three informative groups are required; otherwise
reason=insufficient_training_groups. Within each target/partition/domain, event
loss weight=1/(G*n_g), group total=1/G; objective is mean of group means plus
(L2/2)||w||². Labels, source approval, consent and group review are independent.
Online snapshots always require explicit reviewed groups; pure offline legacy
caller fallback does not grant frontend/online eligibility.

memory_search_semantic exposes semantic/cosine or explicit lexical_fallback/none
with null score when no encoder is configured. Configured encoder failure is
MODEL_UNAVAILABLE, not fallback. Expose pool_truncated and encoded_text_truncated;
similarity is evidence relevance, not truth. Lock/reconnect clears all new private
feedback/rank/search caches and queued operations too.

Oct 4 frontend's root communication entry remains its owner's historical statement.
Backend rev5/34-method synthetic contract is delivered. Adapter/group-review,
unlock/version/F14 UI and native acceptance remain pending until separately verified.
The user answered "不管" to the historical privacy note: no action. The frontend
entry is preserved; the document audit does not touch files or Git history.

Preference overall acceptance remains pending: base fixes and reviewed-group
backend contract and rev5 contrast guard have scoped main/fresh acceptance;
same-span utility, magnitude/convex-hull coverage and real extrapolation validity
are still open. Historical 51-test semantic acceptance
is synthetic/mocked and does not establish real encoder weights or semantic quality.

Historical implementation continuation (superseded by final evidence): Goodall owns digest-only screening, convergence/near-tie
abstention and controlled huge-integer ValueError; Zeno owns the separate frozen
manifest preference evaluator. Current source: at most 64 Newton steps/32
backtracks, L2=0.1, returned gradient infinity norm <=1e-11 and top-gap abstention
at <=1e-8; nonfinite_fit/fit_not_converged fail closed. No new online group fields
exist. Source-group independence and identifiable contrast span remain production
acceptance items even if an offline evaluator enforces group isolation.
Historical main proof is 396 full tests/134.672s, followed by semantic 51/1.142s
covering the two added cases in discovery 398, plus independent backup 12/11.220s;
all 0 skips. This supplies earlier regression evidence, not later-edit acceptance
or frontend/native readiness. Keep P2/P3, real validity and frontend tasks pending.

Oct 5 final worker reports 80 synthetic tests (41 preferences/21 hybrid/18 schema),
128.728s, 0 skips; main's new base full and fresh reviews are still running.
Evaluator tests/docs/example are not yet delivered. Exact main proof will update
only its scoped backend subtask, not P3, frontend/native or real validity.

## Confirmed event-group decision — frontend contract pending

Historical Oct 5 proposal, superseded by current rev4 above. Its PROPOSED /
do-not-send / unimplemented statements no longer describe the backend; frontend
adapter/UI acceptance is still pending. Exact-text duplicate hints remain TODO.

The user selected explicit frontend event-group IDs reviewed by the user.
`group_id` is PROPOSED; do not send it to the current closed API or treat it as
an accepted result field. All materials in the same group will share one total
training loss mass within each separate target/partition/domain fit. Exact-text
duplicate hints remain TODO; backend must never infer same-event membership
for distinct texts, assigns groups or supplies user review.

- [ ] Next-phase fresh owner, after Goodall's base fixes: implement field/review
  gate and group weighting. Legacy/unknown-group feedback must be excluded until
  reviewed under that future gate; this exclusion is not implemented now.
- [ ] Frontend owner/main: settle explicit group selection/review, feedback update
  and legacy review contracts; keep unresolved fields PROPOSED and verify UI/
  adapter/native behavior separately. No automatic grouping or endorsement.

Frozen evaluator group isolation is a separate offline contract and does not
prove this online gate or identifiable contrast-span acceptance.

## Oct 5 recovery handoff — rev4 plan remains PROPOSED

Historical recovery sequence; waiting statements through the weighting note are
superseded by the final accepted milestone below, preserving each proof's scope.

Main supplied terminal proof from `back-end-core`:

```sh
TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q
```

458 tests, 181.564s, OK, 0 skips verifies the pre-fix/pre-group rev3 baseline.
It includes then-present evaluator tests, but recovery review found a numeric
duplicate defect, so P3 is not accepted. Pauli supplied 68 pass = 51 evaluator
(47 old + 4 new) + 17 pure before concurrent partial group edits. Independent
re-review and fresh antipattern/quality reviews remain underway. Main's overlapping
51-test run hit transient MIN_SOURCES NameError during group WIP, not acceptance.
Old job 97510 has no terminal proof; fresh 9839 replaces its pending state.
Temporary Python 3.14.7/jsonschema 4.26.0 with inherited PyNaCl is not the permanent
frontend/backend release runtime. Existing 411-test proof and front Oct 4 comments
retain their historical scope.

Descartes has begun online group writes. Planned revision 4 retains 34 methods;
fields remain PROPOSED for handoff until final source/schema and proof arrive.
See [proposed API contract](api.md#prospective-revision-4--proposed-until-owner-proof).

- [ ] Per feedback event, optional `group_id: string|null` and
  `group_reviewed: boolean=false` permit draft saves. Group scope is not an
  entire text file. The frontend supplies deliberate user-reviewed membership;
  no inferred review, source approval or training consent.
- [ ] Keep old stored payload shapes exact; normalize missing group fields to
  unknown/unreviewed for reads. Online eligibility excludes legacy/draft groups
  until explicit guarded save with user review, training_consent, double source
  approval and current source-version/body-digest/epoch. No automatic retry.
- [ ] Show independent `training_groups` (at least 3 informative reviewed groups)
  and `training_sources` (actual source IDs) once implemented/verified. Each
  group has one total loss mass within target/partition/domain. Offline pure-fit
  source-ID fallback is caller-screened and supplies no UI training eligibility.
- [ ] Final source/schema signatures, reason enums, adapters/group review UI,
  duplicate hints, unlock/version/F14/native and contrast-span acceptance remain
  pending. Next: reconcile owner delivery and settled-code fresh proof before enablement.

Real held-out validity, calibration, actual weights and GPU acceptance remain
pending. Agent quota recovery allows continuation; it is not fulfillment evidence.

Latest narrow canonicalization subfix is accepted using Pauli's 68 targeted pass,
Lorentz's independent 51 evaluator/4.258s/0 skips and eight stable repro checks
with unchanged module hashes, plus Mill/James no-blocker static reviews. James
did not run tests. This does not accept P3 baselines/ablation/real validity.
Evaluator report integration with fit['training_groups'] needs a final rerun;
main session 37713 has no terminal result yet. Group owner checkpoint 92 existing
(91.197s) and 18 new (7.916s), 0 skips each, is intermediate. Final schema/backup
tests and fresh group verification/quality/anti remain underway; keep groups
PROPOSED/unaccepted for handoff until exact final source/tests/proof arrive.

### Stable backend delivery — implemented, final group acceptance pending

The group fields now exist in stable source/schema; preceding PROPOSED code
status is superseded by implemented-awaiting-acceptance. Actual optional set
fields are group_id:string|null=null and group_reviewed:boolean=false; all
returned feedback records contain both, with legacy normalized to null/false
without stored-payload backfill. Reviewed=true requires a nonblank 1–128 code
point group ID without NUL/surrogates. Health declares rev4/34 methods and
features.reviewed_event_groups=true. Rank adds training_groups with min3;
insufficient_training_groups replaces the old source-count gate reason, while
training_sources counts actual informative source IDs separately.

Owner final group20 + schema19 = 39/34.034s/0 skips, prior existing92/91.197s
separate. Encrypted reviewed/exact legacy payload backup/DDL/no-backfill proof
is in the new group test file; backup code is unchanged. Main full and three
fresh group reviews are underway. Wait for accepted backend contract delivery;
frontend adapters/group-review UI/unlock/version/F14/native still need owner
verification. Exact-text duplicate hint is TODO.

Synthetic offline P3 tool provision is narrowly accepted after owner final51
(4.695s) and main settled51 (4.139s), 0 skips each; authoritative
fit['training_groups'] report integration and sources/groups regression passed.
Whole P3, baselines/ablation and real predictive validity remain pending.

Current implemented group weighting: G informative groups, n_g informative events
in group g for this target/partition/domain; event loss weight=1/(G*n_g), group
total=1/G. The objective is the mean of group means plus (L2/2)||w||². One group
has one weight unit before group averaging, not normalized mass=1. Neither
training_sources nor training_groups certifies real sample independence.

## Oct 5 final rev4 backend synthetic contract

Main483/121.151s/OK/0 skips accepts final groups/canonicalization/report integration.
Lagrange focused51 (20 group/19 schema/12 backup)/19.543s plus independent3/7.380s,
0 skips; legacy bytes stable across two restarts, axes isolated, independent
scalar group means matched, network0/temp DB only, 62 stable hashes. Meitner8/
7.990s, 34-method parity, 12 valid axes; Kant9 pure plus8 guards, no blockers.
See [exact proof commands](api.md#oct-5-final-rev4-backend-synthetic-contract).

Frontend next: negotiate rev4/group capability, explicitly review per-event
membership, show separate group/source counts and feedback/input activity,
acquire fresh guards and obtain independent consent/labels/impacts. No inferred
membership/review/consent or automatic write retry. Group UI, unlock/version/F14
adapters and native acceptance remain pending. Model next: contrast-span refusal;
duplicate hints, P2/P3 overall, baselines/ablation/calibration, weights, GPU and
real held-out validity remain pending. Synthetic backend delivery is not UI acceptance.

## Oct 6 current rev5 handoff and acceptance scope

Negotiate health.contract_revision=5, the required methods and
features.preference_contrast_guard=true alongside reviewed_event_groups=true.
Public preference_rank includes required contrast_rank (integer0–8) and
contrast_basis (exactly rank rows, eight finite [-1,1] coordinates per row).
Column order is value.autonomy, value.fairness, value.care, value.truth,
value.security, value.growth, value.achievement, value.connection; never derive
it from baseline JSON or 13-rule catalog iteration. Every query option pair
must pass span membership; unsupported_option_features retains precedence,
otherwise unidentified_option_contrasts returns abstain/ranked=[].
Display returned counts, snapshot tokens and separate input/feedback activity
without presenting span/rank/weights as confidence or calibrated behavior.

Rank/membership/orthogonality tolerances1e-10/1e-12/1e-12 are engineering policy;
same-span utility, parameter magnitudes, convex hull and real validity remain
unverified. The evaluator report exposes scalar contrast_rank only, without raw
basis/weights/private internal variables; public preference_rank still returns
its contrast_basis and learned weights. This scalar-only rule is for the P3
evaluator report. Legacy `rank` retains its value-alignment result shape without
contrast metadata.
Huge integer impacts are rejected with controlled ValueError/API INVALID_ARGUMENT
after bounds-before-isfinite validation, without changing state or killing the
process. Exact [main576 and three final reviews](api.md#oct-6-final-rev5-backend-synthetic-contract)
accept only the backend synthetic contract; dated rev4/483 proof above is historical.

Source t/t still updates translator/13-rule model/memories without choice groups;
groups gate only preference. Fit is temporary/read-time with no DB/weight writes
or encoder training; set/get do not fit. Frontend owner still needs independent
adapters, group-review/consent/label/impact/guards, unlock/private-cache/version/F14
and native acceptance. General correction/generic replay, P2/P3 overall, actual
weights, GPU, online CI and real validity remain pending; no automatic write retry.
