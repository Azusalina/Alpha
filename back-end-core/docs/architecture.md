# Brain architecture — discussion draft

## Product contract

Alpha is a laptop-capable, local digital self-model. Its source is the user's
own natural-language input, with journals and chat history available for cold
start. Raw data stays local and remains visible and editable. One input box on
the human side is the natural-language entry point. The particle brain and
technology tree are two views over the same memory structure, not independent
stores. These constraints come from the repository's `IDEA.md` §§1, 3–4.

Frontend/backend contracts now exist in `api.md` and the root
`front-back-communicate.md`. The backend host is implemented, but a real React
Transport connection and native acceptance remain pending; frontend mock or
visual reactions must not be treated as evidence of backend fitting.

The backend prototype in `core/store.py` saves source text and evidence-linked
candidate memories in local SQLite. Accepted candidates can be listed as an
initial node inventory. `search_memories` retrieves accepted claims with their
source references via literal substring matching. `core/extraction.py` defines
a model-neutral extraction contract and validates candidate batches. It does
not yet expose edges or a Tauri interface. The newer `model/` path shares the
SQLite source table, but has its own whole-input agreement flow, isolated
state partitions, effect log, and immutable zero baseline. A model-submitted
source now cannot enter `core/extraction.py` or publish a candidate memory
until agreed; revocation hides its accepted memories from active reads. This
is a shared review boundary. `core/brain.py` now orchestrates the public source,
model and candidate-memory operations over this identity. `core/api.py` exposes
a versioned local JSON-lines protocol. The Tauri command/process host is
implemented; the React Transport connection and release runtime remain pending.
Canonical memory reads exclude legacy store-only records and can filter by
partition before applying their result limit.

## Implemented model v1 pipeline

1. Save raw text with a partition (`rational`, `emotional`, `crazy`) and kind
   (`diary`, `chat`, `philosophy`) and first judgement immediate. This is pending
   when true, disagreed when false, and does not train unless explicit
   exclamation sets both judgements true and fits in the submit transaction.
2. Optionally preview an inactive source's local translation and hypothetical
   effects without updating the active state. Then receive confirm (the review
   agree boolean) for the whole source; both judgements must be true to fit.
   Disagreed sources remain stored but do not
   train. Pending feedback can override a parameter with an exact evidence span;
   feedback history is preserved and whole-input agreement still gates fitting.
   Re-review can remove an agreed fit or restore saved evidence from an inactive
   fit without counting support twice. Decision history includes zero-effect
   transitions; legacy migration changes approval metadata, not existing scores.
3. Extract only explicit, evidence-linked value/expression contributions;
   guard quotations, questions, hypothetical/reported frames and ambiguous
   value negation/comparison before updating the source's own partition with
   shrinkage toward zero. New fits record bounded base-rule diagnostics and
   policy provenance (`evidence-policy.md`). Explicit corrections can override
   guards; committed fits retain their frozen contributions and context.
4. Learn partition-local token/phrase counts using jieba. Recurrent phrases
   become future segmentation hints; this is not semantic fine-tuning.
   Separately, consistent explicit corrections from two agreed sources teach
   exact full-clause reuse within the same partition/kind/separator context;
   conflicts abstain, and inferred examples do not teach. Fit contexts are frozen.
5. Emit parameter effects with exact source spans, before/after values and rule
   identifiers. Revocation removes a source from the active fit and logs it.
6. A structured option-ranking method gives provisional value alignment after
   sufficient rational evidence, or abstains. It is not a calibrated prediction
   of the user's choice or an autonomous decision maker.

The names are local modeling hypotheses, not measured psychological scales.

## Candidate-memory pipeline (partially integrated)

1. Accept text from the existing input box or an explicitly chosen local file.
2. Preserve the original with provenance and stable identifiers.
3. For a model-submitted source, require whole-input agreement before an
   injected text model can generate candidate memories. Keep source references;
   candidates remain pending, not automatically published.
4. Review or otherwise resolve candidates under a user-chosen write policy.
5. Search accepted memories while their model-submitted sources remain agreed.
   A single graph contract for both views is still pending.

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
  The host now serializes requests and owns process lifecycle with bounded
  transport and main/local ACL. Frontend connection and packaged runtime remain.
- Embeddings or supervised preference learning only after representative,
  user-endorsed examples exist. The current model learns interpretable
  evidence counts and personal vocabulary, not neural-network weights.

## Open decisions before broader inference or frontend integration

1. Broader semantic generalization beyond the implemented exact-clause correction
   memory, and explicit replay/revision of already fitted dependent sources.
2. Retrospectively endorsed choice labels and held-out evaluation for deciding
   which parameters improve fit. Until then, choice ranking is provisional.
3. Whether candidate publication remains a separate review or becomes automatic
   after whole-input approval; any future graph taxonomy is still open.
4. F6 inactive-source editing and any-state hard deletion are now implemented;
   edits clear old source-specific histories, deletes also remove active support.
   Other inputs' frozen records remain untouched. External backup governance and
   the password gate in `IDEA.md` §4 remain pending; deletion is not secure erasure.
5. Native acceptance and release runtime distribution for the implemented
   Tauri process/command interface, and eventual visualization effects.
   The local host and frontend wiring are implemented. The frontend reports
   browser/real-Python and Xvfb native smoke acceptance; native failure/restart
   acceptance, release runtime distribution and hardware GPU checks remain.

This draft records choices to discuss; it does not assert that any candidate
technology or memory policy has been approved or implemented.
