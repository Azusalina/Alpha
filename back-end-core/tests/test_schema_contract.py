"""Optional JSON Schema conformance checks using synthetic, temporary data.

Install the test-schema extra to run these; the local runtime stays dependency
free. CI explicitly imports the validator so missing extras cannot look green.
Cross-field evidence/span and approval semantics remain runtime tests too.
"""

import copy
import json
import inspect
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None

from core.api import BrainAPI, METHODS
from core.brain import BrainCore
from core.store import MemoryStore
from model import preferences

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

    def legacy_pending(self, source):
        """Seed a historical pending candidate; new proposals are auto-accepted."""
        candidate = uuid.uuid4().hex
        version = self.api.brain.input_get(source)["source_version"]
        with closing(sqlite3.connect(self.api.path)) as db, db:
            db.execute("INSERT INTO candidates(id,source_id,claim,evidence,status,created_at,source_version) "
                       "VALUES (?,?,'重视公平','公平','pending','synthetic-legacy-time',?)",
                       (candidate, source, version))
        return candidate

    def guards(self, source):
        info = self.api.brain.model.reset_info()
        return dict(expected_source_version=self.api.brain.input_get(source)["source_version"],
                    expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])

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

    def test_all_methods_have_live_request_and_envelope_examples(self):
        self.call("health")
        self.call("baseline")
        self.call("access_status")
        self.call("unlock", password="synthetic unconfigured password")
        self.call("lock")
        source = self.call("submit", text="😀我重视公平。\r\n我很开心。我想联系朋友。", partition="rational")["source_id"]
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
        self.assertEqual(self.call("candidate_propose", source_id=source,
                                  claim="重视公平", evidence="我重视公平")["status"], "accepted")
        self.call("candidate_review", candidate_id=self.legacy_pending(source), accept=True)
        self.call("candidate_list")
        self.call("memory_list", partition="rational")
        self.call("memory_search", query="公平", partition="rational")
        self.call("memory_search_semantic", query="公平", partition=None)
        self.call("choice_feedback_set", source_id=source, event_id="reviewed-event", domain="daily",
                  options=[{"id": "fair", "label": "User reviewed", "impacts": {"value.fairness": 1}},
                           {"id": "other", "impacts": {"value.fairness": -1}}],
                  actual_choice_id="fair", endorsed_choice_id=None, endorsement_partition=None,
                  training_consent=False, reason=None, **self.guards(source))
        self.call("choice_feedback_get", source_id=source)
        self.call("preference_rank", options=[{"id": "fair", "impacts": {"value.fairness": 1}},
                                              {"id": "other", "impacts": {"value.fairness": -1}}],
                  target="actual", partition="rational", domain="daily")
        self.call("replay_preview", source_ids=[source])
        reopened = self.call("correction_reopen", source_id=source, corrections=[], immediate=True,
                             **self.guards(source))
        self.assertTrue(reopened["effects"])
        self.call("correction_history", source_id=source)
        self.call("review_history", source_id=source)
        self.call("review_version", source_id=source, agree=True, **self.guards(source))
        info = self.api.brain.model.reset_info()
        self.call("replay_reopen", source_ids=[source], immediate=True,
                  expected_source_versions={source: self.api.brain.input_get(source)["source_version"]},
                  expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])
        self.call("review_version", source_id=source, agree=True, **self.guards(source))
        self.call("revoke", source_id=source)
        self.call("input_edit", source_id=source, text="我重视自由。", immediate=True)
        self.call("input_delete", source_id=source)
        self.assertEqual(self.called, set(METHODS))
        self.assertEqual(set(self.result_validators), set(METHODS))
        self.assertEqual(len(self.called), 34)
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

    def test_additive_methods_match_actual_module_and_core_signatures(self):
        methods = self.schema["$defs"]["request"]["properties"]["method"]["enum"]
        self.assertEqual((len(methods), len(METHODS)), (34, 34))
        self.assertEqual(set(methods), set(METHODS))
        self.assertEqual(set(self.result_validators), set(METHODS))
        request_schemas = {
            branch["if"]["properties"]["method"]["const"]: branch["then"]["properties"]["params"]
            for branch in self.schema["$defs"]["request"]["allOf"]
            if "const" in branch["if"]["properties"]["method"]
        }
        for method, module in (("memory_search_semantic", None),
                               ("choice_feedback_set", preferences.set_feedback),
                               ("choice_feedback_get", preferences.get_feedback),
                               ("preference_rank", preferences.rank_preferences)):
            for function in (getattr(BrainCore, method), module):
                if function is None:
                    continue
                with self.subTest(method=method, function=function.__name__):
                    parameters = {name: parameter for name, parameter in inspect.signature(function).parameters.items()
                                  if name not in {"self", "store"}}
                    required = {name for name, parameter in parameters.items()
                                if parameter.default is inspect.Parameter.empty}
                    optional = set(parameters) - required
                    self.assertEqual(required, set(METHODS[method][0]))
                    self.assertEqual(optional, set(METHODS[method][1]))
                    self.assertEqual(required, set(request_schemas[method]["required"]))
                    self.assertEqual(set(parameters), set(request_schemas[method]["properties"]))
        self.assertEqual(inspect.signature(BrainCore.memory_search_semantic).parameters["min_score"].default, 0)
        self.assertEqual(request_schemas["memory_search_semantic"]["properties"]["min_score"]["default"], 0)
        for function in (BrainCore.choice_feedback_set, preferences.set_feedback):
            self.assertIsNone(inspect.signature(function).parameters["group_id"].default)
            self.assertIs(inspect.signature(function).parameters["group_reviewed"].default, False)
        group_fields = request_schemas["choice_feedback_set"]["properties"]
        self.assertIsNone(group_fields["group_id"]["default"])
        self.assertIs(group_fields["group_reviewed"]["default"], False)

    def feedback(self, source, **changes):
        fields = dict(source_id=source, event_id="synthetic schema event", domain="daily",
                      options=[{"id": "fair", "label": "Reviewed", "impacts": {"value.fairness": 1}},
                               {"id": "other", "impacts": {"value.fairness": -1}}],
                      actual_choice_id="fair", endorsed_choice_id="other", endorsement_partition="rational",
                      training_consent=True, group_id=source, group_reviewed=True, **self.guards(source))
        fields.update(changes)
        return self.call("choice_feedback_set", **fields)

    def test_hybrid_live_results_and_nested_negative_types(self):
        from tests.test_hybrid_api import FakeEncoder, OPTIONS
        self.api = BrainAPI(self.api.path, semantic_encoder=FakeEncoder())
        sources = [self.call("submit", text="我很开心。我想联系朋友。", partition="rational",
                             exclamation=True)["source_id"] for _ in range(3)]
        for source in sources:
            record = self.feedback(source)
            self.assertIsNone(record["reason"])
            self.assertTrue(record["model_active"])
            self.assertNotIn("learning_eligible", record)
        semantic = self.call("memory_search_semantic", query="开心")
        self.assertEqual(semantic["pool_count"], 3)
        self.assertEqual(semantic["items"][0]["memory"]["evidence"], "开心")
        feedback = self.call("choice_feedback_get", source_id=sources[0])
        provisional = self.call("preference_rank", options=OPTIONS, target="actual", partition="rational", domain="daily")
        self.assertEqual(provisional["status"], "provisional")
        self.assertEqual(self.call("preference_rank", options=OPTIONS, target="endorsed", partition="rational",
                                   domain="daily")["ranked"][0]["id"], "other")
        self.assertEqual(self.call("preference_rank", options=OPTIONS, target="actual", partition="emotional",
                                   domain="daily")["status"], "abstain")
        self.api = BrainAPI(self.api.path)
        fallback = self.call("memory_search_semantic", query="开心")
        self.assertEqual(fallback["mode"], "lexical_fallback")
        for method, example, mutations in (
            ("memory_search_semantic", semantic, (
                lambda x: x["items"][0]["memory"].update(source_version="0"),
                lambda x: x["items"][0]["memory"].pop("source_version"),
                lambda x: x["items"][0]["memory"].update(source_status="revoked"),
                lambda x: x["items"][0]["memory"].update(status="pending"),
                lambda x: x["items"][0]["memory"].update(extra=True),
                lambda x: x["items"][0].update(score=None),
                lambda x: x["items"][0].update(score=True),
                lambda x: x["items"][0].update(score=1.01),
                lambda x: x["items"][0].update(encoded_text_truncated=0),
                lambda x: x.update(pool_count=True),
                lambda x: x.update(score_kind="none"))),
            ("memory_search_semantic", fallback, (
                lambda x: x["items"][0].update(score=0),
                lambda x: x["items"][0].update(encoded_text_truncated=True),
                lambda x: x.update(score_kind="cosine"))),
            ("choice_feedback_set", record, (
                lambda x: x["options"][0]["impacts"].update({"value.fairness": True}),
                lambda x: x["options"][0]["impacts"].update({"affect.anger": 1}),
                lambda x: x["options"][0].update(extra=True),
                lambda x: x.update(training_consent=1),
                lambda x: x.update(training_consent=False),
                lambda x: x.update(group_reviewed=False),
                lambda x: x.update(group_reviewed=1),
                lambda x: x.update(group_id=None),
                lambda x: x.update(group_id=" \t"),
                lambda x: x.pop("group_id"),
                lambda x: x.pop("group_reviewed"),
                lambda x: x.update(model_active=1),
                lambda x: x.update(learning_eligible=True),
                lambda x: x.update(endorsed_choice_id=None, endorsement_partition="rational"),
                lambda x: x.update(body_digest="not-a-digest"),
                lambda x: x.update(reason="bad\0reason"))),
            ("choice_feedback_get", feedback, (
                lambda x: x["records"][0].update(model_active="true"),
                lambda x: x["records"][0].update(input_revision=0),
                lambda x: x["records"][0].pop("training_consent"),
                lambda x: x["records"][0]["options"][0].update(id=" "),
                lambda x: x.update(model_epoch=False))),
            ("preference_rank", provisional, (
                lambda x: x["weights"].update({"value.fairness": "1"}),
                lambda x: x["weights"].update({"value.fairness": float("inf")}),
                lambda x: x["weights"].update({"affect.anger": 0}),
                lambda x: x["ranked"][0]["contributions"].pop("value.fairness"),
                lambda x: x["ranked"][0]["contributions"].update({"value.fairness": True}),
                lambda x: x["ranked"][0].update(score="1"),
                lambda x: x["ranked"][0].update(score=float("inf")),
                lambda x: x["ranked"][0].update(model_probability=1.1),
                lambda x: x["ranked"][0].update(extra=True),
                lambda x: x.update(used_features=["affect.anger"]),
                lambda x: x.update(not_calibrated=False),
                lambda x: x.update(training_sources=0),
                lambda x: x.update(training_groups=2),
                lambda x: x.update(training_groups=True),
                lambda x: x.pop("training_groups"),
                lambda x: x.update(reason="insufficient_independent_sources"),
                lambda x: x.update(status="abstain")) )):
            for index, mutate in enumerate(mutations):
                with self.subTest(method=method, mode=example.get("mode"), mutation=index):
                    malformed = copy.deepcopy(example)
                    mutate(malformed)
                    self.assertFalse(self.result_validators[method].is_valid(malformed))

    def test_preference_contrast_schema_requires_exact_basis_length_for_every_rank(self):
        options = [{"id": "a", "impacts": {"value.growth": 1}},
                   {"id": "b", "impacts": {}}]
        empty = self.call("preference_rank", options=options, target="actual",
                          partition="rational", domain="daily")
        validators = (self.validators["preferenceResult"], self.result_validators["preference_rank"])
        for rank in range(9):
            example = {**empty, "contrast_rank": rank,
                       "contrast_basis": [[float(i == j) for j in range(8)] for i in range(rank)]}
            for validator in validators:
                with self.subTest(rank=rank, definition=validator.schema["$ref"]):
                    self.assertTrue(validator.is_valid(example))
                    for length in range(10):
                        if length != rank:
                            malformed = {**example, "contrast_basis": [[0.0] * 8 for _ in range(length)]}
                            self.assertFalse(validator.is_valid(malformed), (rank, length))

    def test_preference_contrast_schema_rejects_missing_mistyped_and_out_of_bounds_metadata(self):
        options = [{"id": "a", "impacts": {"value.growth": 1}},
                   {"id": "b", "impacts": {}}]
        example = self.call("preference_rank", options=options, target="actual",
                            partition="rational", domain="daily")
        example.update(contrast_rank=1, contrast_basis=[[0.0] * 5 + [1.0, 0.0, 0.0]])
        mutations = (
            lambda x: x.pop("contrast_rank"), lambda x: x.pop("contrast_basis"),
            lambda x: x.update(contrast_rank=True), lambda x: x.update(contrast_rank="1"),
            lambda x: x.update(contrast_rank=None), lambda x: x.update(contrast_rank=1.5),
            lambda x: x.update(contrast_rank=-1), lambda x: x.update(contrast_rank=9),
            lambda x: x.update(contrast_basis=None), lambda x: x.update(contrast_basis={}),
            lambda x: x.update(contrast_basis="basis"),
            lambda x: x.update(contrast_basis=[None]), lambda x: x.update(contrast_basis=[{}]),
            lambda x: x.update(contrast_basis=["row"]),
            lambda x: x["contrast_basis"][0].pop(),
            lambda x: x["contrast_basis"][0].append(0.0),
            lambda x: x["contrast_basis"][0].__setitem__(0, True),
            lambda x: x["contrast_basis"][0].__setitem__(0, "0"),
            lambda x: x["contrast_basis"][0].__setitem__(0, None),
            lambda x: x["contrast_basis"][0].__setitem__(0, float("inf")),
            lambda x: x["contrast_basis"][0].__setitem__(0, -float("inf")),
            lambda x: x["contrast_basis"][0].__setitem__(0, 1.0000000000005),
            lambda x: x["contrast_basis"][0].__setitem__(0, -1.0000000000005),
            lambda x: x.update(extra_contrast_metadata=True),
        )
        validators = (self.validators["preferenceResult"], self.result_validators["preference_rank"])
        for validator in validators:
            self.assertTrue(validator.is_valid(example))
            for index, mutate in enumerate(mutations):
                with self.subTest(mutation=index, definition=validator.schema["$ref"]):
                    malformed = copy.deepcopy(example)
                    mutate(malformed)
                    self.assertFalse(validator.is_valid(malformed))
        # Numeric JSON values such as 1.0 satisfy JSON Schema's integer type;
        # exact Python types, NaN and dynamic geometry are runtime obligations.
        for basis in ([[0.0] * 8], [[1.0] + [0.0] * 7] * 2):
            structural = {**example, "contrast_rank": len(basis), "contrast_basis": basis}
            self.assertTrue(self.result_validators["preference_rank"].is_valid(structural))
            runtime_fit = {**structural, "status": "provisional", "used_features": ["value.growth"]}
            with self.assertRaises(ValueError):
                preferences.rank_from_fit(options, runtime_fit)

    def test_rev5_health_contrast_feature_is_required_typed_and_closed(self):
        health = self.call("health")
        self.assertEqual(health["contract_revision"], 5)
        self.assertEqual(len(health["methods"]), 34)
        self.assertIs(health["features"]["preference_contrast_guard"], True)
        for mutate in (
            lambda x: x.update(contract_revision=4),
            lambda x: x["features"].pop("preference_contrast_guard"),
            lambda x: x["features"].update(preference_contrast_guard=False),
            lambda x: x["features"].update(preference_contrast_guard=1),
            lambda x: x["features"].update(extra_contrast_feature=True),
        ):
            malformed = copy.deepcopy(health)
            mutate(malformed)
            self.assertFalse(self.result_validators["health"].is_valid(malformed))

    def test_hybrid_requests_reject_nested_invalid_types_at_schema_and_runtime(self):
        from tests.test_hybrid_api import OPTIONS
        source = self.call("submit", text="我很开心。我想联系朋友。", partition="rational",
                           exclamation=True)["source_id"]
        valid = dict(source_id=source, event_id="synthetic event", domain="daily", options=copy.deepcopy(OPTIONS),
                     actual_choice_id=None, endorsed_choice_id=None, endorsement_partition=None,
                     training_consent=False, reason=None, **self.guards(source))
        for method, params, mutations in (
            ("memory_search_semantic", {"query": "开心"}, (
                lambda x: x.update(min_score=True), lambda x: x.update(min_score=None),
                lambda x: x.update(query="bad\0query"), lambda x: x.update(limit=0))),
            ("choice_feedback_set", valid, (
                lambda x: x.update(training_consent=1), lambda x: x.update(expected_epoch=True),
                lambda x: x.update(group_id=" \t"), lambda x: x.update(group_id="bad\0group"),
                lambda x: x.update(group_id="\udfff"), lambda x: x.update(group_id="x" * 129),
                lambda x: x.update(group_id=1), lambda x: x.update(group_reviewed=1),
                lambda x: x.update(group_reviewed=None), lambda x: x.update(group_reviewed=True),
                lambda x: x.update(event_id="\ud800"), lambda x: x.update(reason="bad\0reason"),
                lambda x: x.update(endorsed_choice_id="fair", endorsement_partition=None),
                lambda x: x["options"][0]["impacts"].update({"value.fairness": "1"}),
                lambda x: x["options"][0]["impacts"].update({"affect.anger": 1}),
                lambda x: x["options"][0].update(extra=True))),
            ("choice_feedback_get", {"source_id": source}, (lambda x: x.update(source_id=" "),)),
            ("preference_rank", {"options": copy.deepcopy(OPTIONS), "target": "actual", "partition": "rational", "domain": "daily"}, (
                lambda x: x.update(target="inferred"), lambda x: x.update(domain="unknown"),
                lambda x: x.update(partition=None), lambda x: x["options"][0]["impacts"].update({"value.fairness": True})))):
            for index, mutate in enumerate(mutations):
                with self.subTest(method=method, mutation=index):
                    malformed = copy.deepcopy(params)
                    mutate(malformed)
                    request = {"schema_version": 1, "id": "negative hybrid", "method": method, "params": malformed}
                    self.assertFalse(self.validators["request"].is_valid(request))
                    response = self.api.handle(request)
                    self.validate("response", response)
                    self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("choice_feedback_get", source_id=source)["records"], [])
        self.call("choice_feedback_set", **valid)

    def test_three_group_events_in_one_source_are_valid_provisional_contract(self):
        from tests.test_hybrid_api import OPTIONS
        source = self.call("submit", text="Synthetic schema group source.", partition="rational",
                           exclamation=True)["source_id"]
        for i in range(3):
            self.feedback(source, event_id=f"event-{i}", group_id=f"group-{i}")
        fit = self.call("preference_rank", options=OPTIONS, target="actual", partition="rational", domain="daily")
        self.assertEqual((fit["status"], fit["training_sources"], fit["training_groups"]),
                         ("provisional", 1, 3))

    def test_protected_health_schema_matches_locked_and_authenticated_epoch(self):
        from core.access import setup_access
        password = 'synthetic schema password'
        setup_access(self.api.path, password)
        self.api = BrainAPI(self.api.path)
        locked = self.call('health')
        self.assertNotIn('model_epoch', locked)
        self.assertFalse(self.result_validators['health'].is_valid({**locked, 'model_epoch': 0}))
        self.call('unlock', password=password)
        unlocked = self.call('health')
        self.assertEqual(unlocked['model_epoch'], 0)
        missing = copy.deepcopy(unlocked)
        missing.pop('model_epoch')
        self.assertFalse(self.result_validators['health'].is_valid(missing))
        self.call('lock')
        self.assertNotIn('model_epoch', self.call('health'))
        self.assertFalse(self.result_validators['candidate_propose'].is_valid(
            {'candidate_id': 'synthetic', 'source_id': 'synthetic', 'status': 'pending'}))

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
             "error": {"code": "UNKNOWN_ERROR", "message": "not implemented"}}))

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
        self.assertEqual(self.call("candidate_propose", source_id=source, claim="重视公平", evidence="公平")["status"], "accepted")
        candidate_ids = [self.legacy_pending(source) for _ in range(3)]
        self.api = BrainAPI(self.api.path)
        self.assertEqual(len(self.call("candidate_list", status="pending")), 3)
        self.call("candidate_review", candidate_id=candidate_ids[0], accept=True)
        self.call("candidate_review", candidate_id=candidate_ids[1], accept=False)
        rows = self.call("candidate_list")
        self.assertEqual({item["status"] for item in rows}, {"pending", "accepted", "rejected"})
        active = self.call("memory_list")
        self.call("memory_search", query="公平")
        self.call("revoke", source_id=source)
        self.assertEqual(self.call("memory_list"), [])
        self.assertEqual(self.call("memory_search", query="公平"), [])
        self.assertEqual(len(self.call("candidate_list")), 4)
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
                        "params": {"text": "😀我重视公平。\r\n我很开心。我想联系朋友。", "partition": "rational"}}])[0]["result"]["source_id"]
        cases = [("health", {}), ("input_get", {"source_id": source}),
                 ("preview", {"source_id": source}), ("review", {"source_id": source, "agree": True}),
                 ("effects", {}), ("state", {}), ("review_history", {"source_id": source}),
                 ("correction_history", {"source_id": source}), ("input_page", {})]
        wire([{"schema_version": 1, "id": method, "method": method, "params": params}
              for method, params in cases])
        from tests.test_hybrid_api import OPTIONS
        self.api = BrainAPI(path)
        cases = [("memory_search_semantic", {"query": "开心"}),
                 ("choice_feedback_set", {"source_id": source, "event_id": "wire event", "domain": "daily",
                                          "options": OPTIONS, "actual_choice_id": "fair", "endorsed_choice_id": None,
                                          "endorsement_partition": None, "training_consent": False, **self.guards(source)}),
                 ("choice_feedback_get", {"source_id": source}),
                 ("preference_rank", {"options": OPTIONS, "target": "actual", "partition": "rational", "domain": "daily"})]
        responses = wire([{"schema_version": 1, "id": method, "method": method, "params": params}
                          for method, params in cases])
        self.assertEqual(responses[0]["result"]["mode"], "lexical_fallback")
        self.assertEqual(responses[0]["result"]["items"][0]["memory"]["evidence"], "开心")
        self.assertFalse(responses[2]["result"]["records"][0]["model_active"])
        self.assertEqual(responses[3]["result"]["status"], "abstain")


if __name__ == "__main__":
    unittest.main()
