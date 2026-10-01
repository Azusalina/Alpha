import copy
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from model.engine import BrainModel
from model.evaluation import evaluate_database, read_snapshot, validate_cases
from model.ranking import VALUE_PARAMETERS, rank_from_state


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.model = BrainModel(self.path)
        self.sources = []
        for text in ("我重视公平。", "我重视公平。", "我重视诚实。", "我重视诚实。"):
            source = self.model.submit(text, partition="rational")
            self.model.review(source, agree=True)
            self.sources.append(source)
        self.case = {"id": "daily-1", "domain": "daily", "held_out": True,
                     "source_ids": [], "actual_choice": "B", "endorsed_choice": "A",
                     "options": [{"id": "A", "impacts": {"value.fairness": 1, "value.truth": -0.5}},
                                 {"id": "B", "impacts": {"value.fairness": -1, "value.truth": 1}}]}

    def manifest(self, *cases):
        return {"schema_version": 1, "cases": list(cases or (self.case,))}

    def test_shared_ranking_preserves_live_results_and_static_ablation(self):
        state = self.model.state("rational")
        original = copy.deepcopy(state)
        self.assertEqual(self.model.rank_options(self.case["options"]), rank_from_state(self.case["options"], state))
        self.assertEqual(rank_from_state(self.case["options"], state, excluded=("value.fairness",))["ranked"][0]["id"], "B")
        self.assertEqual(state, original)
        with self.assertRaises(ValueError):
            rank_from_state(self.case["options"], state, excluded=("affect.anger",))

    def test_metrics_keep_actual_and_endorsed_labels_separate_and_include_abstentions(self):
        study = dict(self.case, id="study-1", domain="study", actual_choice="B", endorsed_choice="B",
                     options=[{"id": "A", "impacts": {"value.truth": -1}}, {"id": "B", "impacts": {"value.truth": 1}}])
        unknown = dict(self.case, id="social-1", domain="interpersonal", actual_choice="A", endorsed_choice=None,
                       options=[{"id": "A", "impacts": {"value.care": 1}}, {"id": "B", "impacts": {"value.care": -1}}])
        report = evaluate_database(self.path, self.manifest(self.case, study, unknown))
        actual = report["full"]["metrics"]["actual_choice"]
        endorsed = report["full"]["metrics"]["endorsed_choice"]
        self.assertEqual((actual["labelled"], actual["answered"], actual["correct"]), (3, 2, 1))
        self.assertEqual(actual["accuracy_on_answered"], 0.5)
        self.assertEqual(actual["coverage"], 2 / 3)
        self.assertEqual(actual["correct_over_all_labelled"], 1 / 3)
        self.assertEqual(endorsed["accuracy_on_answered"], 1)
        self.assertEqual(endorsed["labelled"], 2)
        self.assertIsNone(report["full"]["by_domain"]["interpersonal"]["endorsed_choice"]["coverage"])
        self.assertEqual(set(report["ablations"]), set(VALUE_PARAMETERS))
        pair = report["ablations"]["value.fairness"]["paired_comparison"]
        self.assertEqual(pair["actual_choice"]["correct_gained_without_parameter"], 1)
        self.assertEqual(pair["endorsed_choice"]["correct_lost_without_parameter"], 1)

    def test_top_ties_never_count_lexicographic_first_as_prediction(self):
        case = dict(self.case, actual_choice="A", options=[
            {"id": "A", "impacts": {"value.fairness": 1}},
            {"id": "B", "impacts": {"value.fairness": 1}},
            {"id": "C", "impacts": {"value.fairness": -1}}])
        report = evaluate_database(self.path, self.manifest(case))
        self.assertEqual(report["full"]["predictions"][0]["reason"], "top_alignment_tie")
        self.assertIsNone(report["full"]["metrics"]["actual_choice"]["accuracy_on_answered"])
        self.assertEqual(report["full"]["metrics"]["actual_choice"]["abstention_rate"], 1)

    def test_lower_ties_use_midrank_not_option_id_order(self):
        case = dict(self.case, options=[
            {"id": "A", "impacts": {"value.fairness": 1}},
            {"id": "B", "impacts": {"value.fairness": -1}},
            {"id": "C", "impacts": {"value.fairness": -1}}])
        metrics = evaluate_database(self.path, self.manifest(case))["full"]["metrics"]["actual_choice"]
        self.assertEqual(metrics["accuracy_on_answered"], 0)
        self.assertEqual(metrics["mean_reciprocal_midrank_on_answered"], 1 / 2.5)

    def test_zero_and_emotional_only_models_abstain_without_cross_partition_learning(self):
        fresh = Path(self.temp.name) / "zero.sqlite3"
        model = BrainModel(fresh)
        self.assertEqual(evaluate_database(fresh, self.manifest())["full"]["metrics"]["actual_choice"]["coverage"], 0)
        for _ in range(2):
            source = model.submit("我重视公平。", partition="emotional")
            model.review(source, agree=True)
        report = evaluate_database(fresh, self.manifest())
        self.assertEqual(report["full"]["metrics"]["actual_choice"]["coverage"], 0)
        self.assertEqual(report["snapshot"]["rational"]["value.fairness"]["support"], 0)

    def test_snapshot_and_evaluation_do_not_mutate_database_or_manifest(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        manifest = self.manifest()
        original = copy.deepcopy(manifest)
        report = evaluate_database(self.path, manifest)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(manifest, original)
        self.assertEqual(report, evaluate_database(self.path, manifest))
        self.assertEqual(set(report["snapshot"]["training_source_ids"]), set(self.sources))
        self.assertEqual(len(report["ranking_sha256"]), 64)
        self.assertEqual(len(report["evaluation_sha256"]), 64)

    def test_leakage_check_rejects_agreed_and_previously_revoked_sources(self):
        leaked = dict(self.case, source_ids=[self.sources[0]])
        with self.assertRaises(ValueError):
            evaluate_database(self.path, self.manifest(leaked))
        self.model.revoke(self.sources[0])
        with self.assertRaises(ValueError):
            evaluate_database(self.path, self.manifest(leaked))
        pending = self.model.submit("未认可的测试事件", partition="emotional")
        evaluate_database(self.path, self.manifest(dict(self.case, source_ids=[pending])))

    def test_rereview_false_does_not_erase_training_exposure_even_with_zero_parameter_effects(self):
        for partition, text in (("rational", "我重视公平。"), ("emotional", "记录一个普通事件。")):
            source = self.model.submit(text, partition=partition)
            fit = self.model.review(source, agree=True)
            if partition == "emotional":
                self.assertEqual(fit["effects"], [])
            self.model.review(source, agree=False)
            self.assertEqual(self.model.store.brain_status(source), "disagreed")
            self.assertIn(source, read_snapshot(self.path)["training_source_ids"])
            with self.assertRaises(ValueError):
                evaluate_database(self.path, self.manifest(dict(self.case, source_ids=[source])))
        never_fitted = self.model.submit("从未拟合的材料。", partition="crazy", immediate=False)
        self.assertNotIn(never_fitted, read_snapshot(self.path)["training_source_ids"])

    def test_invalid_manifests_and_labels_are_rejected(self):
        for change in ({"held_out": False}, {"held_out": 1}, {"actual_choice": True},
                       {"endorsed_choice": "missing"}, {"domain": "clinical"},
                       {"source_ids": ["x", "x"]}, {"actual_choice": None, "endorsed_choice": None},
                       {"options": [{"id": "A", "impacts": {"value.truth": float("nan")}}, {"id": "B", "impacts": {}}]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_cases(self.manifest(dict(self.case, **change)), self.sources)
        with self.assertRaises(ValueError):
            validate_cases(self.manifest(self.case, self.case), self.sources)
        with self.assertRaises(ValueError):
            validate_cases({"schema_version": True, "cases": [self.case]}, self.sources)

    def test_missing_or_invalid_database_is_not_initialized_or_repaired(self):
        missing = Path(self.temp.name) / "missing.sqlite3"
        with self.assertRaises(sqlite3.Error):
            read_snapshot(missing)
        self.assertFalse(missing.exists())
        with closing(sqlite3.connect(self.path)) as db:
            with db:
                db.execute("UPDATE brain_state SET support=-1 WHERE partition='rational' AND parameter='value.truth'")
        with self.assertRaises(ValueError):
            read_snapshot(self.path)

    def test_cli_reads_example_manifest_and_missing_db_fails_without_creating_it(self):
        example = Path(__file__).resolve().parents[1] / "docs/evaluation.example.json"
        args = [sys.executable, "-m", "model.evaluation", "--db", str(self.path), "--cases", str(example)]
        result = subprocess.run(args, text=True, capture_output=True, timeout=15, cwd=example.parents[1])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "offline_experiment")
        missing = Path(self.temp.name) / "does-not-exist.sqlite3"
        args[4] = str(missing)
        result = subprocess.run(args, text=True, capture_output=True, timeout=15, cwd=example.parents[1])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
