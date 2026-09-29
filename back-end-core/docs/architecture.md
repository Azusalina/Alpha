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
not yet expose edges or a Tauri interface. The newer `model/` path shares the
SQLite source table, but has its own whole-input agreement flow, isolated
state partitions, effect log, and immutable zero baseline. It is not yet
wired to `core/extraction.py`'s candidate-memory path or to the frontend.

## Implemented model v1 pipeline

1. Save raw text with a partition (`rational`, `emotional`, `crazy`) and kind
   (`diary`, `chat`, `philosophy`). This is pending and does not train.
2. Receive one agree/disagree boolean for the whole source. Disagreed sources
   remain stored but do not train. Agreed sources are translated locally.
3. Extract only explicit, evidence-linked value/expression contributions;
   update the source's own partition with shrinkage toward zero.
4. Learn partition-local token/phrase counts using jieba. Recurrent phrases
   become future segmentation hints; this is not semantic fine-tuning.
5. Emit parameter effects with exact source spans, before/after values and rule
   identifiers. Revocation removes a source from the active fit and logs it.
6. A structured option-ranking method gives provisional value alignment after
   sufficient rational evidence, or abstains. It is not a calibrated prediction
   of the user's choice or an autonomous decision maker.

The names are local modeling hypotheses, not measured psychological scales.

## Legacy candidate-memory pipeline (not yet integrated)

1. Accept text from the existing input box or an explicitly chosen local file.
2. Preserve the original with provenance and stable identifiers.
3. Generate candidate memories using an injected text model. Keep source
   references and uncertainty with each candidate.
4. Review or otherwise resolve candidates under a user-chosen write policy.
5. Index accepted memories for search and expose one graph to both views.

The visual brain's anatomical regions are temporary presentation groups, not
a taxonomy of the user's personality. Classification, graph semantics, and
what constitutes one memory remain open product decisions (`IDEA.md` §6).

## Technology candidates

- Python for import, extraction, and orchestration; stdlib SQLite for a local
  source-of-truth database. FTS5 is a possible first search index.
- A locally cloned jieba tokenizer for Chinese segmentation and personal
  vocabulary adaptation; no LLM runtime is selected or required for v1.
  `llama.cpp` remains an optional candidate for later ambiguous-text handling.
- A narrow Tauri command boundary to the existing React/TypeScript frontend.
  The transport and process lifecycle still need a concrete design.
- Embeddings or supervised preference learning only after representative,
  user-endorsed examples exist. The current model learns interpretable
  evidence counts and personal vocabulary, not neural-network weights.

## Open decisions before broader inference or frontend integration

1. Targeted semantic corrections for the translator, beyond personal vocabulary.
2. Retrospectively endorsed choice labels and held-out evaluation for deciding
   which parameters improve fit. Until then, choice ranking is provisional.
3. How the original candidate-memory inventory connects to partitioned model
   state and any future graph taxonomy.
4. Raw-data editing, deletion, backups, and the password gate described in
   `IDEA.md` §4. These must agree on what is recoverable.
5. Tauri process/command interface and eventual visualization effects. The
   backend currently emits JSON only; no frontend change was made.

This draft records choices to discuss; it does not assert that any candidate
technology or memory policy has been approved or implemented.
