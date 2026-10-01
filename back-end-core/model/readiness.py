"""Database-free collection validation and export, never inference or fitting.

Draft labels are retained but never scored. Eligibility is an attestation audit,
not proof of independence or real predictive validity.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from model.evaluation import validate_cases as validate_choices
from model.ranking import validate_options
from translator.evaluation import (
    MAX_CASES, MAX_FILE_BYTES, MAX_TOTAL_CHARS, load_manifest,
    validate_cases as validate_extraction, validate_json_strings,
)

_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_LABELS = ("pending", "independent", "model_assisted")


def _fields(value: object, fields: set[str], name: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(name + " has missing or unknown fields")


def _id(value: object) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("identifiers must be opaque ASCII tokens of 1 to 80 characters")


def _ids(value: object) -> None:
    if not isinstance(value, list) or len(value) > MAX_CASES:
        raise ValueError("source identifiers must be a bounded array")
    for item in value:
        _id(item)
    if len(set(value)) != len(value):
        raise ValueError("source identifiers must be distinct")


def _time(value: object) -> datetime:
    if not isinstance(value, str) or _TIME.fullmatch(value) is None:
        raise ValueError("times must use UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid UTC time") from None


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False, separators=(",", ":")).encode("ascii")).hexdigest()


def _choice(case: dict) -> dict:
    data = copy.deepcopy(case["data"])
    return {"id": case["id"], "held_out": True,
            "source_ids": list(case["backend_source_ids"]), **data}


def _extraction(case: dict, *, draft: bool = False) -> dict:
    data = copy.deepcopy(case["data"])
    if draft and data["label_scope"] == []:
        if data["expected"] != []:
            raise ValueError("unchecked extraction scope cannot have expected labels")
        # Structural validation only; no extraction or metric computation.
        data["label_scope"] = "all"
    return {"id": case["id"], "group_id": case["group_id"], "split": case["split"], **data}


def validate_collection(manifest: object) -> list[dict]:
    """Validate even drafts and audit leakage across all cases, without a DB."""
    validate_json_strings(manifest)
    _fields(manifest, {"schema_version", "protocol", "cases"}, "collection")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("collection needs schema_version=1")
    protocol = manifest["protocol"]
    _fields(protocol, {"development_end", "held_out_start", "frozen_at"}, "protocol")
    end, start, frozen = (_time(protocol[key]) for key in ("development_end", "held_out_start", "frozen_at"))
    if not end < start <= frozen:
        raise ValueError("protocol requires development_end < held_out_start <= frozen_at")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"provide 1 to {MAX_CASES} collection cases")
    seen, groups, sources, fingerprints = set(), {}, {}, {}
    extraction_cases = []
    total_chars = 0
    for case in cases:
        _fields(case, {"id", "group_id", "source_ids", "backend_source_ids", "task", "split",
                       "event_at", "labelled_at", "annotator_id", "blind_to_outputs", "exposure",
                       "authenticity", "annotations", "data"}, "case")
        for key in ("id", "group_id"):
            _id(case[key])
        if case["id"] in seen:
            raise ValueError("duplicate collection case id")
        seen.add(case["id"])
        _ids(case["source_ids"])
        _ids(case["backend_source_ids"])
        if not case["source_ids"]:
            raise ValueError("collection needs at least one opaque source identifier")
        if case["task"] not in ("choice", "translator") or case["split"] not in ("development", "held_out"):
            raise ValueError("unknown collection task or split")
        if case["authenticity"] is not None and type(case["authenticity"]) is not bool:
            raise ValueError("authenticity must be true, false or null")
        if case["blind_to_outputs"] is not None and type(case["blind_to_outputs"]) is not bool:
            raise ValueError("blind_to_outputs must be true, false or null")
        if case["annotator_id"] is not None:
            _id(case["annotator_id"])
        event = _time(case["event_at"]) if case["event_at"] is not None else None
        labelled = _time(case["labelled_at"]) if case["labelled_at"] is not None else None
        if event is not None and (event > frozen or (case["split"] == "development" and event > end)
                                  or (case["split"] == "held_out" and event < start)):
            raise ValueError("event is outside its declared split time window")
        if labelled is not None and (labelled > frozen or (event is not None and labelled < event)):
            raise ValueError("label time must follow event and precede collection freeze")
        exposure = case["exposure"]
        _fields(exposure, {"import_status", "model_fit", "rule_development", "manual_tuning"}, "exposure")
        if exposure["import_status"] not in ("never_imported", "imported", "unknown"):
            raise ValueError("unknown import status")
        if any(exposure[key] not in ("none", "exposed", "unknown")
               for key in ("model_fit", "rule_development", "manual_tuning")):
            raise ValueError("unknown exposure status")
        if exposure["import_status"] == "never_imported" and case["backend_source_ids"]:
            raise ValueError("never-imported sources cannot carry backend source IDs")
        if exposure["import_status"] == "imported" and not case["backend_source_ids"]:
            raise ValueError("imported sources require all known backend source IDs")
        if exposure["import_status"] == "never_imported" and exposure["model_fit"] == "exposed":
            raise ValueError("never-imported cannot attest model fitting")
        group, split = case["group_id"], case["split"]
        if group in groups and groups[group] != split:
            raise ValueError("a group crosses development and held_out")
        groups[group] = split
        for namespace, ids in (("collection", case["source_ids"]), ("backend", case["backend_source_ids"])):
            for source in ids:
                key = (namespace, source)
                if key in sources and sources[key] != (group, split):
                    raise ValueError("a source must remain in one group and split")
                sources[key] = (group, split)
        labels = case["annotations"]
        keys = {"options", "actual_choice", "endorsed_choice"} if case["task"] == "choice" else {"extraction"}
        _fields(labels, keys, "annotations")
        if any(value not in _LABELS for value in labels.values()):
            raise ValueError("annotation status must be pending, independent or model_assisted")
        data = case["data"]
        if case["task"] == "choice":
            _fields(data, {"domain", "options", "actual_choice", "endorsed_choice"}, "choice data")
            if data["domain"] not in ("daily", "study", "interpersonal"):
                raise ValueError("unknown choice domain")
            if data["options"] is None:
                if labels["options"] != "pending" or any(data[key] is not None for key in ("actual_choice", "endorsed_choice")):
                    raise ValueError("missing options require pending options and unknown choices")
            else:
                if not isinstance(data["options"], list) or not 2 <= len(data["options"]) <= 100:
                    raise ValueError("choice needs 2 to 100 options or null draft options")
                for option in data["options"]:
                    _fields(option, {"id", "impacts"}, "option")
                    _id(option["id"])
                try:
                    validate_options(data["options"])
                except ValueError:
                    raise ValueError("invalid option identifiers or impacts") from None
                option_ids = {option["id"] for option in data["options"]}
                for field in ("actual_choice", "endorsed_choice"):
                    label = data[field]
                    if label is not None and (not isinstance(label, str) or label not in option_ids):
                        raise ValueError("choice labels must be option identifiers or null")
            for field in ("actual_choice", "endorsed_choice"):
                if labels[field] != "pending" and data[field] is None:
                    raise ValueError("completed choice annotations require an explicit choice")
        else:
            required = {"domain", "partition", "kind", "text", "label_scope", "expected"}
            if not isinstance(data, dict) or not required <= set(data) or set(data) - required - {"self_speaker"}:
                raise ValueError("translator data has missing or unknown fields")
            if data["label_scope"] == [] and labels["extraction"] != "pending":
                raise ValueError("completed extraction requires an explicitly checked scope")
            extraction = _extraction(case, draft=True)
            validate_extraction({"schema_version": 1, "cases": [extraction]})
            extraction_cases.append(extraction)
            total_chars += len(data["text"])
            if total_chars > MAX_TOTAL_CHARS:
                raise ValueError("collection exceeds total text character limit")
            # Also audit duplicates in drafts; exclusion must not hide leakage.
            identity = (data["kind"], data.get("self_speaker"),
                        data["text"].replace("\r\n", "\n").replace("\r", "\n").strip())
            fingerprint = _hash(identity)
            if fingerprint in fingerprints and fingerprints[fingerprint] != (group, split):
                raise ValueError("duplicate text must remain in one group and split")
            fingerprints[fingerprint] = (group, split)
    if extraction_cases:
        validate_extraction({"schema_version": 1, "cases": extraction_cases})
    return copy.deepcopy(cases)


def _contaminated_groups(cases: list[dict]) -> set[str]:
    # A clean variant cannot conceal another variant's known/unknown exposure.
    return {case["group_id"] for case in cases if case["split"] == "held_out" and
            (case["exposure"]["import_status"] == "unknown" or
             any(case["exposure"][key] != "none" for key in ("model_fit", "rule_development", "manual_tuning")))}


def _blockers(case: dict, contaminated: set[str]) -> list[str]:
    reasons = []
    if case["event_at"] is None or case["labelled_at"] is None:
        reasons.append("incomplete_time_provenance")
    if case["annotator_id"] is None or case["blind_to_outputs"] is not True:
        reasons.append("independent_blind_annotation_not_attested")
    if case["split"] == "held_out":
        if case["group_id"] in contaminated:
            reasons.append("held_out_exposure_not_clear")
    labels = case["annotations"]
    if case["task"] == "choice":
        if case["split"] != "held_out":
            reasons.append("choice_requires_held_out")
        if labels["options"] != "independent":
            reasons.append("options_not_independently_labelled")
        if not any(labels[key] == "independent" for key in ("actual_choice", "endorsed_choice")):
            reasons.append("no_independent_choice_label")
    elif labels["extraction"] != "independent":
        reasons.append("extraction_scope_not_independently_checked")
    return reasons


def _exports(cases: list[dict]) -> dict:
    selected = {"choice": [], "translator": []}
    contaminated = _contaminated_groups(cases)
    for case in sorted(cases, key=lambda item: item["id"]):
        if _blockers(case, contaminated):
            continue
        if case["task"] == "choice":
            exported = _choice(case)
            for key in ("actual_choice", "endorsed_choice"):
                if case["annotations"][key] != "independent":
                    exported[key] = None
        else:
            exported = _extraction(case)
        selected[case["task"]].append(exported)
    result = {key: {"schema_version": 1, "cases": values} if values else None for key, values in selected.items()}
    if result["choice"] is not None:
        validate_choices(result["choice"], [])
    if result["translator"] is not None:
        validate_extraction(result["translator"])
    return result


def export_manifests(manifest: object) -> dict:
    """Explicit private-data export; empty tasks return None, never invalid [] manifests."""
    return _exports(validate_collection(manifest))


def assess_readiness(manifest: object, *, details: bool = False) -> dict:
    """Reproducible metadata only; no source text, inference or DB access."""
    if type(details) is not bool:
        raise ValueError("details must be boolean")
    cases = validate_collection(manifest)
    exports = _exports(cases)
    contaminated = _contaminated_groups(cases)
    blockers = Counter(reason for case in cases for reason in _blockers(case, contaminated))
    root = Path(__file__).resolve().parents[1]
    code_paths = ("model/readiness.py", "model/evaluation.py", "model/ranking.py", "model/catalog.py",
                  "model/corrections.py", "translator/evaluation.py")
    report = {"schema_version": 1, "status": "collection_readiness_only", "database_opened": False,
              "collection_sha256": _hash(manifest), "protocol_sha256": _hash(manifest["protocol"]),
              "implementation_sha256": {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                                        for path in code_paths},
              "case_count": len(cases), "source_groups": len({case["group_id"] for case in cases}),
              "source_count": len({source for case in cases for source in case["source_ids"]}),
              "independent_label_counts": {key: sum(case["annotations"].get(key) == "independent" for case in cases)
                                           for key in ("options", "actual_choice", "endorsed_choice", "extraction")},
              "by_task_split": {task: {split: sum(case["task"] == task and case["split"] == split for case in cases)
                                       for split in ("development", "held_out")} for task in exports},
              "eligible": {task: len(value["cases"]) if value else 0 for task, value in exports.items()},
              "export_sha256": {task: _hash(value) if value else None for task, value in exports.items()},
              "blocked_cases": sum(bool(_blockers(case, contaminated)) for case in cases),
              "blocker_counts": dict(sorted(blockers.items())),
              "limitations": ["attestations_not_verified_against_database_or_history",
                              "unknown_exposure_is_not_untrained", "semantic_leakage_not_proven_absent",
                              "authenticity_does_not_supply_choice_or_extraction_labels",
                              "hashes_are_not_anonymization_or_encryption",
                              "no_real_data_or_predictive_validity_acceptance",
                              "choice_export_requires_later_read_only_snapshot_overlap_check",
                              "api_and_f14_deferred"]}
    if details:
        report["case_results"] = [{"id": case["id"], "blockers": _blockers(case, contaminated)}
                                  for case in sorted(cases, key=lambda item: item["id"])]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Database-free offline collection readiness; never trains")
    parser.add_argument("--collection", required=True, type=Path)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--export", choices=("choice", "translator"), help="explicit private evaluator manifest to stdout")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.collection, max_bytes=MAX_FILE_BYTES)
        if args.export:
            report = export_manifests(manifest)[args.export]
            if report is None:
                raise ValueError("no eligible cases for selected export")
        else:
            report = assess_readiness(manifest, details=args.details)
    except (OSError, ValueError, RecursionError):
        parser.exit(2, "Invalid or unreadable local collection; no database was opened.\n")
    sys.stdout.write(json.dumps(report, ensure_ascii=True, allow_nan=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
