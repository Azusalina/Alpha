"""Synthetic source lifecycle tests; every database/file is temporary."""

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model import BrainModel
from model import sources
from model.catalog import BASELINE_PATH
from model.evaluation import read_snapshot, validate_cases


class SourceGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.api = BrainAPI(self.path)
        self.model = self.api.brain.model

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "governance", "method": method, "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def submit(self, text="我重视公平。", **params):
        return self.result("submit", text=text, partition=params.pop("partition", "rational"), **params)["source_id"]

    def database_snapshot(self):
        with self.model.store._connect() as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {table: sorted((tuple(row) for row in db.execute(f'SELECT * FROM "{table}"')), key=repr)
                    for table in tables}

    def assert_purged(self, source):
        with self.model.store._connect() as db:
            for table in (*sources.DEPENDENT_TABLES, "brain_inputs"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {table} WHERE source_id=?", (source,)).fetchone()[0], 0, table)
            self.assertIsNone(db.execute("SELECT id FROM sources WHERE id=?", (source,)).fetchone())
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        for method in ("input_get", "preview", "effects", "review_history", "correction_history", "input_delete"):
            self.assertEqual(self.call(method, source_id=source)["error"]["code"], "NOT_FOUND", method)

    def test_delete_accepts_every_status_and_restores_only_its_partition(self):
        other = self.submit(partition="emotional", exclamation=True)
        other_state = self.model.state("emotional")
        for status in ("pending", "immediate_false", "confirm_false", "revoked", "agreed"):
            with self.subTest(status=status):
                source = self.submit(immediate=status != "immediate_false")
                if status in ("revoked", "agreed"):
                    self.result("review", source_id=source, agree=True)
                if status == "revoked":
                    self.result("revoke", source_id=source)
                if status == "confirm_false":
                    self.result("review", source_id=source, agree=False)
                self.assertEqual(self.result("input_delete", source_id=source), {"source_id": source, "deleted": True})
                self.assert_purged(source)
                self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)
                self.assertEqual(self.model.state("emotional"), other_state)
        self.assertEqual(self.result("input_get", source_id=other)["status"], "agreed")

    def test_active_delete_recomputes_scores_without_rewriting_other_effects(self):
        first = self.submit(exclamation=True)
        second = self.submit(exclamation=True)
        historical = self.result("effects", source_id=second)
        before = self.model.state("rational")["value.fairness"]
        self.assertEqual(before["support"], 2)
        self.result("input_delete", source_id=first)
        self.assertEqual(self.model.state("rational")["value.fairness"], {"value": 0.2, "support": 1, "observed": True})
        self.assertEqual(self.result("effects", source_id=second), historical)
        self.assertEqual(self.result("effects"), historical)
        self.assertGreater(historical[0]["after"], self.model.state("rational")["value.fairness"]["value"])
        self.assertEqual(self.result("terms", partition="rational", min_documents=1)[0]["documents"], 1)
        self.assert_purged(first)

    def test_delete_purges_corrections_all_candidate_states_and_entire_audit(self):
        source = self.submit()
        phrase = "我重视公平"
        self.result("correction_set", source_id=source, expected_revision=0, corrections=[{
            "parameter": "value.fairness", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}])
        self.result("review", source_id=source, agree=True)
        candidates = []
        for decision in (None, True, False):
            candidate = self.result("candidate_propose", source_id=source, claim="公平", evidence="公平")["candidate_id"]
            candidates.append(candidate)
            if decision is not None:
                self.result("candidate_review", candidate_id=candidate, accept=decision)
        self.result("revoke", source_id=source)
        self.result("review", source_id=source, agree=True)
        self.result("input_delete", source_id=source)
        self.assert_purged(source)
        self.assertEqual(self.result("candidate_list"), [])
        self.assertEqual(self.result("memory_list"), [])
        for candidate in candidates:
            self.assertEqual(self.call("candidate_review", candidate_id=candidate, accept=True)["error"]["code"], "NOT_FOUND")

    def test_zero_parameter_fit_deletion_removes_vocabulary_too(self):
        source = self.submit(text="今天记录天气。", exclamation=True)
        self.assertEqual(self.result("effects", source_id=source), [])
        self.assertTrue(self.result("terms", partition="rational", min_documents=1))
        self.result("input_delete", source_id=source)
        self.assertEqual(self.result("terms", partition="rational", min_documents=1), [])
        self.assert_purged(source)

    def test_delete_never_touches_original_files_backups_or_legacy_sources(self):
        original = Path(self.temp.name) / "original.md"
        original.write_text("我重视公平。", encoding="utf-8")
        source = self.submit(source_ref=str(original), exclamation=True)
        legacy = self.model.store.add_source("旧 CLI 原文。")
        backup = Path(self.temp.name) / "backup.sqlite3"
        with self.model.store._connect() as db, closing(sqlite3.connect(backup)) as copied:
            db.backup(copied)
        backup_hash = hashlib.sha256(backup.read_bytes()).digest()
        self.result("input_delete", source_id=source)
        self.assertEqual(original.read_text(encoding="utf-8"), "我重视公平。")
        self.assertEqual(hashlib.sha256(backup.read_bytes()).digest(), backup_hash)
        for method, params in (("input_delete", {}), ("input_edit", {"text": "新版。", "immediate": True})):
            self.assertEqual(self.call(method, source_id=legacy, **params)["error"]["code"], "NOT_FOUND")
        with self.model.store._connect() as db:
            self.assertIsNotNone(db.execute("SELECT id FROM sources WHERE id=?", (legacy,)).fetchone())

    def test_delete_failure_after_deactivation_and_partial_purge_rolls_back_everything(self):
        source = self.submit(exclamation=True)
        before = self.database_snapshot()
        purge = sources.purge_dependents
        def fail_after_purge(db, source_id):
            purge(db, source_id)
            raise sqlite3.IntegrityError("synthetic purge failure")
        with patch("model.sources.purge_dependents", side_effect=fail_after_purge):
            self.assertEqual(self.call("input_delete", source_id=source)["error"]["code"], "STORAGE_ERROR")
        self.assertEqual(self.database_snapshot(), before)
        with patch.object(self.model, "_recompute", side_effect=RuntimeError("synthetic removal failure")):
            self.assertEqual(self.call("input_delete", source_id=source)["error"]["code"], "MODEL_UNAVAILABLE")
        self.assertEqual(self.database_snapshot(), before)

    def test_pending_edit_purges_labels_but_preserves_identity_origin_reference_and_creation(self):
        source = self.submit(source_ref="example.md")
        original = self.result("input_get", source_id=source)
        self.result("correction_set", source_id=source, expected_revision=0, corrections=[{
            "parameter": "value.fairness", "sign": 0, "evidence": "我重视公平", "span": [0, 5]}])
        edited = self.result("input_edit", source_id=source, text="😀我重视自由。\r\n", immediate=True, kind="philosophy")
        self.assertEqual(edited["source_id"], source)
        self.assertEqual(edited["source_ref"], "example.md")
        self.assertEqual(edited["created_at"], original["created_at"])
        self.assertIsNotNone(edited["edited_at"])
        self.assertEqual(edited["status"], "pending")
        self.assertIsNone(edited["confirm"])
        self.assertEqual(edited["char_count"], len("😀我重视自由。\r\n"))
        self.assertNotIn("text", edited)
        self.assertNotIn("ever_fitted", edited)
        self.assertEqual(self.result("review_history", source_id=source)["history"], [])
        corrections = self.result("correction_history", source_id=source)
        self.assertEqual(corrections["revision"], 0)
        self.assertIsNone(corrections["fit_context"])
        self.assertEqual(self.result("input_list")[0], edited)
        self.assertEqual(self.result("input_page")["items"][0], edited)
        with self.model.store._connect() as db:
            self.assertEqual(db.execute("SELECT origin FROM sources WHERE id=?", (source,)).fetchone()[0], "philosophy")

    def test_revoked_edit_clears_frozen_fit_and_never_restores_old_interpretation(self):
        source = self.submit(exclamation=True)
        self.result("revoke", source_id=source)
        other = self.submit(exclamation=True)
        unchanged = self.result("effects", source_id=other)
        before = self.model.state()
        self.result("input_edit", source_id=source, text="我重视自由。", immediate=True)
        self.assertEqual(self.model.state(), before)
        self.assertEqual(self.result("effects", source_id=source), [])
        self.assertEqual(self.result("candidate_list"), [])
        preview = self.result("preview", source_id=source)
        self.assertEqual([item["parameter"] for item in preview["effects"]], ["value.autonomy"])
        fitted = self.result("review", source_id=source, agree=True)
        self.assertFalse(fitted["restored_fit"])
        self.assertEqual([item["parameter"] for item in fitted["effects"]], ["value.autonomy"])
        self.assertEqual(self.result("effects", source_id=other), unchanged)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 1)
        self.assertEqual(self.model.state("rational")["value.autonomy"]["support"], 1)

    def test_edit_reset_gate_and_does_not_auto_train_former_exclamation(self):
        source = self.submit(exclamation=True)
        self.result("review", source_id=source, agree=False)
        edited = self.result("input_edit", source_id=source, text="我重视自由。", immediate=False)
        self.assertEqual((edited["status"], edited["reason"]), ("disagreed", "immediate_false"))
        self.assertFalse(edited["exclamation"])
        self.assertIsNone(edited["confirmed_by"])
        self.assertIsNone(edited["reviewed_at"])
        self.assertEqual(self.call("review", source_id=source, agree=True)["error"]["code"], "INVALID_ARGUMENT")
        self.result("input_edit", source_id=source, text="我重视自由。", immediate=True)
        self.assertEqual(self.model.state("rational")["value.autonomy"]["support"], 0)
        self.assertEqual(self.result("terms", partition="rational", min_documents=1), [])

    def test_edit_chat_identity_is_retained_or_changed_and_cleared_for_nonchat(self):
        text = "朋友: 我重视自由。\r\n我: 😀我重视公平。"
        source = self.submit(text=text, kind="chat", self_speaker="我")
        self.assertEqual(self.result("input_edit", source_id=source, text=text, immediate=True)["self_speaker"], "我")
        preview = self.result("preview", source_id=source)
        self.assertEqual([item["parameter"] for item in preview["effects"]], ["value.fairness"])
        self.result("input_edit", source_id=source, text=text, immediate=True, self_speaker="朋友")
        self.assertEqual([item["parameter"] for item in self.result("preview", source_id=source)["effects"]], ["value.autonomy"])
        self.assertEqual(self.call("input_edit", source_id=source, text=text, immediate=True, self_speaker=None)["error"]["code"], "INVALID_ARGUMENT")
        edited = self.result("input_edit", source_id=source, text="我重视公平。", immediate=True, kind="diary")
        self.assertIsNone(edited["self_speaker"])
        self.assertEqual(self.call("input_edit", source_id=source, text=text, immediate=True, kind="chat")["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.result("input_get", source_id=source)["kind"], "diary")

    def test_invalid_edit_and_agreed_edit_are_nonmutating(self):
        source = self.submit()
        cases = [{"immediate": bad} for bad in (None, 0, 1, "true")]
        cases += [{"kind": bad} for bad in (None, "unknown", [])]
        cases += [{"text": bad} for bad in ("", " \r\n", "x" * 1_000_001, "\ud800")]
        cases += [{"partition": "emotional"}, {"exclamation": True}, {"source_ref": "other.md"}, {"self_speaker": "\ud800"}]
        before = self.database_snapshot()
        for overrides in cases:
            params = {"source_id": source, "text": "新版。", "immediate": True, **overrides}
            self.assertEqual(self.call("input_edit", **params)["error"]["code"], "INVALID_ARGUMENT")
            self.assertEqual(self.database_snapshot(), before)
        self.result("review", source_id=source, agree=True)
        before = self.database_snapshot()
        self.assertEqual(self.call("input_edit", source_id=source, text="新版。", immediate=True)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.database_snapshot(), before)

    def test_all_nul_positions_fail_as_invalid_argument_before_submit_or_edit_writes(self):
        source = self.submit()
        before = self.database_snapshot()
        for text in ("\0内容", "  \0内容", "内容\0", "内\0容", "\0", "\n\0内容"):
            for method, extra in (("submit", {"partition": "rational"}), ("input_edit", {"source_id": source})):
                self.assertEqual(self.call(method, text=text, immediate=True, **extra)["error"]["code"], "INVALID_ARGUMENT")
            with self.assertRaises(ValueError):
                self.model.submit(text, partition="rational")
            with self.assertRaises(ValueError):
                self.model.input_edit(source, text, True)
        self.assertEqual(self.database_snapshot(), before)

    def test_edit_failure_after_purge_rolls_back_raw_fit_metadata_and_clock(self):
        source = self.submit(exclamation=True)
        self.result("revoke", source_id=source)
        before = self.database_snapshot()
        bump = sources.bump_generation
        def fail_after_generation(db):
            bump(db)
            raise sqlite3.IntegrityError("synthetic edit failure")
        with patch("model.sources.bump_generation", side_effect=fail_after_generation):
            self.assertEqual(self.call("input_edit", source_id=source, text="新版。", immediate=True)["error"]["code"], "STORAGE_ERROR")
        self.assertEqual(self.database_snapshot(), before)

    def test_deleted_high_water_and_edit_invalidate_cursors_without_revision_reuse(self):
        keep = self.submit()
        latest = self.submit()
        first = self.result("input_page", limit=1)
        self.result("input_delete", source_id=latest)
        after = self.result("input_page")
        self.assertGreater(after["revision"], first["revision"])
        self.assertEqual(self.call("input_page", limit=1, cursor=first["next_cursor"])["error"]["code"], "STALE_CURSOR")
        self.submit()
        before_edit = self.result("input_page", limit=1)
        self.result("input_edit", source_id=keep, text="新版。", immediate=True)
        self.assertEqual(self.call("input_page", cursor=before_edit["next_cursor"])["error"]["code"], "STALE_CURSOR")
        edited_revision = self.result("input_page")["revision"]
        self.submit()
        self.assertGreater(self.result("input_page")["revision"], edited_revision)
        restarted = BrainAPI(self.path)
        self.assertEqual(restarted.brain.input_page()["revision"], self.result("input_page")["revision"])

    def test_deleting_all_sources_retains_only_global_counters_and_new_ids_keep_increasing(self):
        source = self.submit(exclamation=True)
        effect_id = self.result("effects", source_id=source)[0]["revision"]
        self.result("input_delete", source_id=source)
        empty = self.result("input_page")
        self.assertEqual(empty["total"], 0)
        self.assertGreater(empty["revision"], 0)
        self.assert_purged(source)
        next_source = self.submit(exclamation=True)
        self.assertGreater(self.result("effects", source_id=next_source)[0]["revision"], effect_id)
        self.assertGreater(self.result("input_page")["revision"], empty["revision"])

    def test_deleting_teachers_removes_future_support_but_preserves_other_frozen_fits(self):
        phrase = "我宁愿给每个人同样的机会"
        teachers = []
        for _ in range(2):
            teacher = self.submit(text=phrase + "。")
            self.result("correction_set", source_id=teacher, expected_revision=0, corrections=[{
                "parameter": "value.fairness", "sign": 1, "evidence": phrase, "span": [0, len(phrase)]}])
            self.result("review", source_id=teacher, agree=True)
            teachers.append(teacher)
        pupil = self.submit(text=phrase + "。")
        self.result("review", source_id=pupil, agree=True)
        frozen = self.result("correction_history", source_id=pupil)["fit_context"]
        effect = self.result("effects", source_id=pupil)
        for teacher in teachers:
            self.result("input_delete", source_id=teacher)
            self.assert_purged(teacher)
        fresh = self.submit(text=phrase + "。")
        self.assertEqual(self.result("preview", source_id=fresh)["effects"], [])
        self.assertEqual(self.result("effects", source_id=pupil), effect)
        self.result("revoke", source_id=pupil)
        restored = self.result("review", source_id=pupil, agree=True)
        self.assertTrue(restored["restored_fit"])
        self.assertEqual(restored["interpretation"], frozen)

    def test_edited_training_sources_remain_excluded_from_read_only_held_out_evaluation(self):
        source = self.submit(text="天气记录。", exclamation=True)
        self.result("review", source_id=source, agree=False)
        self.result("input_edit", source_id=source, text="新天气记录。", immediate=True)
        self.assertIsNone(self.result("correction_history", source_id=source)["fit_context"])
        before = hashlib.sha256(self.path.read_bytes()).digest()
        snapshot = read_snapshot(self.path)
        self.assertIn(source, snapshot["training_source_ids"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)
        case = {"id": "held", "domain": "daily", "held_out": True, "source_ids": [source],
                "options": [{"id": "A", "impacts": {}}, {"id": "B", "impacts": {}}],
                "actual_choice": "A", "endorsed_choice": None}
        with self.assertRaises(ValueError):
            validate_cases({"schema_version": 1, "cases": [case]}, snapshot["training_source_ids"])

    def test_concurrent_review_and_delete_do_not_leave_orphans_or_model_contributions(self):
        source = self.submit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.call, method, **params) for method, params in (
                ("review", {"source_id": source, "agree": True}), ("input_delete", {"source_id": source}))]
            reviewed, deleted = [job.result() for job in jobs]
        self.assertTrue(deleted["ok"])
        if not reviewed["ok"]:
            self.assertEqual(reviewed["error"]["code"], "NOT_FOUND")
        self.assert_purged(source)
        self.assertEqual(self.model.state("rational")["value.fairness"]["support"], 0)

    def test_source_migration_is_additive_idempotent_and_preserves_legacy_fits(self):
        source = self.submit(exclamation=True)
        self.result("review", source_id=source, agree=False)
        before = self.result("effects", source_id=source)
        # Recreate the previous schema on a synthetic database, not a real user's file.
        with self.model.store._connect() as db:
            db.execute("ALTER TABLE brain_inputs DROP COLUMN edited_at")
            db.execute("ALTER TABLE brain_inputs DROP COLUMN ever_fitted")
            db.execute("DELETE FROM brain_meta WHERE key IN ('source_schema','input_mutation_generation')")
        restarted = BrainAPI(self.path)
        self.assertEqual(restarted.brain.effects(source_id=source), before)
        self.assertIsNone(restarted.brain.input_get(source)["edited_at"])
        self.assertIn(source, read_snapshot(self.path)["training_source_ids"])
        snapshot = self.database_snapshot()
        BrainModel(self.path)
        self.assertEqual(self.database_snapshot(), snapshot)

    def test_failed_source_migration_rolls_back_additive_columns_and_markers(self):
        with self.model.store._connect() as db:
            db.execute("ALTER TABLE brain_inputs DROP COLUMN edited_at")
            db.execute("ALTER TABLE brain_inputs DROP COLUMN ever_fitted")
            db.execute("DELETE FROM brain_meta WHERE key IN ('source_schema','input_mutation_generation')")
        before = self.database_snapshot()
        migrate = sources.initialize
        def fail_after_migration(db):
            migrate(db)
            raise RuntimeError("synthetic source migration failure")
        with patch("model.sources.initialize", side_effect=fail_after_migration):
            with self.assertRaises(RuntimeError):
                BrainModel(self.path)
        self.assertEqual(self.database_snapshot(), before)
        with self.model.store._connect() as db:
            self.assertNotIn("edited_at", {row["name"] for row in db.execute("PRAGMA table_info(brain_inputs)")})
        BrainModel(self.path)

    def test_serialized_process_edit_delete_and_baseline_preservation(self):
        source = self.submit(immediate=False)
        baseline_hash = hashlib.sha256(BASELINE_PATH.read_bytes()).digest()
        requests = [{"schema_version": 1, "id": str(i), "method": method, "params": params} for i, (method, params) in enumerate((
            ("input_edit", {"source_id": source, "text": "😀我重视自由。\r\n", "immediate": True}),
            ("input_delete", {"source_id": source}), ("input_get", {"source_id": source})))]
        process = subprocess.run([sys.executable, "-E", "-s", "-u", "-m", "core.api", "--db", str(self.path)],
                                 input="".join(json.dumps(request) + "\n" for request in requests),
                                 text=True, capture_output=True, timeout=20, cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(process.returncode, 0)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([response["ok"] for response in responses], [True, True, False])
        self.assertEqual(responses[2]["error"]["code"], "NOT_FOUND")
        self.assertEqual(hashlib.sha256(BASELINE_PATH.read_bytes()).digest(), baseline_hash)
        self.assert_purged(source)
