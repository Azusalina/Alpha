"""Read-only base-extraction benchmark; no database, fitting or personal rules.

Human labels are independent of automatic outputs. Unchecked parameters are
not negatives. Reports contain aggregates, never source text or case IDs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path

from model.catalog import PARAMETERS, PARTITIONS
from model.corrections import validate_corrections
from model.evidence import extract_contributions
from translator.discourse import POLICY_VERSION
from translator.pipeline import MAX_CHARS

DOMAINS = ("daily", "study", "interpersonal", "philosophy")
SPLITS = ("development", "held_out")
MAX_CASES = 1000
MAX_TOTAL_CHARS = 5_000_000
MAX_FILE_BYTES = 32_000_000
_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")


def validate_json_strings(value: object) -> None:
    """Reject NUL/surrogates anywhere, including keys and unused fields."""
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("NUL characters are not permitted")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("surrogate code points are not permitted") from None
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_json_strings(key)
            validate_json_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_json_strings(item)


def validate_cases(manifest: object) -> list[dict]:
    validate_json_strings(manifest)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "cases"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1):
        raise ValueError("corpus needs schema_version=1 and cases")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"provide 1 to {MAX_CASES} cases")
    required = {"id", "group_id", "split", "domain", "partition", "kind", "text", "label_scope", "expected"}
    seen, groups, fingerprints, checked, total_chars = set(), {}, {}, [], 0
    for index, case in enumerate(cases):
        prefix = f"case {index + 1}: "
        if not isinstance(case, dict) or not required <= set(case) or set(case) - required - {"self_speaker"}:
            raise ValueError(prefix + "missing or unknown fields")
        for field in ("id", "group_id"):
            if not isinstance(case[field], str) or _ID.fullmatch(case[field]) is None:
                raise ValueError(prefix + "ids must be opaque ASCII tokens of 1 to 80 characters")
        if case["id"] in seen:
            raise ValueError(prefix + "duplicate case id")
        seen.add(case["id"])
        for field, choices in (("split", SPLITS), ("domain", DOMAINS), ("partition", PARTITIONS),
                               ("kind", ("diary", "chat", "philosophy"))):
            if not isinstance(case[field], str) or case[field] not in choices:
                raise ValueError(prefix + "unknown " + field)
        text, speaker = case["text"], case.get("self_speaker")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError(prefix + f"text needs 1 to {MAX_CHARS} nonblank Unicode code points")
        if speaker is not None and (not isinstance(speaker, str) or not speaker.strip()):
            raise ValueError(prefix + "self_speaker must contain text or be null")
        if case["kind"] == "chat" and speaker is None:
            raise ValueError(prefix + "chat requires self_speaker")
        try:
            text.encode("utf-8")
            if speaker is not None:
                speaker.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError(prefix + "surrogate code points are not permitted") from None
        total_chars += len(text)
        if total_chars > MAX_TOTAL_CHARS:
            raise ValueError("corpus exceeds total text character limit")
        scope = case["label_scope"]
        if isinstance(scope, str) and scope == "all":
            scope = list(PARAMETERS)
        if (not isinstance(scope, list) or not 1 <= len(scope) <= len(PARAMETERS)
                or any(not isinstance(key, str) or key not in PARAMETERS for key in scope)
                or len(set(scope)) != len(scope)):
            raise ValueError(prefix + "label_scope must be all or distinct known parameters")
        try:
            expected = validate_corrections(text, case["kind"], speaker, case["expected"])
        except ValueError as error:
            # The shared validator uses fixed error descriptions, not raw values.
            raise ValueError(prefix + str(error)) from None
        if any(item["sign"] == 0 or item["parameter"] not in scope for item in expected):
            raise ValueError(prefix + "expected entries need nonzero signs within label_scope")
        split, group = case["split"], case["group_id"]
        if group in groups and groups[group] != split:
            raise ValueError(prefix + "a source group crosses development and held_out")
        groups[group] = split
        # Same source copied into another partition/domain is still not unseen.
        # Normalize line endings/outer whitespace for this audit only, never spans.
        identity = (case["kind"], speaker, text.replace("\r\n", "\n").replace("\r", "\n").strip())
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode("ascii")).digest()
        prior = fingerprints.get(fingerprint)
        if prior is not None and prior != (split, group):
            raise ValueError(prefix + "duplicate source text must remain in one split and source group")
        fingerprints[fingerprint] = (split, group)
        checked.append({**case, "self_speaker": speaker, "label_scope": tuple(scope), "expected": expected})
    return checked


def _bucket() -> dict:
    return {"counts": Counter(), "groups": {}, "reasons": Counter()}


def _summary(bucket: dict, *, diagnostics: bool = True) -> dict:
    counts = bucket["counts"]
    tp, fp, fn = (counts[key] for key in ("true_positive", "false_positive", "false_negative"))
    predicted, expected = counts["predicted_positives"], counts["expected_positives"]
    strict = counts["strict_evidence_matches"]
    case_count = counts["cases"]
    groups = bucket["groups"]
    names = ("cases", "checked_parameters", "expected_positives", "predicted_positives",
             "true_positive", "false_positive", "false_negative", "true_negative", "direction_errors",
             "strict_evidence_matches", "evidence_span_mismatches", "ignored_predictions",
             "case_exact_parameter_matches", "recorded_withheld_fragments", "withheld_fragments",
             "truncated_diagnostic_cases")
    if not diagnostics:
        names = names[:-3]
    return {**{name: counts[name] for name in names}, "source_groups": len(groups),
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "strict_evidence_precision": strict / predicted if predicted else None,
            "strict_evidence_recall": strict / expected if expected else None,
            "strict_evidence_f1": 2 * strict / (predicted + expected) if predicted + expected else None,
            "case_exact_parameter_match_rate": counts["case_exact_parameter_matches"] / case_count if case_count else None,
            "group_macro_case_exact_parameter_match_rate":
                sum(matched / total for matched, total in groups.values()) / len(groups) if groups else None,
            **({"recorded_withheld_reasons": dict(sorted(bucket["reasons"].items()))} if diagnostics else {})}


def evaluate_manifest(manifest: object, *, case_details: bool = False) -> dict:
    """Validate then run isolated base rules; no calls into a BrainModel/store."""
    if type(case_details) is not bool:
        raise ValueError("case_details must be a boolean")
    cases = validate_cases(manifest)
    details = []
    overall = _bucket()
    by_split = {key: _bucket() for key in SPLITS}
    by_domain = {key: _bucket() for key in DOMAINS}
    by_partition = {key: _bucket() for key in PARTITIONS}
    split_domains = {split: {domain: _bucket() for domain in DOMAINS} for split in SPLITS}
    by_parameter = {key: _bucket() for key in PARAMETERS}
    for case in cases:
        diagnostics = {}
        contributions = extract_contributions(case["text"], kind=case["kind"],
                                              self_speaker=case["self_speaker"], diagnostics=diagnostics)
        predicted = {item.parameter: item for item in contributions}
        expected = {item["parameter"]: item for item in case["expected"]}
        shared = (overall, by_split[case["split"]], by_domain[case["domain"]],
                  by_partition[case["partition"]], split_domains[case["split"]][case["domain"]])
        exact = True
        errors = []
        for parameter in case["label_scope"]:
            gold, actual = expected.get(parameter), predicted.get(parameter)
            counts = Counter(checked_parameters=1)
            counts["expected_positives"] = int(gold is not None)
            counts["predicted_positives"] = int(actual is not None)
            matched = gold is None and actual is None
            if matched:
                counts["true_negative"] = 1
            elif gold is not None and actual is not None and gold["sign"] == actual.sign:
                counts["true_positive"] = 1
                matched = True
                span_matched = gold["span"] == [actual.start, actual.end] and gold["evidence"] == actual.evidence
                counts["strict_evidence_matches"] = int(span_matched)
                counts["evidence_span_mismatches"] = int(not span_matched)
                if not span_matched:
                    errors.append({"parameter": parameter, "kind": "evidence_span_mismatch",
                                   "expected_span": gold["span"], "predicted_span": [actual.start, actual.end]})
            else:
                counts["false_positive"] = int(actual is not None)
                counts["false_negative"] = int(gold is not None)
                counts["direction_errors"] = int(gold is not None and actual is not None)
                errors.append({"parameter": parameter,
                               "kind": "direction_error" if gold is not None and actual is not None
                               else "false_positive" if actual is not None else "false_negative",
                               "expected_sign": gold["sign"] if gold is not None else 0,
                               "predicted_sign": actual.sign if actual is not None else 0})
            exact = exact and matched
            for bucket in (*shared, by_parameter[parameter]):
                bucket["counts"].update(counts)
            p_bucket = by_parameter[parameter]
            p_bucket["counts"].update(cases=1, case_exact_parameter_matches=int(matched))
            prior = p_bucket["groups"].get(case["group_id"], (0, 0))
            p_bucket["groups"][case["group_id"]] = (prior[0] + int(matched), prior[1] + 1)
        case_counts = Counter(cases=1, case_exact_parameter_matches=int(exact),
                              ignored_predictions=len(set(predicted) - set(case["label_scope"])),
                              recorded_withheld_fragments=len(diagnostics["withheld_values"]),
                              withheld_fragments=diagnostics["withheld_count"],
                              truncated_diagnostic_cases=int(diagnostics["withheld_truncated"]))
        reasons = Counter(item["reason"] for item in diagnostics["withheld_values"])
        for bucket in shared:
            bucket["counts"].update(case_counts)
            bucket["reasons"].update(reasons)
            prior = bucket["groups"].get(case["group_id"], (0, 0))
            bucket["groups"][case["group_id"]] = (prior[0] + int(exact), prior[1] + 1)
        if case_details:
            details.append({"id": case["id"], "domain": case["domain"], "partition": case["partition"],
                            "split": case["split"], "errors": errors,
                            "ignored_predictions": case_counts["ignored_predictions"]})
    report = {"schema_version": 1, "evaluation": "base_translator_extraction",
            "cases_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest(),
            "evaluation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "evidence_policy": POLICY_VERSION, "personal_rules_used": False,
            "overall": _summary(overall), "by_split": {key: _summary(value) for key, value in by_split.items()},
            "by_domain": {key: _summary(value) for key, value in by_domain.items()},
            "by_partition": {key: _summary(value) for key, value in by_partition.items()},
            "by_split_domain": {split: {domain: _summary(bucket) for domain, bucket in domains.items()}
                                for split, domains in split_domains.items()},
            "by_parameter": {key: _summary(value, diagnostics=False) for key, value in by_parameter.items()},
            "limitations": ["human_label_quality_not_verified", "held_out_provenance_is_an_author_assertion",
                            "group_macro_does_not_establish_statistical_independence",
                            "base_rules_only_no_personal_corrections_or_vocabulary_fit",
                            "withheld_reason_counts_use_bounded_diagnostics_not_all_omissions",
                            "extraction_metrics_not_personality_or_choice_prediction_validity"]}
    if case_details:
        report["case_results"] = details
    return report


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value: str):
    raise ValueError("non-finite JSON numbers are not permitted")


def load_manifest(path: str | Path, *, max_bytes: int = MAX_FILE_BYTES) -> object:
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("file byte limit must be a positive integer")
    # Avoid waiting on a FIFO/device; only regular, explicitly selected files.
    descriptor = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("corpus must be a regular file")
        # Keep the module limit patchable for existing callers/tests.
        limit = min(max_bytes, MAX_FILE_BYTES)
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("corpus exceeds file byte limit")
    try:
        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        validate_json_strings(manifest)
        # JSON's exponent syntax can overflow without invoking parse_constant.
        json.dumps(manifest, allow_nan=False)
        return manifest
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("corpus must be bounded, strict UTF-8 JSON without duplicate fields or non-finite numbers") from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only base translator extraction evaluation; never trains")
    parser.add_argument("--cases", required=True, type=Path, help="locally labelled JSON corpus")
    parser.add_argument("--details", action="store_true", help="include opaque case IDs and error kinds/positions, never source text")
    args = parser.parse_args()
    try:
        report = evaluate_manifest(load_manifest(args.cases), case_details=args.details)
    except OSError:
        parser.exit(2, "Cannot read the local corpus; no model or database was opened.\n")
    except (ValueError, RecursionError) as error:
        parser.exit(2, f"Invalid corpus: {error}\n")
    sys.stdout.write(json.dumps(report, ensure_ascii=True, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
