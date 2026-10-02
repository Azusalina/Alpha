import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from core.store import MemoryStore
from model import BrainModel
from model.catalog import BASELINE_PATH


class DualApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.api = BrainAPI(self.path)
        self.model = self.api.brain.model

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "test", "method": method, "params": params})

    def result(self, method, **params):
        result = self.call(method, **params)
        self.assertTrue(result["ok"], result)
        return result["result"]

    def submit(self, **params):
        return self.result("submit", text="我重视公平。", partition="rational", **params)

    def test_default_and_explicit_immediate_do_not_fit_until_confirmation(self):
        for params in ({}, {"immediate": True, "exclamation": False}):
            source = self.submit(**params)
            self.assertIs(source["immediate"], True)
            self.assertIsNone(source["confirm"])
            self.assertEqual(source["status"], "pending")
            self.assertIsNone(source["confirmed_by"])
            self.assertEqual(source["effects"], [])
            self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
            self.assertEqual(self.model.learned_terms(partition="rational", min_documents=1), [])

    def test_immediate_false_preserves_raw_and_blocks_both_reviews_and_memories(self):
        source = self.submit(immediate=False)
        self.assertEqual(source["status"], "disagreed")
        self.assertEqual(source["reason"], "immediate_false")
        self.assertIsNone(source["confirm"])
        source_id = source["source_id"]
        for agree in (True, False):
            self.assertEqual(self.call("review", source_id=source_id, agree=agree)["error"]["code"],
                             "INVALID_ARGUMENT")
        self.assertFalse(self.call("candidate_propose", source_id=source_id, claim="公平", evidence="公平")["ok"])
        self.assertEqual(self.result("input_get", source_id=source_id)["text"], "我重视公平。")
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
        self.assertEqual(len(self.result("review_history", source_id=source_id)["history"]), 1)

    def test_exclamation_sets_both_true_even_if_immediate_false(self):
        for immediate in (True, False):
            source = self.submit(immediate=immediate, exclamation=True)
            self.assertEqual(source["status"], "agreed")
            for key in ("immediate", "confirm", "exclamation"):
                self.assertIs(source[key], True)
            self.assertEqual(source["confirmed_by"], "exclamation")
            self.assertTrue(source["effects"])
            self.assertGreater(source["observed_terms"], 0)
            history = self.result("review_history", source_id=source["source_id"])["history"]
            self.assertEqual([item["action"] for item in history], ["submit", "review"])
            self.assertEqual(history[-1]["after"]["confirmed_by"], "exclamation")
            self.assertEqual(history[-1]["effect_revisions"], [item["revision"] for item in source["effects"]])
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 2)

    def test_exclamation_is_explicit_not_detected_from_punctuation_or_emphasis(self):
        source = self.result("submit", text="这是我自己的想法！！！我强烈认同公平！", partition="rational")
        self.assertEqual(source["status"], "pending")
        self.assertFalse(source["exclamation"])
        self.assertEqual(self.model.learned_terms(partition="rational", min_documents=1), [])

    def test_non_booleans_rejected_by_api_and_python_without_saving_sources(self):
        for field in ("immediate", "exclamation"):
            for bad in (None, 0, 1, "false", [], {}):
                with self.subTest(field=field, bad=bad):
                    self.assertEqual(self.call("submit", text="我重视公平。", partition="rational",
                                               **{field: bad})["error"]["code"], "INVALID_ARGUMENT")
                    with self.assertRaises(ValueError):
                        self.model.submit("我重视公平。", partition="rational", **{field: bad})
        self.assertEqual(self.result("input_list"), [])

    def test_exclamation_failure_rolls_back_raw_audit_fit_and_vocabulary(self):
        before = self.model.state()
        with patch.object(self.model, "_recompute", side_effect=RuntimeError("test fit failure")):
            self.assertEqual(self.call("submit", text="我重视公平。", partition="rational",
                                       exclamation=True)["error"]["code"], "MODEL_UNAVAILABLE")
        self.assertEqual(self.model.state(), before)
        with self.model.store._connect() as db:
            for table in ("sources", "brain_inputs", "brain_review_history", "brain_contributions",
                          "brain_terms", "brain_fit_context", "brain_effects"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_false_to_true_to_false_restores_zero_and_audits_even_zero_effects(self):
        source = self.submit()["source_id"]
        rejected = self.result("review", source_id=source, agree=False)
        self.assertEqual(rejected["reason"], "confirm_false")
        approved = self.result("review", source_id=source, agree=True)
        self.assertEqual(approved["confirmed_by"], "manual")
        self.assertFalse(approved["restored_fit"])
        denied = self.result("review", source_id=source, agree=False)
        self.assertEqual(denied["status"], "disagreed")
        self.assertEqual(denied["effects"][0]["action"], "revoke")
        self.assertEqual(denied["effects"][0]["support_after"], 0)
        self.assertEqual(self.model.learned_terms(partition="rational", min_documents=1), [])
        self.assertFalse(self.model.state("rational")["value.fairness"]["observed"])
        plain = self.result("submit", text="今天记录一件事情。", partition="emotional")["source_id"]
        self.assertEqual(self.result("review", source_id=plain, agree=True)["effects"], [])
        self.result("review", source_id=plain, agree=False)
        history = self.result("review_history", source_id=plain)["history"]
        self.assertEqual(len(history), 3)
        self.assertTrue(all(not item["effect_revisions"] for item in history))

    def test_repeated_same_decision_is_noop_and_cycles_never_duplicate_support(self):
        source = self.submit()["source_id"]
        for _ in range(3):
            self.result("review", source_id=source, agree=True)
            before_history = self.result("review_history", source_id=source)
            self.assertEqual(self.result("review", source_id=source, agree=True)["effects"], [])
            self.assertEqual(self.result("review_history", source_id=source), before_history)
            self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 1)
            terms = self.model.learned_terms(partition="rational", min_documents=1)
            self.assertTrue(all(item["documents"] == 1 for item in terms))
            self.result("review", source_id=source, agree=False)
            before_history = self.result("review_history", source_id=source)
            self.result("review", source_id=source, agree=False)
            self.assertEqual(self.result("review_history", source_id=source), before_history)
        self.assertEqual(len(self.model.effects(source_id=source)), 6)

    def test_revoked_can_be_reapproved_using_original_fit_and_no_memory_republication(self):
        source = self.submit(exclamation=True)["source_id"]
        candidate = self.result("candidate_propose", source_id=source, claim="重视公平", evidence="公平")["candidate_id"]
        memories = self.result("memory_list")
        self.assertEqual([row["id"] for row in memories], [candidate])
        self.assertEqual(memories[0]["status"], "accepted")
        self.assertEqual(memories[0]["source_version"], 0)
        revoked = self.result("revoke", source_id=source)
        self.assertFalse(revoked["confirm"])
        self.assertEqual(revoked["reason"], "user_revoked")
        self.assertEqual(self.result("memory_list"), [])
        self.assertEqual(self.result("preview", source_id=source)["status"], "revoked")
        with patch.object(self.model, "_observations", side_effect=AssertionError("must restore frozen evidence")):
            restored = self.result("review", source_id=source, agree=True)
        self.assertTrue(restored["restored_fit"])
        self.assertEqual(restored["confirmed_by"], "manual")
        self.assertTrue(restored["exclamation"])  # Historical submit flag, not perpetual consent.
        self.assertEqual(len(self.result("memory_list")), 1)
        self.assertEqual(self.result("memory_list")[0]["id"], candidate)
        self.assertEqual(self.result("memory_list"), memories)

    def test_all_inactive_previews_are_read_only_and_agreed_is_rejected(self):
        for immediate in (True, False):
            source = self.submit(immediate=immediate)["source_id"]
            snapshot = self.result("review_history", source_id=source)
            state = self.model.state()
            preview = self.result("preview", source_id=source)
            self.assertTrue(preview["hypothetical"])
            self.assertTrue(preview["effects"])
            self.assertEqual(self.model.state(), state)
            self.assertEqual(self.result("review_history", source_id=source), snapshot)
        source = self.submit(exclamation=True)["source_id"]
        self.assertEqual(self.call("preview", source_id=source)["error"]["code"], "INVALID_ARGUMENT")
        self.result("review", source_id=source, agree=False)
        preview = self.result("preview", source_id=source)
        approved = self.result("review", source_id=source, agree=True)
        for projected, actual in zip(preview["effects"], approved["effects"]):
            for field in ("parameter", "before", "after", "support_before", "support_after", "span", "rule_id"):
                self.assertEqual(projected[field], actual[field])

    def test_translator_downgrade_and_reactivation_follow_active_document_counts(self):
        first = self.submit(exclamation=True)["source_id"]
        second = self.submit(exclamation=True)["source_id"]
        terms = self.model.learned_terms(partition="rational")
        self.assertTrue(terms)
        downgrade = self.result("review", source_id=first, agree=False)["translator_effects"]
        self.assertEqual({item["term"] for item in downgrade}, {item["term"] for item in terms})
        self.assertTrue(all(item["documents_before"] == 2 and item["documents_after"] == 1 for item in downgrade))
        self.assertEqual(self.model.learned_terms(partition="rational"), [])
        self.assertTrue(self.result("review", source_id=first, agree=True)["translator_effects"])
        self.result("revoke", source_id=second)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 1)

    def test_partitions_baseline_and_boolean_metadata_survive_restart(self):
        digest = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
        for partition in ("rational", "emotional", "crazy"):
            self.result("submit", text="我重视公平。", partition=partition, immediate=False, exclamation=True)
        restarted = BrainAPI(self.path)
        self.assertEqual(restarted.brain.state(), self.api.brain.state())
        self.assertEqual(hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest(), digest)
        for row in restarted.brain.input_list():
            self.assertIs(row["immediate"], True)
            self.assertIs(row["confirm"], True)
            self.assertIs(row["exclamation"], True)
            self.assertEqual(self.model.state(row["partition"])["value.fairness"]["support"], 1)

    def test_concurrent_confirmation_is_serialized_without_double_fitting(self):
        source = self.submit()["source_id"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.model.review(source, agree=True), range(4)))
        self.assertEqual(sum(bool(result["effects"]) for result in results), 1)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 1)
        self.assertEqual(len(self.result("review_history", source_id=source)["history"]), 2)

    def test_database_rejects_inconsistent_active_training_gate(self):
        source = self.submit(immediate=False)["source_id"]
        with self.assertRaises(sqlite3.IntegrityError), self.model.store._connect() as db:
            db.execute("UPDATE brain_inputs SET status='agreed', confirm=1 WHERE source_id=?", (source,))
        self.assertEqual(self.result("input_get", source_id=source)["status"], "disagreed")

    def test_reactivation_does_not_reinterpret_after_teaching_sources_are_revoked(self):
        phrase = "我宁愿给每个人同样的机会"
        teachers = []
        for _ in range(2):
            teacher = self.result("submit", text=phrase + "。", partition="rational")["source_id"]
            self.result("correction_set", source_id=teacher, expected_revision=0, corrections=[{
                "parameter": "value.fairness", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}])
            self.result("review", source_id=teacher, agree=True)
            teachers.append(teacher)
        source = self.result("submit", text=phrase + "。", partition="rational")["source_id"]
        initial = self.result("review", source_id=source, agree=True)
        self.assertEqual(initial["effects"][0]["rule_id"], "learned_exact_correction")
        frozen = self.model.correction_history(source)["fit_context"]
        for teacher in teachers:
            self.result("revoke", source_id=teacher)
        self.result("review", source_id=source, agree=False)
        fresh = self.result("submit", text=phrase + "。", partition="rational")["source_id"]
        self.assertEqual(self.result("preview", source_id=fresh)["effects"], [])
        restored = self.result("review", source_id=source, agree=True)
        self.assertEqual(restored["interpretation"], frozen)
        self.assertEqual(restored["effects"][0]["rule_id"], "learned_exact_correction")
        self.assertEqual(self.result("preview", source_id=fresh)["effects"], [])

    def test_failed_rereview_removal_preserves_original_state_and_audit(self):
        source = self.submit(exclamation=True)["source_id"]
        state = self.model.state()
        history = self.result("review_history", source_id=source)
        with patch.object(self.model, "_recompute", side_effect=RuntimeError("test removal failure")):
            self.assertFalse(self.call("review", source_id=source, agree=False)["ok"])
        self.assertEqual(self.model.state(), state)
        self.assertEqual(self.result("review_history", source_id=source), history)
        self.assertEqual(self.result("input_get", source_id=source)["status"], "agreed")

    def test_real_jsonlines_and_cli_deliver_exclamation_actual_effects(self):
        root = Path(__file__).resolve().parents[1]
        requests = [
            {"schema_version": 1, "id": "health", "method": "health", "params": {}},
            {"schema_version": 1, "id": "submit", "method": "submit", "params": {
                "text": "我重视公平。", "partition": "rational", "immediate": False, "exclamation": True}}]
        process = subprocess.run([sys.executable, "-m", "core.api", "--db", str(self.path)],
                                 input="".join(json.dumps(req) + "\n" for req in requests), text=True,
                                 capture_output=True, timeout=20, cwd=root)
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertTrue(responses[0]["result"]["features"]["two_judgements"])
        self.assertEqual(responses[1]["result"]["confirmed_by"], "exclamation")
        self.assertTrue(responses[1]["result"]["effects"])
        process = subprocess.run([sys.executable, "-m", "model", "--db", str(self.path), "submit",
                                  "--text", "我重视公平。", "--partition", "emotional", "--no-immediate"],
                                 text=True, capture_output=True, timeout=20, cwd=root)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout)["reason"], "immediate_false")


class ApprovalMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy.sqlite3"
        self.store = MemoryStore(self.path)
        self.store.initialize()
        with self.store._connect() as db:
            db.executescript("""
                CREATE TABLE brain_inputs (
                    source_id TEXT PRIMARY KEY REFERENCES sources(id), partition TEXT NOT NULL,
                    kind TEXT NOT NULL, self_speaker TEXT, status TEXT NOT NULL, reviewed_at TEXT);
                CREATE TABLE brain_state (partition TEXT, parameter TEXT, value REAL, support INTEGER,
                    net INTEGER, PRIMARY KEY(partition, parameter));
                CREATE TABLE brain_contributions (source_id TEXT, parameter TEXT, sign INTEGER,
                    evidence TEXT, start_offset INTEGER, end_offset INTEGER, rule_id TEXT,
                    PRIMARY KEY(source_id, parameter));
                CREATE TABLE brain_terms (source_id TEXT, term TEXT, occurrences INTEGER,
                    PRIMARY KEY(source_id, term));
                CREATE TABLE brain_fit_context (source_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)
            for status in ("pending", "agreed", "disagreed", "revoked"):
                db.execute("INSERT INTO sources VALUES (?, ?, 'diary', '旧日记.md', 'old-time')",
                           (status, "我重视公平。"))
                db.execute("INSERT INTO brain_inputs VALUES (?, 'rational', 'diary', NULL, ?, ?)",
                           (status, status, None if status == "pending" else "old-review"))
                if status in ("agreed", "revoked"):
                    db.execute("INSERT INTO brain_contributions VALUES (?, 'value.fairness', 1, '我重视公平', 0, 5, 'old-rule')",
                               (status,))
                    db.execute("INSERT INTO brain_terms VALUES (?, '公平', 1)", (status,))
            db.execute("INSERT INTO brain_state VALUES ('rational', 'value.fairness', ?, 1, 1)", (1 / 5,))
            db.execute("INSERT INTO brain_fit_context VALUES ('revoked', ?)",
                       (json.dumps({"correction_revision": 0, "corrections": [], "learned_rules": []}),))
            for status in ("pending", "accepted", "rejected"):
                db.execute("INSERT INTO candidates(id,source_id,claim,evidence,status,created_at,resolved_at) "
                           "VALUES (?,'agreed','旧公平','公平',?,'old-time',?)",
                           ("legacy-" + status, status, None if status == "pending" else "old-resolution"))

    def snapshot(self, table):
        with self.store._connect() as db:
            return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]

    def test_migration_maps_all_statuses_without_refitting_or_rewriting_sources(self):
        snapshots = {table: self.snapshot(table) for table in
                     ("sources", "brain_contributions", "brain_terms", "brain_fit_context", "candidates")}
        api = BrainAPI(self.path)
        expected = {"pending": (None, None), "agreed": (True, None),
                    "disagreed": (False, "confirm_false"), "revoked": (False, "user_revoked")}
        for source, (confirm, reason) in expected.items():
            row = api.brain.input_get(source)
            self.assertTrue(row["immediate"])
            self.assertIs(row["confirm"], confirm)
            self.assertEqual(row["reason"], reason)
            self.assertEqual(row["confirmed_by"], None if source == "pending" else "legacy")
            self.assertEqual(row["created_at"], "old-time")
            self.assertEqual(row["source_version"], 0)
            self.assertEqual(api.brain.review_history(source)["history"][0]["action"], "migrate")
        for table, before in snapshots.items():
            expected_rows = before if table == "sources" else [dict(row, source_version=0) for row in before]
            if table == "brain_fit_context":
                # Early approved fits without context receive an explicit legacy marker.
                expected_rows.append({"source_id": "agreed", "source_version": 0,
                                      "payload": json.dumps({"correction_revision": 0, "corrections": [],
                                                             "learned_rules": [], "legacy_context_unavailable": True})})
            self.assertEqual(self.snapshot(table), expected_rows)
        self.assertEqual([row["id"] for row in api.brain.store.list_memories()], ["legacy-accepted"])
        self.assertEqual(api.brain.state("rational")["value.fairness"],
                         {"value": 1 / 5, "support": 1, "observed": True})
        histories = self.snapshot("brain_review_history")
        candidates = self.snapshot("candidates")
        BrainModel(self.path)
        self.assertEqual(self.snapshot("brain_review_history"), histories)
        self.assertEqual(self.snapshot("candidates"), candidates)

    def test_early_legacy_fit_restores_saved_contributions_without_context_or_reextraction(self):
        model = BrainModel(self.path)
        self.assertTrue(model.correction_history("agreed")["fit_context"]["legacy_context_unavailable"])
        model.revoke("agreed")
        with patch.object(model, "_observations", side_effect=AssertionError("do not re-extract legacy fit")):
            restored = model.review("agreed", agree=True)
        self.assertTrue(restored["restored_fit"])
        self.assertEqual(restored["effects"][0]["rule_id"], "old-rule")
        self.assertEqual(model.state("rational")["value.fairness"]["support"], 1)

    def test_failed_migration_rolls_back_columns_meta_and_audit(self):
        with patch("model.approvals.record", side_effect=RuntimeError("test migration failure")):
            with self.assertRaises(RuntimeError):
                BrainModel(self.path)
        with self.store._connect() as db:
            columns = {row["name"] for row in db.execute("PRAGMA table_info(brain_inputs)")}
            self.assertNotIn("immediate", columns)
            self.assertIsNone(db.execute("SELECT * FROM sqlite_master WHERE name='brain_review_history'").fetchone())
            self.assertIsNone(db.execute("SELECT * FROM brain_meta WHERE key='approval_schema'").fetchone())
        self.assertEqual(BrainModel(self.path).state("rational")["value.fairness"]["support"], 1)


if __name__ == "__main__":
    unittest.main()
