import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model.evidence import Contribution, extract_contributions
from translator.discourse import AssertionGuards, POLICY_VERSION


class SubjectOwnershipTests(unittest.TestCase):
    def values(self, text, kind="diary", **kwargs):
        return {item.parameter: item.sign for item in extract_contributions(text, kind=kind, **kwargs)
                if item.parameter.startswith("value.")}

    def test_known_indirect_other_predicates_and_viewpoints_never_become_own_values(self):
        cases = ("我觉得她把自由看得很重要。", "我覺得她把自由看得很重要。",
                 "我认为他不觉得公平重要。", "我觉得你很重视自由，而且很重要。",
                 "我相信别人一直把诚实放在重要的位置。", "我觉得朋友将公平视为最重要的原则。",
                 "对她来说，我认为自由很重要。", "我认为自由对她来说很重要。",
                 "我觉得在她眼里公平重要。", "我认为她心中自由很重要。")
        for kind in ("diary", "philosophy"):
            for text in cases:
                with self.subTest(kind=kind, text=text):
                    self.assertEqual(self.values(text, kind), {})

    def test_people_as_value_objects_are_not_mistaken_for_value_subjects(self):
        for text, parameter in (("我认为她的安全很重要。", "value.security"),
                                ("我重视朋友的成长。", "value.growth"),
                                ("我认为照顾父母很重要。", "value.care"),
                                ("我重视他人的自由。", "value.autonomy")):
            with self.subTest(text=text):
                self.assertEqual(self.values(text), {parameter: 1})

    def test_explicit_self_views_carry_across_commas_but_not_new_sentences_or_quoted_views(self):
        for text, expected in (("对我来说，安全重要。", {"value.security": 1}),
                               ("對我來說，自由重要。", {"value.autonomy": 1}),
                               ("在我的眼里，公平很重要。", {"value.fairness": 1}),
                               ("对我来说，公平不重要。", {"value.fairness": -1}),
                               ("对我来说，公平重要。自由重要。", {"value.fairness": 1}),
                               ('我写下“对我来说”，公平重要。', {}),
                               ("假如对我来说，公平重要。", {}),
                               ("朋友说：对我来说，公平重要。", {})):
            with self.subTest(text=text):
                self.assertEqual(self.values(text), expected)

    def test_explicit_own_view_reclaims_after_other_view_without_reclaiming_others(self):
        text = "我觉得对她来说自由重要，但对我来说安全重要。"
        self.assertEqual(self.values(text), {"value.security": 1})
        text = "对我来说，安全重要，但她把公平看得很重要。"
        self.assertEqual(self.values(text), {"value.security": 1})
        self.assertEqual(self.values("对我来说，我认为他不觉得公平重要。"), {})

    def test_other_values_do_not_erase_authors_own_feelings_or_intentions(self):
        text = "我觉得她把自由看得很重要，我对她很失望，下次我不会主动约她。"
        items = extract_contributions(text, kind="diary")
        self.assertEqual({item.parameter: item.sign for item in items},
                         {"affect.disappointment": 1, "expression.less_initiative": 1})
        for item in items:
            self.assertEqual(text[item.start:item.end], item.evidence)

    def test_chat_views_and_diagnostics_remain_author_scoped_exact_and_bounded(self):
        text = "朋友: 对我来说，公平重要。\r\n我: 😀我觉得她把自由看得很重要。\r\n我: 我重视安全。"
        diagnostics = {}
        self.assertEqual(self.values(text, kind="chat", self_speaker="我", diagnostics=diagnostics),
                         {"value.security": 1})
        self.assertEqual(diagnostics["withheld_count"], 1)
        item = diagnostics["withheld_values"][0]
        self.assertEqual(item["reason"], "other_subject_value")
        self.assertEqual(text[slice(*item["span"])], item["evidence"])
        self.assertEqual(self.values("朋友: 对我来说自由重要。\n我: 公平重要。", kind="chat", self_speaker="我"), {})
        diagnostics = {}
        self.values("我觉得她把自由看得很重要。" * 70, diagnostics=diagnostics)
        self.assertEqual(diagnostics["withheld_count"], 70)
        self.assertEqual(len(diagnostics["withheld_values"]), 64)
        self.assertTrue(diagnostics["withheld_truncated"])

    def test_many_indexed_subject_frames_keep_query_caches_bounded(self):
        phrase = "我觉得她把自由看得很重要。"
        guards = AssertionGuards(phrase * 3000, "diary", None)
        for start in range(0, len(phrase) * 3000, len(phrase)):
            self.assertEqual(guards.reason(start, start + len(phrase) - 1, include_hedges=True), "other_subject_value")
        self.assertLessEqual(len(guards._reason_cache), 256)


class SubjectOwnershipIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = BrainAPI(Path(self.temp.name) / "brain.sqlite3")
        self.model = self.api.brain.model

    def test_pending_local_and_learned_corrections_can_override_new_subject_guard(self):
        phrase = "我觉得她把自由看得很重要"
        for _ in range(2):
            source = self.model.submit(phrase + "。", partition="rational")
            self.model.correction_set(source, expected_revision=0, corrections=[{
                "parameter": "value.autonomy", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}])
            fitted = self.model.review(source, agree=True)
            self.assertEqual(fitted["interpretation"]["evidence_policy"], POLICY_VERSION)
            self.assertEqual(fitted["effects"][0]["rule_id"], "user_correction")
        source = self.model.submit(phrase + "。", partition="rational")
        preview = self.model.preview(source)
        self.assertEqual(preview["effects"][0]["rule_id"], "learned_exact_correction")
        self.assertEqual(preview["interpretation"]["withheld_values"][0]["reason"], "other_subject_value")

    def test_v1_frozen_contribution_and_policy_survive_v2_restore_without_reinterpretation(self):
        text = "我觉得她把自由看得很重要。"
        source = self.model.submit(text, partition="rational")
        old = Contribution("value.autonomy", 1, text[:-1], 0, len(text) - 1, "explicit_value_statement")
        with patch("model.engine.extract_contributions", return_value=[old]):
            self.model.review(source, agree=True)
        v1_context = {"correction_revision": 0, "corrections": [], "learned_rules": [],
                      "evidence_policy": "assertion-guards-v1", "withheld_values": [],
                      "withheld_count": 0, "withheld_truncated": False}
        with self.model.store._connect() as db:
            db.execute("UPDATE brain_fit_context SET payload=? WHERE source_id=?", (json.dumps(v1_context), source))
        self.model.revoke(source)
        with patch.object(self.model, "_observations", side_effect=AssertionError("do not reinterpret v1")):
            self.assertEqual(self.model.preview(source)["interpretation"], v1_context)
            restored = self.model.review(source, agree=True)
        self.assertEqual(restored["interpretation"], v1_context)
        self.assertTrue(restored["restored_fit"])
        fresh = self.model.submit(text, partition="rational")
        preview = self.model.preview(fresh)
        self.assertEqual(preview["interpretation"]["evidence_policy"], "assertion-guards-v2")
        self.assertEqual(preview["effects"], [])
        self.assertEqual(self.model.state("rational")["value.autonomy"]["support"], 1)
