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
- Request schema includes all 23 methods and correction items. All 23 method
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
- The last verified candidate-publication baseline retains explicit review. The user confirmed
  automatic publication on whole-source double approval; implementation and
  verification remain pending. Legacy pending/rejected candidates must not be
  silently published by migration. UI remains outside the backend implementation.
- `src-tauri`: fixed `brain_call` host, main/local ACL, serialized bounded queue,
  total timeout, response validation, stderr draining and child cleanup. Genuine
  Python and Tauri MockRuntime command/ACL tests exist. React Transport is wired;
  frontend reports browser/real-Python and Xvfb native smoke acceptance. Native
  failure/restart/F6 acceptance and release runtime packaging remain pending.
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
  all 23 request/response envelopes and method bodies, negative shapes,
  lifecycle/ranking/candidate variants, migration and real JSON-lines output.
  Fourteen synthetic tests use temporary databases; without the extra they explicitly
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

- Broader event/semantic correction needs typed, evidence-bound labels and
  representative examples. The reviewed-source policy is decided: withdraw the
  current contribution and require renewed immediate/confirm consent for the
  revised interpretation; implementation and verification are still pending.
- Evaluate whether candidate parameters improve predictions using future
  retrospectively endorsed choice labels; remove ineffective parameters.
- Define the user's retrospectively endorsed choice labels and the model's
  abstention rule when too few examples exist.

## Current backend queue (2026-10-01)

- [x] Terminal telemetry: CLI/API default-on stderr traces and bounded/validated
  Rust host forwarding; no raw evidence, no response/schema changes. Commit-only
  param/fit reporting, receipt vs save/fit distinction, rollback and broken-sink
  checks. Nine synthetic Python tests and one Rust filter/framing test added.
  See terminal-tracing.md; no automatic on-disk logger or private-text logging.
- [x] Frontend reports browser real-Python acceptance for F6, NUL and model
  epoch/activity metadata with deliberate old-source re-enlistment. Verified
  current adapter/record wiring read-only; native acceptance still pending.
- [x] Model-only reset: confirmed local CLI with exact existing absolute DB
  target, epoch/revision checks and atomic zeroing. Translator, approvals and
  history preserved; old fits excluded until explicit re-review. Twelve synthetic
  reset tests plus one post-reset result-schema test. `model-reset.md` is the contract.
- [x] Frontend browser activation: consume model_active/model_epoch, distinguish
  approved history from current-model participation, and deliberately re-enlist
  old sources. Latest ledger reports cache/in-flight invalidation on reconnect
  and browser acceptance; native reset/reconnect acceptance remains pending.
  No live reset endpoint/UI yet.
- [ ] Native acceptance of administrative reset/reconnect and F6 edits/deletes;
  basic browser real-Python tests do not validate native failure/recovery paths.
- [x] P0: F1-F4/F7 dual approval, exclamation, repeated review, decision audit,
  metadata migration and expanded preview implemented and regression-tested.
- [x] P0: F5 summaries and input_page pagination implemented and regression-tested.
- [x] P0: F6 source editing/deletion and NUL validation implemented; final contract
  and frontend activation/acceptance steps in `../../front-back-communicate.md`.
- [ ] P0: protected backup/recovery delivery and general downstream-fit replay;
  current F6 removes only this source's records and future teaching support,
  preserving other inputs' frozen fits and historical effects.
- [ ] P0 / F13: application access gate and encrypted backup/recovery are
  confirmed in scope, no longer deferred. Implementation, API integration,
  frontend unlock wiring and verification remain pending. Cover raw text,
  summary excerpts, evidence, histories and writes, not just input_get.
  The current SQLite database remains plaintext; whole-database encryption is
  outside this round. The gate is not protection from direct same-OS-user file
  access. Recovery must validate into an explicit fresh target, never silently
  overwrite the live database.
- [ ] P1: native failure/restart/F6 acceptance, packaged Python/backend/jieba
  and subsequent contract migrations remain.
  Host transport/lifecycle/timeout/ACL code is implemented (`desktop-bridge.md`),
  with frontend wiring and Xvfb basic acceptance reported by the frontend.
- [x] P1: type all 23 method result bodies and common records, and add local
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
  Template/tool delivery awaits worker verification; real coverage acceptance
  remains an external prerequisite, not a promise to collect private data now.
- [ ] P1: held-out choice labels and parameter ablations before supervised ML;
  the offline evaluation/ablation tool is implemented (`evaluation.md`), but
  real labels, split design and parameter decisions remain. This round supplies
  templates/tools only; no real predictive-validity claim can be accepted.
  Factual choices and retrospective endorsement are different labels; no frontend contract
  or automatic parameter pruning is implemented.
- [ ] Confirmed policy to implement: automatically publish extracted candidate
  memories when the current source/version has immediate=true and confirm=true;
  preserve legacy pending/rejected statuses without migration auto-publication.
- [ ] Confirmed policy to implement: reviewed-source semantic revisions withdraw
  current contributions and require renewed double consent before fitting;
  version-bound revisions and explicit replay must preserve old effect numbers,
  frozen history and model-reset exclusions. F6 text editing is a separate path.
- [ ] Deferred: F14 future choice-feedback contract and sphere v2.

The decisions above record scope, not completion of parallel feature work. Update
pending boxes only after worker evidence and independent verification are reviewed.
