# Terminal model tracing

CLI and JSON-lines backend processes now enable live model telemetry by default.
Each event is flushed to **stderr**, prefixed `[alpha.model]`; stdout remains
the original CLI JSON / API response channel. No frontend/API fields change.

## Watch the desktop backend

Restart/rebuild the desktop program with the updated Rust host, and start it
from a terminal at the repository root:

```bash
npm run tauri -- dev
```

The host forwards only validated trace records from Python to that terminal.
Ordinary Python stderr, warnings, tracebacks and unexpected trace-shaped fields
remain discarded. Forwarding is line-framed and capped at 4096 bytes per line;
the declared DB address must match the host's configured DB. Starting from a GUI
launcher does not create a terminal window, and the browser-only mock does not
print real backend model traces. Existing running binaries must be restarted.

For a directly managed backend, from `back-end-core`:

```bash
python -m core.api --db /absolute/path/to/brain.sqlite3
```

That process waits for JSON-lines requests on stdin; it does not establish an
HTTP connection to an independently running frontend. Tauri owns its own Python
process, so use the desktop command above to watch actual desktop requests.

## Events

- `ready`: initialized database address (`db_path`). No fitting takes place.
- `operation_received`: input/edit character count or opaque source ID.
  Receipt is **not** proof of validation, storage or training.
- `operation_committed`: the method returned after its transaction committed.
- `data_saved`: submit/edit/pending correction/correction_reopen/replay_reopen
  stored, with actual DB address/source ID.
- `judgement`: actual `immediate`, `confirm`, `exclamation`, status and partition.
  `true/null` is pending; `true/true` permits fitting.
- `param_update`: parameter, before/after/delta, support before/after, source,
  partition, effect revision and model epoch. Includes removals on revoke/delete.
- `fit_committed`: selected input fitted/restored; parameter count and observed
  term count, including review_version. Zero parameter effects still can mean a vocabulary-only fit.
- `fit_skipped`: not dual true, or unchanged same-epoch approval (no duplicate fit).
- `source_deleted`: application records deleted after successful transaction.
- `model_reset`: new/previous epoch, translator preserved. This is not data deletion.
- `operation_failed`: error **type** only, no private error message or traceback.

All events have `time_ms` (Unix milliseconds). Read-only preview/history/state
queries do not print fake training events. Parameter records are collected within
the write transaction and printed only after commit; rollback discards them.
Requests in different processes can interleave: source, partition, epoch and
revision identify the affected state. Logs are diagnostic, not durable audit
records, and a process/terminal failure can omit events after a successful write.
Always reconcile using API state/history; missing logs do not prove no mutation.

Version operations `review_version`, `correction_reopen`, `replay_reopen` use the
same operation_received/operation_failed boundary. Reopening emits committed save,
judgement, withdrawal param_update and fit_skipped records; pending status does not
mean there were no withdrawal effects. Batch replay emits one operation_committed
receipt then bounded per-source save/judgement/update/skip records in selected order,
only after the whole transaction commits. Failure anywhere discards all collected
updates. Actual version approval emits fit_committed; idempotent approval emits
fit_skipped(reason="unchanged") with no false fit or updates. No correction labels,
batch result payloads, evidence, source text or passwords are logged.

Host integration handoff: Rust trace validation must allow the operation strings
`review_version`, `correction_reopen`, `replay_reopen` using the existing event field
whitelist, size limit and DB-path checks. Coordinate this change with the Rust owner
through the main integration worker; Python emission alone cannot prove forwarding
by an older host. No new event names or raw-payload fields are required.

No trace includes original text, evidence, source filename/reference, speaker,
personal vocabulary strings, correction labels or arbitrary request IDs.
DB paths, opaque source IDs, parameter values and activity times are still
private metadata. No disk log is created automatically; if you redirect/capture
the terminal, protect that file yourself. Ordinary CLI/API result JSON can still
include evidence/text under its existing contract; the tracing privacy boundary
applies to `[alpha.model]` records, not every business response.

## Quiet mode / Python embedding

```bash
ALPHA_BRAIN_TRACE=0 npm run tauri -- dev
python -m core.api --quiet --db /absolute/path/to/brain.sqlite3
python -m model --quiet --db /absolute/path/to/brain.sqlite3 state
```

The environment switch is inherited at process startup; it is not a frontend
request parameter. For library embedding, defaults remain quiet:
`BrainModel(path, trace=True)`, `BrainCore(path, trace=True)` or
`BrainAPI(path, trace=True)` enables tracing explicitly. Sink failures do not
change a successfully committed model result.
