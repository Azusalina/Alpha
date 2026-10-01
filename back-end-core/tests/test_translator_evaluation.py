import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model.catalog import BASELINE_PATH
from model.evidence import Contribution
from translator.evaluation import evaluate_manifest, load_manifest, validate_cases

EXAMPLE = Path(__file__).resolve().parents[1] / "docs/translator-evaluation.example.json"


def sample(case_id="case-1", text="我重视公平。", **changes):
    evidence = text.rstrip("。！？!?；;")
    case = {"id": case_id, "group_id": "group-" + case_id, "split": "development", "domain": "daily",
            "partition": "rational", "kind": "diary", "text": text, "label_scope": ["value.fairness"],
            "expected": [{"parameter": "value.fairness", "sign": 1, "evidence": evidence, "span": [0, len(evidence)]}]}
    return {**case, **changes}


def manifest(*cases):
    return {"schema_version": 1, "cases": list(cases)}


def fake_extractor(text, *, diagnostics, **kwargs):
    diagnostics.update(withheld_values=[], withheld_count=0, withheld_truncated=False)
    if text.startswith("missing"):
        return []
    return [Contribution("value.fairness", -1 if text.startswith("wrong") else 1,
                         text.rstrip("。！？!?；;"), 0, len(text.rstrip("。！？!?；;")), "test-rule")]


class TranslatorEvaluationTests(unittest.TestCase):
    def test_synthetic_fixture_runs_without_claiming_held_out_accuracy(self):
        corpus = load_manifest(EXAMPLE)
        report = evaluate_manifest(corpus)
        self.assertEqual(report["overall"]["cases"], 5)
        self.assertEqual(report["overall"]["true_positive"], 3)
        self.assertEqual(report["overall"]["strict_evidence_matches"], 3)
        self.assertEqual(report["by_split"]["held_out"]["cases"], 0)
        self.assertIsNone(report["by_split"]["held_out"]["f1"])
        self.assertFalse(report["personal_rules_used"])
        encoded = json.dumps(report, ensure_ascii=False, allow_nan=False)
        for case in corpus["cases"]:
            self.assertNotIn(case["id"], encoded)
            self.assertNotIn(case["text"], encoded)

    def test_partial_scope_never_counts_unchecked_predictions_as_false_positives(self):
        case = sample(text="我重视公平和自由。")
        report = evaluate_manifest(manifest(case))["overall"]
        self.assertEqual(report["checked_parameters"], 1)
        self.assertEqual(report["true_positive"], 1)
        self.assertEqual(report["false_positive"], 0)
        self.assertEqual(report["ignored_predictions"], 1)
        complete = evaluate_manifest(manifest({**case, "label_scope": "all"}))["overall"]
        self.assertEqual(complete["false_positive"], 1)

    def test_direction_errors_count_as_false_positive_and_false_negative(self):
        with patch("translator.evaluation.extract_contributions", side_effect=fake_extractor):
            report = evaluate_manifest(manifest(sample(text="wrong direction。")), case_details=True)
        counts = report["overall"]
        self.assertEqual((counts["true_positive"], counts["false_positive"], counts["false_negative"]), (0, 1, 1))
        self.assertEqual(counts["direction_errors"], 1)
        self.assertEqual(counts["f1"], 0)
        self.assertEqual(report["case_results"][0]["errors"][0]["kind"], "direction_error")

    def test_spurious_and_missed_labels_have_separate_counts_and_details(self):
        cases = manifest(sample("spurious", expected=[]), sample("missed", text="missing observation。"))
        with patch("translator.evaluation.extract_contributions", side_effect=fake_extractor):
            report = evaluate_manifest(cases, case_details=True)
        self.assertEqual(report["overall"]["false_positive"], 1)
        self.assertEqual(report["overall"]["false_negative"], 1)
        self.assertEqual([item["errors"][0]["kind"] for item in report["case_results"]],
                         ["false_positive", "false_negative"])

    def test_evidence_boundary_errors_do_not_change_parameter_direction_metrics(self):
        case = sample(expected=[{"parameter": "value.fairness", "sign": 1, "evidence": "公平", "span": [3, 5]}])
        report = evaluate_manifest(manifest(case), case_details=True)
        self.assertEqual(report["overall"]["f1"], 1)
        self.assertEqual(report["overall"]["strict_evidence_f1"], 0)
        self.assertEqual(report["overall"]["evidence_span_mismatches"], 1)
        self.assertEqual(report["case_results"][0]["errors"][0]["kind"], "evidence_span_mismatch")

    def test_negative_only_and_unchecked_parameters_return_null_undefined_scores(self):
        report = evaluate_manifest(manifest(sample(text="我重视公平吗？", expected=[])))
        self.assertEqual(report["overall"]["true_negative"], 1)
        self.assertIsNone(report["overall"]["precision"])
        self.assertIsNone(report["overall"]["recall"])
        self.assertIsNone(report["overall"]["f1"])
        self.assertEqual(report["by_parameter"]["value.truth"]["cases"], 0)
        self.assertIsNone(report["by_parameter"]["value.truth"]["f1"])

    def test_group_macro_and_split_domain_metrics_do_not_treat_variants_as_independent(self):
        cases = [sample(str(index), text="我重视公平" + punctuation, group_id="one-source")
                 for index, punctuation in enumerate(("。", "！", "；"))]
        cases.append(sample("miss", text="missing claim。", group_id="another-source", split="held_out", domain="study"))
        with patch("translator.evaluation.extract_contributions", side_effect=fake_extractor):
            report = evaluate_manifest(manifest(*cases))
        self.assertEqual(report["overall"]["case_exact_parameter_match_rate"], 0.75)
        self.assertEqual(report["overall"]["group_macro_case_exact_parameter_match_rate"], 0.5)
        self.assertEqual(report["by_split_domain"]["held_out"]["study"]["false_negative"], 1)
        self.assertEqual(report["by_split"]["development"]["source_groups"], 1)

    def test_cross_split_groups_and_normalized_duplicate_sources_are_rejected(self):
        for other in (sample("other", text="我不重视公平。", group_id="group-case-1", split="held_out"),
                      sample("other", split="held_out", partition="emotional"),
                      sample("other", text="我重视公平。\r\n", expected=[], split="held_out"),
                      sample("other", domain="study")):
            with self.subTest(split=other["split"]):
                with self.assertRaises(ValueError):
                    validate_cases(manifest(sample(), other))

    def test_invalid_fields_labels_types_and_surrogates_fail_before_extraction(self):
        mutations = [lambda case: case.update(text="\ud800"), lambda case: case.update(kind=[]),
                     lambda case: case.update(partition="unknown"), lambda case: case.update(split=True),
                     lambda case: case.update(id="private narrative with spaces"),
                     lambda case: case.update(label_scope=[]), lambda case: case.update(label_scope=["value.fairness"] * 2),
                     lambda case: case.update(label_scope=["value.truth"]),
                     lambda case: case["expected"][0].update(sign=True), lambda case: case["expected"][0].update(sign=0),
                     lambda case: case["expected"][0].update(span=[0, 4]),
                     lambda case: case["expected"].append(copy.deepcopy(case["expected"][0])),
                     lambda case: case.update(extra="not allowed"), lambda case: case.pop("expected"),
                     lambda case: case.update(self_speaker="\udfff")]
        for mutation in mutations:
            case = sample()
            mutation(case)
            with patch("translator.evaluation.extract_contributions", side_effect=AssertionError("must validate first")):
                with self.assertRaises(ValueError):
                    evaluate_manifest(manifest(case))
        with self.assertRaises(ValueError):
            evaluate_manifest(manifest(sample()), case_details=1)
        with self.assertRaises(ValueError):
            validate_cases({"schema_version": True, "cases": [sample()]})

    def test_chat_labels_must_belong_to_self_and_codepoint_spans_preserve_crlf_emoji(self):
        text = "朋友: 我重视公平。\r\n我: 😀我重视自由。"
        phrase = "😀我重视自由"
        start = text.index(phrase)
        case = sample(text=text, kind="chat", self_speaker="我", label_scope=["value.autonomy"],
                      expected=[{"parameter": "value.autonomy", "sign": 1, "evidence": phrase,
                                 "span": [start, start + len(phrase)]}])
        self.assertEqual(evaluate_manifest(manifest(case))["overall"]["strict_evidence_matches"], 1)
        other = text.index("我重视公平")
        case.update(label_scope=["value.fairness"], expected=[{"parameter": "value.fairness", "sign": 1,
                                                             "evidence": "我重视公平", "span": [other, other + 5]}])
        with self.assertRaises(ValueError):
            validate_cases(manifest(case))
        case["self_speaker"] = None
        with self.assertRaises(ValueError):
            validate_cases(manifest(case))

    def test_bounded_omission_diagnostics_are_not_reported_as_complete_reason_counts(self):
        report = evaluate_manifest(manifest(sample(text="我重视公平吗？" * 70, expected=[])))
        counts = report["overall"]
        self.assertEqual(counts["withheld_fragments"], 70)
        self.assertEqual(counts["recorded_withheld_fragments"], 64)
        self.assertEqual(counts["recorded_withheld_reasons"], {"question": 64})
        self.assertEqual(counts["truncated_diagnostic_cases"], 1)
        self.assertNotIn("withheld_fragments", report["by_parameter"]["value.fairness"])

    def test_resource_limits_and_strict_regular_file_loading(self):
        for name, limit, corpus in (("MAX_CASES", 1, manifest(sample(), sample("two", text="我不重视公平。"))),
                                    ("MAX_TOTAL_CHARS", 3, manifest(sample())),
                                    ("MAX_CHARS", 3, manifest(sample()))):
            with patch("translator.evaluation." + name, limit):
                with self.assertRaises(ValueError):
                    validate_cases(corpus)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            for invalid in (b'{"schema_version":1,"schema_version":1,"cases":[]}',
                            b'{"schema_version":1,"cases":NaN}', b'\xff', b'[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[['):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    load_manifest(path)
            path.write_bytes(b" " * 20)
            with patch("translator.evaluation.MAX_FILE_BYTES", 10):
                with self.assertRaises(ValueError):
                    load_manifest(path)
            if hasattr(os, "mkfifo"):
                fifo = Path(directory) / "not-a-file"
                os.mkfifo(fifo)
                with self.assertRaises(ValueError):
                    load_manifest(fifo)

    def test_evaluation_never_opens_database_fits_or_mutates_corpus_baseline_and_active_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brain.sqlite3"
            api = BrainAPI(path)
            api.brain.submit("我重视自由。", partition="rational", exclamation=True)
            corpus = manifest(sample())
            before = (json.dumps(corpus, sort_keys=True), BASELINE_PATH.read_bytes(), path.read_bytes(), api.brain.state())
            with patch("sqlite3.connect", side_effect=AssertionError("evaluation must not open a database")), \
                 patch("model.engine.BrainModel.__init__", side_effect=AssertionError("evaluation must not instantiate a model")):
                report = evaluate_manifest(corpus, case_details=True)
            after = (json.dumps(corpus, sort_keys=True), BASELINE_PATH.read_bytes(), path.read_bytes(), api.brain.state())
            self.assertEqual(before, after)
            self.assertEqual(report["overall"]["true_positive"], 1)

    def test_cli_outputs_no_raw_text_and_explicit_details_only_and_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.json"
            secret = "PRIVATE_CANARY_2817我重视公平。"
            path.write_text(json.dumps(manifest(sample(text=secret)), ensure_ascii=False), encoding="utf-8")
            before = path.read_bytes()
            command = [sys.executable, "-m", "translator.evaluation", "--cases", str(path)]
            for flags in ([], ["--details"]):
                result = subprocess.run(command + flags, cwd=EXAMPLE.parents[1], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertNotIn("PRIVATE_CANARY_2817", result.stdout + result.stderr)
                self.assertEqual("case_results" in report, bool(flags))
                if flags:
                    self.assertEqual(report["case_results"][0]["id"], "case-1")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual({p.name for p in Path(directory).iterdir()}, {"private.json"})
            path.write_text('{"cases": "PRIVATE_CANARY_2817"}', encoding="utf-8")
            result = subprocess.run(command, cwd=EXAMPLE.parents[1], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("PRIVATE_CANARY_2817", result.stderr)


if __name__ == "__main__":
    unittest.main()
