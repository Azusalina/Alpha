"""Hybrid API integration against synthetic temporary databases and fake vectors."""

import copy
import json
import os
import shutil
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
from model import preferences


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
        return [[0.0, 1.0] if "难过" in text else [1.0, 0.0] for text in texts]


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

    def submit(self, text="我很开心。我想联系朋友。", partition="rational", approved=True):
        source = self.result("submit", text=text, partition=partition, exclamation=approved)["source_id"]
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
        fair, free = self.submit(), self.submit("我很难过。我想联系朋友。", "emotional")
        self.submit(approved=False)
        result = self.result("memory_search_semantic", query="an unseen paraphrase", min_score=0.1)
        self.assertEqual((result["mode"], result["score_kind"], result["pool_count"]), ("semantic", "cosine", 2))
        self.assertFalse(result["pool_truncated"])
        self.assertEqual(result["items"][0]["memory"]["source_id"], fair)
        self.assertAlmostEqual(result["items"][0]["score"], 1.0)
        row = result["items"][0]["memory"]
        self.assertEqual((row["status"], row["source_status"], row["source_version"]), ("accepted", "agreed", 0))
        self.assertIn("source_ref", row)
        self.assertEqual((row["claim"], row["evidence"]), ("textual_emotion: happiness", "开心"))
        self.assertFalse(result["items"][0]["encoded_text_truncated"])
        other = self.result("memory_search_semantic", query="难过", partition="emotional", limit=1)
        self.assertEqual(other["items"][0]["memory"]["source_id"], free)

    def test_no_encoder_explicit_lexical_fallback_and_no_weight_autoload(self):
        source = self.submit()
        self.api = BrainAPI(self.path)
        with patch("translator.semantic.LocalSentenceEncoder", side_effect=AssertionError("autoload")):
            result = self.result("memory_search_semantic", query="开心")
            self.assertEqual((result["mode"], result["score_kind"]), ("lexical_fallback", "none"))
            self.assertIsNone(result["items"][0]["score"])
            self.assertEqual(result["items"][0]["memory"]["source_id"], source)
            self.assertEqual(self.result("memory_search_semantic", query="paraphrase")["items"], [])
            self.assertFalse(self.result("health")["features"]["semantic_encoder_configured"])
        self.api = BrainAPI(self.path, semantic_model_path=Path(self.temp.name) / "missing-local-model")
        with patch("translator.semantic.LocalSentenceEncoder", side_effect=AssertionError("autoload")):
            self.assertTrue(self.result("health")["features"]["semantic_encoder_configured"])
            self.submit()
        self.assertEqual(self.call("memory_search_semantic", query="开心")["error"],
                         {"code": "MODEL_UNAVAILABLE", "message": "local model unavailable"})
        self.assertEqual(self.encoder.calls, [])

    def test_provider_errors_are_generic_and_never_fall_back(self):
        self.submit()
        for error in (ValueError, RuntimeError, OSError):
            with self.subTest(error=error.__name__):
                class BrokenEncoder:
                    def encode(self, texts):
                        raise error("synthetic private text /secret/model/path")
                self.api.brain.semantic_encoder = BrokenEncoder()
                response = self.call("memory_search_semantic", query="开心")
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
                response = self.call("memory_search_semantic", query="开心")
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                self.assertNotIn("result", response)
                self.assertFalse(any(item["memory"]["source_id"] == source
                                     for item in self.result("memory_search_semantic", query="开心")["items"]))

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
                response = self.call("memory_search_semantic", query="开心")
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
        self.assertEqual(self.result("memory_search_semantic", query="开心")["pool_count"], 3)
        self.assertEqual(len(self.result("memory_search", query="开心")), 3)
        self.assertEqual(self.rank()["status"], "abstain")
        records = self.result("choice_feedback_get", source_id=sources[0])["records"]
        self.assertFalse(records[0]["model_active"])
        self.result("review", source_id=sources[0], agree=True)
        self.assertTrue(self.result("input_get", source_id=sources[0])["model_active"])
        self.assertFalse(self.result("choice_feedback_get", source_id=sources[0])["records"][0]["model_active"])
        self.assertEqual(self.rank()["status"], "abstain")
        for source in sources:
            record = self.feedback(source)
            self.assertTrue(record["model_active"])
            self.assertEqual(self.result("input_get", source_id=source)["model_active"], source == sources[0])
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
        for field in ("expected_source_version", "expected_revision", "expected_epoch"):
            wrong = self.guards(source)
            wrong[field] += 1
            response = self.call("choice_feedback_set", source_id=source, event_id="other", domain="daily",
                                 options=OPTIONS, actual_choice_id="fair", endorsed_choice_id=None,
                                 endorsement_partition=None, training_consent=True, **wrong)
            self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(len(self.result("choice_feedback_get", source_id=source)["records"]), 1)

    def test_cli_exposes_only_explicit_embedding_model_option(self):
        run = subprocess.run([sys.executable, "-m", "core.api", "--help"], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("--embedding-model", run.stdout)

    def test_value_only_source_does_not_invent_memory_and_min_score_defaults_to_zero(self):
        self.submit("我重视公平。")
        self.assertEqual(self.result("memory_search_semantic", query="公平")["items"], [])
        self.assertEqual(self.encoder.calls, [])
        self.submit()
        class OppositeEncoder:
            def encode(self, texts):
                return [[1.0, 0.0] if text == "synthetic opposite" else [-1.0, 0.0] for text in texts]
        self.api.brain.semantic_encoder = OppositeEncoder()
        self.assertEqual(self.result("memory_search_semantic", query="synthetic opposite")["items"], [])
        result = self.result("memory_search_semantic", query="synthetic opposite", min_score=-1)
        self.assertEqual(result["items"][0]["score"], -1)

    def database_snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def test_preference_read_fits_again_without_any_database_writes_or_encoder_calls(self):
        sources = [self.submit() for _ in range(3)]
        for source in sources:
            self.feedback(source)
        before = self.database_snapshot()
        with patch("model.preferences.fit_preferences", wraps=preferences.fit_preferences) as fit:
            first, second = self.rank(), self.rank()
            self.assertEqual(fit.call_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "provisional")
        self.assertEqual(len(first["weights"]), 8)
        self.assertEqual(len(self.result("baseline")["parameters"]), 13)
        self.assertEqual(before, self.database_snapshot())
        self.assertEqual(self.encoder.calls, [])

    def test_feedback_requires_independent_consent_and_double_approval(self):
        source = self.submit(approved=False)
        self.assertFalse(self.feedback(source)["model_active"])
        self.assertEqual(self.rank()["training_sources"], 0)
        self.result("review", source_id=source, agree=True)
        self.assertTrue(self.result("choice_feedback_get", source_id=source)["records"][0]["model_active"])
        self.assertFalse(self.feedback(source, training_consent=False)["model_active"])
        self.assertEqual(self.rank()["training_sources"], 0)

    def test_preference_fit_rejects_mutation_during_cpu_work(self):
        fit = preferences.fit_preferences
        for mutation in ("revoke", "edit", "delete", "reopen", "reset", "consent"):
            with self.subTest(mutation=mutation):
                sources = [self.submit() for _ in range(3)]
                for source in sources:
                    self.feedback(source)
                source = sources[0]
                def changed_fit(*args, **kwargs):
                    result = fit(*args, **kwargs)
                    if mutation == "delete":
                        self.result("input_delete", source_id=source)
                    elif mutation == "reopen":
                        self.result("correction_reopen", source_id=source, corrections=[], immediate=True,
                                    **self.guards(source))
                    elif mutation == "reset":
                        info = self.api.brain.model.reset_info()
                        self.api.brain.model.reset_model(confirmation="RESET_MODEL",
                            expected_epoch=info["model_epoch"], expected_revision=info["input_revision"])
                    elif mutation == "consent":
                        self.feedback(source, training_consent=False)
                    else:
                        self.result("revoke", source_id=source)
                        if mutation == "edit":
                            self.result("input_edit", source_id=source, text="我很难过。", immediate=True)
                    return result
                with patch("model.preferences.fit_preferences", side_effect=changed_fit):
                    response = self.call("preference_rank", options=OPTIONS, target="actual",
                                         partition="rational", domain="daily")
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                self.assertNotIn("result", response)
                self.assertNotIn(source, json.dumps(response))

    def test_same_revision_database_replacement_during_either_inference_never_leaks(self):
        fit = preferences.fit_preferences
        for method, mutation in ((method, mutation) for method in ("memory_search_semantic", "preference_rank")
                                 for mutation in ("replace", "overwrite")):
            with self.subTest(method=method, mutation=mutation):
                sources = [self.submit() for _ in range(3)]
                for source in sources:
                    self.feedback(source)
                replacement = Path(self.temp.name) / f"replacement-{method}.sqlite3"
                BrainAPI(replacement)
                with closing(sqlite3.connect(self.path)) as original, closing(sqlite3.connect(replacement)) as db, db:
                    original.backup(db)
                    key = original.execute("SELECT value FROM brain_meta WHERE key='input_cursor_key'").fetchone()[0]
                    db.execute("UPDATE brain_meta SET value=? WHERE key='input_cursor_key'",
                               (("b" if key == "a" * 64 else "a") * 64,))
                def replace():
                    if mutation == "replace":
                        os.replace(replacement, self.path)
                    else:
                        inode = self.path.stat().st_ino
                        shutil.copyfile(replacement, self.path)
                        self.assertEqual(self.path.stat().st_ino, inode)
                if method == "memory_search_semantic":
                    self.encoder.callback = replace
                    response = self.call(method, query="开心")
                else:
                    def replace_during_fit(*args, **kwargs):
                        result = fit(*args, **kwargs)
                        replace()
                        return result
                    with patch("model.preferences.fit_preferences", side_effect=replace_during_fit):
                        response = self.call(method, options=OPTIONS, target="actual", partition="rational", domain="daily")
                self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
                self.assertNotIn("result", response)
                self.assertNotIn(sources[0], json.dumps(response))

    def test_deleted_database_during_encoding_is_not_recreated(self):
        self.submit()
        self.encoder.callback = self.path.unlink
        response = self.call("memory_search_semantic", query="开心")
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertFalse(self.path.exists())
        self.assertNotIn("result", response)

    def test_source_reapproval_after_edit_or_reopen_does_not_restore_old_feedback(self):
        for mutation in ("edit", "reopen"):
            with self.subTest(mutation=mutation):
                source = self.submit()
                self.feedback(source)
                if mutation == "edit":
                    self.result("revoke", source_id=source)
                    self.result("input_edit", source_id=source, text="我很开心。我想联系朋友。", immediate=True)
                    self.result("review", source_id=source, agree=True)
                    self.assertEqual(self.result("choice_feedback_get", source_id=source)["records"], [])
                else:
                    self.result("correction_reopen", source_id=source, corrections=[], immediate=True,
                                **self.guards(source))
                    self.result("review_version", source_id=source, agree=True, **self.guards(source))
                    record = self.result("choice_feedback_get", source_id=source)["records"][0]
                    self.assertFalse(record["model_active"])
                self.assertTrue(self.feedback(source)["model_active"])

    def test_semantic_snapshot_is_rejected_on_model_reset_but_fresh_memory_survives(self):
        source = self.submit()
        def reset():
            info = self.api.brain.model.reset_info()
            self.api.brain.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                            expected_revision=info["input_revision"])
        self.encoder.callback = reset
        response = self.call("memory_search_semantic", query="开心")
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertNotIn("result", response)
        self.assertEqual(self.result("memory_search_semantic", query="开心")["items"][0]["memory"]["source_id"], source)

    def test_lock_during_failed_provider_and_preference_fit_still_rechecks_auth(self):
        for source in [self.submit() for _ in range(3)]:
            self.feedback(source)
        password = "synthetic post inference password"
        setup_access(self.path, password)
        self.api = BrainAPI(self.path, semantic_encoder=self.encoder)
        self.result("unlock", password=password)
        api = self.api
        class LockingBrokenEncoder:
            def encode(self, texts):
                api.access.lock()
                raise ValueError("synthetic private provider details")
        self.api.brain.semantic_encoder = LockingBrokenEncoder()
        response = self.call("memory_search_semantic", query="开心")
        self.assertEqual(response["error"], {"code": "LOCKED", "message": "access is locked"})
        self.assertIsNone(self.api._brain)
        fit = preferences.fit_preferences
        for mutation in ("lock", "rotate"):
            with self.subTest(mutation=mutation):
                self.result("unlock", password=password)
                def lock_during_fit(*args, **kwargs):
                    result = fit(*args, **kwargs)
                    if mutation == "lock":
                        self.api.access.lock()
                    else:
                        change_password(self.path, password, "synthetic rotated post inference password")
                    return result
                with patch("model.preferences.fit_preferences", side_effect=lock_during_fit):
                    response = self.call("preference_rank", options=OPTIONS, target="actual", partition="rational", domain="daily")
                self.assertEqual(response["error"], {"code": "LOCKED", "message": "access is locked"})
                self.assertIsNone(self.api._brain)
                self.assertNotIn("result", response)


if __name__ == "__main__":
    unittest.main()
