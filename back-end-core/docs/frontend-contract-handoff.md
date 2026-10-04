# Frontend contract handoff: v1 — revision 3 pending main acceptance

> 2026-10-04: current source declares 34 methods/revision 3. This handoff records
> working signatures; Oct 2 revision 2/30 methods remains the accepted historical
> baseline. New hybrid full-suite verification is pending. Once main provides final
> 34-method acceptance, backend availability can be handed off; frontend adapter,
> UI, unlock/cache and native validation still require their owner's evidence.

Oct 2 backend exposed 30 accepted methods; current source declares 34; [api.md](api.md) and [api.schema.json](api.schema.json)
document params/results (new schema conformance pending main). Detect negotiated
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
/tmp/alpha-verify-20261002/bin/python -m unittest tests.test_schema_contract tests.test_api tests.test_access_api tests.test_tracing -q
```

All fixtures use temporary databases. Main runs final full discovery after worker
completion. Full test environments install `.[test-schema,security]` from back-end-core;
system PyNaCl must not mask missing CI dependencies. Online CI was not run here.
Readiness/offline evaluations remain separate authorized read-only
contracts; real held-out validity evidence and frontend/native acceptance remain
pending. F14 development is authorized; working backend signatures are below. No private DB, Git, PNG, frontend or shared TODO edits are
part of this integration handoff.

## F14 and semantic extension handoff (working revision 3)

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

Feedback record model_active is preference eligibility (approved + consent +
matching version/body/partition + feedback current epoch); input model_active is
rule-fit participation. Display these independently. Reset feedback exclusion is
lifted by explicit guarded feedback save; rule re-review does not reactivate it.
A deliberate current-epoch save may be eligible even when the old rule fit is inactive.

preference_rank temporarily CPU-fits on the approved eligible read-only snapshot
then ranks; it writes no DB or weights and does not train the encoder. set/get do
not fit. Show returned model_epoch/input_revision and handle concurrent stale
results; no persistent fit endpoint exists. Report provisional/abstain,
not_calibrated=true; model_probability is uncalibrated, not actual behavior likelihood.

memory_search_semantic exposes semantic/cosine or explicit lexical_fallback/none
with null score when no encoder is configured. Configured encoder failure is
MODEL_UNAVAILABLE, not fallback. Expose pool_truncated and encoded_text_truncated;
similarity is evidence relevance, not truth. Lock/reconnect clears all new private
feedback/rank/search caches and queued operations too.

Oct 4 frontend's root communication entry remains its owner's historical statement.
Backend final 34-method proof is not yet supplied here. Once supplied, notify the
frontend that backend acceptance has advanced, while keeping adapter updates,
unlock/version/F14 UI and native acceptance pending until separately verified.
The user answered "不管" to the historical privacy note: no action. The frontend
entry is preserved; the document audit does not touch files or Git history.

Preference backend acceptance remains pending: memory/convergence/numeric fixes
have Oct 5 final worker proof, awaiting main/fresh acceptance; production groups
and contrast extrapolation are still open. Historical 51-test semantic acceptance
is synthetic/mocked and does not establish real encoder weights or semantic quality.

Current continuation: Goodall owns digest-only screening, convergence/near-tie
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

The user selected explicit frontend event-group IDs reviewed by the user.
`group_id` is PROPOSED; do not send it to the current closed API or treat it as
an accepted result field. All materials in the same group will share one total
training loss mass within each separate target/partition/domain fit. Backend
provides exact-text duplicate hints only; it never infers same-event membership
for distinct texts, assigns groups or supplies user review.

- [ ] Next-phase fresh owner, after Goodall's base fixes: implement field/review
  gate and group weighting. Legacy/unknown-group feedback must be excluded until
  reviewed under that future gate; this exclusion is not implemented now.
- [ ] Frontend owner/main: settle explicit group selection/review, feedback update
  and legacy review contracts; keep unresolved fields PROPOSED and verify UI/
  adapter/native behavior separately. No automatic grouping or endorsement.

Frozen evaluator group isolation is a separate offline contract and does not
prove this online gate or identifiable contrast-span acceptance.
