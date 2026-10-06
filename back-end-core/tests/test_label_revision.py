"""Version-bound semantic label revision: explicit relabel of exact translator output."""

import json
import tempfile
import unittest
from pathlib import Path

from core.api import BrainAPI
from model.corrections import validate_corrections

TEXT = "我取消约会。我很开心。"


def item(family="event", value="cancellation", evidence="取消", **extra):
    start = TEXT.index(evidence)
    return {"type": family, "value": value, "sign": 1, "evidence": evidence,
            "span": [start, start + len(evidence)], **extra}


class LabelRevisionValidationTests(unittest.TestCase):
    def check(self, *corrections):
        return validate_corrections(TEXT, "diary", None, list(corrections))

    def test_revised_value_is_optional_and_preserved_for_every_family(self):
        for family, value, evidence in (("event", "cancellation", "取消"), ("tone", "happiness", "开心"),
                                        ("candidate", "happiness", "开心")):
            with self.subTest(family=family):
                revised = item(family, value, evidence, revised_value="relief")
                self.assertEqual(self.check(revised), [revised])
        self.assertNotIn("revised_value", self.check(item())[0])

    def test_invalid_revisions_are_rejected_before_any_state_change(self):
        for bad in ("", " x", "x ", "same", "a\nb", "a\0b", "x" * 65, 1, None, "\ud800"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.check(item(value="cancellation", revised_value=bad if bad != "same" else "cancellation"))
        with self.assertRaises(ValueError):  # a suppression cannot also relabel
            self.check(item(sign=0, revised_value="relief"))
        with self.assertRaises(ValueError):  # target must still be exact translator output
            self.check(item(value="not_a_label", revised_value="relief"))
        with self.assertRaises(ValueError):  # same target twice
            self.check(item(revised_value="relief"), item())


class LabelRevisionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = BrainAPI(Path(self.temp.name) / "brain.sqlite3")
        self.model = self.api.brain.model

    def test_relabel_changes_interpretation_but_not_rule_effects_or_raw_text(self):
        source = self.model.submit(TEXT, partition="rational")
        before = self.model.preview(source)
        self.model.correction_set(source, corrections=[item(revised_value="relief")], expected_revision=0)
        after = self.model.preview(source)
        values = [c["value"] for c in after["interpretation"]["translation"]["cues"]]
        self.assertIn("relief", values)
        self.assertNotIn("cancellation", values)
        self.assertEqual(before["effects"], after["effects"])
        self.assertEqual(self.api.brain.input_get(source)["text"], TEXT)
        self.assertEqual(after["interpretation"]["corrections"][0]["revised_value"], "relief")
        json.dumps(after)

    def test_relabel_reaches_deterministic_memory_claims(self):
        text = "我很开心。"
        source = self.model.submit(text, partition="emotional")
        tone = {"type": "tone", "value": "happiness", "sign": 1, "evidence": "开心", "span": [2, 4]}
        claims = lambda: [m["claim"] for m in self.model.preview(source)["interpretation"]["memories"]]
        self.assertEqual(claims(), ["textual_emotion: happiness"])
        self.model.correction_set(source, corrections=[dict(tone, revised_value="relief")], expected_revision=0)
        self.assertEqual(claims(), ["textual_emotion: relief"])

    def test_reopen_with_relabel_forces_fresh_double_confirmation(self):
        source = self.model.submit(TEXT, partition="rational")
        self.model.review(source, agree=True)
        snapshot = self.api.brain.input_get(source)
        info = self.model.reset_info()
        revision = self.model.correction_history(source)["revision"]
        result = self.model.correction_reopen(
            source, corrections=[item(revised_value="relief")], immediate=True,
            expected_source_version=snapshot["source_version"],
            expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])
        self.assertEqual(result["status"], "pending")
        self.assertEqual(self.api.brain.input_get(source)["status"], "pending")
        history = self.model.correction_history(source)
        self.assertEqual(history["corrections"][0]["revised_value"], "relief")
        self.assertGreater(history["revision"], revision)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)


if __name__ == "__main__":
    unittest.main()
