import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model.evidence import Contribution, MAX_WITHHELD, extract_contributions
from translator import translate
from translator.discourse import AssertionGuards, POLICY_VERSION


class ExpressionCoverageTests(unittest.TestCase):
    def values(self, text, kind="diary", **kwargs):
        return {item.parameter: item.sign for item in extract_contributions(text, kind=kind, **kwargs)
                if item.parameter.startswith("value.")}

    def test_positive_negative_comparative_and_quoted_concept_statements_remain_supported(self):
        cases = [
            ("我重视公平。", "diary", {"value.fairness": 1}),
            ("我重視公平！", "diary", {"value.fairness": 1}),
            ("我不重视公平。", "diary", {"value.fairness": -1}),
            ("我沒重視公平。", "diary", {"value.fairness": -1}),
            ("我认为公平不重要。", "diary", {"value.fairness": -1}),
            ("我不认为诚实重要。", "diary", {"value.truth": -1}),
            ("我重视自由，但我不重视安全。", "diary", {"value.autonomy": 1, "value.security": -1}),
            ("我认为自由比安全重要。", "diary", {"value.autonomy": 1}),
            ("我重视“公平”和自由。", "diary", {"value.fairness": 1, "value.autonomy": 1}),
            ("我重視「公平」。", "diary", {"value.fairness": 1}),
            ("公平很重要。", "philosophy", {"value.fairness": 1}),
            ("人应该诚实。", "philosophy", {"value.truth": 1}),
        ]
        for text, kind, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.values(text, kind), expected)

    def test_questions_hypotheses_reporting_and_hedged_values_do_not_become_stances(self):
        cases = ["我重视公平吗？", "我重视公平？", "我重視公平嗎", "我是否重视公平。",
                 "我觉得公平重要 \t?", "如果我重视公平，我就会做不同的选择。",
                 "假如我有机会，我认为公平重要。", "朋友说：我重视公平，但我重视自由。",
                 "老师说，我认为公平重要。", "我觉得公平可能重要。", "或许我认为公平很重要。"]
        for kind in ("diary", "philosophy"):
            for text in cases:
                with self.subTest(text=text, kind=kind):
                    self.assertEqual(self.values(text, kind), {})

    def test_quotes_code_markdown_quotes_and_unclosed_quotes_do_not_become_stances(self):
        cases = ['朋友写了“我重视公平，但我重视自由”。', '“我重视公平。\n我重视自由。”',
                 '「我重视公平。『我重视自由』」', '"我重视公平。"', "'我重视公平。'",
                 "我重视《公平》。", "`我重视公平`。", "```text\n我重视公平。\n```",
                 "~~~\n我重视公平。\n~~~", "> 我重视公平。\n> 我重视自由。", "我读到“我重视公平。"]
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(self.values(text), {})

    def test_ambiguity_does_not_contaminate_independent_following_sentences(self):
        for prefix in ("朋友说我重视公平。", "如果我重视公平。", "我重视公平吗？", '“我重视公平。”'):
            self.assertEqual(self.values(prefix + "我重视自由。"), {"value.autonomy": 1})
        self.assertEqual(self.values("我重视公平，朋友说他重视自由。"), {"value.fairness": 1})

    def test_nested_and_mixed_negation_are_withheld_instead_of_flipping_all_values(self):
        for text in ("我不认为公平不重要。", "我觉得公平不是不重要。", "我重视公平并不重视自由。",
                     "我不是不重视公平。", "我认为自由不比安全重要。", "我觉得自由没有安全重要。",
                     "我重视不公平。", "我重视不诚实。", "我不重视不诚实。"):
            with self.subTest(text=text):
                self.assertEqual(self.values(text), {})
        self.assertEqual(self.values("人不应该不诚实。", "philosophy"), {})
        self.assertEqual(self.values("我反对公平很重要的观点。", "philosophy"), {})

    def test_chat_frames_and_unclosed_other_speaker_quotes_never_cross_into_self_messages(self):
        text = '朋友: 如果我有机会，我重视公平。\n朋友: “我重视自由\n我：😀我重视公平。\r\n我: 我重视自由吗？'
        items = extract_contributions(text, kind="chat", self_speaker="我")
        self.assertEqual({item.parameter: item.sign for item in items}, {"value.fairness": 1})
        for item in items:
            self.assertEqual(text[item.start:item.end], item.evidence)
        self.assertEqual(self.values('我: > 我重视公平。', kind="chat", self_speaker="我"), {})

    def test_lexical_cues_stay_visible_when_emotion_or_intention_candidates_are_withheld(self):
        for text in ('“我很失望，但我很开心”。', "我很失望吗？", "如果朋友失约，我会很失望。",
                     "朋友说，自己很失望。", "`我很失望`。", "> 我很失望。"):
            report = translate(text)
            self.assertTrue(report["cues"])
            self.assertEqual(report["candidates"], [])
            for item in report["cues"]:
                self.assertEqual(text[slice(*item["span"])], item["evidence"])
        for text in ("如果朋友失约，我不会主动约他。", '“我不会主动约他”。'):
            self.assertEqual(translate(text)["candidates"], [])

    def test_own_feeling_and_intention_before_later_reporting_are_kept(self):
        self.assertEqual([item["value"] for item in translate("我开心，朋友说他很失望。")["candidates"]], ["happiness"])
        self.assertEqual([item["value"] for item in translate("我对朋友很失望。")["candidates"]], ["disappointment"])
        report = translate("我可能不会主动约他，朋友说他很失望。")
        self.assertEqual([item["value"] for item in report["candidates"]], ["less_initiative"])
        self.assertEqual(report["candidates"][0]["certainty"], "hedged")

    def test_diagnostic_spans_reasons_and_limits_are_exact(self):
        text = "😀我重视公平吗？\r\n我不认为自由不重要。"
        diagnostics = {}
        self.assertEqual(extract_contributions(text, kind="diary", diagnostics=diagnostics), [])
        self.assertEqual({item["reason"] for item in diagnostics["withheld_values"]}, {"question", "ambiguous_negation"})
        for item in diagnostics["withheld_values"]:
            self.assertEqual(text[slice(*item["span"])], item["evidence"])
        diagnostics = {}
        extract_contributions("我重视公平吗？" * 70, kind="diary", diagnostics=diagnostics)
        self.assertEqual(len(diagnostics["withheld_values"]), MAX_WITHHELD)
        self.assertEqual(diagnostics["withheld_count"], 70)
        self.assertTrue(diagnostics["withheld_truncated"])

    def test_guard_indexes_and_caches_are_local_and_bounded_for_many_clauses(self):
        text = "我认为公平重要，" * 3000
        guards = AssertionGuards(text, "diary", None)
        for offset in range(0, len(text), len("我认为公平重要，")):
            end = offset + len("我认为公平重要")
            self.assertIsNone(guards.reason(offset, end))
            self.assertEqual(guards.clause_span(offset + 3, offset, end), (offset, end))
        self.assertLessEqual(len(guards._span_cache), 256)
        self.assertLessEqual(len(guards._reason_cache), 256)


class ExpressionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = BrainAPI(Path(self.temp.name) / "brain.sqlite3")
        self.model = self.api.brain.model

    def test_preview_and_fit_preserve_non_assertion_diagnostics_without_changing_raw_text(self):
        text = "我重视公平吗？我重视自由。"
        source = self.model.submit(text, partition="rational")
        preview = self.model.preview(source)
        self.assertEqual(preview["interpretation"]["evidence_policy"], POLICY_VERSION)
        self.assertEqual(preview["interpretation"]["withheld_count"], 1)
        result = self.model.review(source, agree=True)
        self.assertIsNone(preview["interpretation"]["dependency_provenance"]["fit_id"])
        self.assertRegex(result["interpretation"]["dependency_provenance"]["fit_id"], "^[0-9a-f]{32}$")
        strip = lambda value: {**value, "dependency_provenance": {**value["dependency_provenance"], "fit_id": None}}
        self.assertEqual(strip(preview["interpretation"]), strip(result["interpretation"]))
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
        self.assertEqual(self.model.state("rational")["value.autonomy"]["support"], 1)
        self.assertEqual(self.api.brain.input_get(source)["text"], text)

    def test_explicit_local_and_learned_corrections_can_override_automatic_question_guard(self):
        phrase = "我重视公平"
        for _ in range(2):
            source = self.model.submit(phrase + "？", partition="rational")
            self.model.correction_set(source, expected_revision=0, corrections=[{
                "parameter": "value.fairness", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}])
            result = self.model.review(source, agree=True)
            self.assertEqual(result["effects"][0]["rule_id"], "user_correction")
        next_source = self.model.submit(phrase + "？", partition="rational")
        preview = self.model.preview(next_source)
        self.assertEqual(preview["effects"][0]["rule_id"], "learned_exact_correction")
        self.assertEqual(preview["interpretation"]["withheld_values"][0]["reason"], "question")

    def test_exclamation_confirms_material_without_asserting_every_value_in_its_questions(self):
        result = self.api.brain.submit("我重视公平吗？", partition="rational", exclamation=True)
        self.assertEqual(result["status"], "agreed")
        self.assertEqual(result["effects"], [])
        self.assertGreater(result["observed_terms"], 0)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)

    def test_old_frozen_fit_is_not_reinterpreted_or_relabelled_after_policy_change(self):
        text = "我重视公平吗？"
        source = self.model.submit(text, partition="rational")
        legacy = Contribution("value.fairness", 1, text[:-1], 0, len(text) - 1, "legacy-rule")
        with patch("model.engine.extract_contributions", return_value=[legacy]):
            self.model.review(source, agree=True)
        old_context = {"correction_revision": 0, "corrections": [], "learned_rules": []}
        with self.model.store._connect() as db:
            db.execute("UPDATE brain_fit_context SET payload=? WHERE source_id=?", (json.dumps(old_context), source))
        self.model.review(source, agree=False)
        restored = self.model.review(source, agree=True)
        self.assertEqual(restored["interpretation"], old_context)
        self.assertEqual(restored["effects"][0]["rule_id"], "legacy-rule")
        self.assertTrue(restored["restored_fit"])


if __name__ == "__main__":
    unittest.main()
