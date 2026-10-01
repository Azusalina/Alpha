# Backend TODO

## Implemented application interface

- `core/brain.py`: unified model/source/candidate entry point; canonical queries
  exclude legacy store-only records and filter partitions before limiting results.
- `core/api.py`: persistent local JSON-lines process, schema version 1, strict
  request fields and error envelope; EOF ends the process.
- `docs/api.md` and `docs/api.schema.json`: frontend integration contract.
- Pending interpretation feedback: `correction_set` / `correction_history`,
  append-only revision checks, exact author evidence, and frozen fit provenance.
  Two consistent agreed full-clause labels can teach exact reuse within one
  partition/kind/separator context; conflicts abstain. Rejection/revocation
  cannot supply future teaching support. This is not semantic generalization.
- Request schema includes all 21 methods and correction items. All 21 method
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
- Candidate publication retains existing explicit review while the user's
  preferred policy is pending. UI remains outside the backend implementation.
- `src-tauri`: fixed `brain_call` host, main/local ACL, serialized bounded queue,
  total timeout, response validation, stderr draining and child cleanup. Genuine
  Python and Tauri MockRuntime command/ACL tests exist. React Transport wiring,
  native WebKitGTK acceptance and release runtime packaging remain pending.
- F1-F4/F7: dual whole-input approval, explicit exclamation setting both true
  atomically, repeated decisions/removal/frozen-fit restoration, decision audit
  and inactive preview. Legacy metadata migration does not re-fit existing data.
  Immediate remains immutable until F6 editing; no text-inferred authorization.
- F5: get/list summaries preserve Unicode code points; input_list keeps its
  array shape. New input_page returns bounded items/total/cursor/revision.
  Database-bound cursors reject altered filters or stale input generations;
  each page uses one read snapshot. edited_at is null until source editing exists.
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
  all 21 request/response envelopes and method bodies, negative shapes,
  lifecycle/ranking/candidate variants, migration and real JSON-lines output.
  Twelve synthetic tests use temporary databases; without the extra they explicitly
  skip. Backend CI configuration requires the validator and pins the tokenizer
  and Actions references. Local Python 3.14 passes; online CI and its Python 3.10
  job have not been executed yet. Schema shapes are not model-validity evidence.

## Deferred: MMPI report import

- Not part of brain/model v1. The user will decide the version and input format later.
- If implemented, parse a user-provided official report as a separate source type,
  preserving test version, report date, scale names, supplied scores, validity
  notices, original interpretation, and source references.
- Do not reconstruct proprietary test scoring from items, generate a diagnosis,
  or automatically overwrite the user's value/decision model with clinical
  report fields. Interpretation and weighting require a separate decision.

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

- Extend targeted correction beyond the implemented parameter overrides and
  exact clauses; evaluate meaning/generalization with representative examples.
- Evaluate whether candidate parameters improve predictions using future
  retrospectively endorsed choice labels; remove ineffective parameters.
- Define the user's retrospectively endorsed choice labels and the model's
  abstention rule when too few examples exist.

## Current backend queue (2026-10-01)

- [x] P0: F1-F4/F7 dual approval, exclamation, repeated review, decision audit,
  metadata migration and expanded preview implemented and regression-tested.
- [x] P0: F5 summaries and input_page pagination implemented and regression-tested.
- [ ] P0: F6 source revision/deletion remains in
  `../../front-back-communicate.md`; changing immediate requires the pending edit API.
- [ ] P0: define raw-source history, backup/recovery, reviewed-source revisions
  and invalidation/replay of dependent fits, corrections, and candidate memories.
- [ ] P0: password/access boundary and protected backups; no encryption or
  password gate exists yet. Protect summary excerpts, evidence and correction
  history too, not just input_get, when designing the raw-text access gate.
- [ ] P1: connect React Transport to the implemented Tauri host; native desktop
  acceptance, packaged Python/backend/jieba and contract migrations remain.
  Host transport/lifecycle/timeout/ACL code is implemented (`desktop-bridge.md`),
  but no frontend connection or native end-to-end acceptance exists yet.
- [x] P1: type all 21 method result bodies and common records, and add local
  conformance tests covering lifecycle branches, negative shapes and serialized
  output. Backend CI requires the validator; runtime dependencies are unchanged.
- [ ] P1: verify online backend CI and its Python 3.10 matrix job; local
  Python 3.14 verification does not prove the hosted/older-interpreter jobs.
- [ ] P1: evaluate cluttered diary/chat, quotation, negation and philosophy
  coverage using corrections; add local NLP only where evidence justifies it.
  Base guards and synthetic regression examples are implemented; real held-out
  corrected text and broader subject/irony/indirect-language handling remain.
  The scoped/grouped read-only extraction benchmark now exists. V2 fixes the
  known familiar-actor value leak; next collect independently labelled
  representative cases; do not equate tool tests with real coverage validation.
- [ ] P1: held-out choice labels and parameter ablations before supervised ML;
  the offline evaluation/ablation tool is implemented (`evaluation.md`), but
  real labels, split design and parameter decisions remain. Factual choices
  and retrospective endorsement are different labels; no frontend contract
  or automatic parameter pruning is implemented.
- [ ] Pending policy: candidate publication remains manual unless changed.
- [ ] Deferred: MMPI import, future choice-feedback contract, sphere v2.
