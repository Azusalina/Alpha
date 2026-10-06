# Alpha brain (backend)

> Current continuation (2026-10-06, Asia/Taipei): main's broader goal is active.
> Current schema_version=1 / contract_revision=6 / 35 methods,
> features.exact_text_duplicate_hint=true; prior contrast guarantees unchanged.
> Latest main session90162 exit0: 620 tests / 100.682s / OK / 0 skips;
> independent discovery: 620 unique IDs / 0 loader errors. Aquinas, Tesla and
> Franklin terminal fresh reviews found no blockers. Only the exact-text
> duplicate hint backend is accepted this phase; see
> [latest root log](../frontback-log.md#oct-6-rev6-exact-text-duplicate-hint).
> Earlier [main601/84.585s](../frontback-log.md#oct-6-offline-comparisons-and-typed-validation-performance)
> retains its offline-tools/typed-validation proof scope.
> Earlier rev5 main576/59.590s remains a dated contract proof;
> see [current API and exact numeric proof](docs/api.md#oct-6-final-rev5-backend-synthetic-contract).
> Historical rev4 483, rev3 458, scoped 411 and prerepair 574 retain their scope.
> Dated proposals/intermediate pending narratives below are historical and
> superseded for current status. Overall P2/P3, frontend/native, general semantic
> correction/generic replay, actual encoder weights and real validity remain open.
> Root queue retains 13 pending items; overall goal ACTIVE/NOT ACHIEVED.
> See [current queue](docs/TODO.md#oct-6-rev6-exact-text-duplicate-hint)
> and [hybrid plan](docs/hybrid-learning-plan.md#oct-6-rev6-exact-text-duplicate-hint).
>
> Historical main396/134.672s then semantic51/1.142s (last two additions in
> discovery398) and backup12/11.220s all had 0 skips; these are not a single
> 398-test run. No live DB, private corpus, weights or network are used by this
> documentation update; synthetic tests do not establish real predictive validity.

This directory contains the first local memory and self-model backend. The
particle brain in `src/scene/BrainView.tsx` does not yet read from it.

Current preference contract: frontend supplies an explicit event group, with
optional `group_id: str|null=None` and `group_reviewed: bool=False` on guarded
choice_feedback_set. All returned feedback records include both fields; legacy
payloads read as null/false without backfill and remain ineligible until reviewed
guarded save. Health exposes reviewed_event_groups=true and
preference_contrast_guard=true. Public preference_rank returns contrast_rank/contrast_basis
in the fixed eight-column order and checks every query pair. The P3 evaluator report
exposes scalar contrast_rank only, without raw basis/weights/private internal
variables; see [rev5 contract](docs/api.md#rev5-contrast-contract). Legacy `rank`
retains its value-alignment result shape without contrast metadata.
preference_rank separately counts
actual informative training_sources and training_groups; fewer than 3 groups
abstains with insufficient_training_groups. Authenticated `input_duplicates`
now supplies a read-only exact-current-text hint; it never infers groups/review/
consent. Frontend duplicate adapter/UI/cache/native integration remains pending;
see [handoff](docs/frontend-contract-handoff.md#oct-6-rev6-exact-text-duplicate-hint).

Oct 5 current preference solver: L2=0.1, up to 64 damped Newton/Cholesky steps and
32 backtracks per step; publishable weights require gradient infinity norm
<=1e-11. Top gaps <=1e-8 abstain; nonfinite_fit/fit_not_converged describe numeric
failures. Worker final 80 synthetic tests passed in 128.728s, 0 skips; the scoped
main/fresh acceptance is recorded in the hybrid plan. Dense 1000-event/8-option fit took 2.144934741 CPU
seconds in a synthetic benchmark, not a normal API latency guarantee. Memory
measurements use Python tracemalloc, not native RSS; see
[measurements and scope](docs/hybrid-learning-plan.md#oct-5-final-worker-proof--mainfresh-acceptance-pending).

The product direction and open decisions are in [docs/architecture.md](docs/architecture.md).
`core/` contains a dependency-free Python/SQLite memory prototype. It can
save source text, stage evidence-linked candidate memories, accept or reject
them, and search accepted memories by literal text. `core/extraction.py` can
ask an injected text model to propose candidates, but no model runtime is
configured. `translator/` contains conservative rules plus local personal
vocabulary adaptation using jieba at `../ext-refs/jieba`. `model/` is the first
evidence-linked active self-model with an immutable zero baseline and separate
rational/emotional/"crazy" partitions. It does **not** diagnose a person, fully
understand free text, or connect to the frontend yet. Do not place personal
journals or chat exports in Git.

## Layout

- `core/`: main brain programs and domain logic.
- `translator/`: rule-first observations and local vocabulary learning.
- `model/`: partitioned self-model, effects, and local CLI.
- `data/`: local memories and indexes at runtime; content is ignored by Git.
- `logs/`: local operational logs at runtime; content is ignored by Git.
- `docs/`: design, decisions, and interface contracts.
- `tests/`: behavior checks once the core is implemented.

The repository's existing frontend is React/TypeScript and Tauri 2. The
backend may use a different language, but its interface must preserve the
product's single natural-language input and local-only data boundary.

When a source enters through `model.submit`, `core/extraction.py` and candidate
memory publication require that source's whole-input review to be `agreed`.
Revoking the source hides its accepted candidate memories from active listing
and search while retaining their audit records. Legacy `core.cli add-source`
sources remain a separate prototype path. Fresh double approval atomically
publishes conservative authored current-version memories; legacy pending/rejected
candidates require explicit review and are not silently published.

`core/brain.py` now provides the unified application entry point. Its input,
candidate and active-memory queries exclude legacy store-only sources and
support partition filters. `core/api.py` exposes that entry point as a local
JSON-lines process for a desktop adapter; see [docs/api.md](docs/api.md) and
[docs/api.schema.json](docs/api.schema.json). Start it from this directory with
`python -m core.api --db data/brain.sqlite3`. The Tauri command/process host is
implemented; React Transport is wired, with browser/real-Python and Xvfb native
smoke acceptance reported by the frontend. Native fault/restart acceptance and
runtime distribution remain pending.
See [docs/desktop-bridge.md](docs/desktop-bridge.md); the desktop's default
database is its app-local-data file, not the repository's development database.
Separate candidate review remains for legacy pending records.
The model now requires two whole-input judgements, with an explicit exclamation
shortcut setting both true. Re-review/removal/restoration and decision history
are implemented. F6 now edits inactive inputs (no old raw-text history) and
hard-deletes any-state inputs with atomic contribution removal. It does not
delete external originals/backups or implement password protection/secure erasure.
Input lists now include bounded code-point summaries; `input_page` supplies
total and revision-checked cursor pagination without returning full journals.

The model's commands and limitations are in [model/README.md](model/README.md),
with active/deferred parameters in [docs/parameters.md](docs/parameters.md).
Read-only held-out choice evaluation and static parameter ablations are in
[docs/evaluation.md](docs/evaluation.md): `python -m model.evaluation --db
data/brain.sqlite3 --cases docs/evaluation.example.json`. The example is synthetic,
not evidence of personal predictive accuracy; evaluation never trains on cases.
Run both `python -m unittest discover -s tests -v` and
`python -m unittest discover -s translator -p 'test_*.py' -v`.

New assertion guards and their frontend-visible omission diagnostics are
documented in [docs/evidence-policy.md](docs/evidence-policy.md). They do not
reinterpret old frozen fits or establish real-user predictive validity.
Base extraction can be measured against independent human labels with
`python -m translator.evaluation --cases docs/translator-evaluation.example.json`.
The separate read-only tool never opens the model database or trains;
see [docs/translator-evaluation.md](docs/translator-evaluation.md). Its example
regresses a v1 other-subject false positive fixed by assertion-guards-v2;
all its cases are synthetic development material, not a verified user benchmark.

For optional schema conformance checks, create a development virtual environment
and run `python -m pip install '.[test-schema]'` from this directory, then rerun
the test commands above. Without the extra, schema checks explicitly skip;
the normal runtime still has no additional package dependency. The checks cover
all 34 request/response envelopes and method result bodies, including shorter
no-op decisions, legacy contexts, ranking and candidate-status variants.
Clients select `#/$defs/results/$defs/METHOD` for successful bodies using the
retained request method; generic envelope validation alone is insufficient.
Cross-field identity/evidence equality still needs behavior/runtime checks.
The root `.github/workflows/backend-contract.yml` requires the extra and runs
only synthetic fixtures with temporary databases, using the pinned jieba
reference under `ext-refs/`. Its Python 3.10/3.14 matrix is configured but has
not yet been executed on GitHub. Workflow setup follows the official
[Python action](https://github.com/actions/setup-python) and
[checkout action](https://github.com/actions/checkout) instructions; both are
pinned by commit and have read-only repository permissions.

## Try the local core

Run from `back-end-core` with Python 3.10 or newer:

```bash
python -m core.cli init
python -m core.cli add-source '我喜歡畫畫。'
python -m core.cli list-sources
python -m core.cli propose SOURCE_ID '使用者喜歡畫畫' '我喜歡畫畫'
python -m core.cli list-candidates
python -m core.cli accept CANDIDATE_ID
python -m core.cli list-memories
python -m core.cli search '畫畫'
python -m unittest discover -s tests -v
```

Replace the IDs with those printed by the commands. The default database is
`data/brain.sqlite3` and is ignored by Git. Use `--db /path/to/test.sqlite3`
before the action to use a different database.
Search scans accepted claims and their evidence; it is an initial Chinese and
English compatible retrieval method, not semantic search.

`extract_candidates(store, source_id, model)` accepts any local model adapter
with a `generate(prompt) -> str` method. It validates the JSON response and
exact evidence excerpts, then stages the batch as pending. It never accepts
candidates automatically. A usable adapter and model benchmark are still
pending the runtime decision.

## Oct 6 offline tools and typed validation performance

Accepted 2026-10-06 (Asia/Taipei): only the offline two-baseline comparison tool,
eight matched leave-one-feature-out ablations and typed validation resource /
consistency proof. Main full session65720 exit0: 601 tests / 84.585s / OK /
0 skips; independent discovery found 601 unique IDs / 0 loader errors. Main
focused session67821 exit0: 40 tests / 9.939s / OK / 0 skips overlaps the full
suite. Owner evaluator69/3.415s used DB/network denials. Counts are not added.
Completed Lovelace verification, Linnaeus antipattern and Ramanujan quality
reviews have no demonstrated blockers; details and frozen source hashes are
authoritative in the [latest root log](../frontback-log.md#oct-6-offline-comparisons-and-typed-validation-performance).

Use the selected project Python environment from `back-end-core`:

```sh
python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json
python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json --comparisons
python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json --comparisons --validate-only
python -B -m unittest discover -s tests -q
```

These are generic how-to commands, not executions by this documentation owner.
Comparisons require explicit `--comparisons`: full + nonpersonal equal_weight
sum heuristic + analytic uniform chance + eight fixed ablations = 11 variants,
10 full-vs-variant pairs. Original cohort admission/numeric deduplication occurs
before projection, once; projections preserve event multiplicity/group ownership
without further deduplication. All predictions/distributions precede held-out
scoring-label reads; support loss, original-cohort and equal-group denominators
remain visible. There is no automatic selection or calibration/validity claim.
Using holdout comparisons to select parameters requires a new independent final
holdout. See the [comparison protocol](docs/preference-evaluation.md#opt-in-offline-comparisons).

Main synthetic comparisons CLI exited 0 with empty stderr: 11 variants / 10 pairs,
automatic_selection=False, validity_claim=False, database_opened=False. This
proves synthetic wiring only. Main's exact recorded full-suite command was:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/tmp/alpha-verify-20261006.ltAAKM /tmp/alpha-verify-20261006.ltAAKM/bin/python -B -m unittest discover -s tests -q
```

That dated temporary environment used CPython 3.14.7 / jsonschema 4.26.0; it is
verification evidence, not a permanent runtime path or a promise it still exists.
No tests or benchmarks were rerun for this documentation recovery.

`validate_corrections` lazily performs at most one complete translation per
function invocation; empty/parameter-only/pretranslation failure uses zero.
The batch bound remains 64, without global/cross-invocation caching.
`correction_reopen` still validates before and inside the transaction, and
observations translate separately. This is not a one-translation API-request
budget. The historical 98,752-character / 64 distinct-tone-target benchmark
remains median 2.857913091s -> 0.057367233s and Python peak 542,710 -> 429,267B;
it measures function timing/Python allocation, not API latency/native RSS.
See the [original performance proof](docs/correction-performance.md).

Source t/t continues to update translator/13-rule model/memories; independent
labels/impacts/consent/reviewed groups gate the separate temporary CPU preference
fit. Typed annotations intentionally do not override the 13 rule parameters;
future unified consumption remains an unanswered user decision. General
correction/generic replay, broad P0/P2/P3, real holdout/calibration/parameter
selection, frontend/native, actual weights/resources/GPU/CI and the encryption
decision remain pending. Exact-text duplicate hints are not implemented or
accepted here. Schema v1 / rev5 / 34 methods is unchanged; the broader goal
remains active, not achieved, with [14 root pending items](../front-back-communicate.md).

## Oct 5 verification recovery and next integration

Historical recovery sequence: all pending/PROPOSED statements in this section
are superseded by the current contract above and final accepted milestone below.
Counts keep their original scope; temporary environments are not permanent runtime.

Main supplied this terminal result from `back-end-core`:

```sh
TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q
```

458 tests, 181.564s, OK, 0 skips: scoped rev3 baseline proof before numeric-copy
canonicalization and rev4 group changes. The environment had Python 3.14.7,
jsonschema 4.26.0 and inherited PyNaCl; it is temporary test infrastructure, not
the permanent application runtime or proof of portable dependency installation.
Old job 97510 has no recovered terminal result and its environment is gone;
UnknownProcess is not pass evidence. Fresh job 9839 supplies the result above.

Recovery review ran 47 evaluator tests but found that omitted/explicit-zero and
equivalent numeric impacts could distinguish copies and inflate metrics. Pauli's
three-file fix has 68 targeted pass = 51 evaluator (47 old + 4 new) + 17 pure
before concurrent group partial edits. Independent reviews and settled-code proof
are pending; main's overlapping 51-test run hit WIP MIN_SOURCES NameError and is
not acceptance. These results do not accept P3. Descartes' prospective rev4 still has 34 methods. `group_id`,
`group_reviewed` and `training_groups` remain PROPOSED until final source/schema
and owner proof arrive; see [API plan](docs/api.md#prospective-revision-4--proposed-until-owner-proof).
Feedback grouping is per event, not an entire text file. Exact-duplicate hints,
contrast-span checks and frontend integration remain TODO.

Portable synthetic evaluator commands, run from `back-end-core` with the selected
project Python environment:

```sh
python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json --validate-only
python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json
```

These use no database or encoder; the manifest is synthetic, not a real held-out
benchmark. Next: integrate final corrected evaluator/group signatures and reason
statuses after owner delivery and new main/fresh proof. Real held-out validity,
calibration, weights, GPU and frontend/native acceptance remain pending. Agents
are available again; the earlier quota limit is historical, not a current blocker.

Latest limited acceptance: numeric-copy canonicalization passed Pauli's 68
targeted tests and Lorentz's independent 51 evaluator tests (4.258s, 0 skips),
eight stable numeric-copy repro checks and unchanged module hashes. Mill/James
static reviews found no blocker; James supplied no runtime result. This accepts
only that subfix. Evaluator `training_groups` report integration needs its final
rerun; main session 37713 and group final schema/backup/fresh reviews are pending.
Group owner checkpoint 92 existing/91.197s and 18 new/7.916s, both 0 skips, is
not final acceptance. Groups remain PROPOSED for handoff; whole P3, baselines,
ablation and real validity remain open.

Stable delivery update: synthetic P3 tool provision is now narrowly accepted.
Owner final report integration uses authoritative fit['training_groups'] and
passed 51 tests/4.695s/0 skips; main settled-code rerun passed 51/4.139s/0 skips.
Whole P3, baselines, ablation and real validity remain pending. Rev4 group code is
implemented and inspected, awaiting acceptance: optional group_id=None and
group_reviewed=False, normalized feedback fields, health rev4/34 with
reviewed_event_groups=true, separate source/group counts and min3 group gate.
Owner final 39 tests (20 group + 19 schema)/34.034s/0 skips and prior existing
92/91.197s/0 skips are scoped proof. Main full and fresh three group reviews
are underway; wait for final acceptance before changing the accepted header.
Encrypted reviewed/exact legacy payload backup and no-backfill tests are in the
new group test file; backup code is unchanged. Exact duplicate hints stay TODO.

Current group objective is the mean of informative group means plus
(L2/2)||w||². In each target/partition/domain, G informative groups and n_g
informative events per group give event loss weight 1/(G*n_g) and equal group
mass 1/G. "One weight unit per group" is before averaging, not normalized mass=1.

## Oct 5 final rev4 backend synthetic contract

Accepted scope: reviewed-event groups backend contract, canonicalization and
limited synthetic P3 evaluator provision. Main final full: 483/121.151s/OK/0
skips. Lagrange independent focused51/19.543s plus probes3/7.380s, 0 skips,
62 stable hashes; Meitner8/7.990s, 34-method parity and 12 axes; Kant9 pure plus
8 guards, no blockers. Exact commands/proof boundaries are in
[API final evidence](docs/api.md#oct-5-final-rev4-backend-synthetic-contract).

Whole-source double approval still updates translator, the 13-rule model and
memories without a choice group. The group gate applies only to the separate
8-weight supervised preference branch. Independent choice labels + consent +
group review + source double approval/current version/digest/epoch select its
snapshot. choice_feedback_set/get save/read only; preference_rank temporarily
CPU-recomputes group-mean L2 fit, then explains/ranks or abstains. No persisted
preference weights or encoder training. input.model_active is rule activity;
feedback.model_active is preference eligibility.

Frontend next: explicit per-event group review, labels/impacts/consent and guards;
no automatic retry. Model next: contrast-span abstention. Duplicate hints,
P2/P3 overall, baselines/ablation/calibration, real held-out validity, actual
weights, native/GPU and frontend acceptance stay pending. No further edits are
planned for this documentation milestone; main can review the six owned files.

## Oct 6 rev6 exact-text duplicate hint

Accepted backend only: authenticated read-only
`input_duplicates(source_id: str, *, limit: int = 20)`, schema1/rev6/35 methods,
health.features.exact_text_duplicate_hint=true. It compares current stored raw
text with SQLite BINARY equality, returning bounded private metadata and
snapshot tokens, no raw text or mutation. Backend submit/edit/review do not
invoke it; frontend may request after save/edit, including its own post-save
trigger. User-reviewed groups remain necessary; no automatic grouping/approval/
consent/merge/dedup/block-submit/refit. See the [API](docs/api.md#oct-6-rev6-exact-text-duplicate-hint)
and [pending frontend handoff](docs/frontend-contract-handoff.md#oct-6-rev6-exact-text-duplicate-hint).

Main620/100.682s/OK/0 skips, discovery620 unique/0 loader errors and three
terminal no-blocker reviews are recorded with the exact dated command and
frozen hashes in the [rev6 log](../frontback-log.md#oct-6-rev6-exact-text-duplicate-hint);
the temporary verification environment is not a permanent runtime path.
Root13 pending; frontend adapter/UI/cache/native, general correction/dependency
replay, real holdout/weights/resources/CI/Python3.10 and broad P0/P2/P3 remain
open. Overall goal ACTIVE/NOT ACHIEVED; earlier main601/rev5 main576 proofs and
recovery amendments keep their historical scope.
