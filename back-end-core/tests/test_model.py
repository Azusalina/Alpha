import hashlib
import tempfile
import unittest
from pathlib import Path

from model import BrainModel
from model.catalog import BASELINE_PATH


class BrainModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.model = BrainModel(self.path)

    def test_zero_baseline_and_private_database(self):
        baseline = self.model.baseline()
        self.assertTrue(all(v == 0 for v in baseline["parameters"].values()))
        self.assertEqual(set(self.model.state()), {"rational", "emotional", "crazy"})
        self.assertFalse(self.model.state("rational")["value.fairness"]["observed"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_submit_does_not_train_and_disagreement_preserves_raw(self):
        source = self.model.submit("我重视公平。", partition="rational")
        self.assertEqual(self.model.state("rational")["value.fairness"]["value"], 0)
        result = self.model.review(source, agree=False)
        self.assertEqual(result["effects"], [])
        self.assertEqual(self.model.store.get_source(source)["body"], "我重视公平。")
        self.assertEqual(self.model.learned_terms(partition="rational", min_documents=1), [])
        with self.assertRaises(ValueError):
            self.model.review(source, agree=True)

    def test_approved_philosophy_updates_only_rational_and_can_revoke(self):
        before_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
        text = "我重视公平和自由。"
        source = self.model.submit(text, partition="rational", kind="philosophy")
        result = self.model.review(source, agree=True)
        self.assertEqual({effect["parameter"] for effect in result["effects"]},
                         {"value.fairness", "value.autonomy"})
        for effect in result["effects"]:
            start, end = effect["span"]
            self.assertEqual(text[start:end], effect["evidence"])
            self.assertGreater(effect["after"], 0)
        self.assertEqual(self.model.state("emotional")["value.fairness"]["support"], 0)
        self.assertEqual(hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest(), before_hash)
        self.model.revoke(source)
        self.assertEqual(self.model.state("rational")["value.fairness"]["value"], 0)
        self.assertFalse(self.model.state("rational")["value.fairness"]["observed"])
        self.assertEqual(len(self.model.effects(source_id=source)), 4)
        self.assertEqual(self.model.effects(source_id=source)[0]["evidence"],
                         result["effects"][0]["evidence"])
        with self.assertRaises(ValueError):
            self.model.revoke(source)

    def test_revoking_one_source_preserves_other_evidence(self):
        first = self.model.submit("我重视公平。", partition="rational")
        second = self.model.submit("我也重视公平。", partition="rational")
        self.model.review(first, agree=True)
        self.model.review(second, agree=True)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 2)
        self.model.revoke(first)
        state = self.model.state("rational")["value.fairness"]
        self.assertEqual(state["support"], 1)
        self.assertGreater(state["value"], 0)

    def test_emotional_material_never_updates_rational_partition(self):
        source = self.model.submit("我很难过。我觉得公平很重要。", partition="emotional")
        self.model.review(source, agree=True)
        emotional = self.model.state("emotional")
        self.assertGreater(emotional["affect.sadness"]["value"], 0)
        self.assertGreater(emotional["value.fairness"]["value"], 0)
        rational = self.model.state("rational")
        self.assertEqual(rational["value.fairness"]["value"], 0)
        self.assertEqual(rational["affect.sadness"]["value"], 0)

    def test_chat_excludes_other_speakers_value_claims(self):
        text = "阿明: 我重视公平。\n我: 我重视自由。"
        source = self.model.submit(text, partition="rational", kind="chat", self_speaker="我")
        self.model.review(source, agree=True)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
        self.assertEqual(self.model.state("rational")["value.autonomy"]["support"], 1)

    def test_negative_and_comparative_claims(self):
        negative = self.model.submit("我认为公平不重要。", partition="rational")
        self.model.review(negative, agree=True)
        self.assertLess(self.model.state("rational")["value.fairness"]["value"], 0)
        another = self.model.submit("我不认为诚实重要。", partition="rational")
        self.model.review(another, agree=True)
        self.assertLess(self.model.state("rational")["value.truth"]["value"], 0)
        comparative = self.model.submit("我认为自由比安全重要。", partition="rational")
        self.model.review(comparative, agree=True)
        state = self.model.state("rational")
        self.assertGreater(state["value.autonomy"]["value"], 0)
        self.assertEqual(state["value.security"]["support"], 0)

    def test_opposite_clauses_do_not_reverse_each_other(self):
        text = "我重视自由，但我不重视安全。"
        source = self.model.submit(text, partition="rational")
        self.model.review(source, agree=True)
        state = self.model.state("rational")
        self.assertGreater(state["value.autonomy"]["value"], 0)
        self.assertLess(state["value.security"]["value"], 0)

    def test_topic_mention_does_not_establish_value(self):
        source = self.model.submit("今天讨论了公平问题。", partition="rational")
        self.model.review(source, agree=True)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)

    def test_endorsed_philosophy_statement_without_first_person(self):
        source = self.model.submit("人应该诚实。", partition="rational", kind="philosophy")
        self.model.review(source, agree=True)
        self.assertGreater(self.model.state("rational")["value.truth"]["value"], 0)

    def test_ambiguous_normative_negation_is_not_fitted(self):
        source = self.model.submit("人不应该不诚实。", partition="rational", kind="philosophy")
        self.model.review(source, agree=True)
        self.assertEqual(self.model.state("rational")["value.truth"]["support"], 0)

    def test_translator_learns_partition_local_vocabulary(self):
        first = self.model.submit("长期规划对我很重要。", partition="rational", kind="philosophy")
        second = self.model.submit("我重视长期规划。", partition="rational", kind="philosophy")
        self.model.review(first, agree=True)
        result = self.model.review(second, agree=True)
        terms = self.model.learned_terms(partition="rational")
        self.assertTrue(terms)
        self.assertTrue(result["translator_effects"])
        self.assertEqual(self.model.learned_terms(partition="crazy"), [])
        self.model.revoke(first)
        self.assertEqual(self.model.learned_terms(partition="rational"), [])

    def test_chat_lexicon_learns_only_self_speaker(self):
        text = "阿明: 隔山打牛非常重要。\n我: 我重视长期规划。"
        source = self.model.submit(text, partition="rational", kind="chat", self_speaker="我")
        self.model.review(source, agree=True)
        terms = {row["term"] for row in self.model.learned_terms(
            partition="rational", min_documents=1)}
        self.assertNotIn("隔山打牛", terms)
        self.assertIn("长期", terms)

    def test_ranking_abstains_then_returns_provisional_alignment(self):
        options = [
            {"id": "A", "impacts": {"value.autonomy": 0.8}},
            {"id": "B", "impacts": {"value.autonomy": -0.2}},
        ]
        self.assertEqual(self.model.rank_options(options)["status"], "abstain")
        for text in ("我重视自由。", "自由对我来说很重要。"):
            source = self.model.submit(text, partition="rational")
            self.model.review(source, agree=True)
        result = self.model.rank_options(options)
        self.assertEqual(result["status"], "provisional")
        self.assertEqual([item["id"] for item in result["ranked"]], ["A", "B"])
        self.assertTrue(result["not_a_probability"])


if __name__ == "__main__":
    unittest.main()
