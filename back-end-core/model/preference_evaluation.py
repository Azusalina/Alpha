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
    return sorted(copy.deepcopy(options), key=lambda option: option["id"])


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


def _predict_all(cases: list[dict], contaminated: set[str], fits: dict) -> dict:
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
                ranked = preferences.rank_from_fit(_canonical_options(case["options"]), fit)
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
    correct = sum(row["correct"] for row in unique)
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
    paths = ("model/preference_evaluation.py", "model/preferences.py", "model/ranking.py", "model/catalog.py")
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}


def evaluate_manifest(manifest: object, *, details: bool = False, validate_only: bool = False) -> dict:
    """Run pure production fits on development labels and score frozen queries."""
    if type(details) is not bool or type(validate_only) is not bool:
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
              "ablation_eight_parameters": "pending", "baselines": "pending",
              "limitations": ["attestations_cannot_prove_independence_or_authenticity",
                              "semantic_leakage_not_proven_absent", "no_real_predictive_validity_claim",
                              "freeze_is_declared_not_historically_verified",
                              "implementation_identity_records_current_code_not_historical_freeze",
                              "no_calibrated_confidence_or_statistical_validity",
                              "opaque_ids_and_fingerprints_are_not_anonymization"]}
    if validate_only:
        return report
    fits, training = {}, {target: {} for target in preferences.TARGETS}
    for target in preferences.TARGETS:
        for partition in PARTITIONS:
            training[target][partition] = {}
            for domain in preferences.DOMAINS:
                records, labelled = _development_records(cases, target, partition, domain)
                fit = preferences.fit_preferences(records, target=target, partition=partition, domain=domain)
                # The solver owner may add abstention reasons; status is the gate.
                if fit.get("status") not in ("provisional", "abstain"):
                    raise ValueError("invalid production fit status")
                fits[(target, partition, domain)] = fit
                training[target][partition][domain] = {
                    "eligible_labelled_development": labelled, "training_records": len(records),
                    "eligible_development_groups": len({record["source_id"] for record in records}),
                    "informative_training_groups": fit["training_sources"], "fit_status": fit["status"]}
    # No held-out choice value influences fits or queries. Structural validation
    # above checked identifiers; only the following score pass reads their value.
    predictions = _predict_all(cases, contaminated, fits)
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
    args = parser.parse_args()
    try:
        report = evaluate_manifest(load_manifest(args.manifest), details=args.details, validate_only=args.validate_only)
        output = json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True)
    except Exception:
        # An offline CLI privacy boundary: no exception message, path or label.
        parser.exit(2, _ERROR)
    sys.stdout.write(output + "\n")


if __name__ == "__main__":
    main()
