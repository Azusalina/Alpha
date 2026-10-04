# Offline preference held-out evaluation

This is a database-free audit/evaluator, using the production
`model.preferences.fit_preferences` and `rank_from_fit`. It creates no saved
weights, encoder model, database, imports, downloads, or rule-state changes.
The accompanying manifest is entirely synthetic: three development event
groups and one held-out group. Actual choices prefer option `a`; independent
rational endorsements prefer `b`. Its result is a wiring demonstration, not
evidence about a person or real predictive validity. The template is never
automatically imported.

From `/home/a/Documents/Alpha/back-end-core`, using the supplied offline environment:

```sh
TMPDIR=/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m model.preference_evaluation --manifest docs/preference-evaluation.example.json
```

Add `--details` for held-out opaque case IDs and fixed prediction-reason enums,
or `--validate-only` to check the entire manifest without fitting or ranking.
Successful evaluation/validation prints one JSON object to stdout. Failures
exit 2 with a generic stderr message, including argument and file errors;
paths, identifiers, labels and exception contents are never echoed.

## Closed version 1 manifest

The root has exactly `schema_version` (integer 1), `kind`
(`preference_holdout`), `data_origin` (`synthetic` or `human_collected`),
`protocol`, and `cases`. Other evaluator/readiness manifests are incompatible.
There must be 1–1000 cases. The regular-file JSON loader is reused from
`translator.evaluation`: reads at most 10,000,001 bytes, rejects files larger
than 10,000,000 bytes, duplicate keys at any depth, non-finite numbers, invalid
UTF-8, NUL and surrogate code points. FIFOs/devices are refused. Every object
has a closed field set, including drafts and excluded records. There are no
text, reasons, option descriptions, or private corpus fields.

`protocol` contains `development_end`, `held_out_start`, and `frozen_at`, all
UTC `YYYY-MM-DDTHH:MM:SSZ`, with
`development_end < held_out_start <= frozen_at`.

Each case has exactly these fields:

| Field | Contract |
| --- | --- |
| `id` | Unique opaque case ID, ASCII `[A-Za-z0-9_.-]`, 1–80 characters. |
| `reviewed_group_id` | Opaque manually reviewed event-group ID. Groups cannot cross splits. |
| `source_ids` | Nonempty distinct opaque source IDs, at most 1000. |
| `body_digests` | Nonempty distinct lowercase SHA-256 body identities, at most 1000. These are declarations, not computed from private text. |
| `split` | `development` or `held_out`. |
| `partition` | Production event state: `rational`, `emotional`, or `crazy`. |
| `domain` | Production preference domain: `daily`, `study`, or `relationships`. |
| `event_at` | UTC event time, or null for incomplete provenance. |
| `endorsement_partition` | Explicit state of endorsement; null if the endorsed choice is null. Only rational endorsements are eligible. This can differ from the event partition. |
| `options` | 2–8 distinct opaque option IDs, each with exactly `id` and `impacts`, or null for a draft/unknown options review. |
| `attestations` | Fields described below. |
| `exposure` | Exactly `model_fit`, `rule_development`, `manual_tuning`; each is `none`, `exposed`, or `unknown`. |
| `labels` | Exactly `actual` and `endorsed`, each an independent annotation object described below. |

Impacts may contain only the production eight `value.*` features, with finite
nonboolean numbers in [-1, 1]. Omitted features mean zero, as in production.
Unsupported contrasts still cause abstention. Option display labels are
forbidden. Choice IDs must identify a listed option or be null. A completed
`independent`/`model_assisted` annotation must have a choice. Authenticity
true/false is a whole-source attestation, never either choice label.

`attestations` has exactly `group_review` (`reviewed`, `draft`, or `unknown`),
`whole_source_authenticity` (boolean/null), `training_consent` (boolean/null),
`evaluation_consent` (boolean/null), and `options_review`. The last has exactly
`status`, `reviewer_id`, `blind_to_outputs`, and `reviewed_at`.
Status is `independent`, `model_assisted`, `draft`, or `unknown`; identity and
time can be null; blindness is boolean/null. Each label has exactly `status`,
`annotator_id`, `blind_to_outputs`, `labelled_at`, and `choice_id`, with the
same status/identity/blindness conventions.

Evaluation requires explicit `evaluation_consent: true`. Development fitting
additionally requires `training_consent: true`; held-out scoring does not
require training consent. This local evaluation authorization does not grant
live training or database-import permission. Whole-source authenticity,
reviewed grouping, independently blind options review and independently blind
target annotation must be positively attested. Drafts/unknowns remain in the
audit counts but are ineligible; missing provenance is not filled in.

All declared non-null times are checked, even for ineligible records. Events
must be in their split window. All review/label times follow the event and
precede or equal the split deadline, except development **label** times must
be strictly before `development_end`. Held-out labels must be at or before
`frozen_at`. Missing times exclude eligibility. Shared source IDs or body
digests must belong to the same group AND split, including drafts. This rejects
overlapping train/test provenance and differently grouped copies.

Any held-out member's known/unknown exposure blocks every group member for
both targets. Model-assisted options or either model-assisted label also block
the held-out group, even if exposure fields say `none`. No eligibility filter
can hide malformed or leaking excluded records.

## Training, prediction, and copies

Validation first checks all structural/provenance constraints, including label
membership in options. Training records then come only from eligible development
labels. The other target's choice is masked to null; original source IDs,
digests and annotation metadata never reach the fitter. The production fit's
`source_id` is the `reviewed_group_id`, giving each group equal total loss
mass. Actual fitting uses the event partition; endorsed fitting uses the
rational endorsement state, including events observed in other partitions.
There are separate production fits for both targets and every partition/domain.
There is no pooling to rescue an unsupported axis.

Exact copied event content is deduplicated independently for each target:
group, event time, target axis (partition/domain), canonical options and only
the selected target's choice. Actual identity ignores endorsement state and
endorsed labels; endorsed identity uses the endorsement axis and ignores actual
labels and the source event's partition. Provenance still validates the source
event partition separately.
Case/file IDs, source digests and annotator identities do not distinguish
copies. Option order does not distinguish copies. Meaningful different event
times/options/labels remain separate within-group examples and counterexamples.
After deduplication, the production fitter divides each group's total loss
mass over its remaining informative events. Adding an exact copy cannot
reweight different examples in that group. Provenance is validated before
deduplication; consent or review exclusions are never bypassed by a copy.

Every held-out production query receives only options and a development fit.
All held-out predictions finish before the scoring pass reads held-out choice
values, compares outcomes or deduplicates score units. Structural validation
does not use those labels to fit, tune, choose predictions or generate weights.
The fit's `status`, rather than a hardcoded solver reason, controls abstention;
new solver abstention reasons (such as `fit_not_converged`) need no interface
change here. Ties, unsupported contrasts, conflicting/unidentifiable fits and
untrained axes retain abstention denominators. No calibrated confidence is
reported. Eight-parameter ablation and baselines are explicitly pending.

## Report denominators and privacy

Both targets have overall, partition, domain, and partition/domain summaries,
plus development fit counts/statuses. `all_held_out`, `labelled`, `unlabelled`
and `ineligible` count **every raw case**, including exact copies. `labelled`
means non-null declared choice, even if its annotation is ineligible;
`ineligible` can overlap `unlabelled`. `unique_held_out_events` counts distinct
declared target event content; `copied_event_cases` counts its copies.
`unique_scoring_units`, `duplicate_cases`, `unique_labelled` and
`unique_ineligible` describe scoring deduplication. Scored units deduplicate
exact event content plus target
eligibility/prediction outcome, so adding an excluded variant cannot replace an
eligible variant. Eligibility variants of the same declared event remain
separate scoring units, not independent events; event counts never increase
because eligibility differs. Copies with identical classification have
identical metric outcomes, so the representative chosen cannot change metrics.
Case IDs and input ordering cannot overwrite another classification.
All subsequent evaluated/predicted/correct counts use these
unique units. `evaluated` requires an eligible independent label, `abstain`
is evaluated minus predicted, and `correct` counts matching predictions.

- `coverage = predicted / evaluated`, retaining abstentions.
- `hit_rate = correct / evaluated`, retaining abstentions.
- `conditional_accuracy = correct / predicted` excludes abstentions.
- `all_held_out_coverage` and `all_held_out_hit_rate` use all unique held-out
  scoring units, including ineligible/unlabelled units.

Empty denominators yield null. `macro_group` averages the corresponding
within-group fractions with one equal weight per group having a defined
denominator. It reports all, labelled, ineligible, evaluated and predicted group
counts. Ineligible groups are counted; groups with no evaluated unit have no
evaluated-denominator fraction. Whole-holdout fractions still include them.
Exact copied cases change raw audit counts but cannot improve any hit fraction.
Group balancing alone is not a guarantee of meaningful independent events.

Default reports include no case/group/source IDs, body digests, option IDs,
private reasons, original option labels, impacts, fitted weights, scores or
softmax outputs. Details contain only an opaque case ID and, for each target,
one fixed prediction reason (`predicted`, `ineligible`, `unlabelled`,
`fit_abstained`, or `unsupported_or_tied_options`). The canonical
`manifest_fingerprint` and current implementation hashes identify a run; they
are not anonymization or encryption. `training_only_development`,
`not_calibrated`, `synthetic`, and `validity_claim: false` are explicit.

The freeze time is a declaration, not verified history. There is no persisted
encoder model to freeze: CPU preference weights are ephemeral, rebuilt from
development inputs. Archive the exact manifest and reported implementation
identity when freezing a real protocol; any solver/rule/manual tuning requires
a fresh independent holdout. Current source hashes cannot prove the code had
that identity at the declared historical freeze. Manual group/authenticity/
blindness declarations cannot prove independence, semantic leakage absence,
or statistical validity. This tool does not implement reviewed event groups
in live training. Live grouping, legacy unreviewed-group exclusion and the API
contract remain a separate pending integration phase.

## Synthetic verification

```sh
TMPDIR=/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest tests.test_preference_evaluation -v
```

The same tests are included by backend discovery (`python -B -m unittest
discover -s tests -p 'test_*.py'`); targeted discovery uses
`python -B -m unittest discover -s tests -p test_preference_evaluation.py`.

Tests use synthetic metadata/options, strict-loader fixtures and temporary
files only. They deny database connections and network access while exercising
the actual fitter/ranker. No private corpus or real-data validation is involved.
