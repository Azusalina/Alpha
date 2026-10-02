# Backend TODO

## Implemented application interface

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
  its exact payload and timing are still to be agreed.
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
- Define the user's retrospectively endorsed choice labels and the model's
  abstention rule when too few examples exist.

## Current backend queue (2026-10-02)

- [x] Terminal telemetry: CLI/API default-on stderr traces and bounded/validated
  Rust host forwarding; no raw evidence, no response/schema changes. Commit-only
  param/fit reporting, receipt vs save/fit distinction, rollback and broken-sink
  checks. Nine synthetic Python tests and one Rust filter/framing test added.
  See terminal-tracing.md; no automatic on-disk logger or private-text logging.
- [x] Frontend reports browser real-Python acceptance for F6, NUL and model
  epoch/activity metadata with deliberate old-source re-enlistment. Verified
  prior adapter/record wiring read-only; Xvfb DOM F6 passed. Native administrative/
  physical acceptance and verification of latest frontend changes remain pending.
- [x] Model-only reset: confirmed local CLI with exact existing absolute DB
  target, epoch/revision checks and atomic zeroing. Translator, approvals and
  history preserved; old fits excluded until explicit re-review. Twelve synthetic
  reset tests plus one post-reset result-schema test. `model-reset.md` is the contract.
- [x] Frontend browser activation: consume model_active/model_epoch, distinguish
  approved history from current-model participation, and deliberately re-enlist
  old sources. Latest ledger reports cache/in-flight invalidation on reconnect
  and browser acceptance; native administrative model-reset/reconnect acceptance remains pending.
  No live reset endpoint/UI yet.
- [x] Native DOM EOF/invalid-response/timeout faults: main's final command exited 0;
  summary and all three reports passed in `/tmp/alpha-native-faults-20261002`.
  Each verifies startup failure/explicit reconnect and ambiguous submit/explicit read
  recovering exactly one source; fixture logs show exactly one submit and
  no_write_autoretry=true. Together with real/persistence, five native DOM scenarios passed.
  Earlier process-inspection/unselected-partition failures were harness failures,
  not product failures; final main verification supersedes their pending status.
- [ ] Native administrative model-reset/reconnect and physical input/GPU acceptance.
  Xvfb DOM F6/paging and second-process persistence passed;
  browser and Xvfb evidence do not establish physical acceptance.
- [x] P0: F1-F4/F7 dual approval, exclamation, repeated review, decision audit,
  metadata migration and expanded preview implemented and regression-tested.
- [x] P0: F5 summaries and input_page pagination implemented and regression-tested.
- [x] P0: F6 source editing/deletion and NUL validation implemented; final contract
  and frontend activation/acceptance steps in `../../front-back-communicate.md`.
- [x] P0: protected backup/recovery and explicit selected dependency replay
  delivered; historical effects, unselected frozen fits and reset exclusions
  remain preserved. General downstream causal replay is not implemented.
- [x] P0 / F13: AccessSession gates all private API reads/writes with LOCKED;
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
- [x] P1: type all 30 method result bodies and common records, and add local
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
  or automatic parameter pruning is implemented.
- [x] Implemented: automatically publish extracted authored candidate
  memories when the current source/version has immediate=true and confirm=true;
  preserve legacy pending/rejected statuses without migration auto-publication.
- [x] Implemented: reviewed-source typed revisions withdraw
  current contributions and require renewed double consent before fitting;
  version-bound revisions and explicit replay must preserve old effect numbers,
  frozen history and model-reset exclusions. F6 text editing is a separate path.
- [ ] Frontend unlock/private-cache and guarded version-consent UI; latest
  concurrent frontend changes have not all been verified. See frontend-contract-handoff.md.
- [ ] F6 future content-revision guard: source_version resets to 0 after editing,
  leaving queued unversioned review ambiguity; handoff documents cache/queue cleanup.
- [ ] Typed corrections: assess per-item retranslation performance.
- [ ] Deferred: F14 future choice-feedback contract and sphere v2.

Completed statuses above reflect supplied worker evidence and main's independent
verification. Main owns final full-suite counts and remaining native results;
do not interpret synthetic tests/templates as real coverage or predictive validity.
