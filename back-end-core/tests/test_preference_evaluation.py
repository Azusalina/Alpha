"""Synthetic-only offline holdout tests; never open a database or network."""

import copy
import hashlib
import io
import json
import math
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


def growth_security_options(growth=1, security=1):
    return [{"id": "a", "impacts": {"value.growth": growth, "value.security": security}},
            {"id": "b", "impacts": {}}]


def growth_security_manifest():
    # Three independently reviewed synthetic groups all vary the same direction.
    manifest = example()
    for case in manifest["cases"]:
        case["options"] = growth_security_options()
    manifest["cases"][-1]["options"] = growth_security_options(security=-.5)
    return manifest


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
        self.assertEqual(report["ablation_eight_parameters"], "not_requested")

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

    def test_rank_one_joint_features_refuse_out_of_span_and_keep_denominators(self):
        manifest = growth_security_manifest()
        supported = clone_case(manifest["cases"][-1], "joint-supported")
        supported["options"] = growth_security_options()
        manifest["cases"].append(supported)
        report = self.evaluate(manifest, details=True)
        for target in preferences.TARGETS:
            records, _ = evaluator._development_records(manifest["cases"], target, "rational", "daily")
            fit = preferences.fit_preferences(records, target=target, partition="rational", domain="daily")
            self.assertEqual(fit["status"], "provisional")
            self.assertEqual(fit["training_groups"], 3)
            self.assertEqual(set(fit["used_features"]), {"value.growth", "value.security"})
            self.assertEqual(fit["contrast_rank"], 1)
            self.assertEqual(len(fit["contrast_basis"]), 1)
            self.assertEqual(preferences.rank_from_fit(manifest["cases"][3]["options"], fit), [])
            self.assertTrue(preferences.rank_from_fit(supported["options"], fit))
            self.assertEqual(report["targets"][target]["training"]["rational"]["daily"]["contrast_rank"], 1)
            counts = overall(report, target)
            self.assertEqual((counts["evaluated"], counts["abstain"], counts["predicted"], counts["correct"]),
                             (2, 1, 1, 1))
            for key in ("coverage", "hit_rate", "all_held_out_coverage", "all_held_out_hit_rate"):
                self.assertEqual(counts[key], .5)
            self.assertEqual(counts["conditional_accuracy"], 1)
            self.assertEqual(counts["macro_group"]["coverage"], .5)
            self.assertEqual(counts["macro_group"]["hit_rate"], .5)
        reasons = {row["id"]: row["prediction_reason"] for row in report["case_results"]}
        self.assertEqual(set(reasons[manifest["cases"][3]["id"]].values()), {"unsupported_or_tied_options"})
        self.assertEqual(set(reasons[supported["id"]].values()), {"predicted"})

    def test_independent_development_direction_spans_query_and_predicts(self):
        manifest = growth_security_manifest()
        for index, case in enumerate(manifest["cases"][:3]):
            independent = clone_case(case, "independent-" + str(index))
            independent["options"] = growth_security_options(security=0)
            manifest["cases"].append(independent)
        report = self.evaluate(manifest, details=True)
        for target, choice in (("actual", "a"), ("endorsed", "b")):
            records, _ = evaluator._development_records(manifest["cases"], target, "rational", "daily")
            fit = preferences.fit_preferences(records, target=target, partition="rational", domain="daily")
            self.assertEqual(fit["status"], "provisional")
            self.assertEqual(fit["contrast_rank"], 2)
            self.assertEqual(len(fit["contrast_basis"]), 2)
            self.assertEqual(preferences.rank_from_fit(manifest["cases"][3]["options"], fit)[0]["id"], choice)
            self.assertEqual(report["targets"][target]["training"]["rational"]["daily"]["contrast_rank"], 2)
            self.assertEqual((overall(report, target)["predicted"], overall(report, target)["correct"]), (1, 1))
        self.assertEqual(set(report["case_results"][0]["prediction_reason"].values()), {"predicted"})

    def test_other_target_partition_or_domain_geometry_cannot_rescue_query(self):
        real_fit, real_rank = preferences.fit_preferences, preferences.rank_from_fit
        for target in preferences.TARGETS:
            for exclusion in ("other_target", "partition", "domain"):
                with self.subTest(target=target, exclusion=exclusion):
                    manifest = growth_security_manifest()
                    base_records, _ = evaluator._development_records(manifest["cases"], target, "rational", "daily")
                    base_fit = real_fit(base_records, target=target, partition="rational", domain="daily")
                    other = "endorsed" if target == "actual" else "actual"
                    for index, case in enumerate(manifest["cases"][:3]):
                        extra = clone_case(case, "excluded-direction-" + str(index))
                        extra["options"] = growth_security_options(security=0)
                        if exclusion == "other_target":
                            blank_label(extra, target)
                        elif exclusion == "partition":
                            extra["partition"] = "emotional"
                            extra["endorsement_partition"] = "emotional"
                        else:
                            extra["domain"] = "study"
                        manifest["cases"].append(extra)
                    fits, queries = {}, []
                    def fit(records, **axis):
                        result = real_fit(records, **axis)
                        fits[(axis["target"], axis["partition"], axis["domain"])] = copy.deepcopy(result)
                        return result
                    def rank(options, fit):
                        result = real_rank(options, fit)
                        queries.append((copy.deepcopy(options), copy.deepcopy(fit), copy.deepcopy(result)))
                        return result
                    with patch.object(preferences, "fit_preferences", side_effect=fit), patch.object(preferences, "rank_from_fit", side_effect=rank):
                        report = self.evaluate(manifest, details=True)
                    selected_fit = fits[(target, "rational", "daily")]
                    self.assertEqual(selected_fit, base_fit)
                    self.assertEqual(selected_fit["contrast_rank"], 1)
                    selected_query = next(query for query in queries if query[1]["target"] == target)
                    self.assertEqual(selected_query[0], evaluator._canonical_options(manifest["cases"][3]["options"]))
                    self.assertEqual(selected_query[1], base_fit)
                    self.assertEqual(selected_query[2], [])
                    self.assertEqual((overall(report, target)["evaluated"], overall(report, target)["abstain"]), (1, 1))
                    self.assertEqual(report["case_results"][0]["prediction_reason"][target], "unsupported_or_tied_options")
                    if exclusion == "other_target":
                        self.assertEqual(fits[(other, "rational", "daily")]["contrast_rank"], 2)
                        self.assertEqual(overall(report, other)["predicted"], 1)
                    elif exclusion == "domain":
                        self.assertEqual(fits[(target, "rational", "study")]["contrast_rank"], 1)
                    elif target == "actual":
                        self.assertEqual(fits[(target, "emotional", "daily")]["contrast_rank"], 1)

    def test_full_eight_rank_reports_only_scalar_with_three_reviewed_groups(self):
        manifest = growth_security_manifest()
        development = []
        for group, case in enumerate(manifest["cases"][:3]):
            for dimension, feature in enumerate(evaluator.VALUE_PARAMETERS):
                event = clone_case(case, "full-rank-" + str(group) + "-" + str(dimension), same_group=True)
                event["options"] = [{"id": "a", "impacts": {feature: 1}}, {"id": "b", "impacts": {}}]
                development.append(event)
        manifest["cases"] = development + [manifest["cases"][-1]]
        report = self.evaluate(manifest)
        for target in preferences.TARGETS:
            training = report["targets"][target]["training"]["rational"]["daily"]
            self.assertEqual(training["informative_training_groups"], 3)
            self.assertEqual(training["training_records"], 24)
            self.assertIs(type(training["contrast_rank"]), int)
            self.assertEqual(training["contrast_rank"], 8)
            self.assertEqual((overall(report, target)["evaluated"], overall(report, target)["correct"]), (1, 1))
        self.assertNotIn('"contrast_basis"', json.dumps(report))

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
        manifest = growth_security_manifest()
        supported = clone_case(manifest["cases"][-1], "flip-supported")
        supported["options"] = growth_security_options()
        manifest["cases"].append(supported)
        original_rank = preferences.rank_from_fit
        runs = []
        for flipped in (False, True):
            traces = []
            if flipped:
                for case in manifest["cases"]:
                    if case["split"] == "held_out":
                        case["labels"]["actual"]["choice_id"] = "b"
                        case["labels"]["endorsed"]["choice_id"] = "a"
            def rank(options, fit):
                result = original_rank(options, fit)
                traces.append((copy.deepcopy(fit), copy.deepcopy(result)))
                return result
            with patch.object(preferences, "rank_from_fit", side_effect=rank):
                report = self.evaluate(manifest)
            runs.append((traces, report))
        self.assertEqual(runs[0][0], runs[1][0])
        for fit, result in runs[0][0]:
            self.assertEqual(fit["contrast_rank"], 1)
            self.assertEqual(len(fit["contrast_basis"]), 1)
        self.assertEqual(sum(bool(result) for fit, result in runs[0][0]), 2)
        for target in preferences.TARGETS:
            self.assertEqual(runs[0][1]["targets"][target]["training"], runs[1][1]["targets"][target]["training"])
            self.assertEqual(overall(runs[0][1], target)["correct"], 1)
            self.assertEqual(overall(runs[1][1], target)["correct"], 0)
            for run in runs:
                self.assertEqual((overall(run[1], target)["evaluated"], overall(run[1], target)["abstain"]), (2, 1))

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

    def test_canonical_impacts_equate_numeric_types_signed_zeros_and_omissions(self):
        manifest = example()
        base = evaluator.validate_manifest(manifest)[0]
        before = json.dumps(base, sort_keys=True)
        canonical = evaluator._canonical_options(base["options"])
        float_only = copy.deepcopy(base)
        for option in float_only["options"]:
            option["impacts"] = {feature: float(value) for feature, value in option["impacts"].items()}
        evaluator.validate_manifest({**manifest, "cases": [float_only]})
        self.assertEqual(evaluator._hash(canonical),
                         evaluator._hash(evaluator._canonical_options(float_only["options"])))
        for zero in (0, 0.0, -0.0):
            variant = copy.deepcopy(base)
            variant["options"].reverse()
            for option in variant["options"]:
                option["impacts"] = {
                    feature: float(option["impacts"][feature]) if feature in option["impacts"] else zero
                    for feature in evaluator.VALUE_PARAMETERS}
            variant = evaluator.validate_manifest({**manifest, "cases": [variant]})[0]
            variant_before = json.dumps(variant, sort_keys=True)
            normalized = evaluator._canonical_options(variant["options"])
            with self.subTest(zero=repr(zero)):
                self.assertEqual(evaluator._hash(canonical), evaluator._hash(normalized))
                for target in preferences.TARGETS:
                    self.assertEqual(evaluator._event_identity(base, target),
                                     evaluator._event_identity(variant, target))
                self.assertTrue(all(type(value) is float for option in normalized
                                    for value in option["impacts"].values()))
                self.assertEqual(json.dumps(variant, sort_keys=True), variant_before)
        self.assertEqual(json.dumps(base, sort_keys=True), before)
        empty = copy.deepcopy(base)
        empty["options"][0]["impacts"] = {}
        explicit = copy.deepcopy(empty)
        explicit["options"][0]["impacts"] = dict.fromkeys(evaluator.VALUE_PARAMETERS, -0.0)
        for case in (empty, explicit):
            evaluator.validate_manifest({**manifest, "cases": [case]})
        self.assertEqual(evaluator._hash(evaluator._canonical_options(empty["options"])),
                         evaluator._hash(evaluator._canonical_options(explicit["options"])))

    def test_numeric_heldout_copies_preserve_counts_hit_rates_and_group_metrics(self):
        manifest = example()
        wrong = clone_case(manifest["cases"][-1], "numeric-wrong", same_group=True)
        wrong["labels"]["actual"]["choice_id"] = "b"
        wrong["labels"]["endorsed"]["choice_id"] = "a"
        manifest["cases"].append(wrong)
        baseline = self.evaluate(manifest)
        for index, zero in enumerate((0, 0.0, -0.0)):
            duplicate = clone_case(manifest["cases"][3], "numeric-held-copy-" + str(index), same_group=True)
            for option in duplicate["options"]:
                option["impacts"] = {
                    feature: float(option["impacts"][feature]) if feature in option["impacts"] else zero
                    for feature in evaluator.VALUE_PARAMETERS}
            duplicate["options"].reverse()
            manifest["cases"].append(duplicate)
        before = json.dumps(manifest, sort_keys=True)
        copied = self.evaluate(manifest)
        self.assertEqual(json.dumps(manifest, sort_keys=True), before)
        raw_counts = {"all_held_out", "labelled", "unlabelled", "ineligible",
                      "copied_event_cases", "duplicate_cases"}
        for target in preferences.TARGETS:
            self.assertEqual(overall(baseline, target)["hit_rate"], .5)
            self.assertEqual(overall(baseline, target)["macro_group"]["hit_rate"], .5)
            summaries = [(overall(baseline, target), overall(copied, target))]
            for partition in PARTITIONS:
                summaries.append((baseline["targets"][target]["by_partition"][partition],
                                  copied["targets"][target]["by_partition"][partition]))
                for domain in preferences.DOMAINS:
                    summaries.append((baseline["targets"][target]["by_partition_domain"][partition][domain],
                                      copied["targets"][target]["by_partition_domain"][partition][domain]))
            for domain in preferences.DOMAINS:
                summaries.append((baseline["targets"][target]["by_domain"][domain],
                                  copied["targets"][target]["by_domain"][domain]))
            for original, changed in summaries:
                self.assertEqual({key: value for key, value in original.items() if key not in raw_counts},
                                 {key: value for key, value in changed.items() if key not in raw_counts})
            counts = overall(copied, target)
            self.assertEqual((counts["all_held_out"], counts["labelled"], counts["duplicate_cases"],
                              counts["copied_event_cases"]), (5, 5, 3, 3))
            self.assertEqual((counts["unique_held_out_events"], counts["evaluated"],
                              counts["predicted"], counts["correct"]), (2, 2, 2, 1))

    def test_numeric_development_copies_preserve_records_weights_and_query_result(self):
        manifest = example()
        counterexample = clone_case(manifest["cases"][0], "numeric-dev-counterexample", same_group=True)
        counterexample["labels"]["actual"]["choice_id"] = "b"
        counterexample["labels"]["endorsed"]["choice_id"] = "a"
        manifest["cases"].append(counterexample)
        baseline_cases = evaluator.validate_manifest(manifest)
        baseline = self.evaluate(manifest)
        for index, zero in enumerate((0, 0.0, -0.0)):
            duplicate = clone_case(counterexample, "numeric-dev-copy-" + str(index), same_group=True)
            for option in duplicate["options"]:
                option["impacts"] = {
                    feature: float(option["impacts"][feature]) if feature in option["impacts"] else zero
                    for feature in evaluator.VALUE_PARAMETERS}
            duplicate["options"].reverse()
            manifest["cases"].append(duplicate)
        before = json.dumps(manifest, sort_keys=True)
        copied_cases = evaluator.validate_manifest(manifest)
        copied = self.evaluate(manifest)
        for target, selected in (("actual", "a"), ("endorsed", "b")):
            records, labelled = evaluator._development_records(baseline_cases, target, "rational", "daily")
            copied_records, copied_labelled = evaluator._development_records(copied_cases, target, "rational", "daily")
            self.assertEqual((len(records), labelled, copied_labelled), (4, 4, 7))
            self.assertEqual(records, copied_records)
            axis = {"target": target, "partition": "rational", "domain": "daily"}
            fit = preferences.fit_preferences(records, **axis)
            copied_fit = preferences.fit_preferences(copied_records, **axis)
            self.assertEqual(fit["training_sources"], 3)
            self.assertEqual(fit["weights"], copied_fit["weights"])
            query = baseline_cases[3]["options"]
            result = preferences.rank_from_fit(query, fit)
            self.assertEqual(result[0]["id"], selected)
            self.assertEqual(result, preferences.rank_from_fit(query, copied_fit))
            self.assertEqual(overall(baseline, target), overall(copied, target))
            training = copied["targets"][target]["training"]["rational"]["daily"]
            self.assertEqual((training["training_records"], training["eligible_development_groups"],
                              training["eligible_labelled_development"]), (4, 3, 7))
        self.assertEqual(json.dumps(manifest, sort_keys=True), before)

    def test_canonical_impacts_preserve_exact_nonzero_distinctions_and_counterexamples(self):
        manifest = example()
        base = manifest["cases"][0]
        variants = [base]
        # Include the smallest subnormal and adjacent floats: never round or use a tolerance.
        for index, value in enumerate((math.ulp(0.0), -math.ulp(0.0), 1e-12,
                                       math.nextafter(1e-12, 1.0), .5,
                                       math.nextafter(.5, 1.0))):
            variant = clone_case(base, "nonzero-" + str(index), same_group=True)
            variant["options"][0]["impacts"]["value.autonomy"] = value
            variants.append(variant)
        missing = clone_case(base, "nonzero-missing", same_group=True)
        missing["options"][0]["impacts"] = {}
        variants.append(missing)
        counterexample = clone_case(base, "nonzero-counterexample", same_group=True)
        counterexample["labels"]["actual"]["choice_id"] = "b"
        counterexample["labels"]["endorsed"]["choice_id"] = "a"
        variants.append(counterexample)
        manifest["cases"] = variants
        cases = evaluator.validate_manifest(manifest)
        for target in preferences.TARGETS:
            self.assertEqual(len({evaluator._event_identity(case, target) for case in cases}), len(cases))
            records, _ = evaluator._development_records(cases, target, "rational", "daily")
            self.assertEqual(len(records), len(cases))
        for case in cases:
            normalized = evaluator._canonical_options(case["options"])
            self.assertEqual(normalized[0]["impacts"].get("value.autonomy", 0),
                             case["options"][0]["impacts"].get("value.autonomy", 0))

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
            # Different counts catch accidentally reporting sources as groups.
            result["training_sources"] += 1
            return result
        with patch.object(preferences, "fit_preferences", side_effect=unconverged):
            report = self.evaluate(details=True)
        self.assertEqual(overall(report)["abstain"], 1)
        self.assertEqual(report["case_results"][0]["prediction_reason"]["actual"], "fit_abstained")
        for target in preferences.TARGETS:
            training = report["targets"][target]["training"]["rational"]
            self.assertEqual(training["daily"]["informative_training_groups"], 3)
            self.assertEqual(training["study"]["informative_training_groups"], 0)

    def test_validate_only_does_not_fit_or_rank_or_claim_evaluation(self):
        with patch.object(preferences, "fit_preferences", side_effect=AssertionError("no fit")), patch.object(preferences, "rank_from_fit", side_effect=AssertionError("no rank")):
            report = self.evaluate(validate_only=True, details=True)
        self.assertEqual(report["status"], "manifest_validation_only")
        self.assertNotIn("targets", report)
        self.assertNotIn("case_results", report)

    def test_scalar_rank_on_every_axis_and_current_snapshot_hex_hashes(self):
        fits = {}
        real_fit = preferences.fit_preferences
        def fit(records, **axis):
            result = real_fit(records, **axis)
            fits[(axis["target"], axis["partition"], axis["domain"])] = result
            return result
        with patch.object(preferences, "fit_preferences", side_effect=fit):
            report = self.evaluate()
        for target in preferences.TARGETS:
            for partition in PARTITIONS:
                for domain in preferences.DOMAINS:
                    rank = report["targets"][target]["training"][partition][domain]["contrast_rank"]
                    self.assertIs(type(rank), int)
                    self.assertTrue(0 <= rank <= 8)
                    self.assertEqual(rank, fits[(target, partition, domain)]["contrast_rank"])
                    self.assertEqual(rank, 1 if partition == "rational" and domain == "daily" else 0)
        paths = {"model/preference_evaluation.py", "model/preferences.py", "model/contrast.py",
                 "model/ranking.py", "model/catalog.py"}
        self.assertEqual(set(report["implementation_sha256"]), paths)
        for path, digest in report["implementation_sha256"].items():
            self.assertIsInstance(digest, str)
            self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")
            self.assertEqual(digest, hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
        self.assertRegex(report["manifest_fingerprint"], r"\A[0-9a-f]{64}\Z")
        self.assertEqual(report["manifest_fingerprint"], evaluator._hash(example()))
        self.assertIn("contrast_rank_does_not_establish_parameter_magnitudes_or_validity", report["limitations"])
        self.assertIn("implementation_identity_records_current_code_not_historical_freeze", report["limitations"])
        self.assertEqual(report["baselines"], "not_requested")
        checked = self.evaluate(validate_only=True)
        self.assertEqual(checked["implementation_sha256"], report["implementation_sha256"])

    def test_default_privacy_and_details_only_case_id_reason(self):
        manifest = example()
        default = self.evaluate(manifest)
        text = json.dumps(default)
        for case in manifest["cases"]:
            for value in (case["id"], case["reviewed_group_id"], *case["source_ids"], *case["body_digests"]):
                self.assertNotIn(value, text)
        detailed = self.evaluate(manifest, details=True)
        for rendered in (text, json.dumps(detailed)):
            for field in ("options", "labels", "impacts", "choice_id", "weights", "model_probability",
                          "contributions", "contrast_basis", "used_features", "scores", "score",
                          "source_ids", "source_id", "body_digests", "reviewed_group_id"):
                self.assertNotIn('"' + field + '"', rendered)
        self.assertEqual(set(detailed["case_results"][0]), {"id", "prediction_reason"})
        self.assertEqual(set(detailed["case_results"][0]["prediction_reason"]), {"actual", "endorsed"})

    def comparison_overall(self, report, variant="full", target="actual"):
        return report["comparisons"]["variants"][variant]["targets"][target]["overall"]

    def pair_overall(self, report, variant="equal_weight", target="actual"):
        return report["comparisons"]["full_vs_variant"][variant]["targets"][target]["overall"]

    def test_comparisons_opt_in_strict_flags_validation_only_and_unchanged_full(self):
        default = self.evaluate()
        compared = self.evaluate(comparisons=True)
        self.assertNotIn("comparisons", default)
        self.assertEqual(default["targets"], compared["targets"])
        self.assertEqual(compared["baselines"], "completed")
        self.assertEqual(compared["ablation_eight_parameters"], "completed")
        expected = {"full", "equal_weight", "chance", *("drop:" + key for key in evaluator.VALUE_PARAMETERS)}
        self.assertEqual(set(compared["comparisons"]["variants"]), expected)
        self.assertEqual(set(compared["comparisons"]["full_vs_variant"]), expected - {"full"})
        self.assertEqual(compared["comparisons"]["feature_drop_order"], list(evaluator.VALUE_PARAMETERS))
        self.assertFalse(compared["comparisons"]["automatic_selection"])
        self.assertFalse(compared["comparisons"]["validity_claim"])
        self.assertIn("holdout_used_for_parameter_selection_becomes_development_requires_new_independent_holdout",
                      compared["limitations"])
        for flag in ("comparisons", "details", "validate_only"):
            for value in (None, 0, 1, "true", [], {}):
                with self.subTest(flag=flag, value=repr(value)), self.assertRaises(ValueError):
                    self.evaluate(**{flag: value})
        with patch.object(preferences, "fit_preferences", side_effect=AssertionError("no fit")), \
                patch.object(preferences, "rank_from_fit", side_effect=AssertionError("no rank")), \
                patch.object(evaluator, "_baseline_predictions", side_effect=AssertionError("no baseline")):
            checked = self.evaluate(comparisons=True, validate_only=True, details=True)
        self.assertNotIn("comparisons", checked)
        self.assertNotIn("targets", checked)
        self.assertNotIn("case_results", checked)
        self.assertEqual(checked["baselines"], "not_run_validation_only")

    def test_comparison_all_variant_predictions_precede_any_heldout_label_reads(self):
        manifest = example()
        manifest["cases"].append(clone_case(manifest["cases"][-1], "comparison-second"))
        validated = evaluator.validate_manifest(manifest)
        state = {"queries": 0, "baselines": 0, "guard": False}
        class GuardedLabel(dict):
            def __getitem__(self, key):
                if key == "choice_id" and state["guard"]:
                    if state["queries"] != 36 or state["baselines"] != 1:
                        raise AssertionError("heldout choice read before all variant queries finish")
                return super().__getitem__(key)
            def get(self, key, default=None):
                return self[key] if key in self else default
        for case in validated:
            if case["split"] == "held_out":
                for target in preferences.TARGETS:
                    case["labels"][target] = GuardedLabel(case["labels"][target])
        real_rank, real_baselines = preferences.rank_from_fit, evaluator._baseline_predictions
        def rank(options, fit):
            state["queries"] += 1
            return real_rank(options, fit)
        def baselines(cases, contaminated):
            result = real_baselines(cases, contaminated)
            state["baselines"] += 1
            return result
        def validate(_):
            state["guard"] = True
            return validated
        with patch.object(evaluator, "validate_manifest", side_effect=validate), \
                patch.object(preferences, "rank_from_fit", side_effect=rank), \
                patch.object(evaluator, "_baseline_predictions", side_effect=baselines):
            report = self.evaluate(manifest, comparisons=True)
        self.assertEqual(state["queries"], 36)
        self.assertEqual(self.comparison_overall(report)["correct"], 2)

    def comparison_trace(self, manifest):
        fits, queries, baselines = [], [], []
        real_fit, real_rank, real_baselines = (preferences.fit_preferences, preferences.rank_from_fit,
                                               evaluator._baseline_predictions)
        def fit(records, **axis):
            result = real_fit(records, **axis)
            fits.append((copy.deepcopy(records), axis, copy.deepcopy(result)))
            return result
        def rank(options, fit):
            result = real_rank(options, fit)
            queries.append((copy.deepcopy(options), copy.deepcopy(fit), copy.deepcopy(result)))
            return result
        def baseline(cases, contaminated):
            result = real_baselines(cases, contaminated)
            baselines.append(copy.deepcopy(result))
            return result
        with patch.object(preferences, "fit_preferences", side_effect=fit), \
                patch.object(preferences, "rank_from_fit", side_effect=rank), \
                patch.object(evaluator, "_baseline_predictions", side_effect=baseline):
            report = self.evaluate(manifest, comparisons=True)
        return (fits, queries, baselines), report

    def test_comparison_heldout_choice_perturbation_preserves_every_fit_and_prediction(self):
        manifest = growth_security_manifest()
        supported = clone_case(manifest["cases"][-1], "comparison-supported")
        supported["options"] = growth_security_options()
        manifest["cases"].append(supported)
        original_trace, original = self.comparison_trace(manifest)
        before = copy.deepcopy(manifest)
        flipped = copy.deepcopy(manifest)
        for case in flipped["cases"]:
            if case["split"] == "held_out":
                case["labels"]["actual"]["choice_id"] = "b"
                case["labels"]["endorsed"]["choice_id"] = "a"
        flipped_trace, changed = self.comparison_trace(flipped)
        self.assertEqual(original_trace, flipped_trace)
        self.assertEqual(manifest, before)
        self.assertNotEqual(self.comparison_overall(original)["correct"], self.comparison_overall(changed)["correct"])
        for target in preferences.TARGETS:
            self.assertEqual(self.comparison_overall(original, "chance", target),
                             self.comparison_overall(changed, "chance", target))

    def test_comparison_original_admission_and_no_projection_rededuplication(self):
        manifest = example()
        for case in manifest["cases"]:
            case["options"] = growth_security_options(security=0)
        extra = clone_case(manifest["cases"][0], "project-collision", same_group=True)
        extra["options"][0]["impacts"]["value.autonomy"] = .5
        manifest["cases"].append(extra)
        admitted_calls, real_records = [], evaluator._development_records
        def records(*args):
            result = real_records(*args)
            admitted_calls.append(copy.deepcopy(result))
            return result
        with patch.object(evaluator, "_development_records", side_effect=records):
            (fits, queries, _), report = self.comparison_trace(manifest)
        axes = len(preferences.TARGETS) * len(PARTITIONS) * len(preferences.DOMAINS)
        self.assertEqual(len(admitted_calls), axes)
        self.assertEqual(len(fits), 9 * axes)
        for drop_index, feature in enumerate(evaluator.VALUE_PARAMETERS, 1):
            for index in range(axes):
                original, axis, _ = fits[index]
                projected, projected_axis, _ = fits[drop_index * axes + index]
                self.assertEqual(axis, projected_axis)
                expected = [{**record, "options": evaluator._project_options(record["options"], feature)}
                            for record in original]
                self.assertEqual(projected, expected)
                for record in projected:
                    self.assertIsNone(record["endorsed_choice_id"] if axis["target"] == "actual"
                                      else record["actual_choice_id"])
                    self.assertNotIn("source_ids", record)
                    self.assertNotIn("body_digests", record)
        for target in preferences.TARGETS:
            training = report["comparisons"]["variants"]["drop:value.autonomy"]["targets"][target]["training"]["rational"]["daily"]
            self.assertEqual(training["original_training_records"], 4)
            self.assertEqual(training["training_records"], 4)
            self.assertEqual(training["informative_training_events"], 4)
            self.assertEqual(training["informative_training_groups"], 3)
        self.assertEqual(len(queries), 18)

    def test_comparison_numeric_copies_option_permutations_never_reweight(self):
        manifest = example()
        counter = clone_case(manifest["cases"][0], "comparison-counter", same_group=True)
        counter["labels"]["actual"]["choice_id"] = "b"
        counter["labels"]["endorsed"]["choice_id"] = "a"
        wrong = clone_case(manifest["cases"][-1], "comparison-wrong", same_group=True)
        wrong["labels"]["actual"]["choice_id"] = "b"
        wrong["labels"]["endorsed"]["choice_id"] = "a"
        manifest["cases"].extend([counter, wrong])
        original_trace, original = self.comparison_trace(manifest)
        copied = copy.deepcopy(manifest)
        for index, case in enumerate((counter, manifest["cases"][3])):
            for form, zero in enumerate((0, 0.0, -0.0)):
                duplicate = clone_case(case, f"comparison-numeric-{index}-{form}", same_group=True)
                for option in duplicate["options"]:
                    option["impacts"] = {feature: float(option["impacts"].get(feature, zero))
                                         for feature in evaluator.VALUE_PARAMETERS}
                duplicate["options"].reverse()
                copied["cases"].append(duplicate)
        copied["cases"].reverse()
        before = copy.deepcopy(copied)
        copied_trace, result = self.comparison_trace(copied)
        self.assertEqual(original_trace[0], copied_trace[0])
        self.assertEqual(copied, before)
        self.assertEqual(original["comparisons"]["full_vs_variant"], result["comparisons"]["full_vs_variant"])
        raw = {"all_held_out", "labelled", "unlabelled", "ineligible", "copied_event_cases", "duplicate_cases"}
        for variant in original["comparisons"]["variants"]:
            for target in preferences.TARGETS:
                left = self.comparison_overall(original, variant, target)
                right = self.comparison_overall(result, variant, target)
                self.assertEqual({k: v for k, v in left.items() if k not in raw},
                                 {k: v for k, v in right.items() if k not in raw})
        permuted = copy.deepcopy(manifest)
        permuted["cases"].reverse()
        for case in permuted["cases"]:
            case["options"].reverse()
        trace, report = self.comparison_trace(permuted)
        self.assertEqual(trace, original_trace)
        self.assertEqual(report["comparisons"], original["comparisons"])

    def test_comparison_projection_support_loss_abstains_without_hiding_originals(self):
        manifest = example()
        for case in manifest["cases"][1:]:
            case["options"] = growth_security_options(security=0)
        report = self.evaluate(manifest, comparisons=True)
        for target in preferences.TARGETS:
            training = report["comparisons"]["variants"]["drop:value.autonomy"]["targets"][target]["training"]["rational"]["daily"]
            self.assertEqual(training["original_training_records"], 3)
            self.assertEqual(training["training_records"], 3)
            self.assertEqual(training["original_informative_training_events"], 3)
            self.assertEqual(training["informative_training_events"], 2)
            self.assertEqual(training["original_informative_training_groups"], 3)
            self.assertEqual(training["informative_training_groups"], 2)
            self.assertEqual(training["original_contrast_rank"], 2)
            self.assertEqual(training["contrast_rank"], 1)
            self.assertEqual(training["fit_status"], "abstain")
            summary = self.comparison_overall(report, "drop:value.autonomy", target)
            self.assertEqual((summary["evaluated"], summary["predicted"], summary["abstain"]), (1, 0, 1))
        zero = self.evaluate(comparisons=True)
        training = zero["comparisons"]["variants"]["drop:value.autonomy"]["targets"]["actual"]["training"]["rational"]["daily"]
        self.assertEqual((training["informative_training_events"], training["informative_training_groups"],
                          training["contrast_rank"]), (0, 0, 0))

    def test_comparison_unidentifiable_chosen_vector_is_removed_not_only_zero_contrast(self):
        manifest = example()
        for case in manifest["cases"]:
            case["options"] = [
                {"id": "a", "impacts": {"value.growth": 1, "value.autonomy": 1}},
                {"id": "b", "impacts": {"value.growth": -1, "value.autonomy": -1}},
                {"id": "c", "impacts": {"value.growth": 1, "value.autonomy": -1}}]
        report = self.evaluate(manifest, comparisons=True)
        summary = report["comparisons"]["variants"]["drop:value.autonomy"]["targets"]["actual"]["training"]["rational"]["daily"]
        self.assertEqual(summary["original_informative_training_events"], 3)
        self.assertEqual(summary["informative_training_events"], 0)
        endorsed = report["comparisons"]["variants"]["drop:value.autonomy"]["targets"]["endorsed"]["training"]["rational"]["daily"]
        self.assertEqual(endorsed["informative_training_events"], 3)

    def test_comparison_equal_weight_top_ties_tolerance_and_exact_chance_expectations(self):
        manifest = example()
        held = manifest["cases"][-1]
        held["options"] = [{"id": "a", "impacts": {"value.growth": 1}},
                           {"id": "b", "impacts": {"value.security": 1}},
                           {"id": "c", "impacts": {"value.care": -1}}]
        two = clone_case(held, "chance-two", same_group=True)
        two["options"] = two["options"][:2]
        eight = clone_case(held, "chance-eight")
        eight["options"] = [{"id": chr(97 + i), "impacts": {}} for i in range(8)]
        manifest["cases"].extend([two, eight])
        with patch("random.random", side_effect=AssertionError("no chance draws")), \
                patch("random.choice", side_effect=AssertionError("no chance choices")):
            report = self.evaluate(manifest, comparisons=True)
        equal = self.comparison_overall(report, "equal_weight")
        self.assertEqual((equal["evaluated"], equal["predicted"], equal["abstain"]), (3, 0, 3))
        chance = self.comparison_overall(report, "chance")
        expected = math.fsum((1 / 3, 1 / 2, 1 / 8))
        self.assertIs(type(chance["expected_correct"]), float)
        self.assertEqual(chance["expected_correct"], expected)
        self.assertEqual(chance["expected_hit_rate"], expected / 3)
        self.assertEqual(chance["expected_conditional_accuracy"], expected / 3)
        self.assertEqual(chance["macro_group"]["expected_hit_rate"], ((1 / 3 + 1 / 2) / 2 + 1 / 8) / 2)
        self.assertEqual(chance["coverage"], 1)
        for key in ("correct", "hit_rate", "conditional_accuracy"):
            self.assertNotIn(key, chance)
            self.assertNotIn(key, chance["macro_group"])
        for gap, selected in ((1e-9, None), (5e-10, None), (2e-9, "a")):
            options = [{"id": "a", "impacts": {"value.growth": gap}}, {"id": "b", "impacts": {}}]
            self.assertEqual(evaluator._equal_weight_choice(options), selected)

    def test_comparison_pairwise_intersection_fixed_denominators_and_group_macros(self):
        manifest = growth_security_manifest()
        supported = clone_case(manifest["cases"][-1], "pair-supported")
        supported["options"] = growth_security_options()
        wrong = clone_case(supported, "pair-wrong", same_group=True)
        wrong["labels"]["actual"]["choice_id"] = "b"
        tied = clone_case(supported, "pair-tied")
        tied["options"] = [{"id": "a", "impacts": {}}, {"id": "b", "impacts": {}}]
        manifest["cases"].extend([supported, wrong, tied])
        report = self.evaluate(manifest, comparisons=True)
        for variant in ("equal_weight", "drop:value.growth"):
            pair = self.pair_overall(report, variant)
            self.assertEqual((pair["evaluated"], pair["full_predicted"], pair["variant_predicted"],
                              pair["both_predicted"]), (4, 2, 3, 2))
            self.assertEqual(pair["both_predicted_coverage"], .5)
            self.assertEqual(pair["full_accuracy_on_both"], .5)
            self.assertEqual(pair["variant_accuracy_on_both"], .5)
            self.assertEqual((pair["both_correct"], pair["neither_correct"]), (1, 1))
            self.assertEqual(pair["both_correct_cohort_rate"], .25)
            self.assertEqual(pair["full_hit_rate"], .25)
            self.assertEqual(pair["macro_group"]["both_predicted_groups"], 1)
            self.assertEqual(pair["macro_group"]["evaluated_groups"], 3)
            self.assertEqual(pair["macro_group"]["full_coverage"], 1)
            self.assertEqual(pair["cohort_macro_group"]["full_coverage"], 1 / 3)
            self.assertEqual(pair["cohort_macro_group"]["full_hit_rate"], 1 / 6)
        chance = self.pair_overall(report, "chance")
        self.assertEqual((chance["evaluated"], chance["variant_predicted"], chance["both_predicted"]), (4, 4, 2))
        for key in ("both_correct", "full_only_correct", "variant_only_correct", "neither_correct"):
            self.assertNotIn(key, chance)
            self.assertEqual(chance["expected_" + key], .5)
            self.assertEqual(chance["expected_" + key + "_cohort_rate"], .125)
        self.assertEqual(chance["expected_variant_correct"], 2.0)
        self.assertEqual(chance["expected_variant_accuracy_on_both"], .5)
        refused = self.pair_overall(report, "drop:value.care")
        self.assertEqual(refused["both_predicted"], 2)
        reversed_report = self.evaluate(comparisons=True)
        endorsed = self.pair_overall(reversed_report, target="endorsed")
        self.assertEqual((endorsed["full_only_correct"], endorsed["variant_only_correct"]), (1, 0))

    def test_comparison_original_heldout_events_do_not_merge_after_projection(self):
        manifest = example()
        variant = clone_case(manifest["cases"][-1], "heldout-project-collision", same_group=True)
        variant["options"][0]["impacts"]["value.care"] = .25
        manifest["cases"].append(variant)
        report = self.evaluate(manifest, comparisons=True)
        for name in report["comparisons"]["variants"]:
            for target in preferences.TARGETS:
                summary = self.comparison_overall(report, name, target)
                self.assertEqual((summary["unique_held_out_events"], summary["unique_scoring_units"],
                                  summary["evaluated"]), (2, 2, 2))
        drop = self.comparison_overall(report, "drop:value.care")
        full = self.comparison_overall(report)
        self.assertEqual((drop["predicted"], full["predicted"]), (2, 1))
        pair = self.pair_overall(report, "drop:value.care")
        self.assertEqual((pair["evaluated"], pair["both_predicted"], pair["variant_only_predicted"]), (2, 1, 1))

    def test_comparison_axes_contamination_consents_and_general_baseline_support(self):
        manifest = example()
        for case in manifest["cases"]:
            case["partition"] = "emotional"
        unsupported = clone_case(manifest["cases"][-1], "comparison-new-domain")
        unsupported["domain"] = "study"
        blocked = clone_case(unsupported, "comparison-tainted")
        taint = clone_case(blocked, "comparison-taint-copy", same_group=True)
        taint["labels"]["endorsed"]["status"] = "model_assisted"
        no_consent = clone_case(unsupported, "comparison-no-consent")
        no_consent["attestations"]["evaluation_consent"] = False
        wrong_state = clone_case(unsupported, "comparison-nonrational")
        wrong_state["endorsement_partition"] = "crazy"
        dev = clone_case(manifest["cases"][0], "comparison-nonconsent-development")
        dev["domain"] = "study"
        dev["attestations"]["training_consent"] = False
        manifest["cases"].extend([unsupported, blocked, taint, no_consent, wrong_state, dev])
        report = self.evaluate(manifest, comparisons=True)
        for name, variant in report["comparisons"]["variants"].items():
            actual = variant["targets"]["actual"]
            endorsed = variant["targets"]["endorsed"]
            self.assertEqual((actual["overall"]["evaluated"], endorsed["overall"]["evaluated"]), (3, 2))
            self.assertEqual(actual["by_partition"]["rational"]["evaluated"], 0)
            self.assertEqual(endorsed["by_partition"]["emotional"]["evaluated"], 0)
            self.assertEqual(actual["overall"]["ineligible"], 3)
            if "training" in actual:
                self.assertEqual(actual["training"]["emotional"]["study"]["training_records"], 0)
                self.assertEqual(endorsed["training"]["rational"]["study"]["training_records"], 0)
        self.assertEqual(self.comparison_overall(report)["predicted"], 1)
        self.assertEqual(self.comparison_overall(report, "equal_weight")["predicted"], 3)
        self.assertEqual(self.comparison_overall(report, "chance")["predicted"], 3)
        self.assertEqual(report["comparisons"]["variants"]["equal_weight"]["kind"],
                         "nonpersonal_equal_weight_sum_heuristic")

    def test_comparison_empty_cohort_and_privacy_with_details(self):
        manifest = example()
        blank_label(manifest["cases"][-1], "actual")
        manifest["cases"][-1]["attestations"]["evaluation_consent"] = False
        report = self.evaluate(manifest, comparisons=True, details=True)
        for variant in report["comparisons"]["variants"]:
            summary = self.comparison_overall(report, variant)
            self.assertEqual(summary["evaluated"], 0)
            self.assertIsNone(summary["coverage"])
            self.assertIsNone(summary["expected_hit_rate"] if variant == "chance" else summary["hit_rate"])
        for variant in report["comparisons"]["full_vs_variant"]:
            pair = self.pair_overall(report, variant)
            self.assertIsNone(pair["both_predicted_coverage"])
            self.assertIsNone(pair["full_accuracy_on_both"])
            self.assertEqual(pair["macro_group"]["both_predicted_groups"], 0)
        for details in (False, True):
            private = self.evaluate(comparisons=True, details=details)
            rendered = json.dumps(private)
            for case in example()["cases"]:
                identifiers = [case["reviewed_group_id"], *case["source_ids"], *case["body_digests"]]
                if not details or case["split"] != "held_out":
                    identifiers.append(case["id"])
                for identifier in identifiers:
                    self.assertNotIn(identifier, rendered)
            for field in ("impacts", "options", "labels", "choice_id", "weights", "contrast_basis",
                          "used_features", "score", "scores", "source_id", "reviewed_group_id"):
                self.assertNotIn('"' + field + '"', rendered)
            json.dumps(private, allow_nan=False)

    def test_comparison_cli_flag_generic_errors_and_validation_only(self):
        result = self.cli("--manifest", EXAMPLE, "--comparisons")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("comparisons", json.loads(result.stdout))
        checked = self.cli("--manifest", EXAMPLE, "--comparisons", "--validate-only", "--details")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("comparisons", json.loads(checked.stdout))
        for arguments in (("--manifest", EXAMPLE, "--comparisons=PRIVATE_FLAG"),
                          ("--manifest", EXAMPLE, "--comparisons", "PRIVATE_FLAG"),
                          ("--manifest", self.directory / "PRIVATE_MISSING", "--comparisons")):
            bad = self.cli(*arguments)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, "")
            self.assertEqual(bad.stderr, evaluator._ERROR)

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
