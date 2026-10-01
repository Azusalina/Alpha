# Backend completion plan — 2026-10-01

## Scope and non-negotiable boundaries

Implement the remaining backend queue in independently verified phases. Preserve
the frontend developer's changes, the current staged changes, the zero baseline,
three state partitions, double consent, model epochs, and frozen historical effects.
Do not access, reset, encrypt, restore over, or train the user's live database during
development. Use synthetic material and temporary databases. No Git commit/push.

MMPI report analysis is removed from the current requirements at the user's request;
no parser, proprietary scoring, clinical diagnosis, or clinical-model weighting is
part of this plan. F14 remains deferred unless separately requested.

## Phase 0 — documentation discovery and decisions

Parallel read-only discovery covers publication/correction/replay, local security
and backups, desktop runtime/native acceptance, and evaluation/contracts. Each
report must identify consulted sources, actual APIs/signatures, reusable examples,
verification commands, confidence and remaining gaps. Consolidate the reports
before assigning implementation; never assume a proposed frontend method exists.

Decisions confirmed by the user this round:

- Automatically publish extracted candidate memories on whole-source double
  approval. Do not silently publish legacy candidates during a migration.
- Reviewed-source corrections withdraw the current contribution and require
  renewed double consent before fitting the revised interpretation.
- F13 is in scope: access control and encrypted backups. Whole database encryption
  remains outside this round and requires a separate migration/recovery decision.
- Independently labelled real held-out material must be supplied locally before
  real coverage or predictive validity can be accepted.

Phase 0 findings (read-only reports consolidated):

- `core/brain.py` and `model/engine.py`: `correction_set` currently handles
  pending parameter overrides only; `review` restores frozen fits. Revisions need
  a separate version-bound reopen/review path, never F6 text replacement.
- `core/store.py`/`core/extraction.py`: candidates are currently manual. New
  publication must preserve legacy pending/rejected statuses and verify current
  source consent/version within the write transaction.
- `model/evaluation.py`: `read_snapshot`, `validate_cases`, `evaluate_database`
  exist. `translator/evaluation.py`: `load_manifest`, `validate_cases`,
  `evaluate_manifest` exist. Add collection readiness separately from scoring;
  current fixtures are synthetic, not real final-test data. User confirmed no
  real held-out files are available this round; deliver templates/tools only.
- `src-tauri/src/brain_host.rs`: fixed launch uses `-E -s -u -m core.api`;
  no release runtime is bundled. Xvfb/XTest are available; native WebDriver is
  absent. Physical GPU enumeration does not establish functional/performance
  acceptance. Preserve the bounded trace and host queue contract.
- Security foundation uses PyNaCl 1.6.2 Argon2id and libsodium secretstream.
  Primary docs: https://pynacl.readthedocs.io/en/latest/api/pwhash/ and
  https://doc.libsodium.org/secret-key_cryptography/secretstream . SQLite's backup
  API is the snapshot primitive, not copying the live main file. Gate setup is
  explicit; absent configuration preserves existing behavior. Corrupt config
  fails closed. The gate is an application boundary, not protection against a
  same-OS-user directly reading the unencrypted database.

## Phase 1 — evaluation readiness and requirements reconciliation

Read `evaluation.md`, `translator-evaluation.md`, their actual CLI implementations,
example manifests and tests. Reuse strict validation and read-only evaluation
patterns to make a reproducible local collection/acceptance workflow. Remove MMPI
from active queues, retaining historical discussion as history. Reconcile latest
frontend capabilities with older TODO wording without declaring native acceptance.

Verification: synthetic evaluation and schema tests; malformed/contaminated
manifests rejected; no writes to training DB; no synthetic metrics described as real
accuracy; no raw private material committed. Existing future-choice feedback is
not implicitly enabled by an offline evaluation manifest.

## Phase 2 — deployment and native acceptance

Read `desktop-bridge.md`, `src-tauri` runtime resolution/build configuration and
existing real-backend tests. Build an explicit reproducible release runtime and
exercise synthetic native F6, failure/reconnect, restart persistence and large-list
paths where environment permits. Keep browser, Rust MockRuntime and native-window
evidence separate. Record physical GPU availability and renderer honestly.

Verification: packaged Python/backend/jieba works without development source or
system Python; native tests use an explicit temporary database; no automatic retry
of ambiguous writes; release build and dependency versions recorded. Software
rendering is not hardware GPU acceptance. Do not change frontend visual design.

## Phase 3 — publication, corrections and explicit replay

Read `core/brain.py`, `model/engine.py`, correction/source/reset modules, governance
tests and API/schema. Implement only the selected consent/publication policy.
General semantic or event corrections need typed, evidence-bound labels, not
unsupported automatic semantic inference. Explicit replay must preserve old effect
numbers and model-only reset exclusion; source revision conflicts must fail before
any mutation. No silent re-interpretation or re-enlistment of old materials.

Verification: lifecycle, rollback, migrations, stale revisions, provenance, epochs,
deletion and dependency support; full API result validation and unchanged old-client
behavior for supported methods. New methods require documentation and schema.

## Phase 4 — security and protected backup/recovery

After scope is resolved, use an established cryptographic implementation. Read the
actual storage/access boundaries and primary library documentation. Backups must be
consistent snapshots with restrictive permissions, authenticated integrity, version
metadata and explicit target selection. Recovery validates into a fresh target;
never silently overwrites a live database. A gate must cover excerpts, evidence,
history and writes, not only raw-text retrieval. Never log credentials or keys.

Verification: wrong password/tampering/truncation/version failures; transaction
consistency; temporary files and secret handling; locked API coverage; migration and
recovery failures leave the original untouched. File permissions or ACL alone are
not encryption. A forgotten key cannot have a hidden bypass.

## Final phase — independent verification and handoff

Implementation workers have disjoint write scopes. Independent agents run the
verification checklist, scan anti-patterns and review code quality. The coordinator
reviews evidence and records exact commands/results in the communication ledger.
Preserve existing modifications; do not stage, commit or push.

Integration ownership: model/candidate changes and new standalone security/backup
modules can be developed independently. Assign one subsequent worker the shared
`core/api.py`, API schema and API documentation integration, after both contracts
are known. Desktop work owns host/build/runtime packaging files, not `src/`.
Evaluation work owns evaluation modules/templates/tests, not the live database.
Final requirements reconciliation owns the shared TODO and communication ledger.
All workers must inspect existing changes before editing and report changed paths.

Completion status must distinguish implemented and tested features from external
acceptance prerequisites: user decisions, representative independent labels,
physical GPU access and frontend unlock wiring. Never mark those prerequisites
complete using synthetic examples or software-rendered tests.
