# Backend TODO

> 2026-10-06 (Asia/Taipei): main goal active; schema_version=1 /
> contract_revision=5 / 34 methods, features.preference_contrast_guard=true.
> Main session80693 exit0: 576/59.590s/OK/0 skips; all three final reviews found
> no blockers. Main accepts only the rev5 backend synthetic contract. Numeric
> repair, fixed column order and final verification are archived in the
> [Oct 6 log](../../frontback-log.md#oct-6-final-rev5-backend-synthetic-contract).
> P2/P3 overall, frontend/native, general correction/generic replay, actual weights
> and real validity remain pending. Dated historical pending/PROPOSED statements
> are superseded for current status by the [Oct 6 queue](#oct-6-current-rev5-delivery-and-remaining-queue).
> Completed task lines use //// - [x]; partial categories stay [ ] with notes.

## Implemented application interface — Oct 2 accepted baseline

- `core/brain.py`: unified model/source/candidate entry point; canonical queries
  exclude legacy store-only records and filter partitions before limiting results.
- `core/api.py`: persistent local JSON-lines process, schema version 1, strict
  request fields and error envelope; EOF ends the process.
- `docs/api.md` and `docs/api.schema.json`: frontend integration contract.
- Pending interpretation feedback: `correction_set` / `correction_history`,
  append-only revision checks within the current source version, exact author
  evidence, and frozen fit provenance. F6 edit/delete clear that source's history.
  Two consistent agreed full-clause labels can teach exact reuse within one
  partition/kind/separator context; conflicts abstain. Rejection/revocation
  cannot supply future teaching support. This is not semantic generalization.
- Request schema includes all 30 methods and correction items (schema_version=1,
  contract_revision=2). All 30 method
  result bodies are typed under `$defs.results.$defs`, with common translation,
  interpretation, approval, input, effect, state and candidate definitions.
  Select the body validator using the retained request method; envelope-only
  validation is insufficient. ID/span equality still needs runtime checks.
- Unicode text: surrogate code points are rejected before submit storage;
  CRLF and supplementary characters preserve source offsets and round-trip text.
- `model/evaluation.py`: read-only snapshot evaluation, separate actual/endorsed
  labels, domain metrics, coverage/abstention and static value-parameter ablations.
  Shared ranking logic preserves live API behavior. Synthetic fixture tests
  prove tool behavior only; no real-user predictive validation has occurred.
- Fresh whole-source double approval automatically publishes authored candidate
  memories for the current source/version. Legacy pending/rejected candidates
  remain untouched by migration/startup/frozen reapproval. UI remains outside
  the backend implementation.
- `src-tauri`: fixed `brain_call` host, main/local ACL, serialized bounded queue,
  total timeout, response validation, stderr draining and child cleanup. Genuine
  Python and Tauri MockRuntime command/ACL tests exist. React Transport is wired;
  frontend reports browser/real-Python and Xvfb native smoke acceptance. Native
  Xvfb DOM F6/paging, second-process persistence and EOF/invalid-response/timeout
  faults passed. Administrative model-reset/reconnect and physical input/GPU
  acceptance remain pending.
  Linux x86_64 portable production release/runtime passed (glibc >= 2.34,
  nonstatic GTK dependencies); main independently verified relocation/security
  acceptance and artifact hashes. No macOS/Windows acceptance is claimed.
- F1-F4/F7: dual whole-input approval, explicit exclamation setting both true
  atomically, repeated decisions/removal/frozen-fit restoration, decision audit
  and inactive preview. Legacy metadata migration does not re-fit existing data.
  Immediate can change only through F6 editing; no text-inferred authorization.
- F5: get/list summaries preserve Unicode code points; input_list keeps its
  array shape. New input_page returns bounded items/total/cursor/revision.
  Database-bound cursors reject altered filters or stale input generations;
  each page uses one read snapshot. edited_at records the last edit, initially null.
- F6: inactive-source edit clears its old raw text and all source-specific
  histories/labels/fits/candidates, then resets confirmation without training.
  Any-state delete atomically removes active support and all that source's records;
  no tombstone, no external-file/backup cleanup and no password/secure-erasure claim.
  Other sources' effects/frozen contexts remain untouched. Additive metadata
  migration and monotonic cursor generations are tested; an internal ever-fitted
  flag survives edits for held-out exclusion and disappears on deletion.
  Twenty-one synthetic governance tests cover rollback, concurrency, every
  status, teaching support, external-file isolation, migration and real process IO.
- U+0000 anywhere in new submit/edit text is INVALID_ARGUMENT before writes.
  Legacy text is preserved, not silently normalized by migration.
- Base assertion guards withhold questions/quotation/code/Markdown quotation,
  reported/hypothetical frames, value hedges and ambiguous negation/comparison.
  New interpretation contexts record bounded reason/evidence diagnostics and
  policy version; explicit corrections can override, old fits remain frozen.
  Fourteen synthetic coverage tests exist (`evidence-policy.md`); representative
  real-material coverage and predictive validation are still unproven.
- `translator.evaluation` now measures base extraction against independent
  human labels, explicit parameter scopes, source groups and development/held-out
  splits; no database, personal corrections or training. Metrics distinguish
  direction from evidence-window errors; optional details never include raw
  text. Fourteen tool tests exist (`translator-evaluation.md`). Synthetic
  examples regress a v1 indirect-other-subject false positive now fixed in v2;
  they are development cases, not real-user or held-out validation.
- Assertion-guards-v2 adds bounded familiar-actor value ownership and explicit
  self-viewpoint scopes, preserving own concern for others and own emotion/intent.
  Nine synthetic tests cover these boundaries, correction overrides and frozen
  v1 restoration. Schema accepts v1/v2 without relabelling historical fits;
  arbitrary names, relative clauses and complex mixed ownership remain gaps.
- Optional `test-schema` extra validates the schema itself, live examples for
  all 30 request/response envelopes and method bodies, negative shapes,
  lifecycle/ranking/candidate variants, migration and real JSON-lines output.
  Synthetic tests use temporary databases; without the extra they explicitly
  skip. Backend CI configuration requires the validator and pins the tokenizer
  and Actions references. Local Python 3.14 passes; online CI and its Python 3.10
  job have not been executed yet. Schema shapes are not model-validity evidence.

## Current scope note (2026-10-01)

MMPI report import/analysis is temporarily outside the current scope at the
user's request, with no active or deferred implementation requirement. Historical
conversation is retained; bringing it back requires a separate user request.

## Model v1 decisions recorded

- Scope: local backend model for daily life, study, interpersonal events, and
  user-supplied philosophical statements/ideas. No frontend or sphere work.
- The frontend will have three separate input pages: rational, emotional, and
  user-named "crazy". A source belongs to one page/state. This last name is a
  user-facing state label, not a clinical diagnosis.
- Two frontend booleans apply to one whole input: immediate and confirm. Both
  true permit fitting; explicit exclamation sets both true (updated user decision).
  Agreement on rational material updates the rational partition; agreement on
  emotional or "crazy" material updates only its corresponding partition,
  without endorsing the recorded decision as a rational ideal.
- Preserve raw input even when the boolean is false, but do not use a rejected
  interpretation to fit the endorsed-self model. A correction path is needed.
- Keep an untouched original model snapshot with all numeric parameters at 0.
  Zero must also carry a separate "unobserved" marker so absence of evidence
  is not mistaken for a measured neutral preference. Only an active copy may
  learn from approved material; all updates stay local.
- The translator itself learns personal vocabulary from agreed material.
  Explicit correction labels now teach scoped exact-clause rules separately.
- Every parameter change needs an exact evidence reference and a reversible
  change record. The frontend can later consume these effects.

## Frontend feedback contract to implement later

- Provide three source-entry pages (rational, emotional, "crazy"). Return a
  stable `source_id`, page/state, and immediate/confirm for each whole input.
  Connect the implemented dual-approval API and render actual submit effects
  when exclamation skips the second confirmation. See `desktop-bridge.md`.
- Provide separate feedback for whether a past *choice* is still endorsed in
  hindsight. This is distinct from confirming that the source is authentic;
  current flat payload is documented in api.md and hybrid-learning-plan.md;
  final backend/collection/frontend acceptance remains pending. It does not infer labels.
- Show the source, any inferred parameter changes, and the evidence behind
  them; permit correction without silently rewriting history.

## Pending decisions for model v1

- Typed event/intent/tone/candidate retain/suppress corrections are implemented
  for exact authored evidence. correction_reopen/review_version/replay_preview/
  replay_reopen use explicit source-version, global input-revision and epoch
  guards, withdraw selected contributions and require renewed double consent.
  Other fits remain frozen; selected dependency replay is not a general causal
  graph, general semantic relabelling or ML.
- Evaluate whether candidate parameters improve predictions using future
  retrospectively endorsed choice labels; remove ineffective parameters.
- F14 now explicitly separates actual_choice_id/endorsed_choice_id/consent;
  current exploratory preference abstention thresholds await final synthetic
  acceptance and independent real validity evidence.

## Accepted baseline and remaining queue (2026-10-02; annotated Oct 4)

//// - [x] Terminal telemetry: CLI/API default-on stderr traces and bounded/validated
  Rust host forwarding; no raw evidence, no response/schema changes. Commit-only
  param/fit reporting, receipt vs save/fit distinction, rollback and broken-sink
  checks. Nine synthetic Python tests and one Rust filter/framing test added.
  See terminal-tracing.md; no automatic on-disk logger or private-text logging.
//// - [x] Frontend reports browser real-Python acceptance for F6, NUL and model
  epoch/activity metadata with deliberate old-source re-enlistment. Verified
  prior adapter/record wiring read-only; Xvfb DOM F6 passed. Native administrative/
  physical acceptance and verification of latest frontend changes remain pending.
//// - [x] Model-only reset: confirmed local CLI with exact existing absolute DB
  target, epoch/revision checks and atomic zeroing. Translator, approvals and
  history preserved; old fits excluded until explicit re-review. Twelve synthetic
  reset tests plus one post-reset result-schema test. `model-reset.md` is the contract.
//// - [x] Frontend browser activation: consume model_active/model_epoch, distinguish
  approved history from current-model participation, and deliberately re-enlist
  old sources. Latest ledger reports cache/in-flight invalidation on reconnect
  and browser acceptance; native administrative model-reset/reconnect acceptance remains pending.
  No live reset endpoint/UI yet.
//// - [x] Native DOM EOF/invalid-response/timeout faults: main's final command exited 0;
  summary and all three reports passed in `/tmp/alpha-native-faults-20261002`.
  Each verifies startup failure/explicit reconnect and ambiguous submit/explicit read
  recovering exactly one source; fixture logs show exactly one submit and
  no_write_autoretry=true. Together with real/persistence, five native DOM scenarios passed.
  Earlier process-inspection/unselected-partition failures were harness failures,
  not product failures; final main verification supersedes their pending status.
- [ ] Native administrative model-reset/reconnect and physical input/GPU acceptance.
  Xvfb DOM F6/paging and second-process persistence passed;
  browser and Xvfb evidence do not establish physical acceptance.
//// - [x] P0: F1-F4/F7 dual approval, exclamation, repeated review, decision audit,
  metadata migration and expanded preview implemented and regression-tested.
//// - [x] P0: F5 summaries and input_page pagination implemented and regression-tested.
//// - [x] P0: F6 source editing/deletion and NUL validation implemented; final contract
  and frontend activation/acceptance steps in `../../front-back-communicate.md`.
//// - [x] P0: protected backup/recovery and explicit selected dependency replay
  delivered; historical effects, unselected frozen fits and reset exclusions
  remain preserved. General downstream causal replay is not implemented.
//// - [x] P0 / F13: AccessSession gates all private API reads/writes with LOCKED;
  malformed unlock revokes authorization and private caches. CLI/evaluation
  paths retain/recheck sessions. Argon2id gate and XChaCha20-Poly1305 backup/
  fresh-target recovery are implemented and verified. Frontend unlock UI remains
  pending. The gate covers raw text, excerpts, evidence, histories and writes.
  The current SQLite database remains plaintext; whole-database encryption is
  outside this round. The gate is not protection from direct same-OS-user file
  access. Recovery must validate into an explicit fresh target, never silently
  overwrite the live database.
- [ ] P1: native administrative model-reset/reconnect acceptance and subsequent
  contract migrations remain. Linux portable Python/backend/jieba/security runtime
  and production release passed; Xvfb DOM F6/paging/persistence and all three
  EOF/invalid-response/timeout fault cases passed. F13 frontend UI remains pending.
  Host transport/lifecycle/timeout/ACL code is implemented (`desktop-bridge.md`),
  with frontend wiring and Xvfb basic acceptance reported by the frontend.
//// - [x] P1: type all 30 method result bodies and common records, and add local
  conformance tests covering lifecycle branches, negative shapes and serialized
  output. Backend CI requires the validator; runtime dependencies are unchanged.
- [ ] P1: verify online backend CI and its Python 3.10 matrix job; local
  Python 3.14 verification does not prove the hosted/older-interpreter jobs.
- [ ] P1: evaluate cluttered diary/chat, quotation, negation and philosophy
  coverage using corrections; add local NLP only where evidence justifies it.
  Base guards and synthetic regression examples are implemented; real held-out
  validation and broader subject/irony/indirect-language handling remain.
  The scoped/grouped read-only extraction benchmark now exists. V2 fixes the
  known familiar-actor value leak; next collect independently labelled
  representative cases; do not equate tool tests with real coverage validation.
  No private held-out material is available this round: deliver local collection
  templates/readiness tools only, with independent labels and leakage checks.
  Template/readiness/evaluation tool delivery is verified; real coverage acceptance
  remains an external prerequisite, not a promise to collect private data now.
- [ ] P1: held-out choice labels and parameter ablations before supervised ML;
  the offline evaluation/ablation tool is implemented (`evaluation.md`), but
  real labels, split design and parameter decisions remain. This round supplies
  templates/tools only; no real predictive-validity claim can be accepted.
  Factual choices and retrospective endorsement are different labels; no frontend contract
  for the new F14 UI or automatic parameter pruning is accepted; working F14
  backend signatures are now documented, final verification pending.
//// - [x] Implemented: automatically publish extracted authored candidate
  memories when the current source/version has immediate=true and confirm=true;
  preserve legacy pending/rejected statuses without migration auto-publication.
//// - [x] Implemented: reviewed-source typed revisions withdraw
  current contributions and require renewed double consent before fitting;
  version-bound revisions and explicit replay must preserve old effect numbers,
  frozen history and model-reset exclusions. F6 text editing is a separate path.
- [ ] Frontend unlock/private-cache and guarded version-consent UI; latest
  concurrent frontend changes have not all been verified. See frontend-contract-handoff.md.
- [ ] F6 future content-revision guard: source_version resets to 0 after editing,
  leaving queued unversioned review ambiguity; handoff documents cache/queue cleanup.
- [ ] Typed corrections: assess per-item retranslation performance.
- [ ] F14 is authorized since Oct 3: current flat feedback/preferences implementation
  and contract require final main verification, frontend labels/consent/impacts UI,
  and separate native acceptance. Sphere v2 remains a later frontend scope.

Completed statuses above reflect supplied worker evidence and main's independent
verification. Main owns final full-suite counts and remaining native results;
do not interpret synthetic tests/templates as real coverage or predictive validity.

## Hybrid queue — resumed 2026-10-04 (overall acceptance pending)

//// - [x] Tested security compatibility subtask: exact optional brain_choice_feedback
  table/index reference in backup.validate_database, preserving unknown/tampered
  DDL rejection. Backup owner reports tests.test_hybrid_backup 12/0 skips and
  security/access/evalaccess 54/0 skips; main reviewed the six-line implementation.
  This marks only this supplied owner-tested subtask, not full hybrid acceptance.
- [ ] P0 final 34-method schema/allowlist/result/health and protected setup/access/
  backup/restore full compatibility verification on final code. Main independently
  passed hybrid/schema/access 39/0 skips (27.496s); workers are still adding checks.
- [ ] P1 final semantic offline-protection and lifecycle/no-cache/no-network
  synthetic evidence after last edits. Earlier semantic 35/preferences 28 pass
  preceded current offline protection changes; actual weights/zero-network
  runtime/CPU performance and real semantic quality are unverified.
- [ ] P2 final F14/preferences lifecycle, consent, source/current-content/feedback
  epoch gates, temporary CPU fit/no DB writes/no encoder training, Reset explicit
  guarded feedback re-enlistment and full-suite main verification. Feedback
  model_active differs from rule inputRecord.model_active.
- [ ] P3 new grouped/time preference evaluator/templates and final synthetic
  acceptance; independent real actual/endorsed labels, coverage/prediction and
  parameter decisions remain unverified.
- [ ] P4 frontend 34-method adapter update, unlock/private-cache/version/F14 UI,
  user-reviewed impacts, administrative Reset/reconnect/native, offline encoder
  packaging/resources, physical input/GPU and online CI/Python 3.10 evidence.

Main evidence commands supplied (from back-end-core; temporary synthetic fixtures):

```sh
/tmp/alpha-verify-20261004.tPaapz/bin/python -m unittest tests.test_semantic_encoder tests.test_preferences -q
TMPDIR=/tmp/alpha-verify-20261004.tPaapz /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest tests.test_hybrid_api tests.test_schema_contract tests.test_access_api -q
```

First: semantic 35/preferences 28, no skips, before final offline edits. Second:
main 39/no skips. Backup owner test names/results above are supplied evidence;
exact owner command/log and final discovery counts remain with main, not invented
here. No new hybrid phase completion is inferred from these intermediate passes.
Oct 4 main get_goal active replaces current paused status; historical pause remains
in checkpoint. Personal hybrid scope has no digital-self or real validity claim.

## Preference acceptance blockers — Oct 4 review (no implementation in audit)

These are Mencius review findings supplied by main, not independently reproduced
by the document worker. P2 remains unaccepted even if regression suites pass.

- [ ] Bound ranking memory: cached whole source bodies for up to 1000 IDs can
  approach 1GB; supplied 40 x 1m ASCII case is about 40MB. Use budgeted provenance/
  digest screening without retaining all bodies; verify peak memory and unchanged
  eligibility/ranking at input limits.
- [ ] Define fit convergence/error bounds and abstain on unstable near ties:
  fixed 400 iterations reversed the winner versus 4000 iterations/Newton in the
  supplied example. Compare loss/gradient, ordering/permutations and a converged
  reference; a fixed-step test pass does not establish convergence.
- [ ] Reject enormous integer weights safely before float conversion can raise
  OverflowError; verify controlled numeric/type error handling, no leaked
  exception, and process survival at boundary values.
- [ ] Define provenance and copy/paraphrase/event groups for training eligibility
  and held-out isolation. Three distinct IDs do not prove independent samples;
  prevent duplicated groups from inflating support or crossing splits.
- [ ] Check identifiable contrast span and extrapolation: individual used_features
  coverage does not establish that new option contrasts lie in the learned
  subspace. Define abstention for collinear/unidentified new directions and
  validate controlled synthetic counterexamples.

Historical API-owner targeted result: 151 distinct tests passed; its exact
command was not supplied here. The document audit did not implement P3;
the current continuation authorizes Zeno's separate preference evaluator work.
Historical privacy note: user answered "不管"; no action.

//// - [x] Historical main-verified synthetic regression subtask: from back-end-core,
  `TMPDIR=/tmp/alpha-verify-20261004.tPaapz HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest discover -s tests -q`
  passed 396 tests in 134.672s, 0 skips. Subsequent same-environment
  `-m unittest tests.test_semantic_encoder -q` passed 51 in 1.142s, 0 skips;
  discovery then contained 398, with the last two semantic tests covered by that
  separate run. This is not a single 398-test run or proof for subsequent edits.
//// - [x] Historical main-verified backup compatibility subtask:
  `tests.test_hybrid_backup` passed 12 in 11.220s, 0 skips. Semantic evidence uses
  synthetic exports/mocks, without real encoder weights or validity claims.

## Current implementation continuation — awaiting main's new proof

Historical Oct 4 continuation; scoped deliveries are now checked below, with
final Oct 5 evidence at the end. Broad phases remain open.

//// - [x] Goodall: digest-only source screening cache, converged pure-Python solver
  and near-tie abstention, and controlled ValueError for huge integer weights;
  final scoped proof is the historical 411 acceptance recorded below.
//// - [x] Limited synthetic evaluator provision: `model/preference_evaluation.py`, its tests, and
  `docs/preference-evaluation.md` / `docs/preference-evaluation.example.json`.
  The documentation integrator does not edit these four owner files. Describe
  the frozen-manifest/shared-production-fit/held-out-predict/scoring workflow
  now inspected and verified; see final Oct 5 milestone. Baselines/ablation/real
  validity and whole P3 are not completed by this tool delivery.
- [ ] Main: final verification commands/results after all new changes, followed
  by fresh-agent final review. Check only verified automated subtasks with
  `//// - [x]`; P2/P3 and real validity remain pending.

Source-group/provenance independence and identifiable contrast span remain live
acceptance blockers unless main supplies implementation and proof. Offline
evaluator group isolation alone does not resolve production eligibility.

## Confirmed event-group decision — implementation pending (2026-10-05)

Historical proposal, superseded by current rev4 and final proof below. Pending
field/handoff wording in the dated narrative is not the current backend contract.

DECISION: use explicit frontend event-group IDs reviewed by the user; draft
`group_id` remains PROPOSED until main settles the contract. All materials in one
group contribute one total training loss mass within each separate target/
partition/domain fit. Backend may hint at exact-text duplicates only; it must not
infer that distinct texts describe the same event, assign groups or grant review.

//// - [x] IMPLEMENTATION, next phase with a fresh owner after Goodall's base fixes:
  group field and explicit review gate; aggregate all same-group source/events
  into one total training mass. Under that future gate, existing feedback with
  legacy/unknown groups is excluded until the user reviews its group. Current
  feedback now enforces this policy without automatic backfill/endorsement.
  Completed narrowly by main483 and all three fresh reviews; see final milestone.
- [ ] Frontend contract and acceptance: explicit group input/review, guarded
  updates and legacy review workflow; unresolved field names remain PROPOSED.
  Do not declare schema/API integration or online provenance acceptance complete.

This confirmed decision does not resolve contrast-subspace extrapolation and
does not turn offline evaluator group isolation into production enforcement.

## Oct 5 intermediate preference proof — no new completion marks

Main supplied preferences 36 pass, 22.441s, 0 skips, before the final added tests;
the exact command is not supplied here. Independent seed804 asserted winner=b
with margin `1.0117349352838784e-05` after the patch, versus winner=a at the old
400-step setting. This is a synthetic regression comparison, not real validity.
Final worker proof, fresh reviews and main's final full-suite must all arrive
before any new preference/evaluator subtask is marked `//// - [x]`.

## Oct 5 final Goodall worker proof — acceptance still pending

Main supplied final preferences 41 + hybrid 21 + schema 18 = 80 tests,
128.728s, 0 skips; exact command awaits main. The only new schema reason is
fit_not_converged; no online group fields were added. Current source uses
64 Newton steps/32 backtracks, L2=0.1, gradient infinity norm <=1e-11 and
tie tolerance 1e-8, with finite checks and residual-guarded roundoff slack.
Dense 1000-event/8-option CPU benchmark: 2.144934741 CPU seconds,
final gradient 2.609e-17. Memory/measurement limits are recorded in
[hybrid plan](hybrid-learning-plan.md#oct-5-final-worker-proof--mainfresh-acceptance-pending).
Independent 92-test verification (including 12 backup) and fresh antipattern/
quality reviews are running; no result or new completion is inferred.

Main's independent base-backend full discovery has also started; exact count/
time/command await main. P3 tests/docs/example are not ready, so this must be
reported as scoped base full proof, not final evaluator or whole-hybrid proof.

Fresh reviews supplied by main (Oct 5): antipattern no findings, 17 pure tests/
parity pass; jsonschema was unavailable only in that isolated review environment,
while the full environment has the validator. Quality no blockers, 41 preferences
pass; uneven source mass 7/1/1 reference difference 1.18e-12, seed804 gradient
3.26e-15/max weight difference 1.89e-12, Cholesky residual 1.39e-17. A separate
dense 1000-event/8-option observation was 1.48 CPU seconds, not API latency.
Main 92-test and base full 411-test runs remain unfinished. Once both pass,
mark only three limited fixes (digest cache, convergence/near ties, huge integer
weights) `//// - [x]`; source groups, contrast span and whole P2/P3 remain pending.

Oct 5 evaluator owner reports 47 tests, but tests/docs/example were created at
the wrong repository-root paths. Main directed only that owner to correct its
new files with apply_patch into back-end-core/tests/test_preference_evaluation.py,
docs/preference-evaluation.md and docs/preference-evaluation.example.json.
Do not link incorrect root artifacts or count these 47 in base full 411.
Correct-path command (from back-end-core), new proof and fresh tool reviews
must follow the correction; delivery and P3 acceptance remain unchecked.

## Oct 5 scoped base acceptance — excludes P3

Main independently ran from back-end-core:

```sh
TMPDIR=/tmp/alpha-verify-20261004.tPaapz HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest discover -s tests -q
```

411 tests, 170.066s, OK, 0 skips, before P3 test relocation; not evaluator or whole
hybrid proof. FreshVerifier 92 (41 preferences/21 hybrid/18 schema/12 backup),
85.576s, no failures/skips; fresh antipattern 17 pure and quality 41 found no
blockers. Supplemental main synthetic live-API check verifies fit_not_converged
against full result schema with 0 SQL writes/0 encoder calls and unchanged source
hashes; no user live DB was used. These results supersede the running statuses.

//// - [x] Limited fix: digest-only source screening and training-only record
  cache, with synthetic 40-source/1m-code-point/1000-event tracemalloc proof.
  Native RSS and real request latency are outside this completion.
//// - [x] Limited fix: converged pure-Python solver/near-tie abstention,
  fit_not_converged schema reason, independent residual/reference/seed804 checks
  and supplemental no-write/no-encoder-call failure path.
//// - [x] Limited fix: huge integer fitted weights safely rejected with ValueError
  before float conversion, with synthetic preference/hybrid/schema regression.

Production event-group implementation, contrast span, entire P2/P3, real validity
and frontend/native remain pending. Correct-path [evaluator docs](preference-evaluation.md)
and [synthetic manifest](preference-evaluation.example.json) now exist; P3 final
proof and fresh tool reviews must follow owner path correction.

## Oct 5 recovery — fresh rev3 baseline, subsequent changes pending

Historical recovery sequence: pending statuses in the following dated delivery
records are superseded by the final accepted milestone. Counts remain scoped.

//// - [x] Scoped rev3 baseline full regression: main supplied the terminal result
  from `back-end-core` for
  `TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q`:
  458 tests, 181.564s, OK, 0 skips. This predates the evaluator zero/numeric-impact
  canonicalization fix and new rev4 group edits; it does not accept either change
  or the whole P2/P3. Existing 411/170.066s scoped proof stays historical.

Old main job 97510 has no recovered terminal proof; UnknownProcess and the lost
old temporary environment cannot prove success. Fresh job 9839 supplies the
result above. Its temporary environment had Python 3.14.7, jsonschema 4.26.0
and inherited PyNaCl, not a permanent runtime or portable-install acceptance.
The recovered quota limit is no longer an agent blocker; the broad goal remains
active. Existing front Oct 4 comments and other owners' changes are preserved.

- [ ] P3 tool fix acceptance: Lorentz's recovered 47-test review found omitted
  zero/equivalent numeric impacts could evade duplicate identity and inflate
  metrics. Pauli supplied 68 pass = 51 evaluator (47 old + 4 new) + 17 pure
  using the Oct 5 temporary environment, before concurrent partial group edits.
  The final numeric-copy patch has targeted proof, but independent Lorentz
  re-review and fresh antipattern/code-quality reviews are still underway.
  Main's overlapping 51-test run encountered transient MIN_SOURCES NameError
  during group WIP; it is not acceptance. Await settled-code fresh verification;
  no final P3 completion mark.
- [ ] Rev4 online groups: Descartes began writes after the baseline terminal.
  Optional nullable `group_id`, `group_reviewed: bool=false`, normalized legacy
  unknown/unreviewed exclusion and the reviewed save path remain PROPOSED for
  handoff until final source/schema and proof. Preserve exact legacy stored
  payloads; no automatic review. Consent, double approval, version/digest/epoch
  and group review must all gate online eligibility. Scope is per feedback event.
- [ ] Group weighting/counts: one total loss mass per reviewed group; at least
  3 informative training_groups, with actual source IDs counted separately as
  training_sources. Pure offline legacy callers may screen their own provenance
  and fall back to source IDs; that fallback grants no online/UI eligibility.
- [ ] Exact-text duplicate hints remain TODO; never infer distinct texts as the
  same event. Contrast span, frontend adapters/review UI/native, real held-out
  validity, calibration, actual weights and physical GPU acceptance remain open.
- [ ] Next safe action: inspect final evaluator/group signatures and reason
  statuses, integrate only actual delivered behavior, then append new main/fresh
  verification with counts/commands/scope. Only independently verified subtasks
  receive `//// - [x]`; no wholesale historical rewrite or broad-goal completion.

Portable synthetic CLI examples are in [README](../README.md#oct-5-verification-recovery-and-next-integration)
and the [hybrid plan](hybrid-learning-plan.md#oct-5-recovery--baseline-proof-and-pending-integration).
Their normal `python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json`
invocation runs from `back-end-core`; a recorded `/tmp` test interpreter is not
a permanent execution requirement.

### Canonicalization subfix accepted; report/group integration still pending

//// - [x] Narrow numeric-copy canonicalization subfix: Pauli supplied 68 pass
  (51 evaluator = 47 old + 4 new, plus 17 pure) before group WIP. Independent
  Lorentz reran 51 evaluator tests in 4.258s, 0 skips, with unchanged module
  hashes; eight actual/endorsed int/float/0/0.0/-0.0 repro checks kept held-out
  and macro metrics at 0.5, development records at 4, and fits/predictions
  identical. Mill's fresh static quality review found no blocker. James' fresh
  antipattern static review found no blocker, parsing 2 ASTs and inspecting 51
  test definitions; James did not provide runtime evidence. This completion is
  limited to canonicalization and does not accept whole P3 or group integration.

- [ ] Pauli's evaluator report integration now uses fit['training_groups']; final
  settled-code rerun is required. Main evaluator51 session 37713 is running;
  no terminal result is inferred. Baselines, eight-feature ablation and real
  held-out validity remain pending even after tool fixes pass.
- [ ] Group owner checkpoint: 92 existing tests/91.197s/0 skips and 18 new
  tests/7.916s/0 skips, reported separately. Code is coherent, but additional
  final schema/backup tests and fresh group verification/quality/antipattern
  reviews are underway. Fields remain PROPOSED/unaccepted for frontend handoff
  until exact final code, commands/results and owner/main/fresh proof arrive.

### Stable owner deliveries — final group acceptance pending

//// - [x] Limited synthetic P3 tool provision: Pauli's final report integration
  reads authoritative fit['training_groups'] and regresses distinct source/group
  counts: 51 evaluator tests, 4.695s, 0 skips. Main's settled-code evaluator
  rerun passed 51, 4.139s, 0 skips (session 37713). Earlier independent Lorentz
  51/4.258s/0 skips plus eight numeric repros and Mill/James no-blocker reviews
  retain their exact scope; canonicalization was unchanged by the tiny report
  integration. This accepts synthetic tool provision only, not whole P3,
  baselines, eight-feature ablation, calibration or real held-out validity.

- [ ] Rev4 group final acceptance: owner completed eight scoped paths; fields are
  implemented, awaiting main/fresh acceptance rather than absent/PROPOSED code.
  Actual `choice_feedback_set` optional `group_id: str|null=None`,
  `group_reviewed: bool=False`; all returned feedback records include both
  normalized fields. Health reports rev4/34 and reviewed_event_groups=true.
  Rank separately counts informative actual source IDs and training_groups;
  fewer than 3 groups gives insufficient_training_groups. Source/schema inspected
  read-only by the documentation integrator; no frontend acceptance inferred.
- [ ] Owner final new tests: 20 group + 19 schema = 39, 34.034s, 0 skips; prior
  existing 92/91.197s/0 skips retained separately. New group test file covers
  encrypted reviewed and exact legacy-payload backup/DDL/no-backfill; existing
  backup implementation/file is unchanged. Main's new full suite and three fresh
  group reviews are running. Wait for their final proof before group completion
  marks and the accepted rev4 header/health-table switch. Duplicate hints TODO.

Current implemented math: G informative groups and n_g informative events within
group g for one target/partition/domain; event loss weight 1/(G*n_g), group total
1/G. Objective = mean of group means + (L2/2)||w||². One pre-average group weight
unit does not mean normalized mass=1. Earlier dated proposal wording is retained
as history; group/source counts remain separate and do not establish independence.

## Oct 5 final rev4 backend synthetic contract

//// - [x] Reviewed-event-group backend contract delivered: rev4/34 methods,
  optional group_id=None/group_reviewed=False, both normalized feedback result
  fields, explicit review/consent/double-source-approval/version/digest/epoch
  eligibility, no legacy backfill, event group weighting and separate informative
  source/group counts. MIN_GROUPS=3; insufficient_training_groups abstains.
  Main final full483/121.151s/OK/0 skips and all three fresh reviews accept only
  this backend synthetic contract. Exact proof commands are in
  [API final evidence](api.md#oct-5-final-rev4-backend-synthetic-contract).
//// - [x] Final synthetic regression execution: session28196 exit0, final
  canonicalization + group20 + schema19 + evaluator51 report integration covered.
  Lagrange independent focused51/19.543s/0 skips plus probes3/7.380s/0 skips,
  62 stable hashes; Meitner8/7.990s/0 skips, all34 parity/12 axes; Kant9 pure
  plus8 guards, no blockers. Two verifier runs are not a single 54-test run;
  overlaps are not added to main full counts.
//// - [x] Limited synthetic P3 tool provision and numeric-copy subfix: final
  owner evaluator51/4.695s and main51/4.139s, 0 skips each, authoritative
  fit['training_groups'] report and source/group regression; earlier independent
  Lorentz51/4.258s/eight repros/Mill/James reviews retain scope.

G informative groups and n_g informative events in this axis give event weight
1/(G*n_g), group total1/G; objective is mean of group means + (L2/2)||w||².
Only the eight-weight preference branch requires reviewed groups. Existing
whole-source double approval still updates translator/13-rule model/memories
without choice metadata. feedback_set/get do not fit; preference_rank temporarily
CPU-recomputes fit and ranks/explains/abstains, no saved weights/encoder training.
input.model_active and feedback.model_active describe separate activities.

- [ ] Broad online groups AND contrast span: group backend subtask done above;
  identifiable contrast-span abstention remains the next model task.
- [ ] Frontend per-event group-review/labels/impacts/consent/guard UI and adapters,
  unlock/version/F14/native acceptance; backend delivery does not check UI tasks.
- [ ] Exact-text duplicate hint; no inferred groups/review/consent.
- [ ] P2/P3 overall, baselines/eight-feature ablation/calibration, real held-out
  validity, actual encoder weights, native/GPU and hosted CI/Python3.10 remain open.

This is the stable six-document milestone for main diff review; no further edits
are planned here. No code/schema/test/frontend/evaluator-doc/Git mutations or
real corpus/DB/weight access were performed by this documentation owner.

## Oct 6 current rev5 delivery and remaining queue

2026-10-06 (Asia/Taipei): main accepted the limited rev5 backend synthetic
contract, including 80-digit Decimal contrast repair with unchanged tolerances,
fixed eight-column order, every-pair span refusal, closed preference_rank fields,
scalar-only evaluator contrast reporting and controlled huge-integer bounds
validation. Exact main576/59.590s/OK/0 skips and all three final reviews are in
[API final proof](api.md#oct-6-final-rev5-backend-synthetic-contract); completed
root tasks are in the [log](../../frontback-log.md#oct-6-final-rev5-backend-synthetic-contract).
The dated rev4/483 records above retain their scope; their contrast pending
statements describe Oct 5 and are superseded only for this backend subtask.

- [ ] P2/P3 overall, independent provenance/real held-out validity, baselines,
  eight-parameter ablations, calibration, same-span utility/magnitude/convex-hull
  validity and parameter selection.
- [ ] Frontend group-review/labels/impacts/consent/guards/adapters, unlock/private
  caches/version/F14/native acceptance; general semantic correction/generic replay
  and typed-correction performance.
- [ ] Exact-text duplicate hint, future content-revision guards, actual encoder
  weights/offline distribution/resources, physical input/GPU/cross-platform,
  online CI/Python3.10 and optional whole-database-encryption decision.

Root [active queue](../../front-back-communicate.md) contains 15 pending items.
Source t/t still feeds translator/13-rule model/memories without choice groups;
groups gate only preference. Fit stays temporary/read-only, with no DB writes,
persisted weights or encoder training. Overall goal active, not achieved.
