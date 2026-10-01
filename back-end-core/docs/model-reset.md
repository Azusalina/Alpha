# Model-only reset (local administration)

The user chose to preserve translator understanding while returning the
personalized model to its untrained state. This is **not** a factory reset,
raw-text deletion, password bypass, or clinical operation.

## Scope

- All three model partitions return to `value=0`, `net=0`, `support=0`,
  `observed=false`. The immutable zero baseline is never rewritten.
- Original text, approval metadata, candidate memories, correction history,
  frozen fits, personal vocabulary and exact-clause teaching support remain.
- An incrementing model epoch excludes every old contribution from the active
  model. Reopening the database or fitting a new source cannot reactivate them.
- Old approved sources stay `status=agreed` for translator/memory eligibility,
  but their `model_active=false`. Approval and active-model participation are
  now distinct. `model_active=true` means participation in this model epoch,
  including fits that yielded zero parameter effects; it does not mean a
  nonzero parameter was found.
- Explicit `review(source_id, agree=true)` re-enlists only that old source's
  frozen fit into the current epoch. Repeating it in the same epoch is a no-op.
  Do not send this automatically when reconnecting or hydrating old records.
- Revoke/delete still remove that source's translator support. If it has no
  current-epoch model fit they must not change the new model's parameter state.
- Effect history keeps its original values/revisions and adds `model_epoch`.
  Historical effects are not current state and must not replay as animation.
- Previously fitted sources retain their held-out exclusion flags. Preserved
  translator learning can influence new fits: this is not an independent,
  never-exposed NLP pipeline. Evaluation fingerprints include the model epoch.

## Commands

First stop the desktop app and any backend process using this database. The
command serializes SQLite writes, but it does not cancel requests already
queued in a separate host. Stop old clients so an old queued explicit review
cannot re-enlist a source after reset. Use the desktop's actual database path,
not the repository CLI default; paths below are placeholders.

From `back-end-core`:

```bash
python -m model --db /absolute/path/to/brain.sqlite3 reset-info
```

The response supplies `model_epoch`, `input_revision`, `active_model_inputs`
and `translator_preserved`. `reset-info` may perform the normal additive
metadata migration when opening an older compatible model; it does not fit.
Copy the exact returned epoch and revision into the reset command:

```bash
python -m model --db /absolute/path/to/brain.sqlite3 reset --confirm RESET_MODEL --expected-epoch EPOCH_FROM_INFO --expected-revision REVISION_FROM_INFO
```

`EPOCH_FROM_INFO` / `REVISION_FROM_INFO` must be replaced with integers. The
command refuses a relative/missing path, unrelated database, wrong confirmation,
stale epoch or stale input revision. Reset is one `BEGIN IMMEDIATE` transaction;
failure rolls back epoch, state and cursor generation together. A second reset
with the same preflight values fails rather than silently repeating a mutation.
Success reports the new epoch/revision and previous active-input count.

The confirmation phrase prevents accidental use; **it is not authentication**.
The entry point is local CLI / `BrainModel.reset_model`, not an exposed
JSON-lines method or secret frontend API. API method count remains 23.
No raw file, external backup, retained fit or history is erased, and no
automatic backup or restore-all command is introduced. Restoring a previous
active model wholesale is deferred; selected sources can be explicitly reviewed.

## Frontend handoff

- On reconnect, `health.model_epoch` identifies the current epoch.
- `input_get` / `input_list` / `input_page` / `input_edit` add `model_active`
  and per-source `model_epoch`. Pending/never-fitted epoch values are metadata,
  not proof of a fit; use `model_active` for activity. Treat missing fields in
  older backends as unsupported reset metadata, not as an inferred reset.
- Formal effects add `model_epoch`; old databases migrate effects to epoch 0
  without changing historical numeric values. Optional schema fields preserve
  compatibility with older v1 results; current backend emits them consistently.
- After an administrative reset, restart/reconnect, drop old caches/in-flight
  operations, load `state`, health and input page 1 again. Old cursors are stale.
- Show approved-but-inactive sources separately from currently fitted sources.
  A deliberate re-enlistment may call `review(...,agree=true)`; no bulk automatic
  review, automatic restore, retry or historical-effects playback.
- No frontend Reset control was built. A live reset endpoint with authorization,
  epoch-bound mutation requests and native UI acceptance is a separate task.

Twelve synthetic reset tests cover epochs, all partitions, translator retention,
explicit re-enlistment, restart, history, stale preflight, concurrent resets,
rollback, CLI path guards and migration. One result-schema test covers the
post-reset API and re-enlistment. These are correctness tests, not model-validity
or security certification.
