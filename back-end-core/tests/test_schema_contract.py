"""Optional JSON Schema conformance checks using synthetic, temporary data.

Install the test-schema extra to run these; the local runtime stays dependency
free. CI explicitly imports the validator so missing extras cannot look green.
Cross-field evidence/span and approval semantics remain runtime tests too.
"""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

from core.api import BrainAPI, METHODS
from core.store import MemoryStore

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs/api.schema.json"


@unittest.skipIf(Draft202012Validator is None, "install alpha-brain[test-schema] for contract checks")
class SchemaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validators = {name: Draft202012Validator({**cls.schema, "$ref": f"#/$defs/{name}"})
                          for name in cls.schema["$defs"]}
        cls.result_validators = {method: Draft202012Validator(
            {**cls.schema, "$ref": f"#/$defs/results/$defs/{method}"})
            for method in cls.schema["$defs"]["results"]["$defs"]}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = BrainAPI(Path(self.temp.name) / "brain.sqlite3")
        self.called = set()
        self.examples = {}

    def test_model_reset_metadata_and_old_effects_remain_schema_compatible(self):
        first = self.call('submit', text='我重视公平。', partition='rational', exclamation=True)['source_id']
        self.call('submit', text='我重视公平。', partition='rational', exclamation=True)
        info = self.api.brain.model.reset_info()
        self.api.brain.model.reset_model(confirmation='RESET_MODEL', expected_epoch=info['model_epoch'],
                                        expected_revision=info['input_revision'])
        self.assertEqual(self.call('health')['model_epoch'], 1)
        record = self.call('input_get', source_id=first)
        self.assertEqual(record['status'], 'agreed')
        self.assertFalse(record['model_active'])
        self.assertEqual(record['model_epoch'], 0)
        self.call('input_page', limit=1)
        self.call('input_list')
        self.assertTrue(all(e['model_epoch'] == 0 for e in self.call('effects')))
        self.call('state')
        self.call('review_history', source_id=first)
        self.call('correction_history', source_id=first)
        restored = self.call('review', source_id=first, agree=True)
        self.assertTrue(all(e['model_epoch'] == 1 for e in restored['effects']))
        self.assertTrue(self.call('input_get', source_id=first)['model_active'])

    def validate(self, name, value):
        # Failures contain paths/messages, not a dump of input text.
        errors = list(self.validators[name].iter_errors(value))
        self.assertFalse(errors, [(list(error.absolute_path), error.message) for error in errors])

    def call(self, method, **params):
        request = {"schema_version": 1, "id": "schema-test", "method": method, "params": params}
        self.validate("request", request)
        response = self.api.handle(request)
        self.validate("response", response)
        self.assertEqual(response["id"], request["id"])
        self.assertTrue(response["ok"], response.get("error"))
        self.called.add(method)
        result = response["result"]
        errors = list(self.result_validators[method].iter_errors(result))
        self.assertFalse(errors, (method, [(list(error.absolute_path), error.message) for error in errors]))
        self.examples[method] = copy.deepcopy(result)
        if isinstance(result, dict):
            if "immediate" in result:
                self.validate("approvalMetadata", result)
            for name in ("interpretation", "translation"):
                if name in result:
                    self.validate(name, result[name])
            if result.get("fit_context") is not None:
                self.validate("interpretation", result["fit_context"])
        if method == "input_list":
            for item in result:
                self.validate("inputRecord", item)
        elif method == "input_page":
            self.validate("inputPage", result)
        elif method == "state":
            self.validate("partitionState" if params.get("partition") is not None else "allState", result)
        return result

    def test_all_23_methods_have_live_request_and_envelope_examples(self):
        self.call("health")
        self.call("baseline")
        source = self.call("submit", text="😀我重视公平。\r\n我很开心。", partition="rational")["source_id"]
        self.call("input_get", source_id=source)
        self.call("input_list", partition="rational", status="pending")
        self.call("input_page", limit=1)
        self.call("preview", source_id=source)
        self.call("correction_history", source_id=source)
        self.call("correction_set", source_id=source, expected_revision=0, corrections=[])
        self.call("review", source_id=source, agree=True)
        self.call("review_history", source_id=source)
        self.call("state", partition="rational")
        self.call("effects", source_id=source)
        self.call("terms", partition="rational", min_documents=1)
        self.call("rank", options=[{"id": "fair", "impacts": {"value.fairness": 1}},
                                   {"id": "other", "impacts": {}}])
        candidate = self.call("candidate_propose", source_id=source,
                              claim="重视公平", evidence="我重视公平")["candidate_id"]
        self.call("candidate_review", candidate_id=candidate, accept=True)
        self.call("candidate_list")
        self.call("memory_list", partition="rational")
        self.call("memory_search", query="公平", partition="rational")
        self.call("revoke", source_id=source)
        self.call("input_edit", source_id=source, text="我重视自由。", immediate=True)
        self.call("input_delete", source_id=source)
        self.assertEqual(self.called, set(METHODS))
        self.assertEqual(set(self.result_validators), set(METHODS))
        for method, value in self.examples.items():
            with self.subTest(method=method):
                # Every body rejects unknown fields, including inside list rows.
                malformed = copy.deepcopy(value)
                if isinstance(malformed, dict):
                    malformed["unexpected_contract_field"] = True
                elif malformed:
                    malformed[0]["unexpected_contract_field"] = True
                else:
                    malformed.append({"unexpected_contract_field": True})
                self.assertFalse(self.result_validators[method].is_valid(malformed))

    def test_questions_quotes_ambiguity_and_truncated_diagnostics_match_schema(self):
        cases = [("我重视公平吗？", "diary", None),
                 ("我重视“公平”。我不认为自由不重要。", "philosophy", None),
                 ('> 我重视公平。\n```\n我重视自由。\n```', "philosophy", None),
                 ('朋友: “我重视自由\r\n我: 😀我重视公平吗？\r\n我: 我对朋友很失望。', "chat", "我"),
                 ("我重视公平吗？" * 70, "diary", None)]
        for text, kind, self_speaker in cases:
            with self.subTest(kind=kind, chars=len(text)):
                source = self.call("submit", text=text, partition="rational", kind=kind,
                                   self_speaker=self_speaker)["source_id"]
                preview = self.call("preview", source_id=source)
                context = preview["interpretation"]
                for item in context["withheld_values"]:
                    self.assertEqual(text[slice(*item["span"])], item["evidence"])
                fitted = self.call("review", source_id=source, agree=True)
                self.assertEqual(context, fitted["interpretation"])
                self.call("correction_history", source_id=source)
        self.assertTrue(context["withheld_truncated"])
        self.assertEqual(context["withheld_count"], 70)

    def test_local_learned_insufficient_active_and_conflicting_contexts_match_schema(self):
        phrase = "我重视公平"
        for sign, expected in ((1, "insufficient"), (1, "active"), (-1, "conflict")):
            source = self.call("submit", text=phrase + "？", partition="rational")["source_id"]
            self.call("correction_set", source_id=source, expected_revision=0,
                      corrections=[{"parameter": "value.fairness", "sign": sign,
                                    "evidence": phrase, "span": [0, len(phrase)]}])
            self.call("preview", source_id=source)
            self.call("review", source_id=source, agree=True)
            probe = self.call("submit", text=phrase + "？", partition="rational")["source_id"]
            context = self.call("preview", source_id=probe)["interpretation"]
            self.assertEqual(context["learned_rules"][0]["status"], expected)
        legacy = {"correction_revision": 0, "corrections": [], "learned_rules": []}
        self.validate("interpretation", legacy)
        self.validate("interpretation", {**legacy, "legacy_context_unavailable": True})
        v1 = {**legacy, "evidence_policy": "assertion-guards-v1", "withheld_values": [],
              "withheld_count": 0, "withheld_truncated": False}
        self.validate("interpretation", v1)
        probe = self.call("submit", text="我觉得她把自由看得很重要。", partition="rational")["source_id"]
        context = self.call("preview", source_id=probe)["interpretation"]
        self.assertEqual(context["evidence_policy"], "assertion-guards-v2")
        self.assertEqual(context["withheld_values"][0]["reason"], "other_subject_value")
        mislabeled = {**context, "evidence_policy": "assertion-guards-v1"}
        self.assertFalse(self.validators["interpretation"].is_valid(mislabeled))

    def test_approval_shapes_and_stale_page_error_match_schema(self):
        rejected = self.call("submit", text="我重视公平。", partition="rational", immediate=False)["source_id"]
        normal = self.call("submit", text="我重视自由。", partition="rational")["source_id"]
        self.call("input_page", status="disagreed")
        page = self.call("input_page", limit=1)
        self.assertIsNotNone(page["next_cursor"])
        self.call("review", source_id=normal, agree=True)
        stale = self.api.handle({"schema_version": 1, "id": "stale", "method": "input_page",
                                 "params": {"limit": 1, "cursor": page["next_cursor"]}})
        self.validate("response", stale)
        self.assertEqual(stale["error"]["code"], "STALE_CURSOR")
        self.call("review", source_id=normal, agree=False)
        self.call("input_list")
        self.call("review", source_id=normal, agree=True)
        self.call("revoke", source_id=normal)
        self.call("input_list")
        self.call("submit", text="我开心。", partition="emotional", immediate=False, exclamation=True)
        self.call("input_list")
        self.assertEqual(self.call("input_get", source_id=rejected)["status"], "disagreed")

    def test_source_governance_branches_nul_rejection_and_negative_shapes_match_schema(self):
        health = self.call("health")
        self.assertTrue(health["features"]["source_edit"])
        self.assertTrue(health["features"]["source_delete"])
        source = self.call("submit", text="😀我重视公平。\r\n", partition="rational", immediate=False)["source_id"]
        for immediate in (False, True):
            record = self.call("input_edit", source_id=source, text="😀我重视自由。\r\n", immediate=immediate)
            self.assertIsNone(record["confirm"])
            self.assertIsInstance(record["edited_at"], str)
            self.assertNotIn("ever_fitted", record)
            self.assertFalse(self.result_validators["input_edit"].is_valid({**record, "edited_at": None}))
            self.assertFalse(self.result_validators["input_edit"].is_valid({**record, "text": "not a metadata result"}))
            self.call("input_get", source_id=source)
            self.call("input_page")
        self.call("review", source_id=source, agree=True)
        deleted = self.call("input_delete", source_id=source)
        self.assertFalse(self.result_validators["input_delete"].is_valid({**deleted, "deleted": False}))
        self.assertFalse(self.result_validators["input_delete"].is_valid({**deleted, "effects": []}))
        response = self.api.handle({"schema_version": 1, "id": "deleted", "method": "input_get", "params": {"source_id": source}})
        self.validate("response", response)
        self.assertEqual(response["error"]["code"], "NOT_FOUND")
        for method, params in (("submit", {"partition": "rational"}),
                               ("input_edit", {"source_id": source, "immediate": True})):
            for text in ("\0内容", "内\0容", "内容\0"):
                request = {"schema_version": 1, "id": "nul", "method": method, "params": {**params, "text": text}}
                self.assertFalse(self.validators["request"].is_valid(request))
                response = self.api.handle(request)
                self.validate("response", response)
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")

    def test_invalid_request_and_response_structures_are_rejected(self):
        base = {"schema_version": 1, "id": "bad", "method": "submit",
                "params": {"text": "我重视公平。", "partition": "rational"}}
        invalid = [{**base, "schema_version": 2}, {**base, "id": ""},
                   {**base, "method": "input_edit"}, {**base, "extra": True},
                   {**base, "params": {**base["params"], "db": "not-allowed"}},
                   {**base, "params": {**base["params"], "immediate": 1}},
                   {**base, "params": {**base["params"], "partition": "unknown"}},
                   {**base, "params": {**base["params"], "text": ""}}]
        for request in invalid:
            self.assertFalse(self.validators["request"].is_valid(request))
            response = self.api.handle(request)
            self.validate("response", response)
            self.assertFalse(response["ok"])
        self.assertEqual(self.call("input_list"), [])
        self.assertFalse(self.validators["response"].is_valid(
            {"schema_version": 1, "id": "bad", "ok": True}))
        self.assertFalse(self.validators["response"].is_valid(
            {"schema_version": 1, "id": "", "ok": True, "result": {}}))
        self.assertFalse(self.validators["response"].is_valid(
            {"schema_version": 1, "id": "bad", "ok": False,
             "error": {"code": "LOCKED", "message": "not implemented"}}))

    def test_invalid_diagnostics_cannot_pass_the_public_definition(self):
        source = self.call("submit", text="我重视公平吗？", partition="rational")["source_id"]
        context = self.call("preview", source_id=source)["interpretation"]
        for mutate in (lambda value: value.pop("withheld_count"),
                       lambda value: value.pop("evidence_policy"),
                       lambda value: value.update(evidence_policy="unknown"),
                       lambda value: value["withheld_values"][0].update(reason="unknown"),
                       lambda value: value["withheld_values"][0].update(parameters=["affect.anger"]),
                       lambda value: value["withheld_values"][0].update(span=[0, "6"]),
                       lambda value: value["withheld_values"].extend(value["withheld_values"] * 64)):
            malformed = copy.deepcopy(context)
            mutate(malformed)
            self.assertFalse(self.validators["interpretation"].is_valid(malformed))

    def test_decision_noops_restoration_and_vocabulary_threshold_effects_match_schema(self):
        first = self.call("submit", text="我重视公平。", partition="rational")["source_id"]
        self.call("review", source_id=first, agree=False)
        fitted = self.call("review", source_id=first, agree=True)
        self.assertFalse(fitted["restored_fit"])
        second = self.call("submit", text="我重视公平。", partition="rational", exclamation=True)
        self.assertTrue(second["translator_effects"])
        noop = self.call("review", source_id=first, agree=True)
        self.assertNotIn("interpretation", noop)
        self.assertEqual(noop["effects"], [])
        removed = self.call("revoke", source_id=first)
        self.assertTrue(removed["translator_effects"])
        self.call("preview", source_id=first)
        self.assertEqual(self.call("review", source_id=first, agree=False)["status"], "revoked")
        restored = self.call("review", source_id=first, agree=True)
        self.assertTrue(restored["restored_fit"])
        self.assertTrue(restored["translator_effects"])
        self.call("review_history", source_id=first)
        self.call("effects")
        for field in ("interpretation", "observed_terms", "restored_fit"):
            malformed = copy.deepcopy(restored)
            malformed.pop(field)
            self.assertFalse(self.result_validators["review"].is_valid(malformed))
        malformed = copy.deepcopy(restored)
        malformed["effects"][0].pop("revision")
        self.assertFalse(self.result_validators["review"].is_valid(malformed))
        malformed = copy.deepcopy(restored)
        malformed["effects"][0]["action"] = "preview"
        self.assertFalse(self.result_validators["review"].is_valid(malformed))

    def test_rank_abstention_provisional_and_indistinguishable_forms_match_schema(self):
        options = [{"id": "fair", "impacts": {"value.fairness": 1}}, {"id": "other", "impacts": {}}]
        self.assertEqual(self.call("rank", options=options)["reason"], "insufficient_confirmed_value_evidence")
        for _ in range(2):
            self.call("submit", text="我重视公平。", partition="rational", exclamation=True)
        ranked = self.call("rank", options=options)
        self.assertEqual(ranked["status"], "provisional")
        self.assertEqual(self.call("rank", options=[{"id": "a", "impacts": {"value.fairness": 1}},
                                                   {"id": "b", "impacts": {"value.fairness": 1}}])["reason"],
                         "options_indistinguishable_with_current_evidence")
        for mutate in (lambda value: value.update(not_a_probability=False),
                       lambda value: value.update(used_parameters=["affect.anger"]),
                       lambda value: value["ranked"][0].update(alignment_score=float("inf"))):
            malformed = copy.deepcopy(ranked)
            mutate(malformed)
            self.assertFalse(self.result_validators["rank"].is_valid(malformed))

    def test_zero_baseline_full_state_partition_state_and_observed_zero_match_schema(self):
        baseline = self.call("baseline")
        self.call("state")
        self.call("state", partition=None)
        for partition in ("rational", "emotional", "crazy"):
            self.call("state", partition=partition)
        for text in ("我重视公平。", "我不重视公平。"):
            self.call("submit", text=text, partition="rational", exclamation=True)
        state = self.call("state", partition="rational")
        self.assertEqual(state["value.fairness"], {"value": 0, "support": 2, "observed": True})
        malformed = copy.deepcopy(state)
        malformed["value.fairness"]["observed"] = False
        self.assertFalse(self.result_validators["state"].is_valid(malformed))
        malformed = copy.deepcopy(state)
        malformed.pop("value.fairness")
        self.assertFalse(self.result_validators["state"].is_valid(malformed))
        malformed = copy.deepcopy(baseline)
        malformed["parameters"]["value.fairness"] = 1
        self.assertFalse(self.result_validators["baseline"].is_valid(malformed))
        self.assertEqual(self.call("baseline"), baseline)

    def test_candidate_and_active_memory_records_keep_different_status_boundaries(self):
        source = self.call("submit", text="我重视公平。", partition="rational", exclamation=True)["source_id"]
        candidate_ids = [self.call("candidate_propose", source_id=source, claim="重视公平", evidence="公平")["candidate_id"]
                         for _ in range(3)]
        self.call("candidate_review", candidate_id=candidate_ids[0], accept=True)
        self.call("candidate_review", candidate_id=candidate_ids[1], accept=False)
        rows = self.call("candidate_list")
        self.assertEqual({item["status"] for item in rows}, {"pending", "accepted", "rejected"})
        active = self.call("memory_list")
        self.call("memory_search", query="公平")
        self.call("revoke", source_id=source)
        self.assertEqual(self.call("memory_list"), [])
        self.assertEqual(self.call("memory_search", query="公平"), [])
        self.assertEqual(len(self.call("candidate_list")), 3)
        self.call("candidate_review", candidate_id=candidate_ids[2], accept=False)
        malformed = copy.deepcopy(active)
        malformed[0]["source_status"] = "revoked"
        self.assertFalse(self.result_validators["memory_list"].is_valid(malformed))
        malformed = copy.deepcopy(active)
        malformed[0]["status"] = "pending"
        self.assertFalse(self.result_validators["memory_search"].is_valid(malformed))

    def test_real_legacy_migration_and_frozen_context_forms_match_schema(self):
        path = Path(self.temp.name) / "legacy.sqlite3"
        MemoryStore(path).initialize()
        # A valid old all-zero fit with no extracted parameter/word evidence.
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
                CREATE TABLE brain_inputs (source_id TEXT PRIMARY KEY REFERENCES sources(id),
                    partition TEXT NOT NULL, kind TEXT NOT NULL, self_speaker TEXT,
                    status TEXT NOT NULL, reviewed_at TEXT);
                CREATE TABLE brain_fit_context (source_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            for status in ("pending", "agreed", "disagreed", "revoked"):
                db.execute("INSERT INTO sources VALUES (?, '🙂', 'diary', NULL, 'old-time')", (status,))
                db.execute("INSERT INTO brain_inputs VALUES (?, 'rational', 'diary', NULL, ?, NULL)",
                           (status, status))
            db.execute("INSERT INTO brain_fit_context VALUES ('revoked', ?)",
                       (json.dumps({"correction_revision": 0, "corrections": [], "learned_rules": []}),))
        self.api = BrainAPI(path)
        self.call("input_list")
        self.call("input_page")
        for status in ("pending", "agreed", "disagreed", "revoked"):
            self.call("input_get", source_id=status)
            history = self.call("review_history", source_id=status)
            self.assertEqual(history["history"][0]["before"], {"status": status})
            self.call("correction_history", source_id=status)
        self.call("revoke", source_id="agreed")
        context = self.call("preview", source_id="agreed")["interpretation"]
        self.assertTrue(context["legacy_context_unavailable"])
        self.assertNotIn("evidence_policy", context)
        self.assertTrue(self.call("review", source_id="agreed", agree=True)["restored_fit"])
        context = self.call("preview", source_id="revoked")["interpretation"]
        self.assertNotIn("legacy_context_unavailable", context)
        self.assertNotIn("evidence_policy", context)
        self.call("review", source_id="revoked", agree=True)

    def test_serialized_jsonlines_responses_match_method_body_schemas(self):
        path = Path(self.temp.name) / "wire.sqlite3"

        def wire(requests):
            for request in requests:
                self.validate("request", request)
            process = subprocess.run([sys.executable, "-m", "core.api", "--db", str(path)],
                                     cwd=SCHEMA_PATH.parents[1],
                                     input="".join(json.dumps(request, ensure_ascii=True) + "\n" for request in requests),
                                     text=True, capture_output=True, timeout=10, check=True)
            responses = [json.loads(line) for line in process.stdout.splitlines()]
            self.assertEqual(len(responses), len(requests))
            for request, response in zip(requests, responses):
                self.validate("response", response)
                self.assertEqual(response["id"], request["id"])
                self.assertTrue(response["ok"], response.get("error"))
                self.assertTrue(self.result_validators[request["method"]].is_valid(response["result"]))
            return responses

        source = wire([{"schema_version": 1, "id": "submit", "method": "submit",
                        "params": {"text": "😀我重视公平。\r\n", "partition": "rational"}}])[0]["result"]["source_id"]
        cases = [("health", {}), ("input_get", {"source_id": source}),
                 ("preview", {"source_id": source}), ("review", {"source_id": source, "agree": True}),
                 ("effects", {}), ("state", {}), ("review_history", {"source_id": source}),
                 ("correction_history", {"source_id": source}), ("input_page", {})]
        wire([{"schema_version": 1, "id": method, "method": method, "params": params}
              for method, params in cases])


if __name__ == "__main__":
    unittest.main()
