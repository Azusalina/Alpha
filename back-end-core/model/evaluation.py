"""Read-only, held-out evaluation of provisional rational value alignment.

This is an offline experiment contract, not the frontend choice-feedback API.
It never imports cases, changes parameters, or interprets clinical scales.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

from .catalog import BASELINE_PATH, PARAMETERS, PRIOR_STRENGTH
from .ranking import VALUE_PARAMETERS, rank_from_state, validate_options

DOMAINS = ("daily", "study", "interpersonal")
MAX_CASES = 1000
MAX_FILE_BYTES = 10_000_000


def read_snapshot(path: str | Path) -> dict:
    """Read one consistent SQLite snapshot; never initialize a missing database."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        stored = db.execute("SELECT value FROM brain_meta WHERE key='baseline_sha256'").fetchone()
        baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
        if stored is None or stored["value"] != baseline_hash:
            raise ValueError("baseline mismatch; migrate explicitly before evaluation")
        rows = db.execute("SELECT parameter, value, support, net FROM brain_state WHERE partition='rational'").fetchall()
        if len(rows) != len(PARAMETERS) or {r["parameter"] for r in rows} != set(PARAMETERS):
            raise ValueError("incomplete rational state")
        state = {}
        for row in rows:
            value, support, net = row["value"], row["support"], row["net"]
            if (type(support) is not int or support < 0 or type(net) is not int or abs(net) > support
                    or not isinstance(value, (int, float)) or not math.isfinite(value)
                    or not math.isclose(value, net / (support + PRIOR_STRENGTH), abs_tol=1e-12)):
                raise ValueError("invalid rational state")
            state[row["parameter"]] = {"value": value, "support": support, "observed": support > 0}
        # Previously fitted sources are not held-out either; their labels may
        # have influenced dependent frozen fits, even after their own revocation.
        input_columns = {r["name"] for r in db.execute("PRAGMA table_info(brain_inputs)")}
        ever_fitted = "OR i.ever_fitted=1 " if "ever_fitted" in input_columns else ""
        sources = [r[0] for r in db.execute(
            "SELECT i.source_id FROM brain_inputs i WHERE i.status IN ('agreed','revoked') "
            + ever_fitted +
            "OR EXISTS (SELECT 1 FROM brain_fit_context f WHERE f.source_id=i.source_id) "
            "ORDER BY i.source_id")]
        revision = db.execute("SELECT COALESCE(MAX(revision),0) FROM brain_effects").fetchone()[0]
        snapshot = {"baseline_sha256": baseline_hash, "revision": revision,
                    "rational": state, "training_source_ids": sources}
        snapshot["fingerprint"] = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()
        return snapshot
    finally:
        db.close()


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_cases(manifest: dict, training_source_ids: list[str]) -> list[dict]:
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "cases"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1):
        raise ValueError("evaluation manifest needs schema_version=1 and cases")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"provide 1 to {MAX_CASES} cases")
    seen, training = set(), set(training_source_ids)
    required = {"id", "domain", "held_out", "source_ids", "options", "actual_choice", "endorsed_choice"}
    for case in cases:
        if not isinstance(case, dict) or set(case) != required:
            raise ValueError("case fields must be id, domain, held_out, source_ids, options, actual_choice, endorsed_choice")
        if not _text(case["id"]) or case["id"] in seen:
            raise ValueError("case ids must be nonempty and unique")
        seen.add(case["id"])
        if case["domain"] not in DOMAINS or case["held_out"] is not True:
            raise ValueError("case needs a known domain and explicit held_out=true")
        source_ids = case["source_ids"]
        if (not isinstance(source_ids, list) or any(not _text(s) for s in source_ids)
                or len(set(source_ids)) != len(source_ids)):
            raise ValueError("source_ids must be distinct text identifiers")
        if training.intersection(source_ids):
            raise ValueError("held-out case overlaps an agreed training source")
        validate_options(case["options"])
        if len(case["options"]) > 100:
            raise ValueError("each evaluation case supports at most 100 options")
        option_ids = {option["id"] for option in case["options"]}
        for field in ("actual_choice", "endorsed_choice"):
            label = case[field]
            if label is not None and (not isinstance(label, str) or label not in option_ids):
                raise ValueError(f"{field} must be an option id or null")
        if case["actual_choice"] is None and case["endorsed_choice"] is None:
            raise ValueError("each case needs at least one choice label")
    return cases


def _predict(case: dict, rational: dict, excluded: tuple[str, ...]) -> dict:
    ranked = rank_from_state(case["options"], rational, excluded=excluded)
    if ranked["status"] == "abstain":
        return {"id": case["id"], "domain": case["domain"], "prediction": None,
                "reason": ranked["reason"], "ranked": []}
    best = ranked["ranked"][0]["alignment_score"]
    tied = [item["id"] for item in ranked["ranked"]
            if math.isclose(item["alignment_score"], best, rel_tol=1e-12, abs_tol=1e-12)]
    # The live API returns an ordering. Evaluation must not treat ID tie-breaking
    # as an actual personal preference, even when lower options have other scores.
    return {"id": case["id"], "domain": case["domain"],
            "prediction": tied[0] if len(tied) == 1 else None,
            "reason": None if len(tied) == 1 else "top_alignment_tie", "ranked": ranked["ranked"]}


def _metrics(cases: list[dict], predictions: list[dict], field: str) -> dict:
    pairs = [(case, pred) for case, pred in zip(cases, predictions) if case[field] is not None]
    labelled = len(pairs)
    answered = sum(pred["prediction"] is not None for _, pred in pairs)
    correct = sum(pred["prediction"] == case[field] for case, pred in pairs)
    reciprocal = []
    for case, pred in pairs:
        if pred["prediction"] is None:
            continue
        target = next(item["alignment_score"] for item in pred["ranked"] if item["id"] == case[field])
        scores = [item["alignment_score"] for item in pred["ranked"]]
        tied = sum(math.isclose(score, target, rel_tol=1e-12, abs_tol=1e-12) for score in scores)
        better = sum(score > target and not math.isclose(score, target, rel_tol=1e-12, abs_tol=1e-12) for score in scores)
        reciprocal.append(1 / (1 + better + (tied - 1) / 2))
    return {"labelled": labelled, "answered": answered, "correct": correct,
            "accuracy_on_answered": correct / answered if answered else None,
            "coverage": answered / labelled if labelled else None,
            "abstention_rate": (labelled - answered) / labelled if labelled else None,
            "correct_over_all_labelled": correct / labelled if labelled else None,
            "mean_reciprocal_midrank_on_answered": sum(reciprocal) / answered if answered else None,
            "uniform_random_top1_reference": sum(1 / len(case["options"]) for case, _ in pairs) / labelled if labelled else None}


def _run(cases: list[dict], rational: dict, excluded: tuple[str, ...] = ()) -> dict:
    predictions = [_predict(case, rational, excluded) for case in cases]
    def metrics(selected_cases, selected_predictions):
        return {field: _metrics(selected_cases, selected_predictions, field)
                for field in ("actual_choice", "endorsed_choice")}
    by_domain = {}
    for domain in DOMAINS:
        pairs = [(case, pred) for case, pred in zip(cases, predictions) if case["domain"] == domain]
        by_domain[domain] = metrics([c for c, _ in pairs], [p for _, p in pairs])
    return {"excluded_parameters": list(excluded), "metrics": metrics(cases, predictions),
            "by_domain": by_domain, "predictions": predictions}


def evaluate_database(path: str | Path, manifest: dict) -> dict:
    snapshot = read_snapshot(path)
    cases = validate_cases(manifest, snapshot["training_source_ids"])
    full = _run(cases, snapshot["rational"])
    ablations = {}
    for parameter in VALUE_PARAMETERS:
        run = _run(cases, snapshot["rational"], (parameter,))
        run["changed_predictions"] = sum(a["prediction"] != b["prediction"]
                                         for a, b in zip(full["predictions"], run["predictions"]))
        # Paired gains/losses use all labelled cases, not differing answered sets.
        paired = {}
        for field in ("actual_choice", "endorsed_choice"):
            gains = losses = 0
            for case, a, b in zip(cases, full["predictions"], run["predictions"]):
                if case[field] is None:
                    continue
                full_hit, removed_hit = a["prediction"] == case[field], b["prediction"] == case[field]
                gains += int(removed_hit and not full_hit)
                losses += int(full_hit and not removed_hit)
            paired[field] = {"correct_gained_without_parameter": gains, "correct_lost_without_parameter": losses}
        run["paired_comparison"] = paired
        ablations[parameter] = run
    return {"schema_version": 1, "status": "offline_experiment", "case_count": len(cases),
            "cases_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest(),
            "ranking_sha256": hashlib.sha256(Path(__file__).with_name("ranking.py").read_bytes()).hexdigest(),
            "evaluation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "snapshot": snapshot, "full": full, "ablations": ablations,
            "limitations": ["provisional_value_alignment_not_choice_probability",
                            "impacts_are_manual_annotations_not_inferred_from_events",
                            "held_out_attested_and_source_id_overlap_checked_not_semantic_leakage_proven",
                            "static_ablation_not_retrained_or_causal_evidence",
                            "no_automatic_parameter_removal_or_training",
                            "no_statistical_or_psychological_validity_claim"]}


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_number(value: str):
    raise ValueError("non-finite JSON numbers are not supported")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only held-out value-alignment evaluation")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    args = parser.parse_args()
    try:
        with args.cases.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("evaluation manifest exceeds size limit")
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_number)
        report = evaluate_database(args.db, manifest)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"evaluation failed: {type(error).__name__}: {error}\n")
    json.dump(report, sys.stdout, ensure_ascii=True, allow_nan=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
