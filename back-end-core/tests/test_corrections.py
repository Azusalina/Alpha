import tempfile
import unittest
from pathlib import Path

from core.api import BrainAPI


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = BrainAPI(Path(self.temp.name) / "brain.sqlite3")
        self.model = self.api.brain.model

    def sample(self, text, parameter="value.fairness", sign=1, partition="rational", kind="diary"):
        source = self.model.submit(text + "。", partition=partition, kind=kind)
        correction = {"parameter": parameter, "sign": sign, "evidence": text, "span": [0, len(text)]}
        self.model.correction_set(source, corrections=[correction], expected_revision=0)
        self.model.review(source, agree=True)
        return source

    def test_pending_correction_is_audited_without_fitting_and_zero_removes_false_inference(self):
        text = "我重视公平。"
        source = self.model.submit(text, partition="rational")
        self.assertTrue(self.model.preview(source)["effects"])
        request = {"schema_version": 1, "id": "correct", "method": "correction_set",
                   "params": {"source_id": source, "expected_revision": 0, "corrections": [
                       {"parameter": "value.fairness", "sign": 0, "evidence": text[:-1], "span": [0, len(text)-1]}]}}
        response = self.api.handle(request)
        self.assertTrue(response["ok"], response)
        self.assertEqual(self.model.preview(source)["effects"], [])
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
        self.assertEqual(self.model.store.get_source(source)["body"], text)
        approved = self.model.review(source, agree=True)
        self.assertEqual(approved["effects"], [])
        history = self.model.correction_history(source)
        self.assertEqual(history["fit_context"]["correction_revision"], response["result"]["revision"])
        with self.assertRaises(ValueError):
            self.model.correction_set(source, corrections=[], expected_revision=history["revision"])

    def test_revision_check_and_reset_preserve_feedback_history(self):
        source = self.model.submit("我重视公平。", partition="rational")
        item = {"parameter": "value.fairness", "sign": 0, "evidence": "公平", "span": [3, 5]}
        first = self.model.correction_set(source, corrections=[item], expected_revision=0)
        with self.assertRaises(ValueError):
            self.model.correction_set(source, corrections=[], expected_revision=0)
        second = self.model.correction_set(source, corrections=[], expected_revision=first["revision"])
        history = self.model.correction_history(source)
        self.assertEqual(history["revision"], second["revision"])
        self.assertEqual(len(history["history"]), 2)
        self.assertEqual(history["corrections"], [])
        self.assertTrue(self.model.preview(source)["effects"])

    def test_invalid_feedback_and_other_speaker_offsets_do_not_persist(self):
        text = "阿明: 我重视公平。\n我: 我重视自由。"
        source = self.model.submit(text, partition="rational", kind="chat", self_speaker="我")
        item = {"parameter": "value.fairness", "sign": 1, "evidence": "我重视公平", "span": [4, 9]}
        for correction in (item, dict(item, span=[4, 10]), dict(item, sign=True),
                           dict(item, parameter="clinical.fake")):
            with self.subTest(correction=correction), self.assertRaises(ValueError):
                self.model.correction_set(source, corrections=[correction], expected_revision=0)
        self.assertEqual(self.model.correction_history(source)["history"], [])
        start = text.rindex("我重视自由")
        own = {"parameter": "value.autonomy", "sign": 0, "evidence": "我重视自由", "span": [start, start+5]}
        self.model.correction_set(source, corrections=[own], expected_revision=0)
        self.assertEqual(self.model.preview(source)["effects"], [])

    def test_two_explicit_labels_teach_exact_clause_only_in_same_partition_and_kind(self):
        phrase = "我宁愿给每个人同样的机会"
        first = self.sample(phrase)
        pending = self.model.submit(phrase + "。", partition="rational")
        self.assertEqual(self.model.preview(pending)["effects"], [])
        second = self.sample(phrase)
        preview = self.model.preview(pending)
        self.assertEqual(preview["effects"][0]["rule_id"], "learned_exact_correction")
        self.assertEqual(preview["interpretation"]["learned_rules"][0]["support_source_ids"], sorted([first, second]))
        for partition, kind, text in (("emotional", "diary", phrase),
                                      ("rational", "philosophy", phrase),
                                      ("rational", "diary", "朋友说" + phrase)):
            source = self.model.submit(text + "。", partition=partition, kind=kind)
            self.assertEqual(self.model.preview(source)["effects"], [])

    def test_disagreement_and_revocation_remove_training_support_without_rewriting_prior_fits(self):
        phrase = "我宁愿给每个人同样的机会"
        first = self.sample(phrase)
        self.sample(phrase)
        inferred = self.model.submit(phrase + "。", partition="rational")
        self.model.review(inferred, agree=True)
        self.model.revoke(first)
        next_input = self.model.submit(phrase + "。", partition="rational")
        self.assertEqual(self.model.preview(next_input)["effects"], [])
        old_context = self.model.correction_history(inferred)["fit_context"]
        self.assertIn(first, old_context["learned_rules"][0]["support_source_ids"])
        # An inferred fit is not an explicit label and cannot reinforce itself.
        self.assertEqual(self.model.preview(next_input)["interpretation"]["learned_rules"][0]["support"], 1)
        correction = {"parameter": "value.fairness", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}
        self.model.correction_set(next_input, corrections=[correction], expected_revision=0)
        self.model.review(next_input, agree=False)
        later = self.model.submit(phrase + "。", partition="rational")
        self.assertEqual(self.model.preview(later)["effects"], [])

    def test_conflicting_training_labels_abstain_and_other_clauses_still_count(self):
        phrase = "我宁愿给每个人同样的机会"
        self.sample(phrase)
        self.sample(phrase)
        contradictory = self.model.submit(phrase + "。我不重视公平。", partition="rational")
        self.assertEqual(self.model.preview(contradictory)["effects"], [])
        self.sample(phrase, sign=0)
        pending = self.model.submit(phrase + "。", partition="rational")
        preview = self.model.preview(pending)
        self.assertEqual(preview["effects"], [])
        self.assertEqual(preview["interpretation"]["learned_rules"][0]["status"], "conflict")

    def test_short_excerpt_correction_is_local_and_whole_batch_is_validated(self):
        text = "我重视公平。"
        short = {"parameter": "value.fairness", "sign": 0, "evidence": "公平", "span": [3, 5]}
        for _ in range(2):
            source = self.model.submit(text, partition="rational")
            self.model.correction_set(source, corrections=[short], expected_revision=0)
            self.model.review(source, agree=True)
        source = self.model.submit(text, partition="rational")
        self.assertTrue(self.model.preview(source)["effects"])
        with self.assertRaises(ValueError):
            self.model.correction_set(source, corrections=[short, dict(short)], expected_revision=0)
        self.assertEqual(self.model.correction_history(source)["history"], [])

    def test_question_correction_does_not_suppress_the_same_words_as_a_statement(self):
        phrase = "我重视公平"
        for _ in range(2):
            source = self.model.submit(phrase + "？", partition="rational")
            self.model.correction_set(source, corrections=[{"parameter": "value.fairness", "sign": 0,
                                      "evidence": phrase, "span": [0, len(phrase)]}], expected_revision=0)
            self.model.review(source, agree=True)
        question = self.model.submit(phrase + "？", partition="rational")
        statement = self.model.submit(phrase + "。", partition="rational")
        self.assertEqual(self.model.preview(question)["effects"], [])
        self.assertTrue(self.model.preview(statement)["effects"])


if __name__ == "__main__":
    unittest.main()
