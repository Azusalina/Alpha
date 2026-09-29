# Brain architecture — discussion draft

## Product contract

Alpha is a laptop-capable, local digital self-model. Its source is the user's
own natural-language input, with journals and chat history available for cold
start. Raw data stays local and remains visible and editable. One input box on
the human side is the natural-language entry point. The particle brain and
technology tree are two views over the same memory structure, not independent
stores. These constraints come from the repository's `IDEA.md` §§1, 3–4.

The current frontend input is a demonstration: it hashes text to illuminate a
placeholder region and does not save or run a model. `src/fixtures/graph.ts`
provides placeholder nodes. No frontend/backend contract has been established.

The backend prototype in `core/store.py` saves source text and evidence-linked
candidate memories in local SQLite. Accepted candidates can be listed as an
initial node inventory. `search_memories` retrieves accepted claims with their
source references via literal substring matching. `core/extraction.py` defines
a model-neutral extraction contract and validates candidate batches. It does
not yet expose edges, a taxonomy, import parsers, a configured model runtime,
or a Tauri interface. The candidate resolution API supports either a
manual-review UI or a later automatic policy; no automatic promotion occurs
in the prototype.

## Candidate pipeline (pending discussion)

1. Accept text from the existing input box or an explicitly chosen local file.
2. Preserve the original with provenance and stable identifiers.
3. Generate candidate memories using a local language model. Keep source
   references and uncertainty with each candidate.
4. Review or otherwise resolve candidates under a user-chosen write policy.
5. Index accepted memories for search and expose one graph to both views.

The visual brain's anatomical regions are temporary presentation groups, not
a taxonomy of the user's personality. Classification, graph semantics, and
what constitutes one memory remain open product decisions (`IDEA.md` §6).

## Technology candidates

- Python for import, extraction, and orchestration; stdlib SQLite for a local
  source-of-truth database. FTS5 is a possible first search index.
- A replaceable local inference adapter, with CPU-first quantized model
  evaluation. `llama.cpp` is a candidate runtime, not a selected dependency.
- A narrow Tauri command boundary to the existing React/TypeScript frontend.
  The transport and process lifecycle still need a concrete design.
- Embeddings or other ML features only when lexical retrieval proves
  insufficient on representative Chinese/English data. No training is needed
  for the first usable system.

## Open decisions before expanding storage or adding inference

1. First input mode: individual entries, bulk journal/chat import, or both.
2. Candidate write policy: explicit approval, or automatic write with edits.
3. Memory unit and classification: user-defined tags, model suggestions,
   relationships, and how corrections affect previous inferences.
4. Raw-data editing, deletion, backups, and the password gate described in
   `IDEA.md` §4. These must agree on what is recoverable.
5. Local model/runtime choice after measuring latency and memory on the target
   Intel i9-13900H / 16 GiB / Iris Xe laptop.

This draft records choices to discuss; it does not assert that any candidate
technology or memory policy has been approved or implemented.
