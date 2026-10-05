# Typed correction validation resources

## Scope and consistency

`model.corrections.validate_corrections` now lazily translates the complete
source at most **once per validation function invocation**. The local report is
created only when the first typed correction passes the existing shape, exact
span/evidence, authorship, family and sign checks. Later typed items in that
invocation reuse that report. It is discarded when the invocation ends.

This is a single deterministic translator snapshot for one invocation. The
current rule translator depends on the same source text, effective kind and
self speaker for every item, so repeating translation used to produce the same
report. Reuse preserves that behavior. A future nondeterministic translator
would need to honor this single-snapshot policy or explicitly revisit it.
No persistent/global report cache, target index, encoder or model was added.

The budget is **not one translation per JSON/API request**. In particular,
`BrainModel.correction_reopen` still calls validation twice: once optimistically,
then again after taking the transaction lock and rechecking the source/guards.
Each invocation gets its own fresh report. The observations path also performs
its own translation. These concurrency checks and downstream translations are
unchanged; the benchmark below measures only `validate_corrections`.

All existing validation steps, their order and exceptions remain in place.
Philosophy still translates as diary; chat requires exact self-speaker ranges.
Events still target `event_word` cues, intent targets `contact_intention`, tone
targets `textual_emotion`, and candidate targets any candidate. Duplicate aliases
share candidate identity; cue and candidate identities stay separate even at
the same offsets. Typed signs remain integers 0/1; parameter sign/uniqueness
rules, Unicode spans, input immutability and copied output spans are unchanged.
The total batch limit remains 64.

## Deterministic call budget

Let `T` be the number of typed items reached through their pretranslation checks
before returning or raising; parameter items do not contribute to `T`.

| Invocation | Previous translate calls | Current translate calls |
| --- | ---: | ---: |
| Empty or parameter-only | 0 | 0 |
| Invalid array or more than 64 items | 0 | 0 |
| Failure before any typed item needs translation | 0 | 0 |
| At least one typed item needs translation | T, up to 64 | 1 |
| 64 distinct valid typed targets | 64 | 1 |

An invalid later record does not initiate another translation. A valid typed
prefix can already have used the one report before that record fails.
Translation errors still propagate at the first eligible typed item.

## Validation evidence

`tests/test_correction_resources.py` contains 12 synthetic tests, including an
independent frozen copy of the pre-change validator. Differential checks compare
successful lists or exact exception class/message and separately count calls.
The reference body was checked by AST against the original validation body;
undoing only the small lazy-reuse edit reconstructs the original file SHA-256:

```text
34657c0903ff823cd39ccf778816efe3adefcb641c7412666075f0a72670ae79
```

Coverage includes all four families and typed signs, their order permutations
with mixed parameters, negative value parameter signs, duplicate/alias rejection
in both orders and signs, distinct repeated positions, cue/candidate identity at
one position, invalid batches and malformed fields, exact targets and family
filters, quote/code/negation guards, diary/philosophy and chat ownership with
CRLF and non-BMP Unicode offsets, translator exceptions, fresh invocations, and
input/output/report mutation isolation. The same-position identity test uses an
explicit synthetic translator report; source-policy tests use the real rule
translator. No database is required by the new tests or benchmark.

From `/home/a/Documents/Alpha/back-end-core`:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/alpha-verify-20261005-night.khVPhV/bin/python -m unittest tests.test_correction_resources tests.test_corrections tests.test_revisions
```

Recorded 2026-10-06: all 40 tests passed (12 new resource tests, 8 correction
tests, 20 revision tests). Existing integration tests use temporary synthetic
databases. Only these modules were run, leaving the full suite to the main
owner. The existing jieba dependency emitted its `pkg_resources` deprecation
warning during integration tests.

## Bounded synthetic measurement

Reproduce from the same directory with the same interpreter:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/alpha-verify-20261005-night.khVPhV/bin/python -m tests.test_correction_resources --benchmark
```

The source is exactly `('中性记录' * 384 + '。我很开心。\n') * 64`:
98,752 Python Unicode characters, 296,128 UTF-8 bytes, 64 blocks, 64 distinct
tone target spans, 64 emotion-word cues and 64 textual-emotion
candidates. All 64 corrections target those distinct tone positions, with
alternating suppress/retain signs. Both validators return the same batch.
Interpreter: CPython 3.14.7, GCC 16.1.1, existing local environment above.

Calls are counted in a separate wrapped-translator run. Each algorithm is warmed
once, then measured for three untraced `time.perf_counter` validation runs.
Three separate `tracemalloc` runs measure peak Python allocation bytes, including
translation and validation. Garbage collection runs before each trial; source,
batch, imports and fixture construction precede measurement. There is no
walltime assertion. Values below are the final recorded benchmark run on
2026-10-06; machine load can affect timing.

| Measure per validation invocation | Before (frozen legacy) | After |
| --- | ---: | ---: |
| Complete-source translator calls | 64 | 1 |
| Time trial 1, seconds | 2.704405503 | 0.057367233 |
| Time trial 2, seconds | 2.857913091 | 0.056117566 |
| Time trial 3, seconds | 2.900876628 | 0.058904482 |
| Median time, seconds | 2.857913091 | 0.057367233 |
| Peak Python allocation trial 1, bytes | 542,710 | 429,267 |
| Peak Python allocation trial 2, bytes | 542,710 | 429,267 |
| Peak Python allocation trial 3, bytes | 542,710 | 429,267 |
| Median peak Python allocation, bytes | 542,710 | 429,267 |

These are local function timings and Python allocations for this exact fixture.
They do not measure native RSS, database/transaction cost, API/request latency,
encoder performance or frontend responsiveness. The smaller allocation peak
does not imply a 64-fold memory reduction: the old reports were temporary too.

## Remaining work per invocation

For translator cost `P(N)` on source length `N`, translation work changes from
`T * P(N)` to at most `P(N)`. Existing per-item filtering and exact-match scans
are deliberately retained: `O(T * R)` over report rows `R`, with up to 64 typed
items. Existing exact-evidence comparisons and chat author-range scans also
remain; for `A` author ranges the latter can cost `O(64 * A)`.

Validation retains one translation report plus the at-most-64-item batch,
checked span copies and duplicate tracking. Temporary pool/target lists contain
references to report rows and are `O(R)`; chat author ranges are `O(A)`.
The translator itself still has transient source-sized parsing/indexing
allocations. Memory is source/report-sized, not an input-independent constant,
and no reports accumulate across invocations. An index is unnecessary for this
change and would enlarge the semantic review surface.

This document is evidence for main-owner verification; active TODO/log files and
archive status were not edited.
