# Alpha brain (backend)

This directory contains the first local memory and self-model backend. The
particle brain in `src/scene/BrainView.tsx` does not yet read from it.

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
sources remain a separate prototype path; the final auto/individual candidate
publication policy remains to be confirmed.

`core/brain.py` now provides the unified application entry point. Its input,
candidate and active-memory queries exclude legacy store-only sources and
support partition filters. `core/api.py` exposes that entry point as a local
JSON-lines process for a desktop adapter; see [docs/api.md](docs/api.md) and
[docs/api.schema.json](docs/api.schema.json). Start it from this directory with
`python -m core.api --db data/brain.sqlite3`. The Tauri command/process host is
implemented; React Transport wiring and runtime distribution remain pending.
See [docs/desktop-bridge.md](docs/desktop-bridge.md); the desktop's default
database is its app-local-data file, not the repository's development database.
Candidate memories retain the current separate explicit review step.
The model now requires two whole-input judgements, with an explicit exclamation
shortcut setting both true. Re-review/removal/restoration and decision history
are implemented; original-text editing/deletion remain unavailable.
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
the test commands above. Without the extra, twelve schema tests explicitly skip;
the normal runtime still has no additional package dependency. The checks cover
all 21 request/response envelopes and method result bodies, including shorter
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
