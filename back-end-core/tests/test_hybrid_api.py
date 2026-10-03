"""Hybrid API integration against synthetic temporary databases and fake vectors."""

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core.access import change_password, setup_access
from core.api import BrainAPI, METHODS, PUBLIC_METHODS
from model.engine import BrainModel


OPTIONS = [{"id": "fair", "label": "Reviewed fair option", "impacts": {"value.fairness": 1}},
           {"id": "other", "label": "Reviewed alternative", "impacts": {"value.fairness": -1}}]


class FakeEncoder:
    def __init__(self, callback=None):
        self.calls = []
        self.callback = callback

    def encode(self, texts):
        self.calls.append(list(texts))
        if self.callback:
            callback, self.callback = self.callback, None
            callback()
        return [[0.0, 1.0] if "自由" in text else [1.0, 0.0] for text in texts]


class HybridAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.encoder = FakeEncoder()
        self.api = BrainAPI(self.path, semantic_encoder=self.encoder)

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "hybrid-test", "method": method, "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def submit(self, text="我重视公平。", partition="rational", approved=True):
        source = self.result("submit", text=text, partition=partition, exclamation=approved)["source_id"]
        if approved:
            self.result("candidate_propose", source_id=source, claim=text, evidence=text)
        return source

    def guards(self, source):
        info = self.api.brain.model.reset_info()
        return dict(expected_source_version=self.result("input_get", source_id=source)["source_version"],
                    expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])

    def feedback(self, source, **changes):
        params = dict(source_id=source, event_id="synthetic-event", domain="daily", options=copy.deepcopy(OPTIONS),
                      actual_choice_id="fair", endorsed_choice_id="other", endorsement_partition="rational",
                      training_consent=True, reason="synthetic reviewed reason", **self.guards(source))
        params.update(changes)
        return self.result("choice_feedback_set", **params)

    def rank(self, target="actual", **changes):
        params = dict(options=copy.deepcopy(OPTIONS), target=target, partition="rational", domain="daily")
        params.update(changes)
        return self.result("preference_rank", **params)

    def test_real_api_fake_vectors_preserve_active_row_provenance_and_filters(self):
        fair, free = self.submit(), self.submit("我重视自由。", "emotional")
        self.submit(approved=False)
        result = self.result("memory_search_semantic", query="an unseen paraphrase", min_score=0.1)
        self.assertEqual((result["mode"], result["score_kind"], result["pool_count"]), ("semantic", "cosine", 2))
        self.assertFalse(result["pool_truncated"])
        self.assertEqual(result["items"][0]["memory"]["source_id"], fair)
        self.assertAlmostEqual(result["items"][0]["score"], 1.0)
        row = result["items"][0]["memory"]
        self.assertEqual((row["status"], row["source_status"], row["source_version"]), ("accepted", "agreed", 0))
        self.assertIn("source_ref", row)
        self.assertFalse(result["items"][0]["encoded_text_truncated"])
        other = self.result("memory_search_semantic", query="自由", partition="emotional", limit=1)
        self.assertEqual(other["items"][0]["memory"]["source_id"], free)

    def test_no_encoder_explicit_lexical_fallback_and_no_weight_autoload(self):
        source = self.submit()
        self.api = BrainAPI(self.path)
        with patch("translator.semantic.LocalSentenceEncoder", side_effect=AssertionError("autoload")):
            result = self.result("memory_search_semantic", query="公平")
            self.assertEqual((result["mode"], result["score_kind"]), ("lexical_fallback", "none"))
            self.assertIsNone(result["items"][0]["score"])
            self.assertEqual(result["items"][0]["memory"]["source_id"], source)
            self.assertEqual(self.result("memory_search_semantic", query="paraphrase")["items"], [])
            self.assertFalse(self.result("health")["features"]["semantic_encoder_configured"])
        self.api = BrainAPI(self.path, semantic_model_path=Path(self.temp.name) / "missing-local-model")
        with patch("translator.semantic.LocalSentenceEncoder", side_effect=AssertionError("autoload")):
            self.assertTrue(self.result("health")["features"]["semantic_encoder_configured"])
            self.submit()
        self.assertEqual(self.call("memory_search_semantic", query="公平")["error"],
                         {"code": "MODEL_UNAVAILABLE", "message": "local model unavailable"})
        self.assertEqual(self.encoder.calls, [])

    def test_provider_errors_are_generic_and_never_fall_back(self):
        self.submit()
        class BrokenEncoder:
            def encode(self, texts):
                raise ValueError("synthetic private text /secret/model/path")
        self.api.brain.semantic_encoder = BrokenEncoder()
        response = self.call("memory_search_semantic", query="公平")
        self.assertEqual(response["error"], {"code": "MODEL_UNAVAILABLE", "message": "local model unavailable"})
        self.assertNotIn("secret", json.dumps(response))

    def test_stale_revoke_edit_delete_reopen_while_encoding_rejects_snapshot(self):
        for mutation in ("revoke", "edit", "delete", "reopen"):
            with self.subTest(mutation=mutation):
                source = self.submit()
                def change():
                    if mutation == "delete":
                        self.result("input_delete", source_id=source)
                    elif mutation == "reopen":
                        self.result("correction_reopen", source_id=source, corrections=[], immediate=True, **self.guards(source))
                    else:
                        self.result("revoke", source_id=source)
                        if mutation == "edit":
                            self.result("input_edit", source_id=source, text="我重视自由。", immediate=True)
                self.encoder.callback = change
                response = self.call("memory_search_semantic", query="公平")
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                self.assertNotIn("result", response)
                self.assertFalse(any(item["memory"]["source_id"] == source
                                     for item in self.result("memory_search_semantic", query="公平")["items"]))

    def test_lock_and_config_rotation_mid_inference_block_result_and_discard_brain(self):
        source = self.submit()
        password = "synthetic hybrid access password"
        setup_access(self.path, password)
        for mutation in ("lock", "rotate"):
            with self.subTest(mutation=mutation):
                self.api = BrainAPI(self.path, semantic_encoder=self.encoder)
                self.result("unlock", password=password)
                self.encoder.callback = (lambda: self.result("lock")) if mutation == "lock" else (
                    lambda: change_password(self.path, password, "synthetic new hybrid password"))
                response = self.call("memory_search_semantic", query="公平")
                self.assertEqual(response["error"], {"code": "LOCKED", "message": "access is locked"})
                self.assertIsNone(self.api._brain)
                self.assertNotIn(source, json.dumps(response))

    def test_all_private_methods_are_locked_automatically_without_db_or_model_access(self):
        setup_access(self.path, "synthetic lock sweep password")
        self.api = BrainAPI(self.path, semantic_encoder=self.encoder)
        with patch("core.api.BrainCore", side_effect=AssertionError("private DB access")):
            for method in set(METHODS) - PUBLIC_METHODS:
                with self.subTest(method=method):
                    self.assertEqual(self.call(method)["error"]["code"], "LOCKED")
            health = self.result("health")
            self.assertEqual((health["contract_revision"], len(health["methods"])), (3, 34))
            self.assertNotIn("model_epoch", health)
            self.assertTrue(health["features"]["semantic_encoder_configured"])
            self.result("unlock", password="synthetic lock sweep password")
            self.assertIsNone(self.api._brain)
        self.assertEqual(self.encoder.calls, [])

    def test_preferences_actual_endorsed_and_consent_do_not_write_rule_state(self):
        sources = [self.submit() for _ in range(3)]
        state = self.result("state")
        for source in sources:
            record = self.feedback(source, training_consent=False)
            self.assertFalse(record["model_active"])
        self.assertEqual(self.rank()["status"], "abstain")
        for source in sources:
            self.feedback(source)
        actual, endorsed = self.rank(), self.rank("endorsed")
        self.assertEqual(actual["status"], "provisional")
        self.assertEqual(actual["ranked"][0]["id"], "fair")
        self.assertEqual(endorsed["ranked"][0]["id"], "other")
        self.assertTrue(actual["not_calibrated"])
        self.assertEqual(self.result("state"), state)
        self.assertEqual(self.rank("endorsed", partition="emotional")["reason"], "endorsed_requires_rational_partition")
        for source in sources:
            self.feedback(source, actual_choice_id=None, endorsed_choice_id=None, endorsement_partition=None)
        self.assertEqual(self.rank()["status"], "abstain")
        self.assertEqual(self.rank("endorsed")["status"], "abstain")

    def test_model_reset_preserves_search_excludes_feedback_until_deliberate_save(self):
        sources = [self.submit() for _ in range(3)]
        for source in sources:
            self.feedback(source)
        info = self.api.brain.model.reset_info()
        self.api.brain.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                        expected_revision=info["input_revision"])
        self.assertEqual(self.result("memory_search_semantic", query="公平")["pool_count"], 3)
        self.assertEqual(len(self.result("memory_search", query="公平")), 3)
        self.assertEqual(self.rank()["status"], "abstain")
        records = self.result("choice_feedback_get", source_id=sources[0])["records"]
        self.assertFalse(records[0]["model_active"])
        for source in sources:
            record = self.feedback(source)
            self.assertTrue(record["model_active"])
            self.assertFalse(self.result("input_get", source_id=source)["model_active"])
        self.assertEqual(self.rank()["status"], "provisional")

    def test_f6_standalone_model_purges_feedback_evidence_and_reasons_if_table_exists(self):
        source = self.submit()
        self.feedback(source)
        model = BrainModel(self.path)
        model.revoke(source)
        model.input_edit(source, "我重视自由。", True)
        self.assertEqual(self.result("choice_feedback_get", source_id=source)["records"], [])
        self.feedback(source)
        model.input_delete(source)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM brain_choice_feedback").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sources WHERE id=?", (source,)).fetchone()[0], 0)
        plain = BrainModel(Path(self.temp.name) / "standalone.sqlite3")
        source = plain.submit("我重视公平。", partition="rational")
        plain.input_edit(source, "我重视自由。", True)
        plain.input_delete(source)

    def test_bounded_newest_pool_and_unchanged_legacy_literal_search(self):
        source = self.submit()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("DELETE FROM candidates")
            db.executemany("INSERT INTO candidates(id,source_id,claim,evidence,status,created_at,source_version) "
                           "VALUES (?,?,'synthetic claim','synthetic evidence','accepted',?,0)",
                           [(f"c{i:04d}", source, f"synthetic-{i:04d}") for i in range(1001)])
        result = self.result("memory_search_semantic", query="synthetic")
        self.assertEqual((result["pool_count"], result["pool_truncated"]), (1000, True))
        self.assertNotIn("c0000", {item["memory"]["id"] for item in result["items"]})
        self.assertEqual(result["items"][0]["memory"]["id"], "c0001")
        self.assertEqual(self.result("memory_search", query="synthetic", limit=1)[0]["id"], "c0000")
        self.api = BrainAPI(self.path)
        fallback = self.result("memory_search_semantic", query="synthetic", limit=1)
        self.assertEqual(fallback["items"][0]["memory"]["id"], "c1000")

    def test_semantic_validation_and_feedback_guards_are_strict(self):
        for fields in ({"query": "x" * 2049}, {"query": "\0"}, {"query": "\ud800"},
                       {"query": " "}, {"query": "fair", "min_score": True},
                       {"query": "fair", "min_score": float("nan")}, {"query": "fair", "min_score": float("inf")},
                       {"query": "fair", "min_score": -1.01}, {"query": "fair", "min_score": None},
                       {"query": "fair", "limit": True}, {"query": "fair", "limit": 101},
                       {"query": "fair", "extra": 1}):
            self.assertEqual(self.call("memory_search_semantic", **fields)["error"]["code"], "INVALID_ARGUMENT")
        source = self.submit()
        guard = self.guards(source)
        self.feedback(source)
        stale = self.call("choice_feedback_set", source_id=source, event_id="other", domain="daily", options=OPTIONS,
                          actual_choice_id="fair", endorsed_choice_id=None, endorsement_partition=None,
                          training_consent=True, **guard)
        self.assertEqual(stale["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(len(self.result("choice_feedback_get", source_id=source)["records"]), 1)

    def test_cli_exposes_only_explicit_embedding_model_option(self):
        run = subprocess.run([sys.executable, "-m", "core.api", "--help"], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("--embedding-model", run.stdout)


if __name__ == "__main__":
    unittest.main()
