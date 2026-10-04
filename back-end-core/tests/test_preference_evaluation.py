"""Synthetic-only offline holdout tests; never open a database or network."""

import copy
import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from model import preference_evaluation as evaluator, preferences
from model.catalog import PARTITIONS
from translator import evaluation as strict_json

EXAMPLE = ROOT / "docs/preference-evaluation.example.json"
PYTHON = sys.executable


def example():
    return evaluator.load_manifest(EXAMPLE)


def clone_case(case, suffix, *, same_group=False):
    cloned = copy.deepcopy(case)
    cloned["id"] = "case-" + suffix
    if not same_group:
        cloned["reviewed_group_id"] = "group-" + suffix
        cloned["source_ids"] = ["source-" + suffix]
        cloned["body_digests"] = [hashlib.sha256(suffix.encode()).hexdigest()]
    return cloned


def blank_label(case, target):
    case["labels"][target].update(choice_id=None, status="unknown", labelled_at=None,
                                  annotator_id=None, blind_to_outputs=None)
    if target == "endorsed":
        case["endorsement_partition"] = None


def overall(report, target="actual"):
    return report["targets"][target]["overall"]


class PreferenceEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alpha-preference-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name in ("sqlite3.connect", "socket.create_connection", "socket.socket"):
            guard = patch(name, side_effect=AssertionError("offline evaluator must not access DB/network"))
            guard.start()
            self.addCleanup(guard.stop)

    def evaluate(self, manifest=None, **kwargs):
        return evaluator.evaluate_manifest(example() if manifest is None else manifest, **kwargs)

    def invalid(self, manifest):
        with self.assertRaises(ValueError):
            evaluator.validate_manifest(manifest)

    def write_json(self, manifest, name="synthetic.json"):
        path = self.directory / name
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def cli(self, *args):
        # Deny DB/network BEFORE model package import, not just during fitting.
        script = (
            "import sqlite3, socket, sys, runpy; "
            "deny=lambda *a, **k: (_ for _ in ()).throw(AssertionError('forbidden')); "
            "sqlite3.connect=deny; socket.create_connection=deny; socket.socket=deny; "
            "sys.argv=['model.preference_evaluation']+sys.argv[1:]; "
            "runpy.run_module('model.preference_evaluation',run_name='__main__')"
        )
        env = {**os.environ, "TMPDIR": self.temp.name, "HF_HUB_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": str(ROOT)}
        return subprocess.run([PYTHON, "-B", "-c", script, *map(str, args)], cwd=self.directory,
                              env=env, capture_output=True, text=True, timeout=30)

    def test_synthetic_actual_endorsed_reversal_with_production_functions(self):
        fits, rankings = [], []
        real_fit, real_rank = preferences.fit_preferences, preferences.rank_from_fit
        def fit(records, **axis):
            result = real_fit(records, **axis)
            fits.append((axis, copy.deepcopy(records), result))
            return result
        def rank(options, fit):
            result = real_rank(options, fit)
            rankings.append((fit["target"], result))
            return result
        with patch.object(preferences, "fit_preferences", side_effect=fit), patch.object(preferences, "rank_from_fit", side_effect=rank):
            report = self.evaluate()
        self.assertEqual(len(fits), len(preferences.TARGETS) * len(PARTITIONS) * len(preferences.DOMAINS))
        self.assertEqual({target: ranked[0]["id"] for target, ranked in rankings}, {"actual": "a", "endorsed": "b"})
        for target in preferences.TARGETS:
            counts = overall(report, target)
            self.assertEqual((counts["evaluated"], counts["predicted"], counts["correct"]), (1, 1, 1))
            self.assertEqual(counts["coverage"], 1)
            self.assertEqual(counts["hit_rate"], 1)
            self.assertEqual(counts["conditional_accuracy"], 1)
        self.assertTrue(report["synthetic"])
        self.assertTrue(report["training_only_development"])
        self.assertTrue(report["not_calibrated"])
        self.assertFalse(report["validity_claim"])
        self.assertFalse(report["database_opened"])
        self.assertFalse(report["weights_persisted"])
        self.assertFalse(report["persisted_encoder_model"])
        self.assertEqual(report["ablation_eight_parameters"], "pending")

    def test_closed_root_kind_version_and_case_limit(self):
        mutations = [{"schema_version": True}, {"schema_version": 2}, {"kind": "readiness"},
                     {"data_origin": "private"}, {"cases": []}, {"cases": [None] * 1001}, {"text": "forbidden"}]
        for mutation in mutations:
            with self.subTest(keys=list(mutation)):
                manifest = example()
                manifest.update(mutation)
                self.invalid(manifest)

    def test_case_option_annotation_and_protocol_fields_are_closed(self):
        for location in ("case", "option", "label", "options_review", "exposure", "protocol"):
            manifest = example()
            case = manifest["cases"][0]
            obj = {"case": case, "option": case["options"][0], "label": case["labels"]["actual"],
                   "options_review": case["attestations"]["options_review"],
                   "exposure": case["exposure"], "protocol": manifest["protocol"]}[location]
            obj["private_reason"] = "not permitted"
            with self.subTest(location=location):
                self.invalid(manifest)
        manifest = example()
        manifest["cases"][0]["options"][0]["label"] = "private option description"
        self.invalid(manifest)

    def test_unique_opaque_ids(self):
        manifest = example()
        manifest["cases"][-1]["id"] = manifest["cases"][0]["id"]
        self.invalid(manifest)
        for value in ("", "space forbidden", "x" * 81, True, 4, [], "a\0", "\ud800"):
            manifest = example()
            manifest["cases"][0]["id"] = value
            with self.subTest(value=repr(value)):
                self.invalid(manifest)

    def test_group_cross_split_even_ineligible(self):
        manifest = example()
        held = manifest["cases"][-1]
        held["reviewed_group_id"] = manifest["cases"][0]["reviewed_group_id"]
        held["attestations"]["group_review"] = "draft"
        self.invalid(manifest)

    def test_sources_and_digests_never_cross_groups_or_splits(self):
        for field in ("source_ids", "body_digests"):
            for same_split in (False, True):
                manifest = example()
                other = manifest["cases"][1 if same_split else -1]
                other[field] = manifest["cases"][0][field][:]
                other["attestations"]["whole_source_authenticity"] = False
                with self.subTest(field=field, same_split=same_split):
                    self.invalid(manifest)

    def test_shared_provenance_within_group_is_valid_and_not_extra_support(self):
        manifest = example()
        duplicate = clone_case(manifest["cases"][0], "copied", same_group=True)
        manifest["cases"].append(duplicate)
        report = self.evaluate(manifest)
        training = report["targets"]["actual"]["training"]["rational"]["daily"]
        self.assertEqual(training["eligible_labelled_development"], 4)
        self.assertEqual(training["training_records"], 3)
        self.assertEqual(training["informative_training_groups"], 3)

    def test_invalid_digest_empty_and_duplicate_provenance(self):
        for field, value in (("source_ids", []), ("source_ids", ["a", "a"]),
                             ("body_digests", []), ("body_digests", ["f" * 63]),
                             ("body_digests", ["F" * 64]), ("body_digests", ["f" * 64] * 2),
                             ("source_ids", ["a"] * 1001)):
            manifest = example()
            manifest["cases"][0][field] = value
            with self.subTest(field=field, value=str(value)[:70]):
                self.invalid(manifest)

    def test_protocol_ordering_and_strict_utc(self):
        for field, value in (("development_end", "2026-01-05T00:00:00Z"),
                             ("held_out_start", "2026-01-07T00:00:00Z"),
                             ("frozen_at", "2026-01-05T00:00:00+00:00"),
                             ("frozen_at", "2026-02-30T00:00:00Z"),
                             ("frozen_at", "2026-01-06T00:00:00.001Z"),
                             ("frozen_at", None)):
            manifest = example()
            manifest["protocol"][field] = value
            with self.subTest(field=field, value=value):
                self.invalid(manifest)

    def test_event_times_and_labels_checked_even_ineligible(self):
        for index, field, value in ((0, "event_at", "2026-01-04T00:00:01Z"),
                                   (-1, "event_at", "2026-01-04T23:59:59Z"),
                                   (-1, "event_at", "2026-01-06T00:00:01Z"),
                                   (0, "labelled_at", "2026-01-01T11:59:59Z"),
                                   (0, "labelled_at", "2026-01-04T00:00:00Z"),
                                   (0, "labelled_at", "2026-01-04T00:00:01Z"),
                                   (-1, "labelled_at", "2026-01-06T00:00:01Z")):
            manifest = example()
            case = manifest["cases"][index]
            case["attestations"]["group_review"] = "unknown"
            if field == "event_at":
                case[field] = value
            else:
                case["labels"]["actual"][field] = value
            with self.subTest(index=index, field=field, value=value):
                self.invalid(manifest)

    def test_holdout_label_can_equal_freeze_and_event_can_equal_start(self):
        manifest = example()
        held = manifest["cases"][-1]
        held["event_at"] = manifest["protocol"]["held_out_start"]
        for target in preferences.TARGETS:
            held["labels"][target]["labelled_at"] = manifest["protocol"]["frozen_at"]
        self.assertEqual(overall(self.evaluate(manifest))["evaluated"], 1)

    def test_options_review_times_are_checked(self):
        for index, value in ((0, "2026-01-01T11:59:59Z"), (0, "2026-01-04T00:00:01Z"),
                             (-1, "2026-01-06T00:00:01Z")):
            manifest = example()
            manifest["cases"][index]["attestations"]["options_review"]["reviewed_at"] = value
            self.invalid(manifest)

    def test_boolean_attestations_reject_coercion(self):
        for field in ("training_consent", "evaluation_consent", "whole_source_authenticity"):
            for value in (0, 1, "true", [], {}):
                manifest = example()
                manifest["cases"][-1]["attestations"][field] = value
                self.invalid(manifest)
        for location in ("options", "label"):
            manifest = example()
            held = manifest["cases"][-1]
            review = held["attestations"]["options_review"] if location == "options" else held["labels"]["actual"]
            review["blind_to_outputs"] = 1
            self.invalid(manifest)

    def test_invalid_options_booleans_nulls_huge_and_nonfinite(self):
        for value in (True, None, 1.1, -1.1, 10 ** 1000, float("nan"), float("inf")):
            manifest = example()
            manifest["cases"][-1]["options"][0]["impacts"]["value.autonomy"] = value
            with self.subTest(value=str(value)[:50]):
                self.invalid(manifest)
        for value in ([], [example()["cases"][0]["options"][0]] * 9):
            manifest = example()
            manifest["cases"][-1]["options"] = value
            self.invalid(manifest)
        manifest = example()
        manifest["cases"][-1]["options"][0]["impacts"]["value.unknown"] = 1
        self.invalid(manifest)

    def test_choice_is_not_authenticity_boolean_and_must_identify_option(self):
        for value in (True, False, 0, "missing", "a\0", "\ud800"):
            manifest = example()
            manifest["cases"][-1]["labels"]["actual"]["choice_id"] = value
            self.invalid(manifest)
        manifest = example()
        manifest["cases"][-1]["attestations"]["whole_source_authenticity"] = False
        counts = overall(self.evaluate(manifest))
        self.assertEqual((counts["labelled"], counts["ineligible"], counts["evaluated"]), (1, 1, 0))

    def test_nulls_are_retained_in_counts_and_never_fabricated(self):
        manifest = example()
        held = manifest["cases"][-1]
        for target in preferences.TARGETS:
            blank_label(held, target)
        held["options"] = None
        held["event_at"] = None
        held["attestations"]["options_review"].update(status="draft", reviewed_at=None)
        counts = overall(self.evaluate(manifest))
        self.assertEqual((counts["all_held_out"], counts["labelled"], counts["unlabelled"], counts["ineligible"]), (1, 0, 1, 1))
        self.assertEqual(counts["evaluated"], 0)
        self.assertIsNone(counts["coverage"])
        self.assertIsNone(counts["hit_rate"])
        self.assertIsNone(counts["conditional_accuracy"])

    def test_independent_labels_require_choice_and_endorsement_state(self):
        manifest = example()
        manifest["cases"][-1]["labels"]["actual"]["choice_id"] = None
        self.invalid(manifest)
        manifest = example()
        manifest["cases"][-1]["endorsement_partition"] = None
        self.invalid(manifest)
        manifest = example()
        blank_label(manifest["cases"][-1], "endorsed")
        manifest["cases"][-1]["endorsement_partition"] = "rational"
        self.invalid(manifest)

    def test_missing_blind_identity_time_and_options_review_exclude(self):
        for location, field, value in (("actual", "blind_to_outputs", False),
                                       ("actual", "annotator_id", None),
                                       ("actual", "labelled_at", None),
                                       ("options", "status", "unknown"),
                                       ("options", "reviewer_id", None),
                                       ("options", "reviewed_at", None)):
            manifest = example()
            held = manifest["cases"][-1]
            annotation = held["attestations"]["options_review"] if location == "options" else held["labels"][location]
            annotation[field] = value
            counts = overall(self.evaluate(manifest))
            self.assertEqual((counts["ineligible"], counts["evaluated"]), (1, 0))

    def test_exposed_and_unknown_status_block_all_heldout_group_members(self):
        for dimension in ("model_fit", "rule_development", "manual_tuning"):
            for status in ("exposed", "unknown"):
                manifest = example()
                copied = clone_case(manifest["cases"][-1], "tainted", same_group=True)
                copied["exposure"][dimension] = status
                copied["attestations"]["group_review"] = "draft"
                manifest["cases"].append(copied)
                report = self.evaluate(manifest, details=True)
                self.assertEqual(report["blocked_held_out_groups"], 1)
                for target in preferences.TARGETS:
                    self.assertEqual(overall(report, target)["ineligible"], 2)
                    self.assertEqual(overall(report, target)["evaluated"], 0)
                self.assertTrue(all(set(row["prediction_reason"].values()) == {"ineligible"}
                                    for row in report["case_results"]))

    def test_model_assisted_options_or_either_label_block_entire_heldout_group(self):
        for location in ("options", "actual", "endorsed"):
            manifest = example()
            copied = clone_case(manifest["cases"][-1], "assisted", same_group=True)
            annotation = copied["attestations"]["options_review"] if location == "options" else copied["labels"][location]
            annotation["status"] = "model_assisted"
            manifest["cases"].append(copied)
            report = self.evaluate(manifest)
            for target in preferences.TARGETS:
                self.assertEqual(overall(report, target)["ineligible"], 2)
                self.assertEqual(overall(report, target)["evaluated"], 0)

    def test_development_model_assisted_draft_unknown_labels_not_fit(self):
        for status in ("model_assisted", "draft", "unknown"):
            manifest = example()
            manifest["cases"][0]["labels"]["actual"]["status"] = status
            report = self.evaluate(manifest)
            self.assertEqual(report["targets"]["actual"]["training"]["rational"]["daily"]["training_records"], 2)
            self.assertEqual(overall(report)["abstain"], 1)
            self.assertEqual(overall(report, "endorsed")["correct"], 1)

    def test_training_consent_only_affects_development_eval_consent_is_separate(self):
        for consent in (False, None):
            manifest = example()
            manifest["cases"][-1]["attestations"]["training_consent"] = consent
            self.assertEqual(overall(self.evaluate(manifest))["correct"], 1)
            manifest["cases"][0]["attestations"]["training_consent"] = consent
            self.assertEqual(overall(self.evaluate(manifest))["abstain"], 1)
        manifest = example()
        manifest["cases"][-1]["attestations"]["evaluation_consent"] = False
        self.assertEqual(overall(self.evaluate(manifest))["ineligible"], 1)

    def test_endorsed_requires_rational_state_not_event_partition(self):
        manifest = example()
        for case in manifest["cases"]:
            case["partition"] = "emotional"
        report = self.evaluate(manifest)
        self.assertEqual(report["targets"]["actual"]["by_partition"]["emotional"]["correct"], 1)
        self.assertEqual(report["targets"]["endorsed"]["by_partition"]["rational"]["correct"], 1)
        manifest["cases"][-1]["endorsement_partition"] = "crazy"
        report = self.evaluate(manifest)
        self.assertEqual(overall(report, "endorsed")["ineligible"], 1)
        self.assertEqual(overall(report)["correct"], 1)

    def test_domain_and_partition_axes_are_isolated(self):
        manifest = example()
        manifest["cases"][-1]["domain"] = "study"
        report = self.evaluate(manifest)
        self.assertEqual(overall(report)["abstain"], 1)
        self.assertEqual(report["targets"]["actual"]["by_domain"]["study"]["evaluated"], 1)
        manifest = example()
        manifest["cases"][-1]["partition"] = "crazy"
        report = self.evaluate(manifest)
        self.assertEqual(overall(report)["abstain"], 1)
        self.assertEqual(overall(report, "endorsed")["correct"], 1)

    def test_untrained_and_unsupported_and_tied_keep_abstention_denominators(self):
        manifest = example()
        unsupported = clone_case(manifest["cases"][-1], "unsupported")
        unsupported["options"] = [{"id": "a", "impacts": {"value.connection": 1}},
                                  {"id": "b", "impacts": {"value.connection": -1}}]
        tied = clone_case(manifest["cases"][-1], "tied")
        tied["options"] = [{"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}]
        untrained = clone_case(manifest["cases"][-1], "untrained")
        untrained["domain"] = "relationships"
        manifest["cases"].extend([unsupported, tied, untrained])
        counts = overall(self.evaluate(manifest))
        self.assertEqual((counts["evaluated"], counts["abstain"], counts["predicted"], counts["correct"]), (4, 3, 1, 1))
        self.assertEqual(counts["coverage"], .25)
        self.assertEqual(counts["hit_rate"], .25)
        self.assertEqual(counts["conditional_accuracy"], 1)
        self.assertEqual(counts["macro_group"]["hit_rate"], .25)

    def test_conflicting_balanced_labels_abstain_without_dropping_counterexamples(self):
        manifest = example()
        manifest["cases"][1]["labels"]["actual"]["choice_id"] = "b"
        extra = clone_case(manifest["cases"][0], "fourth-development")
        extra["labels"]["actual"]["choice_id"] = "b"
        manifest["cases"].append(extra)
        counts = overall(self.evaluate(manifest))
        self.assertEqual((counts["evaluated"], counts["abstain"], counts["correct"]), (1, 1, 0))
        self.assertEqual(counts["hit_rate"], 0)

    def test_no_heldout_label_or_source_provenance_reaches_fit(self):
        manifest = example()
        calls = []
        real = preferences.fit_preferences
        def guarded(records, **axis):
            calls.append((copy.deepcopy(records), axis))
            for record in records:
                self.assertTrue(record["source_id"].startswith("synth-event-"))
                self.assertNotEqual(record["source_id"], "synth-event-4")
                self.assertNotIn("source_ids", record)
                self.assertNotIn("body_digests", record)
                self.assertIsNone(record["endorsed_choice_id"] if axis["target"] == "actual" else record["actual_choice_id"])
            return real(records, **axis)
        with patch.object(preferences, "fit_preferences", side_effect=guarded):
            self.evaluate(manifest)
        self.assertEqual(len(calls), 18)

    def test_all_predictions_complete_before_score_reads_heldout_choices(self):
        manifest = example()
        manifest["cases"].append(clone_case(manifest["cases"][-1], "second-test"))
        validated = evaluator.validate_manifest(manifest)
        state = {"queries": 0, "guard": False}
        class GuardedLabel(dict):
            def __getitem__(self, key):
                if key == "choice_id" and state["guard"] and state["queries"] != 4:
                    raise AssertionError("heldout label accessed before every prediction")
                return super().__getitem__(key)
        for case in validated:
            if case["split"] == "held_out":
                for target in preferences.TARGETS:
                    case["labels"][target] = GuardedLabel(case["labels"][target])
        real = preferences.rank_from_fit
        def guarded_rank(options, fit):
            self.assertEqual(set(options[0]), {"id", "impacts"})
            state["queries"] += 1
            return real(options, fit)
        def validated_only(_):
            state["guard"] = True
            return validated
        with patch.object(evaluator, "validate_manifest", side_effect=validated_only), patch.object(preferences, "rank_from_fit", side_effect=guarded_rank):
            report = self.evaluate(manifest)
        self.assertEqual(state["queries"], 4)
        self.assertEqual(overall(report)["correct"], 2)

    def test_heldout_choice_flip_changes_score_not_fit_or_predictions(self):
        manifest = example()
        original_rank = preferences.rank_from_fit
        runs = []
        for flipped in (False, True):
            traces = []
            if flipped:
                manifest["cases"][-1]["labels"]["actual"]["choice_id"] = "b"
                manifest["cases"][-1]["labels"]["endorsed"]["choice_id"] = "a"
            def rank(options, fit):
                result = original_rank(options, fit)
                traces.append((copy.deepcopy(fit), copy.deepcopy(result)))
                return result
            with patch.object(preferences, "rank_from_fit", side_effect=rank):
                report = self.evaluate(manifest)
            runs.append((traces, report))
        self.assertEqual(runs[0][0], runs[1][0])
        self.assertEqual(overall(runs[0][1])["correct"], 1)
        self.assertEqual(overall(runs[1][1])["correct"], 0)

    def test_case_and_option_permutation_preserve_fit_metrics_and_input(self):
        manifest = example()
        before = copy.deepcopy(manifest)
        original = self.evaluate(manifest)
        self.assertEqual(manifest, before)
        manifest["cases"].reverse()
        for case in manifest["cases"]:
            case["options"].reverse()
        permuted = self.evaluate(manifest)
        self.assertEqual(original["targets"], permuted["targets"])
        self.assertNotEqual(original["manifest_fingerprint"], permuted["manifest_fingerprint"])

    def test_event_group_mass_and_exact_training_copies_do_not_reweight_counterexample(self):
        manifest = example()
        counterexample = clone_case(manifest["cases"][0], "counterexample", same_group=True)
        counterexample["labels"]["actual"]["choice_id"] = "b"
        manifest["cases"].append(counterexample)
        records, _ = evaluator._development_records(manifest["cases"], "actual", "rational", "daily")
        fit = preferences.fit_preferences(records, target="actual", partition="rational", domain="daily")
        for index in range(8):
            manifest["cases"].append(clone_case(counterexample, "copy-" + str(index), same_group=True))
        copied_records, _ = evaluator._development_records(manifest["cases"], "actual", "rational", "daily")
        copied_fit = preferences.fit_preferences(copied_records, target="actual", partition="rational", domain="daily")
        self.assertEqual(records, copied_records)
        self.assertEqual(fit, copied_fit)
        self.assertEqual(fit["training_sources"], 3)
        self.assertEqual(len(records), 4)
        self.assertEqual({record["source_id"] for record in records}, {"synth-event-1", "synth-event-2", "synth-event-3"})

    def test_distinct_event_time_within_group_is_not_deduplicated(self):
        manifest = example()
        extra = clone_case(manifest["cases"][0], "later-event", same_group=True)
        extra["event_at"] = "2026-01-01T12:00:01Z"
        manifest["cases"].append(extra)
        report = self.evaluate(manifest)
        training = report["targets"]["actual"]["training"]["rational"]["daily"]
        self.assertEqual(training["training_records"], 4)
        self.assertEqual(training["informative_training_groups"], 3)

    def test_exact_scoring_copies_never_improve_within_group_or_aggregate_hit_fraction(self):
        manifest = example()
        wrong = clone_case(manifest["cases"][-1], "wrong-same-event", same_group=True)
        wrong["labels"]["actual"]["choice_id"] = "b"
        manifest["cases"].append(wrong)
        other_group = clone_case(wrong, "wrong-other-group")
        manifest["cases"].append(other_group)
        baseline = overall(self.evaluate(manifest))
        for index in range(8):
            manifest["cases"].append(clone_case(manifest["cases"][3], "good-copy-" + str(index), same_group=True))
        copied = overall(self.evaluate(manifest))
        self.assertEqual(baseline["hit_rate"], 1 / 3)
        self.assertEqual(baseline["macro_group"]["hit_rate"], .25)
        self.assertEqual(copied["all_held_out"], 11)
        self.assertEqual(copied["duplicate_cases"], 8)
        self.assertEqual(copied["unique_held_out_events"], 3)
        for key in ("evaluated", "abstain", "predicted", "correct", "coverage", "hit_rate", "conditional_accuracy", "macro_group"):
            self.assertEqual(baseline[key], copied[key])

    def test_other_target_labels_states_and_statuses_cannot_reweight_actual_fit(self):
        manifest = example()
        duplicate = clone_case(manifest["cases"][0], "actual-copy", same_group=True)
        counterexample = clone_case(manifest["cases"][0], "actual-counterexample", same_group=True)
        counterexample["labels"]["actual"]["choice_id"] = "b"
        manifest["cases"].extend([duplicate, counterexample])
        before_records, _ = evaluator._development_records(manifest["cases"], "actual", "rational", "daily")
        before = self.evaluate(manifest)["targets"]["actual"]
        duplicate["labels"]["endorsed"].update(choice_id="a", status="draft")
        duplicate["endorsement_partition"] = "emotional"
        changed_records, _ = evaluator._development_records(manifest["cases"], "actual", "rational", "daily")
        self.assertEqual(before_records, changed_records)
        self.assertEqual(before, self.evaluate(manifest)["targets"]["actual"])

    def test_other_actual_label_status_cannot_reweight_endorsed_fit(self):
        manifest = example()
        duplicate = clone_case(manifest["cases"][0], "endorsed-copy", same_group=True)
        counterexample = clone_case(manifest["cases"][0], "endorsed-counterexample", same_group=True)
        counterexample["labels"]["endorsed"]["choice_id"] = "a"
        manifest["cases"].extend([duplicate, counterexample])
        before_records, _ = evaluator._development_records(manifest["cases"], "endorsed", "rational", "daily")
        before = self.evaluate(manifest)["targets"]["endorsed"]
        duplicate["labels"]["actual"].update(choice_id="b", status="unknown")
        changed_records, _ = evaluator._development_records(manifest["cases"], "endorsed", "rational", "daily")
        self.assertEqual(before_records, changed_records)
        self.assertEqual(before, self.evaluate(manifest)["targets"]["endorsed"])

    def test_other_target_changes_do_not_change_target_scoring_copy_identity(self):
        for target, other in (("actual", "endorsed"), ("endorsed", "actual")):
            manifest = example()
            duplicate = clone_case(manifest["cases"][-1], "same-target-copy", same_group=True)
            wrong = clone_case(manifest["cases"][-1], "target-counterexample", same_group=True)
            wrong["labels"][target]["choice_id"] = "b" if target == "actual" else "a"
            manifest["cases"].extend([duplicate, wrong])
            before = self.evaluate(manifest)["targets"][target]
            duplicate["labels"][other].update(choice_id="a" if other == "endorsed" else "b", status="draft")
            if other == "endorsed":
                duplicate["endorsement_partition"] = "crazy"
            self.assertEqual(before, self.evaluate(manifest)["targets"][target])

    def test_eligibility_variant_cannot_override_scored_copy(self):
        manifest = example()
        duplicate = clone_case(manifest["cases"][-1], "excluded-copy", same_group=True)
        duplicate["attestations"]["evaluation_consent"] = False
        manifest["cases"].append(duplicate)
        counts = overall(self.evaluate(manifest))
        self.assertEqual((counts["all_held_out"], counts["ineligible"], counts["evaluated"], counts["correct"]), (2, 1, 1, 1))
        self.assertEqual(counts["unique_held_out_events"], 1)
        self.assertEqual(counts["unique_scoring_units"], 2)
        self.assertEqual(counts["all_held_out_coverage"], .5)

    def test_copy_eligibility_id_swap_and_permutation_cannot_hide_ineligible(self):
        manifest = example()
        for status in ("draft", "unknown"):
            variant = clone_case(manifest["cases"][-1], "audit-" + status, same_group=True)
            variant["labels"]["actual"].update(status=status, blind_to_outputs=None)
            manifest["cases"].append(variant)
        before = self.evaluate(manifest)["targets"]
        held = manifest["cases"][3:]
        ids = [case["id"] for case in held]
        for case, identifier in zip(held, reversed(ids)):
            case["id"] = identifier
        manifest["cases"].reverse()
        after = self.evaluate(manifest)["targets"]
        self.assertEqual(before, after)
        self.assertEqual(before["actual"]["overall"]["all_held_out"], 3)
        self.assertEqual(before["actual"]["overall"]["ineligible"], 2)
        self.assertEqual(before["actual"]["overall"]["unique_held_out_events"], 1)

    def test_solver_reason_enum_does_not_control_abstention(self):
        real = preferences.fit_preferences
        def unconverged(records, **axis):
            result = real(records, **axis)
            result.update(status="abstain", reason="fit_not_converged")
            return result
        with patch.object(preferences, "fit_preferences", side_effect=unconverged):
            report = self.evaluate(details=True)
        self.assertEqual(overall(report)["abstain"], 1)
        self.assertEqual(report["case_results"][0]["prediction_reason"]["actual"], "fit_abstained")

    def test_validate_only_does_not_fit_or_rank_or_claim_evaluation(self):
        with patch.object(preferences, "fit_preferences", side_effect=AssertionError("no fit")), patch.object(preferences, "rank_from_fit", side_effect=AssertionError("no rank")):
            report = self.evaluate(validate_only=True, details=True)
        self.assertEqual(report["status"], "manifest_validation_only")
        self.assertNotIn("targets", report)
        self.assertNotIn("case_results", report)

    def test_default_privacy_and_details_only_case_id_reason(self):
        manifest = example()
        default = self.evaluate(manifest)
        text = json.dumps(default)
        for case in manifest["cases"]:
            for value in (case["id"], case["reviewed_group_id"], *case["source_ids"], *case["body_digests"]):
                self.assertNotIn(value, text)
        for field in ("impacts", "choice_id", "weights", "model_probability", "contributions"):
            self.assertNotIn('"' + field + '"', text)
        detailed = self.evaluate(manifest, details=True)
        self.assertEqual(set(detailed["case_results"][0]), {"id", "prediction_reason"})
        self.assertEqual(set(detailed["case_results"][0]["prediction_reason"]), {"actual", "endorsed"})

    def test_strict_json_duplicate_keys_nonfinite_nul_surrogate_and_bad_utf8(self):
        for content in (b'{"schema_version":1,"schema_version":1}', b'{"nested":{"x":1,"x":2}}',
                        b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e10000}',
                        b'{"x":"\\u0000"}', b'{"x":"\\ud800"}', b'\xff', b'{'):
            path = self.directory / "strict.json"
            path.write_bytes(content)
            with self.subTest(content=repr(content)), self.assertRaises(ValueError):
                evaluator.load_manifest(path)

    def test_bounded_loader_reads_limit_plus_one_only(self):
        path = self.directory / "bounded.json"
        path.write_bytes(b" " * 1000)
        reads, original_fdopen = [], os.fdopen
        class Tracked:
            def __init__(self, descriptor, mode):
                self.stream = original_fdopen(descriptor, mode)
            def __enter__(self):
                self.stream.__enter__()
                return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def fileno(self):
                return self.stream.fileno()
            def read(self, limit):
                reads.append(limit)
                return self.stream.read(limit)
        with patch.object(evaluator, "MAX_FILE_BYTES", 32), patch.object(strict_json.os, "fdopen", side_effect=Tracked):
            with self.assertRaises(ValueError):
                evaluator.load_manifest(path)
        self.assertEqual(reads, [33])

    def test_nonregular_fifo_rejected_without_waiting(self):
        path = self.directory / "synthetic-fifo"
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            evaluator.load_manifest(path)

    def test_cli_stdout_json_details_and_no_database_or_network(self):
        before = sorted(path.name for path in self.directory.iterdir())
        result = self.cli("--manifest", EXAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        report = json.loads(result.stdout)
        self.assertEqual(overall(report)["correct"], 1)
        self.assertEqual(before, sorted(path.name for path in self.directory.iterdir()))
        detailed = self.cli("--manifest", EXAMPLE, "--details")
        self.assertEqual(detailed.returncode, 0, detailed.stderr)
        self.assertEqual(set(json.loads(detailed.stdout)["case_results"][0]), {"id", "prediction_reason"})

    def test_cli_validate_only_and_generic_error_privacy(self):
        checked = self.cli("--manifest", EXAMPLE, "--validate-only")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("targets", json.loads(checked.stdout))
        manifest = example()
        manifest["cases"][-1]["options"][0]["label"] = "PRIVATE_REASON_MARKER"
        private_path = self.write_json(manifest, "PRIVATE_PATH_MARKER.json")
        for arguments in (("--manifest", private_path), ("--manifest", self.directory / "PRIVATE_MISSING_MARKER"),
                          ("--private-marker", "PRIVATE_ARGUMENT_MARKER"), ()):
            result = self.cli(*arguments)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, evaluator._ERROR)
            self.assertNotIn("PRIVATE", result.stderr)
            self.assertNotIn(str(self.directory), result.stderr)

    def test_cli_generic_privacy_for_unexpected_runtime_error(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["evaluator", "--manifest", str(EXAMPLE)]), patch.object(evaluator, "evaluate_manifest", side_effect=RuntimeError("PRIVATE_TRACE_MARKER")), redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exited:
                evaluator.main()
        self.assertEqual(exited.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), evaluator._ERROR)


if __name__ == "__main__":
    unittest.main()
