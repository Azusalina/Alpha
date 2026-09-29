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

The model's commands and limitations are in [model/README.md](model/README.md),
with active/deferred parameters in [docs/parameters.md](docs/parameters.md).
Run both `python -m unittest discover -s tests -v` and
`python -m unittest discover -s translator -p 'test_*.py' -v`.

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
