import unittest

from translator import summarize, translate


class TranslatorTests(unittest.TestCase):
    def test_example_cues_candidates_and_exact_offsets(self):
        text = "阿明又临时取消。我说没事，但其实很失望；下次我可能不会主动约他了。"
        report = translate(text)
        for item in report["cues"] + report["candidates"]:
            start, end = item["span"]
            self.assertEqual(text[start:end], item["evidence"])
        self.assertIn("claimed_repetition", [c["value"] for c in report["cues"]])
        self.assertEqual([c["value"] for c in report["candidates"]],
                         ["disappointment", "less_initiative"])
        self.assertEqual(report["candidates"][1]["certainty"], "hedged")

    def test_negated_and_reported_emotion_is_not_self_emotion(self):
        for text in ("我没有失望。", "他说他很失望。", "他很失望。"):
            with self.subTest(text=text):
                self.assertEqual(translate(text)["candidates"], [])

    def test_first_person_feeling_about_another_person_is_kept(self):
        report = translate("我对他很失望。")
        self.assertEqual([item["value"] for item in report["candidates"]],
                         ["disappointment"])

    def test_chat_requires_identity_and_ignores_other_speakers(self):
        text = "阿明: 我很失望。\n我：我很失望。\n无标签的行\n"
        with self.assertRaises(ValueError):
            translate(text, kind="chat")
        report = translate(text, kind="chat", self_speaker="我")
        self.assertEqual(len(report["candidates"]), 1)
        self.assertEqual(report["candidates"][0]["speaker"], "我")
        self.assertEqual(report["skipped"][0]["reason"], "unlabeled_chat_line")
        start, end = report["candidates"][0]["span"]
        self.assertEqual(text[start:end], "失望")

    def test_summary_counts_inputs_not_traits(self):
        first = translate("我很失望。我还是失望。")
        second = translate("我很失望。")
        summary = summarize([first, second])
        self.assertEqual(summary["cross_document_counts"], [
            {"type": "textual_emotion", "value": "disappointment", "document_count": 2}
        ])
        self.assertIn("not a stable tendency", summary["interpretation"])

    def test_invalid_input_and_no_source_mutation(self):
        with self.assertRaises(ValueError):
            translate(" ")
        with self.assertRaises(ValueError):
            translate("hello", kind="unknown")
        with self.assertRaises(ValueError):
            translate("x" * 1_000_001)

    def test_unicode_scalar_text_and_crlf_offsets(self):
        for text in ("\ud800", "\udfff", "\ud83d\ude00"):
            with self.assertRaises(ValueError):
                translate(text)
        text = "😀我开心。\r\n我失望。"
        for item in translate(text)["cues"]:
            self.assertEqual(text[slice(*item["span"])], item["evidence"])


if __name__ == "__main__":
    unittest.main()
