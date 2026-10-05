"""Offline preference holdout audit using the production pure CPU fitter.

No corpus text, database, encoder, saved weights, or template import. A valid
manifest audits declarations; it cannot prove annotation independence.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from model import preferences
from model.catalog import PARTITIONS
from model.ranking import VALUE_PARAMETERS, validate_options
from translator.evaluation import load_manifest as _load_manifest, validate_json_strings

MAX_CASES = 1000
MAX_FILE_BYTES = 10_000_000
# Absolute top-two sum gap; fixed before any manifest is read or labels scored.
EQUAL_WEIGHT_TIE_TOLERANCE = 1e-9
_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_REVIEWS = ("independent", "model_assisted", "draft", "unknown")
_ERROR = "Invalid or unreadable preference manifest; no database was opened.\n"


def _fields(value: object, fields: set[str]) -> None:
    # Closed schemas and fixed errors follow model/readiness.py; never echo data.
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("missing or unknown manifest fields")


def _id(value: object) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("identifiers must be bounded opaque ASCII tokens")


def _boolean(value: object) -> None:
    if value is not None and type(value) is not bool:
        raise ValueError("attestations must be boolean or null")


def _time(value: object) -> datetime:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        raise ValueError("times require UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError("invalid UTC time") from None


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()


def _options(value: object) -> None:
    if not isinstance(value, list) or not 2 <= len(value) <= 8:
        raise ValueError("provide two to eight options")
    for option in value:
        _fields(option, {"id", "impacts"})
        _id(option["id"])
        impacts = option["impacts"]
        if not isinstance(impacts, dict) or len(impacts) > len(VALUE_PARAMETERS):
            raise ValueError("invalid option impacts")
        for feature, impact in impacts.items():
            if (feature not in VALUE_PARAMETERS or type(impact) not in (int, float)
                    or not -1 <= impact <= 1 or not math.isfinite(impact)):
                raise ValueError("invalid option impacts")
    validate_options(value)


def _annotation(value: object, *, options: bool, event: datetime | None,
                deadline: datetime, development: bool) -> None:
    _fields(value, {"status", "reviewer_id", "blind_to_outputs", "reviewed_at"} if options
            else {"status", "annotator_id", "blind_to_outputs", "labelled_at", "choice_id"})
    if value["status"] not in _REVIEWS:
        raise ValueError("invalid annotation status")
    _boolean(value["blind_to_outputs"])
    identity = value["reviewer_id" if options else "annotator_id"]
    if identity is not None:
        _id(identity)
    timestamp = value["reviewed_at" if options else "labelled_at"]
    if timestamp is not None:
        time = _time(timestamp)
        if (time > deadline or (development and not options and time >= deadline)
                or (event is not None and time < event)):
            raise ValueError("annotation is outside its split time window")


def validate_manifest(manifest: object) -> list[dict]:
    """Validate ALL provenance and labels, including ineligible cases.

    Label access here is structural validation only. No fit, prediction,
    eligibility for scoring, or metric calculation occurs in this function.
    """
    _fields(manifest, {"schema_version", "kind", "data_origin", "protocol", "cases"})
    validate_json_strings(manifest)
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("invalid preference manifest version")
    if manifest["kind"] != "preference_holdout" or manifest["data_origin"] not in ("synthetic", "human_collected"):
        raise ValueError("invalid preference manifest kind or origin")
    protocol = manifest["protocol"]
    _fields(protocol, {"development_end", "held_out_start", "frozen_at"})
    end, start, frozen = (_time(protocol[key]) for key in ("development_end", "held_out_start", "frozen_at"))
    if not end < start <= frozen:
        raise ValueError("invalid development/holdout/freeze ordering")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("provide one to one thousand cases")
    seen, groups, sources, digests = set(), {}, {}, {}
    for case in cases:
        _fields(case, {"id", "reviewed_group_id", "source_ids", "body_digests", "split",
                       "partition", "domain", "event_at", "endorsement_partition", "options",
                       "attestations", "exposure", "labels"})
        _id(case["id"])
        _id(case["reviewed_group_id"])
        if case["id"] in seen:
            raise ValueError("duplicate case identifier")
        seen.add(case["id"])
        if (case["split"] not in ("development", "held_out") or case["partition"] not in PARTITIONS
                or case["domain"] not in preferences.DOMAINS):
            raise ValueError("invalid split, partition or domain")
        if case["endorsement_partition"] is not None and case["endorsement_partition"] not in PARTITIONS:
            raise ValueError("invalid endorsement partition")
        owner = (case["reviewed_group_id"], case["split"])
        if owner[0] in groups and groups[owner[0]] != owner[1]:
            raise ValueError("a reviewed group crosses splits")
        groups[owner[0]] = owner[1]
        for field, registry, pattern in (("source_ids", sources, _ID), ("body_digests", digests, _DIGEST)):
            values = case[field]
            if not isinstance(values, list) or not 1 <= len(values) <= MAX_CASES:
                raise ValueError("provenance identifiers must be a bounded nonempty array")
            for value in values:
                if not isinstance(value, str) or pattern.fullmatch(value) is None:
                    raise ValueError("invalid provenance identifier")
                if value in registry and registry[value] != owner:
                    raise ValueError("shared provenance must stay in one group and split")
                registry[value] = owner
            if len(set(values)) != len(values):
                raise ValueError("duplicate provenance identifier")
        event = _time(case["event_at"]) if case["event_at"] is not None else None
        deadline = end if owner[1] == "development" else frozen
        if event is not None and (event > deadline or (owner[1] == "held_out" and event < start)):
            raise ValueError("event is outside its split time window")
        attestations = case["attestations"]
        _fields(attestations, {"group_review", "whole_source_authenticity", "training_consent",
                              "evaluation_consent", "options_review"})
        if attestations["group_review"] not in ("reviewed", "draft", "unknown"):
            raise ValueError("invalid group review status")
        _boolean(attestations["whole_source_authenticity"])
        _boolean(attestations["training_consent"])
        _boolean(attestations["evaluation_consent"])
        _annotation(attestations["options_review"], options=True, event=event, deadline=deadline,
                    development=owner[1] == "development")
        exposure = case["exposure"]
        _fields(exposure, {"model_fit", "rule_development", "manual_tuning"})
        if any(value not in ("none", "exposed", "unknown") for value in exposure.values()):
            raise ValueError("invalid exposure status")
        labels = case["labels"]
        _fields(labels, set(preferences.TARGETS))
        for target in preferences.TARGETS:
            _annotation(labels[target], options=False, event=event, deadline=deadline,
                        development=owner[1] == "development")
        if case["options"] is None:
            if attestations["options_review"]["status"] not in ("draft", "unknown"):
                raise ValueError("missing options require draft or unknown review")
            option_ids = set()
        else:
            _options(case["options"])
            option_ids = {option["id"] for option in case["options"]}
        for label in labels.values():
            choice = label["choice_id"]
            if choice is not None:
                _id(choice)
                if choice not in option_ids:
                    raise ValueError("choice must identify an option")
            if choice is None and label["status"] in ("independent", "model_assisted"):
                raise ValueError("completed annotations require a choice")
        if labels["endorsed"]["choice_id"] is None:
            if case["endorsement_partition"] is not None:
                raise ValueError("null endorsement requires null endorsement partition")
        elif case["endorsement_partition"] is None:
            raise ValueError("endorsed choices require an explicit endorsement state")
    return copy.deepcopy(cases)


def load_manifest(path: str | Path) -> object:
    """Reuse translator.evaluation's bounded, regular-file duplicate-key loader."""
    return _load_manifest(path, max_bytes=MAX_FILE_BYTES)


def _independent(annotation: dict, *, options: bool = False) -> bool:
    return (annotation["status"] == "independent" and annotation["blind_to_outputs"] is True
            and annotation["reviewer_id" if options else "annotator_id"] is not None
            and annotation["reviewed_at" if options else "labelled_at"] is not None)


def _contaminated_groups(cases: list[dict]) -> set[str]:
    # Metadata only: no choice values. A clean file cannot hide another variant.
    return {case["reviewed_group_id"] for case in cases if case["split"] == "held_out" and
            (any(value != "none" for value in case["exposure"].values())
             or case["attestations"]["options_review"]["status"] == "model_assisted"
             or any(label["status"] == "model_assisted" for label in case["labels"].values()))}


def _common_eligible(case: dict, contaminated: set[str]) -> bool:
    attestations = case["attestations"]
    return (case["event_at"] is not None and case["options"] is not None
            and attestations["group_review"] == "reviewed"
            and attestations["whole_source_authenticity"] is True
            and attestations["evaluation_consent"] is True
            and _independent(attestations["options_review"], options=True)
            and case["reviewed_group_id"] not in contaminated)


def _axis(case: dict, target: str) -> tuple[str, str]:
    # Endorsement state is distinct from the state of the observed event.
    partition = case["partition"] if target == "actual" else (case["endorsement_partition"] or case["partition"])
    return partition, case["domain"]


def _label_eligible(case: dict, target: str) -> bool:
    return (_independent(case["labels"][target])
            and (target == "actual" or case["endorsement_partition"] == "rational"))


def _canonical_options(options: list[dict]) -> list[dict]:
    """Canonicalize validated impacts as production floats, omitting exact zeros."""
    return [{"id": option["id"],
             "impacts": {feature: float(option["impacts"][feature])
                         for feature in VALUE_PARAMETERS
                         if feature in option["impacts"] and option["impacts"][feature] != 0}}
            for option in sorted(options, key=lambda option: option["id"])]


def _event_identity(case: dict, target: str) -> str:
    """Copied event content, independent of case/file/annotation-person IDs.

    Used for development fitting, or AFTER held-out predictions for scoring.
    Distinct event times and conflicting labels remain distinct counterexamples.
    """
    return _hash({"group": case["reviewed_group_id"], "event_at": case["event_at"],
                  "target": target, "axis": _axis(case, target),
                  "options": _canonical_options(case["options"]) if case["options"] is not None else None,
                  "choice": case["labels"][target]["choice_id"]})


def _development_records(cases: list[dict], target: str, partition: str, domain: str) -> tuple[list[dict], int]:
    records, seen, labelled = [], set(), 0
    for case in cases:
        if (case["split"] != "development" or _axis(case, target) != (partition, domain)
                or not _common_eligible(case, set()) or not _label_eligible(case, target)):
            continue
        if case["attestations"]["training_consent"] is not True:
            continue
        choice = case["labels"][target]["choice_id"]
        if choice is None:
            continue
        labelled += 1
        record = {"source_id": case["reviewed_group_id"], "partition": case["partition"],
                  "domain": domain, "options": _canonical_options(case["options"]),
                  "actual_choice_id": choice if target == "actual" else None,
                  "endorsed_choice_id": choice if target == "endorsed" else None,
                  "endorsement_partition": "rational" if target == "endorsed" else None,
                  "training_consent": True}
        # Exact duplicate variants within a group add neither support nor loss.
        identity = _event_identity(case, target)
        if identity not in seen:
            seen.add(identity)
            records.append(record)
    return sorted(records, key=_hash), labelled


def _project_options(options: list[dict], dropped: str | None) -> list[dict]:
    return [{"id": option["id"], "impacts": {key: value for key, value in option["impacts"].items()
                                            if key != dropped}}
            for option in _canonical_options(options)]


def _predict_all(cases: list[dict], contaminated: set[str], fits: dict,
                 dropped: str | None = None) -> dict:
    """Finish ALL held-out queries before any scoring inspects choice values."""
    predictions = {}
    for case in cases:
        if case["split"] != "held_out":
            continue
        for target in preferences.TARGETS:
            axis = _axis(case, target)
            fit = fits[(target, *axis)]
            if not _common_eligible(case, contaminated):
                prediction, reason = None, "ineligible"
            else:
                # Only options and the development fit reach production scoring.
                ranked = preferences.rank_from_fit(_project_options(case["options"], dropped), fit)
                prediction = ranked[0]["id"] if ranked else None
                reason = ("predicted" if ranked else
                          "fit_abstained" if fit["status"] == "abstain" else "unsupported_or_tied_options")
            predictions[(case["id"], target)] = (prediction, reason)
    return predictions


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _counts(rows: list[dict]) -> dict:
    units = {(row["group"], row["unit"]): row for row in rows}
    unique = list(units.values())
    evaluated = sum(row["evaluated"] for row in unique)
    predicted = sum(row["predicted"] for row in unique)
    correct = (math.fsum(row["correct"] for row in unique)
               if any(type(row["correct"]) is float for row in unique)
               else sum(row["correct"] for row in unique))
    events = {(row["group"], row["event"]) for row in rows}
    return {"all_held_out": len(rows), "unique_held_out_events": len(events),
            "unique_scoring_units": len(unique), "copied_event_cases": len(rows) - len(events),
            "duplicate_cases": len(rows) - len(unique),
            "labelled": sum(row["labelled"] for row in rows),
            "unique_labelled": sum(row["labelled"] for row in unique),
            "unique_ineligible": sum(row["ineligible"] for row in unique),
            "unlabelled": sum(not row["labelled"] for row in rows),
            "ineligible": sum(row["ineligible"] for row in rows), "evaluated": evaluated,
            "abstain": evaluated - predicted, "predicted": predicted, "correct": correct,
            "coverage": _ratio(predicted, evaluated), "hit_rate": _ratio(correct, evaluated),
            "conditional_accuracy": _ratio(correct, predicted),
            "all_held_out_coverage": _ratio(predicted, len(unique)),
            "all_held_out_hit_rate": _ratio(correct, len(unique))}


def _summary(rows: list[dict]) -> dict:
    result = _counts(rows)
    groups = defaultdict(dict)
    for row in rows:
        # Macro units collapse identical target views; file copies cannot alter
        # a group's composition. Case-level counts still include every case.
        groups[row["group"]][row["unit"]] = row
    summaries = [_counts(list(units.values())) for units in groups.values()]
    def mean(key: str) -> float | None:
        values = [summary[key] for summary in summaries if summary[key] is not None]
        return math.fsum(values) / len(values) if values else None
    result["macro_group"] = {
        "all_held_out_groups": len(groups),
        "labelled_groups": sum(summary["labelled"] > 0 for summary in summaries),
        "ineligible_groups": sum(summary["ineligible"] > 0 for summary in summaries),
        "evaluated_groups": sum(summary["evaluated"] > 0 for summary in summaries),
        "predicted_groups": sum(summary["predicted"] > 0 for summary in summaries),
        "coverage": mean("coverage"), "hit_rate": mean("hit_rate"),
        "conditional_accuracy": mean("conditional_accuracy"),
        "all_held_out_coverage": mean("all_held_out_coverage"),
        "all_held_out_hit_rate": mean("all_held_out_hit_rate"),
    }
    return result


def _implementation_identity() -> dict:
    root = Path(__file__).resolve().parents[1]
    paths = ("model/preference_evaluation.py", "model/preferences.py", "model/contrast.py",
             "model/ranking.py", "model/catalog.py")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def _equal_weight_choice(options: list[dict]) -> str | None:
    scored = sorted((math.fsum(option["impacts"].get(feature, 0.0)
                              for feature in VALUE_PARAMETERS), option["id"])
                    for option in _canonical_options(options))
    return (scored[-1][1] if scored[-1][0] - scored[-2][0] > EQUAL_WEIGHT_TIE_TOLERANCE
            else None)


def _baseline_predictions(cases: list[dict], contaminated: set[str]) -> dict:
    # Neither baseline receives fit state, annotations, or choices. Chance is
    # an analytic probability, never a sampled/pseudo-deterministic option ID.
    predictions = {"equal_weight": {}, "chance": {}}
    for case in cases:
        if case["split"] != "held_out":
            continue
        eligible = _common_eligible(case, contaminated)
        equal = _equal_weight_choice(case["options"]) if eligible else None
        chance = 1 / len(case["options"]) if eligible else None
        for target in preferences.TARGETS:
            key = (case["id"], target)
            predictions["equal_weight"][key] = equal
            predictions["chance"][key] = chance
    return predictions


def _informative_events(records: list[dict], target: str) -> int:
    # Mirror only the production fitter's exact-vector identifiability filter
    # for these already admitted per-axis records; do not deduplicate projection.
    count = 0
    for record in records:
        choice = record[target + "_choice_id"]
        vectors = {option["id"]: tuple(option["impacts"].get(feature, 0.0)
                                        for feature in VALUE_PARAMETERS)
                   for option in record["options"]}
        count += (choice is not None and
                  all(vector != vectors[choice] for key, vector in vectors.items() if key != choice))
    return count


def _comparison_queries(cases: list[dict], contaminated: set[str], admitted: dict,
                        full_predictions: dict, training: dict) -> tuple[dict, dict]:
    predictions = {"full": {key: value[0] for key, value in full_predictions.items()},
                   **_baseline_predictions(cases, contaminated)}
    support = {"full": copy.deepcopy(training)}
    for target in preferences.TARGETS:
        for partition in PARTITIONS:
            for domain in preferences.DOMAINS:
                summary = support["full"][target][partition][domain]
                summary["informative_training_events"] = _informative_events(
                    admitted[(target, partition, domain)], target)
    for feature in VALUE_PARAMETERS:
        name = "drop:" + feature
        fits, support[name] = {}, {target: {} for target in preferences.TARGETS}
        for target in preferences.TARGETS:
            for partition in PARTITIONS:
                support[name][target][partition] = {}
                for domain in preferences.DOMAINS:
                    axis = (target, partition, domain)
                    original = support["full"][target][partition][domain]
                    # Preserve each admitted original record, label, group and
                    # ordering even when multiple events now share a projection.
                    records = [{**record, "options": _project_options(record["options"], feature)}
                               for record in admitted[axis]]
                    fit = preferences.fit_preferences(records, target=target,
                                                      partition=partition, domain=domain)
                    if fit.get("status") not in ("provisional", "abstain"):
                        raise ValueError("invalid production fit status")
                    fits[axis] = fit
                    support[name][target][partition][domain] = {
                        "original_training_records": original["training_records"],
                        "original_eligible_development_groups": original["eligible_development_groups"],
                        "original_informative_training_events": original["informative_training_events"],
                        "original_informative_training_groups": original["informative_training_groups"],
                        "original_contrast_rank": original["contrast_rank"],
                        "training_records": len(records),
                        "informative_training_events": _informative_events(records, target),
                        "informative_training_groups": fit["training_groups"],
                        "contrast_rank": fit["contrast_rank"], "fit_status": fit["status"]}
        predictions[name] = {key: value[0] for key, value in
                             _predict_all(cases, contaminated, fits, feature).items()}
    return predictions, support


def _stratified(rows: list[dict], summarize) -> dict:
    return {"overall": summarize(rows),
            "by_partition": {partition: summarize([row for row in rows if row["axis"][0] == partition])
                             for partition in PARTITIONS},
            "by_domain": {domain: summarize([row for row in rows if row["axis"][1] == domain])
                          for domain in preferences.DOMAINS},
            "by_partition_domain": {
                partition: {domain: summarize([row for row in rows if row["axis"] == (partition, domain)])
                            for domain in preferences.DOMAINS} for partition in PARTITIONS}}


def _chance_summary(rows: list[dict]) -> dict:
    result = _summary(rows)
    # Probability mass is never rendered as an observed count/accuracy.
    for values in (result, result["macro_group"]):
        for key in ("correct", "hit_rate", "conditional_accuracy", "all_held_out_hit_rate"):
            if key in values:
                values["expected_" + key] = values.pop(key)
    result["expected_correct"] = float(result["expected_correct"])
    return result


def _pair_counts(rows: list[dict], *, chance: bool) -> dict:
    units = list({(row["group"], row["unit"]): row for row in rows}.values())
    eligible = [row for row in units if row["evaluated"]]
    both = [row for row in eligible if row["full_predicted"] and row["predicted"]]
    full_count = sum(row["full_predicted"] for row in eligible)
    variant_count = sum(row["predicted"] for row in eligible)
    full_correct = sum(row["full_correct"] for row in eligible)
    variant_correct = (math.fsum(row["correct"] for row in eligible) if chance
                       else sum(row["correct"] for row in eligible))
    full_both = sum(row["full_correct"] for row in both)
    variant_both = (math.fsum(row["correct"] for row in both) if chance
                    else sum(row["correct"] for row in both))
    outcomes = {"both_correct": math.fsum(row["full_correct"] * row["correct"] for row in both),
                "full_only_correct": math.fsum(row["full_correct"] * (1 - row["correct"]) for row in both),
                "variant_only_correct": math.fsum((1 - row["full_correct"]) * row["correct"] for row in both),
                "neither_correct": math.fsum((1 - row["full_correct"]) * (1 - row["correct"]) for row in both)}
    prefix = "expected_" if chance else ""
    result = {"unique_scoring_units": len(units), "evaluated": len(eligible),
              "full_predicted": full_count, "variant_predicted": variant_count,
              "both_predicted": len(both), "full_only_predicted": full_count - len(both),
              "variant_only_predicted": variant_count - len(both),
              "neither_predicted": len(eligible) - full_count - variant_count + len(both),
              "full_coverage": _ratio(full_count, len(eligible)),
              "variant_coverage": _ratio(variant_count, len(eligible)),
              "both_predicted_coverage": _ratio(len(both), len(eligible)),
              "all_held_out_both_predicted_coverage": _ratio(len(both), len(units)),
              "full_correct": full_correct, prefix + "variant_correct": variant_correct,
              "full_hit_rate": _ratio(full_correct, len(eligible)),
              prefix + "variant_hit_rate": _ratio(variant_correct, len(eligible)),
              "full_correct_on_both": full_both, prefix + "variant_correct_on_both": variant_both,
              "full_accuracy_on_both": _ratio(full_both, len(both)),
              prefix + "variant_accuracy_on_both": _ratio(variant_both, len(both))}
    for key, count in outcomes.items():
        result[prefix + key] = count if chance else int(count)
        result[prefix + key + "_cohort_rate"] = _ratio(count, len(eligible))
    return result


def _pair_summary(rows: list[dict], *, chance: bool) -> dict:
    result = _pair_counts(rows, chance=chance)
    groups = defaultdict(list)
    for row in rows:
        groups[row["group"]].append(row)
    summaries = [_pair_counts(group, chance=chance) for group in groups.values()]
    for macro_key, denominator in (("macro_group", "both_predicted"),
                                   ("cohort_macro_group", "evaluated")):
        macro = {"all_held_out_groups": len(groups),
                 "evaluated_groups": sum(summary["evaluated"] > 0 for summary in summaries),
                 "both_predicted_groups": sum(summary["both_predicted"] > 0 for summary in summaries)}
        for key in result:
            if "coverage" in key or "rate" in key or "accuracy" in key:
                values = [summary[key] for summary in summaries
                          if summary[denominator] > 0 and summary[key] is not None]
                macro[key] = math.fsum(values) / len(values) if values else None
        result[macro_key] = macro
    return result


def _comparison_report(cases: list[dict], contaminated: set[str], predictions: dict,
                       support: dict) -> dict:
    rows = {name: {target: [] for target in preferences.TARGETS} for name in predictions}
    for case in cases:
        if case["split"] != "held_out":
            continue
        for target in preferences.TARGETS:
            choice = case["labels"][target]["choice_id"]
            eligible = _common_eligible(case, contaminated) and _label_eligible(case, target)
            evaluated = eligible and choice is not None
            event = _event_identity(case, target)
            base = {"group": case["reviewed_group_id"], "axis": _axis(case, target),
                    "event": event, "labelled": choice is not None, "ineligible": not eligible,
                    "evaluated": evaluated}
            # One ORIGINAL unit identity for every variant; outcomes/projection
            # cannot merge original events or create a smaller scoring cohort.
            base["unit"] = _hash({"event": event, "eligible": eligible, "evaluated": evaluated})
            key = (case["id"], target)
            full = predictions["full"][key]
            for name, values in predictions.items():
                prediction = values[key]
                predicted = evaluated and prediction is not None
                correct = (prediction if name == "chance" else prediction == choice) if predicted else False
                rows[name][target].append({**base, "predicted": predicted, "correct": correct,
                                          "full_predicted": evaluated and full is not None,
                                          "full_correct": evaluated and full is not None and full == choice})
    result = {"cohort_identity": "original_event_and_target_eligibility",
              "pairwise_cohort": "BOTH_PREDICTED",
              "chance_mode": "analytic_uniform_expectation_no_draws",
              "chance_coverage_interpretation": "analytic_distribution_availability",
              "equal_weight_tie_tolerance": EQUAL_WEIGHT_TIE_TOLERANCE,
              "feature_drop_order": list(VALUE_PARAMETERS),
              "automatic_selection": False, "validity_claim": False,
              "variants": {}, "full_vs_variant": {}}
    for name, targets in rows.items():
        kind = ("nonpersonal_equal_weight_sum_heuristic" if name == "equal_weight" else
                "analytic_uniform_chance" if name == "chance" else
                "production_full" if name == "full" else "production_leave_one_feature_out")
        result["variants"][name] = {"kind": kind, "targets": {}}
        for target, values in targets.items():
            summary = _stratified(values, _chance_summary if name == "chance" else _summary)
            if name in support:
                summary["training"] = support[name][target]
            result["variants"][name]["targets"][target] = summary
        if name != "full":
            result["full_vs_variant"][name] = {"targets": {
                target: _stratified(values, lambda group: _pair_summary(group, chance=name == "chance"))
                for target, values in targets.items()}}
    return result


def evaluate_manifest(manifest: object, *, details: bool = False, validate_only: bool = False,
                      comparisons: bool = False) -> dict:
    """Run pure production fits on development labels and score frozen queries."""
    if any(type(flag) is not bool for flag in (details, validate_only, comparisons)):
        raise ValueError("report flags must be boolean")
    cases = sorted(validate_manifest(manifest), key=lambda case: case["id"])
    contaminated = _contaminated_groups(cases)
    report = {"schema_version": 1, "kind": "preference_holdout_report",
              "status": "manifest_validation_only" if validate_only else "offline_preference_evaluation",
              "data_origin": manifest["data_origin"], "synthetic": manifest["data_origin"] == "synthetic",
              "validity_claim": False, "training_only_development": True, "not_calibrated": True,
              "database_opened": False, "weights_persisted": False, "persisted_encoder_model": False,
              "manifest_fingerprint": _hash(manifest), "implementation_sha256": _implementation_identity(),
              "case_count": len(cases),
              "split_counts": {split: sum(case["split"] == split for case in cases)
                               for split in ("development", "held_out")},
              "held_out_groups": len({case["reviewed_group_id"] for case in cases if case["split"] == "held_out"}),
              "blocked_held_out_groups": len(contaminated),
              "ablation_eight_parameters": "not_requested", "baselines": "not_requested",
              "limitations": ["attestations_cannot_prove_independence_or_authenticity",
                              "semantic_leakage_not_proven_absent", "no_real_predictive_validity_claim",
                              "freeze_is_declared_not_historically_verified",
                              "implementation_identity_records_current_code_not_historical_freeze",
                              "contrast_rank_does_not_establish_parameter_magnitudes_or_validity",
                              "no_calibrated_confidence_or_statistical_validity",
                              "opaque_ids_and_fingerprints_are_not_anonymization"]}
    if validate_only:
        if comparisons:
            report["ablation_eight_parameters"] = "not_run_validation_only"
            report["baselines"] = "not_run_validation_only"
        return report
    fits, admitted, training = {}, {}, {target: {} for target in preferences.TARGETS}
    for target in preferences.TARGETS:
        for partition in PARTITIONS:
            training[target][partition] = {}
            for domain in preferences.DOMAINS:
                records, labelled = _development_records(cases, target, partition, domain)
                if comparisons:
                    admitted[(target, partition, domain)] = records
                fit = preferences.fit_preferences(records, target=target, partition=partition, domain=domain)
                # The solver owner may add abstention reasons; status is the gate.
                if fit.get("status") not in ("provisional", "abstain"):
                    raise ValueError("invalid production fit status")
                fits[(target, partition, domain)] = fit
                training[target][partition][domain] = {
                    "eligible_labelled_development": labelled, "training_records": len(records),
                    "eligible_development_groups": len({record["source_id"] for record in records}),
                    "informative_training_groups": fit["training_groups"], "fit_status": fit["status"],
                    "contrast_rank": fit["contrast_rank"]}
    # No held-out choice value influences fits or queries. Structural validation
    # above checked identifiers; only the following score pass reads their value.
    predictions = _predict_all(cases, contaminated, fits)
    if comparisons:
        comparison_predictions, comparison_support = _comparison_queries(
            cases, contaminated, admitted, predictions, training)
    rows, case_details = {target: [] for target in preferences.TARGETS}, []
    for case in cases:
        if case["split"] != "held_out":
            continue
        reasons = {}
        for target in preferences.TARGETS:
            choice = case["labels"][target]["choice_id"]
            prediction, reason = predictions[(case["id"], target)]
            eligible = _common_eligible(case, contaminated) and _label_eligible(case, target)
            evaluated = eligible and choice is not None
            predicted = evaluated and prediction is not None
            reasons[target] = "ineligible" if not eligible else "unlabelled" if choice is None else reason
            options = _canonical_options(case["options"]) if case["options"] is not None else None
            row = {"group": case["reviewed_group_id"], "axis": _axis(case, target),
                   "labelled": choice is not None, "ineligible": not eligible,
                   "evaluated": evaluated, "predicted": predicted,
                   "correct": predicted and prediction == choice}
            row["event"] = _event_identity(case, target)
            row["unit"] = _hash({"event": row["event"], "options": options, "choice": choice,
                                  "labelled": row["labelled"], "ineligible": row["ineligible"],
                                  "evaluated": evaluated, "prediction": prediction if evaluated else None})
            rows[target].append(row)
        if details:
            case_details.append({"id": case["id"], "prediction_reason": reasons})
    report["targets"] = {}
    for target, values in rows.items():
        report["targets"][target] = {
            "overall": _summary(values), "training": training[target],
            "by_partition": {partition: _summary([row for row in values if row["axis"][0] == partition])
                             for partition in PARTITIONS},
            "by_domain": {domain: _summary([row for row in values if row["axis"][1] == domain])
                          for domain in preferences.DOMAINS},
            "by_partition_domain": {
                partition: {domain: _summary([row for row in values if row["axis"] == (partition, domain)])
                            for domain in preferences.DOMAINS} for partition in PARTITIONS}}
    if details:
        report["case_results"] = case_details
    if comparisons:
        report["comparisons"] = _comparison_report(cases, contaminated, comparison_predictions, comparison_support)
        report["ablation_eight_parameters"] = "completed"
        report["baselines"] = "completed"
        report["limitations"].extend([
            "comparisons_are_descriptive_not_parameter_selection_or_significance",
            "holdout_used_for_parameter_selection_becomes_development_requires_new_independent_holdout",
            "chance_expectation_is_not_calibrated_personal_probability",
            "general_baselines_can_cover_queries_outside_learned_span"])
    return report


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default errors repeat unknown arguments, which may be text.
        self.exit(2, _ERROR)


def main() -> None:
    parser = _Parser(description="Database-free offline preference holdout audit")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--comparisons", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate_manifest(load_manifest(args.manifest), details=args.details,
                                   validate_only=args.validate_only, comparisons=args.comparisons)
        output = json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True)
    except Exception:
        # An offline CLI privacy boundary: no exception message, path or label.
        parser.exit(2, _ERROR)
    sys.stdout.write(output + "\n")


if __name__ == "__main__":
    main()
