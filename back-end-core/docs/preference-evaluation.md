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
TMPDIR=/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /tmp/alpha-verify-20261005-night.khVPhV/bin/python -B -m model.preference_evaluation --manifest docs/preference-evaluation.example.json
```

Add `--details` for held-out opaque case IDs and fixed prediction-reason enums,
or `--validate-only` to check the entire manifest without fitting or ranking.
Add `--comparisons` to request descriptive offline baselines and eight fixed
leave-one-feature-out ablations. The Python entry point is
`evaluate_manifest(manifest, *, details=False, validate_only=False, comparisons=False)`;
all three flags require actual booleans, without coercion. Validation-only
never fits, predicts, computes baselines or scores, even with comparisons enabled.
Default report keys are preserved: `baselines` and `ablation_eight_parameters`
are `not_requested` (replacing the historical `pending` markers). Requested
validation-only comparisons use `not_run_validation_only`; completed comparisons
use `completed` and add a `comparisons` object. Schema version 1 is unchanged;
no production API or contract revision changes are involved.
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
mass. Reported `informative_training_groups` comes from the fit's authoritative
`training_groups` count, rather than its separate `training_sources` count.
Actual fitting uses the event partition; endorsed fitting uses the
rational endorsement state, including events observed in other partitions.
There are separate production fits for both targets and every partition/domain.
There is no pooling to rescue an unsupported axis.

Each development-fit summary reports `contrast_rank` directly from that
axis's production fit: an integer from 0 to 8 giving the number of independent
directions in its admitted development option contrasts. The production fitter
constructs an internal orthonormal `contrast_basis` from those same informative
events. Neither another target's labels nor events outside that partition/domain
can expand the fit's geometry. Held-out options and choices never contribute
directions. Both rank and internal basis remain unchanged when only held-out
choices change. Zero rank and an abstained fit remain reportable; a nonzero rank
does not override the fit's abstention status or group-support gate.

Every query contrast must lie in its own fitted development span, within the
production numerical tolerance, and pass the existing feature-support check.
Varying two features together can supply only one direction: three reviewed
groups with development contrasts `[growth=1, security=1]` have rank 1 even
though both features are present. A held-out contrast `[growth=1, security=-0.5]`
is outside that span and must abstain. Independently varying growth in eligible
development events supplies the missing direction and can support that query.
The L2 penalty picks weights but cannot establish a preference direction absent
from the admitted design. Rank does not establish individual parameter
magnitudes, sound feature measurement, personal predictive validity, or calibrated
confidence; even rank 8 does not establish these claims. The opt-in comparisons
below are descriptive engineering checks, not real predictive validation.

Exact copied event content is deduplicated independently for each target:
group, event time, target axis (partition/domain), canonical options and only
the selected target's choice. Actual identity ignores endorsement state and
endorsed labels; endorsed identity uses the endorsement axis and ignores actual
labels and the source event's partition. Provenance still validates the source
event partition separately.
Case/file IDs, source digests and annotator identities do not distinguish
copies. Option order does not distinguish copies. After validation, canonical
options sort by option ID and represent impacts as sparse floats with exact
zeros removed: omitted features, `0`, `0.0` and `-0.0` are equivalent, as are
integer and float forms of equal nonzero values (for example, `1` and `1.0`).
This shared representation is used for development record deduplication and
post-prediction metric identity, as well as production queries. It does not
mutate the input or round impacts; even tiny nonzero values and adjacent
distinct floats retain their meaning and distinct identities. Numeric copies
can increase raw audit counts but cannot change training record counts,
weights, query results or unique-unit/group metrics. The manifest fingerprint
still identifies the supplied manifest representation.
Meaningful different event
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
change here. Ties, unsupported or out-of-span contrasts, conflicting/unidentifiable fits and
untrained axes retain abstention denominators. No calibrated confidence is
reported. Optional baselines and ablations obey the same prediction-before-scoring
boundary: all full and variant queries and baseline distributions finish before
any held-out scoring choice is read. Structural validation remains permitted.

## Opt-in offline comparisons

Run the synthetic protocol with:

```sh
TMPDIR=/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /tmp/alpha-verify-20261005-night.khVPhV/bin/python -B -m model.preference_evaluation --manifest docs/preference-evaluation.example.json --comparisons
```

The eleven predeclared variants are `full`, `equal_weight`, `chance`, and
`drop:value.autonomy`, `drop:value.fairness`, `drop:value.care`, `drop:value.truth`,
`drop:value.security`, `drop:value.growth`, `drop:value.achievement`,
`drop:value.connection`, in the production fixed column order. These eight
names are public protocol identifiers; they do not disclose learned features.

`equal_weight` is a **nonpersonal heuristic**: sum all eight supplied impacts,
using zero for missing features, and select the unique largest sum. It does not
model rational endorsement or maximum personal utility. It fits nothing and
receives no choices or learned state. A top-two sum gap at or below the fixed
absolute tolerance `1e-9` abstains, including a tied top pair with lower-ranked
options. No tolerance, feature or coefficient is tuned on this holdout.

`chance` is the analytic expectation of a hypothetical uniform choice from
the original `n` options: expected correctness is exactly `1/n`. It performs
no random draws and creates no option choice or deterministic correct count.
`expected_correct` is a float summing those probabilities over eligible unique
units, using `math.fsum`; `expected_hit_rate` divides by evaluated units, and
`expected_conditional_accuracy` divides by units with a distribution available.
`expected_all_held_out_hit_rate` uses all original scoring units. The same
expected rates have equal-group macro summaries. `predicted`, `coverage` and
`predicted_groups` in this variant mean **analytic distribution availability**,
not observed stochastic decisions. On eligible units the distribution is always
available, including tied impacts. Its exact hypothetical expectation is not a
calibrated personal probability, fitted confidence or empirical accuracy.

Both general baselines share target eligibility, consent, contamination and
axis rules with all variants. They do not require trained groups or learned
feature/span support and can cover queries refused by a production model.
Their broader coverage is disclosed rather than gated by the full fit.

Each ablation removes one column from both development and query impacts
(equivalently fixes that coordinate to zero) and retrains through the unchanged
production fitter with its existing loss, group normalization, support, span,
tie and convergence guards. Admission and canonical numeric deduplication occur
once per target/partition/domain, on the ORIGINAL development records. Every
ablation receives that same ordered record cohort, labels, event multiplicity,
group ownership and target masking. No second deduplication occurs after
projection: distinct original events can become identical in projection and
still remain original events. Numeric copies and option permutations do not
reweight any fit or evaluation. There is no axis pooling.

The production fitter can remove newly unidentifiable events after projection:
an all-equal option design, or a chosen vector equal to another option vector,
does not supply informative support. Each ablation's per-axis `training` entry
reports `original_training_records`, `original_eligible_development_groups`,
`original_informative_training_events`, `original_informative_training_groups`,
and `original_contrast_rank`, alongside `training_records`,
`informative_training_events`, `informative_training_groups`, `contrast_rank`,
and `fit_status`. Group count and rank come from the production fit; the event
count mirrors its exact-vector admission guard on these screened records.
Records remain in the supplied cohort even when the fit removes their support.
Full comparison training adds `informative_training_events` to the existing
training summary; the ordinary report's training shape is unchanged. Baselines
have no training summary.

This opt-in mode performs nine production fits per axis (full plus eight
ablations), rather than one: 162 rather than 18 fit calls for the two targets,
three partitions and three domains, including unsupported axes. It also runs
nine model query passes and the two fixed baselines. Original admitted records
are retained only in comparison mode. The existing 1–1000 case bound and
production `MAX_RECORDS` limit remain in force; no larger input limit, packages,
network access, saved weights or database access are introduced.

The added JSON object's keys are:

```json
{
  "cohort_identity": "original_event_and_target_eligibility",
  "pairwise_cohort": "BOTH_PREDICTED",
  "chance_mode": "analytic_uniform_expectation_no_draws",
  "chance_coverage_interpretation": "analytic_distribution_availability",
  "equal_weight_tie_tolerance": 1e-9,
  "feature_drop_order": ["value.autonomy", "value.fairness", "value.care", "value.truth", "value.security", "value.growth", "value.achievement", "value.connection"],
  "automatic_selection": false,
  "validity_claim": false,
  "variants": {},
  "full_vs_variant": {}
}
```

The empty maps above stand for these populated structures:

- `variants[variant]` contains `kind` and `targets`. Kinds are `production_full`,
  `nonpersonal_equal_weight_sum_heuristic`, `analytic_uniform_chance`, and
  `production_leave_one_feature_out`. Each of `targets.actual` and
  `targets.endorsed` contains `overall`, `by_partition`, `by_domain`, and
  `by_partition_domain`, plus `training` for model variants.
- Deterministic variant summaries use the existing counts, coverage, hit rates,
  conditional accuracy and `macro_group` fields. Chance replaces `correct`,
  `hit_rate`, `conditional_accuracy` and `all_held_out_hit_rate` with the
  corresponding `expected_*` fields, including the macro rates.
- `full_vs_variant[variant].targets[target]` uses the same four summary levels
  for each of the ten non-full variants. Each summary has
  `unique_scoring_units`, `evaluated`, `full_predicted`, `variant_predicted`,
  `both_predicted`, `full_only_predicted`, `variant_only_predicted`,
  `neither_predicted`, `full_coverage`, `variant_coverage`,
  `both_predicted_coverage`, `all_held_out_both_predicted_coverage`,
  `full_correct`, `variant_correct`, `full_hit_rate`, `variant_hit_rate`,
  `full_correct_on_both`, `variant_correct_on_both`, `full_accuracy_on_both`,
  and `variant_accuracy_on_both`. The four intersection outcomes are
  `both_correct`, `full_only_correct`, `variant_only_correct`, and
  `neither_correct`, each with an accompanying `*_cohort_rate`.
  For chance, all variant-correctness fields and all four outcomes/rates
  use the `expected_` prefix; full-only counts remain observed full-model counts.
- Pair summaries contain `macro_group` and `cohort_macro_group`. Both report
  `all_held_out_groups`, `evaluated_groups` and `both_predicted_groups`, plus
  the same coverage/rate/accuracy fields. `macro_group` averages groups with
  `both_predicted > 0`, each with one equal weight; `cohort_macro_group`
  averages groups with `evaluated > 0`, retaining groups with no intersection.
  Intersection accuracies remain null when no group supplies their denominator.

All comparisons use a common original event identity and target eligibility
classification; neither projected options nor prediction outcomes define the
unit identity. Original events with different options cannot collapse after
projection. Copied eligible and excluded representations remain separate
eligibility units, without allowing a copy to replace the other classification.
Raw audit counts still include copies; unique-unit and equal-group metrics do not.
The ordinary full report remains available under the existing top-level
`targets`; its historical identity includes the prediction outcome, whereas
the full comparison variant uses the shared original comparison identity.

`BOTH_PREDICTED` is the intersection of eligible units on which full and variant
both predict (or full predicts and the chance distribution is available).
Intersection accuracies divide by `both_predicted`. Coverage and hit rates,
and every outcome's `*_cohort_rate`, divide by the fixed ORIGINAL `evaluated`
cohort; `all_held_out_both_predicted_coverage` divides by all original units.
The four outcomes sum to the intersection size, while exclusive and neither
prediction counts expose support loss. These denominators prevent a gain in
conditional accuracy on a smaller cohort from silently becoming a quality gain.
No predictions, impacts, labels, fitted coefficients or geometry are added to
default or detailed reports; details retain only the existing opaque case IDs
and full-model reason enums.

Comparisons are descriptive, not proof of parameter selection, statistical
significance, calibration or personal predictive validity. There are no
p-values, significance claims, automatic winners, selection or promotion.
If held-out results are used to choose features, parameters, rules or tolerances,
that holdout becomes development data: a NEW independent holdout is required
for final validity assessment. These boundaries also appear as fixed report
limitations. An implementation fingerprint identifies current code and does
not certify any of these validity properties.

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
private reasons, original option labels, impacts, fitted weights, scores,
softmax outputs, learned feature lists or raw contrast geometry/basis. The
opt-in static eight feature names identify the public comparison protocol.
Only the scalar
`contrast_rank` is added to development-fit summaries. Details contain only an
opaque case ID and, for each target,
one fixed prediction reason (`predicted`, `ineligible`, `unlabelled`,
`fit_abstained`, or `unsupported_or_tied_options`). A provisional fit refusing
an out-of-span query uses the existing `unsupported_or_tied_options` reason,
retains its eligible unit in `evaluated` and `abstain`, and lowers coverage and
hit-rate denominators in the same way as other query abstentions. The canonical
`manifest_fingerprint` and current implementation hashes are lowercase
64-character hexadecimal SHA-256 strings. The implementation identity covers
`model/preference_evaluation.py`, `model/preferences.py`, `model/contrast.py`,
`model/ranking.py` and `model/catalog.py`. These fingerprints identify a run; they
are not anonymization or encryption. `training_only_development`,
`not_calibrated`, `synthetic`, and `validity_claim: false` are explicit.

The freeze time is a declaration, not verified history. There is no persisted
encoder model to freeze: CPU preference weights are ephemeral, rebuilt from
development inputs. Archive the exact manifest and reported implementation
identity when freezing a real protocol; any solver/rule/manual tuning requires
a fresh independent holdout. Current source hashes cannot prove the code had
that identity at the declared historical freeze. Manual group/authenticity/
blindness declarations cannot prove independence, semantic leakage absence,
or statistical validity. This tool supplies the offline reviewed-group identity
as a screened `source_id`; it does not open the database or grant consent for
live training. Live provenance/grouping guards and API contracts require
verification separately from this manifest audit.

## Synthetic verification

```sh
TMPDIR=/tmp HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /tmp/alpha-verify-20261005-night.khVPhV/bin/python -B -m unittest tests.test_preference_evaluation -v
```

The same tests are included by backend discovery (`python -B -m unittest
discover -s tests -p 'test_*.py'`); targeted discovery uses
`python -B -m unittest discover -s tests -p test_preference_evaluation.py`.

Tests use synthetic metadata/options, strict-loader fixtures and temporary
files only. They deny database connections and network access while exercising
the actual fitter/ranker. No private corpus or real-data validation is involved.
Geometry regressions cover a rank-1 joint growth/security design refusing the
`[1, -0.5]` query while retaining abstention denominators, an independently
supported rank-2 companion, and rank 8 from three groups spanning all eight
features. They also check target/partition/domain isolation at both fit and
query boundaries, held-out label flips preserving internal geometry and
predictions, exact per-axis scalar rank reporting, strict current-source
SHA-256 identities, and omission of raw geometry from default and detail reports.
Comparison regressions extend the prediction-before-label-read guard to all
variants, perturb held-out choices while checking identical fits and predictions,
verify single original admission/no projection deduplication, numeric copies,
option permutations, axis/consent/contamination isolation, informative support
loss and abstention, exact chance expectations, fixed heuristic ties, pairwise
intersection and cohort/group denominators, input immutability, strict boolean
flags, privacy and generic CLI errors. Only this focused test module is required
for the comparison implementation owner's verification.
