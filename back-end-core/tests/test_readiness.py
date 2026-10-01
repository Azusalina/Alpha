"""Synthetic collection/format checks only; no private database or corpus."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from model.evaluation import load_manifest as load_choices, validate_cases as validate_choices
from model.readiness import assess_readiness, export_manifests, validate_collection
from translator.evaluation import evaluate_manifest, load_manifest, validate_cases as validate_extraction

ROOT = Path(__file__).resolve().parents[1]


def sample(task="choice", **changes):
    data = {"domain": "daily", "options": [{"id": "A", "impacts": {"value.fairness": 1}},
                                              {"id": "B", "impacts": {"value.fairness": -1}}],
            "actual_choice": "A", "endorsed_choice": "B"}
    annotations = {"options": "independent", "actual_choice": "independent", "endorsed_choice": "independent"}
    if task == "translator":
        data = {"domain": "daily", "partition": "rational", "kind": "diary", "text": "我重视公平。",
                "label_scope": ["value.fairness"],
                "expected": [{"parameter": "value.fairness", "sign": 1, "evidence": "我重视公平", "span": [0, 5]}]}
        annotations = {"extraction": "independent"}
    return {"id": "c-1", "group_id": "g-1", "source_ids": ["s-1"], "backend_source_ids": [],
            "task": task, "split": "held_out", "event_at": "2026-09-21T00:00:00Z",
            "labelled_at": "2026-09-22T00:00:00Z", "annotator_id": "a-1", "blind_to_outputs": True,
            "exposure": {"import_status": "never_imported", "model_fit": "none", "rule_development": "none", "manual_tuning": "none"},
            "authenticity": None, "annotations": annotations, "data": data, **changes}


def collection(*cases):
    return {"schema_version": 1,
            "protocol": {"development_end": "2026-09-20T00:00:00Z", "held_out_start": "2026-09-21T00:00:00Z",
                         "frozen_at": "2026-09-30T00:00:00Z"}, "cases": list(cases or [sample()])}


class ReadinessTests(unittest.TestCase):
    def test_exports_use_exact_evaluator_contracts_and_separate_choice_labels(self):
        cases = collection(sample(), sample("translator", id="c-2", group_id="g-2", source_ids=["s-2"]))
        exports = export_manifests(cases)
        self.assertEqual(validate_choices(exports["choice"], ["unrelated"])[0]["actual_choice"], "A")
        self.assertEqual(exports["choice"]["cases"][0]["endorsed_choice"], "B")
        self.assertEqual(validate_extraction(exports["translator"])[0]["label_scope"], ("value.fairness",))
        self.assertEqual(evaluate_manifest(exports["translator"])["overall"]["true_positive"], 1)

    def test_drafts_are_not_negatives_or_invalid_empty_manifests(self):
        choice = sample()
        choice["data"].update(options=None, actual_choice=None, endorsed_choice=None)
        choice["annotations"] = dict.fromkeys(choice["annotations"], "pending")
        extraction = sample("translator", id="c-2", group_id="g-2", source_ids=["s-2"])
        extraction["data"].update(label_scope=[], expected=[])
        extraction["annotations"]["extraction"] = "pending"
        corpus = collection(choice, extraction)
        self.assertEqual(export_manifests(corpus), {"choice": None, "translator": None})
        self.assertEqual(assess_readiness(corpus)["blocked_cases"], 2)
        choice["data"].update(options=sample()["data"]["options"])
        self.assertIsNone(export_manifests(collection(choice))["choice"])
        extraction["data"]["expected"] = sample("translator")["data"]["expected"]
        with self.assertRaises(ValueError):
            validate_collection(collection(extraction))

    def test_unreviewed_or_model_assisted_label_never_enters_export(self):
        for status in ("pending", "model_assisted"):
            case = sample()
            case["annotations"]["actual_choice"] = status
            exported = export_manifests(collection(case))["choice"]["cases"][0]
            self.assertIsNone(exported["actual_choice"])
            self.assertEqual(exported["endorsed_choice"], "B")
            case["annotations"]["endorsed_choice"] = status
            self.assertIsNone(export_manifests(collection(case))["choice"])
            case = sample("translator")
            case["annotations"]["extraction"] = status
            self.assertIsNone(export_manifests(collection(case))["translator"])

    def test_authenticity_never_supplies_or_replaces_semantic_or_choice_labels(self):
        for authenticity in (True, False, None):
            case = sample(authenticity=authenticity)
            self.assertEqual(export_manifests(collection(case))["choice"]["cases"][0]["actual_choice"], "A")
            case["annotations"] = dict.fromkeys(case["annotations"], "pending")
            self.assertIsNone(export_manifests(collection(case))["choice"])

    def test_partial_extraction_scope_keeps_unchecked_parameters_ignored(self):
        case = sample("translator")
        case["data"]["text"] = "我重视公平和自由。"
        case["data"]["expected"] = [{"parameter": "value.fairness", "sign": 1,
                                      "evidence": "我重视公平和自由", "span": [0, 8]}]
        exported = export_manifests(collection(case))["translator"]
        report = evaluate_manifest(exported)["overall"]
        self.assertEqual(report["checked_parameters"], 1)
        self.assertEqual(report["ignored_predictions"], 1)
        self.assertEqual(report["false_positive"], 0)

    def test_unknown_or_exposed_provenance_blocks_entire_held_out_group_including_drafts(self):
        for field in ("import_status", "model_fit", "rule_development", "manual_tuning"):
            case = sample()
            case["exposure"][field] = "unknown"
            draft = sample(id="c-2")
            draft["annotations"] = dict.fromkeys(draft["annotations"], "pending")
            corpus = collection(case, draft)
            self.assertEqual(assess_readiness(corpus)["blocker_counts"]["held_out_exposure_not_clear"], 2)
            self.assertIsNone(export_manifests(corpus)["choice"])
        for field in ("rule_development", "manual_tuning"):
            case = sample()
            case["exposure"][field] = "exposed"
            self.assertIsNone(export_manifests(collection(case))["choice"])

    def test_imported_never_fitted_export_still_needs_later_snapshot_check(self):
        case = sample(backend_source_ids=["db-source-1"])
        case["exposure"]["import_status"] = "imported"
        exported = export_manifests(collection(case))["choice"]
        self.assertEqual(exported["cases"][0]["source_ids"], ["db-source-1"])
        with self.assertRaises(ValueError):
            validate_choices(exported, ["db-source-1"])
        case["exposure"]["model_fit"] = "exposed"
        self.assertIsNone(export_manifests(collection(case))["choice"])

    def test_explicit_never_imported_path_preserves_legacy_source_ids_empty(self):
        exported = export_manifests(collection())["choice"]
        self.assertEqual(exported["cases"][0]["source_ids"], [])
        validate_choices(exported, [])
        case = sample(backend_source_ids=["bad"])
        with self.assertRaises(ValueError):
            validate_collection(collection(case))
        case = sample()
        case["exposure"]["import_status"] = "imported"
        with self.assertRaises(ValueError):
            validate_collection(collection(case))

    def test_groups_and_source_ids_cannot_cross_splits_or_be_reassigned(self):
        other = sample(id="c-2", split="development", event_at="2026-09-19T00:00:00Z")
        for changes in ({}, {"group_id": "g-2"}, {"group_id": "g-2", "split": "held_out", "event_at": "2026-09-21T00:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_collection(collection(sample(), {**other, **changes}))
        first = sample(backend_source_ids=["db-1"])
        first["exposure"]["import_status"] = "imported"
        second = sample(id="c-2", group_id="g-2", source_ids=["s-2"], backend_source_ids=["db-1"])
        second["exposure"]["import_status"] = "imported"
        with self.assertRaises(ValueError):
            validate_collection(collection(first, second))

    def test_duplicate_text_in_drafts_does_not_hide_cross_split_leakage(self):
        other = sample("translator", id="c-2", group_id="g-2", source_ids=["s-2"],
                       split="development", event_at="2026-09-19T00:00:00Z")
        other["data"].update(text="我重视公平。\r\n", expected=[], label_scope=[])
        other["annotations"]["extraction"] = "pending"
        with self.assertRaises(ValueError):
            validate_collection(collection(sample("translator"), other))

    def test_time_windows_and_unknown_time_provenance(self):
        for change in ({"event_at": "2026-09-20T00:00:00Z"}, {"event_at": "2026-10-01T00:00:00Z"},
                       {"event_at": "2026-09-31T00:00:00Z"}, {"event_at": "2026-09-21T08:00:00+08:00"},
                       {"labelled_at": "2026-09-20T00:00:00Z"}, {"labelled_at": "2026-10-01T00:00:00Z"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_collection(collection(sample(**change)))
        for field in ("event_at", "labelled_at", "annotator_id", "blind_to_outputs"):
            self.assertIsNone(export_manifests(collection(sample(**{field: None})))["choice"])
        corpus = collection()
        corpus["protocol"]["held_out_start"] = corpus["protocol"]["development_end"]
        with self.assertRaises(ValueError):
            validate_collection(corpus)

    def test_development_translator_is_separate_from_held_out_choice(self):
        dev = {"split": "development", "event_at": "2026-09-19T00:00:00Z"}
        self.assertIsNone(export_manifests(collection(sample(**dev)))["choice"])
        case = sample("translator", **dev)
        case["exposure"]["rule_development"] = "exposed"
        exported = export_manifests(collection(case))["translator"]
        self.assertEqual(exported["cases"][0]["split"], "development")

    def test_strict_nested_fields_and_types_and_opaque_ids(self):
        mutations = [lambda c: c.update(extra=True), lambda c: c.update(id="private words"),
                     lambda c: c.update(source_ids=["s", "s"]), lambda c: c.update(source_ids=[]),
                     lambda c: c.update(authenticity=1), lambda c: c.update(blind_to_outputs=1),
                     lambda c: c["annotations"].update(extra="pending"),
                     lambda c: c["annotations"].update(actual_choice="agreed"),
                     lambda c: c["data"].update(extra=True),
                     lambda c: c["data"]["options"][0].update(extra="PRIVATE_CANARY"),
                     lambda c: c["data"]["options"][0].update(id="narrative words"),
                     lambda c: c["data"].update(actual_choice=True),
                     lambda c: c["data"]["options"][0]["impacts"].update(secret_parameter=1),
                     lambda c: c["annotations"].update(actual_choice="independent") or c["data"].update(actual_choice=None)]
        for mutation in mutations:
            case = sample()
            mutation(case)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_collection(collection(case))
        corpus = collection()
        corpus["schema_version"] = True
        with self.assertRaises(ValueError):
            validate_collection(corpus)

    def test_malformed_draft_options_fail_cleanly_without_fabricating_labels(self):
        for options in ([], [{}], None, "not-options", [None, None], [{"id": "A"}, {"id": "B"}]):
            case = sample()
            case["data"].update(options=options, actual_choice=None, endorsed_choice=None)
            case["annotations"] = dict.fromkeys(case["annotations"], "pending")
            if options is None:
                self.assertIsNone(export_manifests(collection(case))["choice"])
            else:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    validate_collection(collection(case))
        case = sample()
        case["data"].pop("options")
        with self.assertRaises(ValueError):
            validate_collection(collection(case))

    def test_nul_anywhere_and_option_extra_fields_in_offline_evaluators(self):
        choice = export_manifests(collection())["choice"]
        extraction = export_manifests(collection(sample("translator")))["translator"]
        for corpus, validator in ((choice, lambda value: validate_choices(value, [])), (extraction, validate_extraction)):
            for field in ("id", "domain"):
                changed = copy.deepcopy(corpus)
                changed["cases"][0][field] += "\x00"
                with self.assertRaises(ValueError):
                    validator(changed)
            changed = copy.deepcopy(corpus)
            changed["\x00"] = "ignored"
            with self.assertRaises(ValueError):
                validator(changed)
        for field in ("text", "self_speaker"):
            changed = copy.deepcopy(extraction)
            changed["cases"][0][field] = "secret\x00"
            with self.assertRaises(ValueError):
                validate_extraction(changed)
        changed = copy.deepcopy(extraction)
        changed["cases"][0]["expected"][0]["evidence"] += "\x00"
        with self.assertRaises(ValueError):
            validate_extraction(changed)
        for option_change in ({"extra": "private"}, {"id": "A\x00"}, {"impacts": {"value.fairness\x00": 1}}):
            changed = copy.deepcopy(choice)
            changed["cases"][0]["options"][0].update(option_change)
            with self.assertRaises(ValueError):
                validate_choices(changed, [])

    def test_bounded_regular_strict_json_loaders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            for loader in (load_manifest, load_choices):
                for raw in (b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}',
                            b'{"a":1e999}', b'{"a":"\\u0000"}', b'{"\\u0000":1}',
                            b'{"a":"\\ud800"}', b'\xff', b'[' * 2000, b'{"a":'):
                    path.write_bytes(raw)
                    with self.subTest(loader=loader, raw=raw), self.assertRaises(ValueError):
                        loader(path)
                if hasattr(os, "mkfifo"):
                    fifo = Path(directory) / (loader.__module__ + ".fifo")
                    os.mkfifo(fifo)
                    with self.assertRaises(ValueError):
                        loader(fifo)
                with self.assertRaises(ValueError):
                    loader("/dev/null")
            path.write_bytes(b" " * 20)
            with patch("model.evaluation.MAX_FILE_BYTES", 10), self.assertRaises(ValueError):
                load_choices(path)
            with self.assertRaises(ValueError):
                load_manifest(path, max_bytes=10)
            for limit in (-2, 0, True, "10"):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    load_manifest(path, max_bytes=limit)

    def test_resource_limits(self):
        with patch("model.readiness.MAX_CASES", 1), self.assertRaises(ValueError):
            validate_collection(collection(sample(), sample(id="c-2")))
        with patch("model.readiness.MAX_TOTAL_CHARS", 1), self.assertRaises(ValueError):
            validate_collection(collection(sample("translator")))

    def test_report_hashes_privacy_and_no_mutation_or_database_access(self):
        corpus = collection(sample("translator"))
        before = copy.deepcopy(corpus)
        with patch("sqlite3.connect", side_effect=AssertionError("database access forbidden")), \
             patch("model.engine.BrainModel.__init__", side_effect=AssertionError("model construction forbidden")):
            report = assess_readiness(corpus)
            self.assertEqual(report, assess_readiness(copy.deepcopy(corpus)))
            export_manifests(corpus)
        self.assertEqual(corpus, before)
        encoded = json.dumps(report, ensure_ascii=False)
        for secret in ("我重视公平", "c-1", "g-1", "s-1", "a-1"):
            self.assertNotIn(secret, encoded)
        self.assertFalse(report["database_opened"])
        self.assertEqual(len(report["collection_sha256"]), 64)
        changed = copy.deepcopy(corpus)
        changed["cases"][0]["authenticity"] = True
        self.assertNotEqual(report["collection_sha256"], assess_readiness(changed)["collection_sha256"])
        exports = export_manifests(corpus)
        exports["translator"]["cases"][0]["text"] = "changed"
        self.assertEqual(corpus, before)
        with self.assertRaises(ValueError):
            assess_readiness(corpus, details=1)

    def test_cli_and_draft_template_never_claim_real_held_out_readiness(self):
        template = load_manifest(ROOT / "docs/readiness.example.json")
        self.assertEqual(assess_readiness(template)["eligible"], {"choice": 0, "translator": 0})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(collection(sample("translator"))), encoding="utf-8")
            before = path.read_bytes()
            command = [sys.executable, "-m", "model.readiness", "--collection", str(path)]
            for flags in ([], ["--details"], ["--export", "translator"]):
                result = subprocess.run(command + flags, cwd=ROOT, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                if "--export" not in flags:
                    self.assertNotIn("我重视公平", result.stdout)
                    self.assertEqual("case_results" in report, "--details" in flags)
                else:
                    validate_extraction(report)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            path.write_text('{"secret":"PRIVATE_CANARY\\u0000"}', encoding="utf-8")
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("PRIVATE_CANARY", result.stderr)


if __name__ == "__main__":
    unittest.main()
