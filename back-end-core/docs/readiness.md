# Database-free evaluation collection readiness v1

This phase supplies a collection protocol, draft template, validator and strict
evaluator exports. **No real held-out files exist or were inspected.** Synthetic
tests establish tool behavior only. Collection eligibility is not independent
provenance verification, real coverage, predictive validity or parameter acceptance.
API and F14 remain deferred; this offline format does not enable future-choice
feedback, fitting, publication or consent.

Run from `back-end-core`:

```bash
python -m model.readiness --collection docs/readiness.example.json
python -m model.readiness --collection /absolute/path/local-collection.json --details
python -m model.readiness --collection /absolute/path/local-collection.json --export choice
python -m model.readiness --collection /absolute/path/local-collection.json --export translator
python -m unittest discover -s tests -p 'test_readiness.py' -v
python -m unittest discover -s tests -p 'test*evaluation*.py' -v
```

The committed example is a **synthetic draft template**, with zero export-eligible
cases. Its held_out tag reserves a slot; it is not a labelled held-out dataset.
An export with no eligible cases exits 2 rather than emitting an invalid empty
evaluator manifest. No command opens a DB or writes a collection/report/export.
Export goes to stdout only when explicitly requested. Translator exports contain
raw text and evidence; keep them local. Default readiness output contains aggregate
counts and hashes, without source text, case/group/source/annotator IDs or dates.
`--details` adds only opaque case IDs and fixed blocker codes.

## Collection protocol

Before collection, record the source grouping convention, development cutoff,
held-out start, collection freeze, annotation windows and rules/version being tested.
Retain the frozen collection and reports locally. Do not repeatedly tune against
the final held-out set; after such exposure, mark it exposed and collect a new set.
Choose boundaries in advance, rather than selecting favorable cases afterward.

Collect variants, excerpts, copies and paraphrases into the same opaque source
group. Assign one split to the entire group across both tasks. Collect daily,
study and interpersonal choice events; translator additionally supports philosophy.
Do not treat case count as independent source count. The tool does not select
sample-size targets, calculate confidence intervals or enforce population coverage.
No scipy or other new dependency is introduced.

Label independently before inspecting model output. Record the actual observed
choice, later endorsed choice and manually judged option impacts separately.
Authenticity/whole-source T/F never supplies these labels or extraction expectations.
An unknown actual/endorsed choice is null, not a negative; actual and endorsed may
differ. Do not convert predicted options, inferred impacts or whole-source approval
into gold. For extraction, independently check only the declared parameter scope.
In a completed scope, an omitted expected parameter means no extractable contribution;
outside that scope it is unchecked. Uncertain parameters stay outside the scope.

Time and exposure are author declarations. The validator checks their consistency
with the declared windows, **not their truth, pre-registration, or independence**.
It does not consult the wall clock, files' timestamps, history, rules or a DB.
Future-dated or retrospectively invented protocol dates cannot prove hold-out status.
The collection's reproducible hashes are audit aids, not an independence certificate.

## Strict collection format

The root has exactly `schema_version: 1`, `protocol` and `cases` (1–1000).
Protocol has exactly `development_end`, `held_out_start`, `frozen_at`, using UTC
`YYYY-MM-DDTHH:MM:SSZ`; `development_end < held_out_start <= frozen_at`.
Every case has exactly:

| Field | Contract |
| --- | --- |
| `id`, `group_id` | Opaque ASCII tokens: letters/digits/`_`/`.`/`-`, 1–80 characters. Unique case ID. Never names/narrative. |
| `source_ids` | 1–1000 distinct opaque collection source tokens. Include all contributing sources. |
| `backend_source_ids` | 0–1000 distinct opaque actual backend source IDs, separate from collection tokens. |
| `task` | `choice` or `translator`. |
| `split` | `development` or `held_out`. |
| `event_at`, `labelled_at` | UTC timestamps or null while unknown. Development events at/before development_end; held-out events at/after held_out_start; all events/labels at/before frozen_at; labels at/after event. |
| `annotator_id` | Opaque token or null; required for eligibility. |
| `blind_to_outputs` | true/false/null; only true is eligible. |
| `authenticity` | true/false/null, stored independently and never converted to task labels or eligibility. |
| `exposure` | Exactly the fields described below. |
| `annotations` | Task-specific label status declarations described below. |
| `data` | Task-specific evaluator data described below. |

`exposure` fields:

- `import_status`: `never_imported`, `imported`, `unknown`.
- `model_fit`, `rule_development`, `manual_tuning`: independently `none`, `exposed`, `unknown`.

`never_imported` requires empty backend IDs and cannot claim model_fit=exposed.
`imported` requires all known backend IDs; it can still be never fitted, but requires
the later read-only snapshot overlap check. Never importing does not establish
absence of rule-development or manual-tuning exposure. Any unknown or exposed
held-out provenance blocks the **whole group**, including otherwise clean variants.
Do not claim untrained from unknown provenance, revocation, reset or missing IDs.
The tool rejects source tokens reassigned to other groups/splits, groups crossing
splits, and normalized duplicate translator text in different groups/splits even
when a duplicate is an incomplete draft. Semantic paraphrase leakage and omitted
backend IDs still require manual review.

Choice `annotations` has exactly `options`, `actual_choice`, `endorsed_choice`.
Translator `annotations` has exactly `extraction`. Each status is `pending`,
`independent`, or `model_assisted`. Pending labels may be stored as drafts; they
are not gold. Completed choice labels cannot be null. Completed extraction needs
a nonempty explicitly checked scope. Independence and blinding remain attestations.

Choice `data` has exactly `domain`, `options`, `actual_choice`, `endorsed_choice`.
It follows [evaluation.md](evaluation.md), with null draft options allowed only
when options are pending and both choices are null. Completed options have 2–100
items, exactly `id` and `impacts`; option IDs are opaque, impacts finite value.*
numbers in [-1,1]. Unknown impact keys and option extra fields are rejected.
To export, options must be independent and at least one choice must be independent.
Unreviewed/model-assisted choice labels are replaced by null in the export, even
if an independent label on the other axis allows the case to export. Development
choices never export into the held-out choice evaluator.

Translator `data` has exactly `domain`, `partition`, `kind`, `text`, `label_scope`,
`expected`, with optional `self_speaker`, as in
[translator-evaluation.md](translator-evaluation.md). Draft `label_scope: []` is
allowed only with pending extraction and `expected: []`; it never exports or gets
scored as all-negative. Independent partial scopes are supported. Both development
and eligible held-out extraction cases export, preserving split and group metadata.
Reports from the translator evaluator still distinguish development from held-out.
Evidence spans preserve original Unicode code points, emoji and CRLF.

Missing/extra fields and malformed drafts fail before export. The shared loader
opens only bounded regular files with nonblocking open; it rejects FIFO/devices,
duplicate JSON keys at every level, malformed UTF-8/JSON, nonfinite numbers
(including exponent overflow), NUL anywhere and surrogate characters. Collection
file limit is 32,000,000 bytes; total translator text 5,000,000 code points and
per-case text 1,000,000. Choice evaluator file limit remains 10,000,000 bytes.

## Exports, APIs and snapshot authorization

`model.readiness.validate_collection(manifest)` validates and returns an isolated
copy. `assess_readiness(manifest, *, details=False)` returns counts, blockers,
collection/protocol hashes, implementation hashes and eligible export hashes.
Hashes use deterministic JSON serialization; dictionary key order is ignored,
collection array order is retained, exports sort by case ID. Reordering or changing
collection entries changes its hash; identical metadata/input/code reproduce the
same report. Hashes can leak correlations and are not encryption/anonymization.
`export_manifests(manifest)` returns `{choice: manifest_or_None,
translator: manifest_or_None}`; outputs are validated against actual evaluator APIs.
Freeze and retain the original collection and readiness report with each export,
because legacy choice manifests cannot carry group/time/exposure metadata.

Actual evaluator APIs:

- `model.evaluation.validate_cases(manifest, training_source_ids)` validates strict
  legacy choice manifests. The explicit **never-imported** legacy path
  `held_out: true, source_ids: []` remains backward compatible. Legacy files alone
  cannot prove exposure independence; the collection format adds attestations.
- `read_snapshot(path, *, access_session=None)` checks authorization before SQLite
  and uses `mode=ro`, `query_only` and a single transaction. Existing unconfigured
  callers are compatible. Configured callers without an unlocked matching
  `core.access.AccessSession` fail locked; library calls never prompt.
- `evaluate_database(path, manifest, *, access_session=None)` passes that session
  to snapshot reading and rejects overlap with historical fitted source IDs.
- The choice CLI uses `core.access.authorize_database` for explicit secure getpass
  authorization before any DB read, then passes the session. Access failures emit
  generic stderr without raw exception text, credentials, IDs or a snapshot.
- `translator.evaluation.evaluate_manifest(manifest, *, case_details=False)` is
  database-free base-rule extraction evaluation. It is separate from readiness;
  collection auditing does not run predictions or score drafts.

For configured synthetic/local evaluation only, a caller explicitly unlocks its
session before passing it:

```python
from core.access import AccessSession
from model.evaluation import evaluate_database

session = AccessSession(explicit_database_path)
session.unlock(password_from_secure_local_prompt)
report = evaluate_database(explicit_database_path, choice_manifest, access_session=session)
session.lock()
```

Do not store a password in a manifest, script, argv, environment variable or report.
This integration uses the existing foundation; it does not implement core API gates
or database encryption. A read-only report still contains sensitive model metadata.
Neither collection readiness nor ID overlap detects deleted/reimported material,
all indirect rule exposure or semantic leakage. There is no real validity claim.
