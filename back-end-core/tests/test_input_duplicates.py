"""Exact-text advisory hints using only synthetic temporary SQLite databases."""

import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from core import pagination
from core.access import change_password, setup_access
from core.api import BrainAPI, METHODS, PUBLIC_METHODS, serve
from core.brain import BrainCore
from model import preferences
from translator.pipeline import MAX_CHARS


RESULT_FIELDS = {"source_id", "source_version", "match_kind", "items", "total", "truncated",
                 "input_revision", "model_epoch"}
ITEM_FIELDS = {"source_id", "partition", "kind", "status", "source_version", "model_epoch",
               "model_active", "created_at"}
OPTIONS = [{"id": "fair", "label": "synthetic private label", "impacts": {"value.fairness": 1}},
           {"id": "other", "impacts": {"value.fairness": -1}}]


class InputDuplicateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.api = BrainAPI(self.path)
        self.brain = self.api.brain

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "duplicate-test", "method": method, "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def submit(self, text="我重视公平。", **params):
        # Application submit preserves raw text; legacy add_source strips it.
        return self.brain.submit(text, partition=params.pop("partition", "rational"), **params)["source_id"]

    def duplicates(self, source, **params):
        result = self.result("input_duplicates", source_id=source, **params)
        self.assertEqual(set(result), RESULT_FIELDS)
        self.assertEqual(result["source_id"], source)
        self.assertEqual(result["match_kind"], "exact_text")
        self.assertIs(result["truncated"], result["total"] > len(result["items"]))
        self.assertNotIn(source, [item["source_id"] for item in result["items"]])
        for item in result["items"]:
            self.assertEqual(set(item), ITEM_FIELDS)
            self.assertIs(item["model_active"], item["status"] == "agreed" and
                          item["model_epoch"] == result["model_epoch"])
        return result

    def dump(self):
        with self.brain.store._connect() as db:
            return tuple(db.iterdump())

    def reset_model(self, brain=None):
        model = (brain or self.brain).model
        info = model.reset_info()
        return model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                                 expected_revision=info["input_revision"])

    def feedback(self, source, **changes):
        info = self.brain.model.reset_info()
        fields = dict(source_id=source, event_id="synthetic-event", domain="daily", options=OPTIONS,
                      actual_choice_id="fair", endorsed_choice_id=None, endorsement_partition=None,
                      training_consent=False, reason="synthetic private reason", group_id=None,
                      group_reviewed=False, expected_source_version=self.brain.input_get(source)["source_version"],
                      expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])
        fields.update(changes)
        return self.result("choice_feedback_set", **fields)

    def guards(self, source, brain=None):
        brain = brain or self.brain
        info = brain.model.reset_info()
        return dict(expected_source_version=brain.input_get(source)["source_version"],
                    expected_revision=info["input_revision"], expected_epoch=info["model_epoch"])

    def test_counts_bounds_default_and_stable_newest_then_id_order(self):
        target = self.submit()
        sources = []
        for index in range(105):
            with patch("model.engine._now", return_value=f"2026-10-01T00:00:{index % 3:02d}+00:00"):
                source = self.submit()
            sources.append((f"2026-10-01T00:00:{index % 3:02d}+00:00", source))
        self.submit("A different current body.")
        expected = [source for _, source in sorted(sources, reverse=True)]
        for limit in (1, 2, 20, 99, 100):
            with self.subTest(limit=limit):
                result = self.duplicates(target, limit=limit)
                self.assertEqual(result["total"], 105)
                self.assertEqual([item["source_id"] for item in result["items"]], expected[:limit])
                self.assertTrue(result["truncated"])
                self.assertEqual(self.duplicates(target, limit=limit), result)
        self.assertEqual(len(self.duplicates(target)["items"]), 20)

    def test_self_exclusion_zero_one_and_exact_limit_truncation(self):
        target = self.submit()
        result = self.duplicates(target)
        self.assertEqual((result["total"], result["items"], result["truncated"]), (0, [], False))
        first = self.submit()
        result = self.duplicates(target, limit=1)
        self.assertEqual((result["total"], result["truncated"]), (1, False))
        self.assertEqual(result["items"][0]["source_id"], first)
        self.submit()
        self.assertTrue(self.duplicates(target, limit=1)["truncated"])
        self.assertFalse(self.duplicates(target, limit=2)["truncated"])

    def test_ordinary_operations_never_invoke_hint_or_block_duplicate_submission(self):
        with patch.object(BrainCore, "input_duplicates", side_effect=AssertionError("automatic hint invocation")):
            target = self.submit()
            match = self.submit()
            self.result("input_get", source_id=target)
            self.result("input_list")
            self.result("input_page")
            self.result("preview", source_id=target)
            self.result("review", source_id=target, agree=True)
            self.result("review", source_id=match, agree=True)
            self.result("revoke", source_id=match)
            self.result("input_edit", source_id=match, text="我重视公平。", immediate=True)
            self.result("review", source_id=match, agree=True)
        self.assertEqual(self.duplicates(target)["total"], 1)
        self.assertEqual(self.result("state", partition="rational")["value.fairness"]["support"], 2)

    def test_binary_equality_never_normalizes_case_whitespace_crlf_or_unicode(self):
        text = "  Café 😀Ａ Case\r\n尾\t "
        target = self.submit(text)
        exact = self.submit(text)
        variants = (text.strip(), text.lower(), text.upper(), text.replace("\r\n", "\n"),
                    text.replace("\r\n", "\r"), text.replace("é", "e\u0301"),
                    text.replace("Ａ", "A"), text.replace(" ", "\u00a0"),
                    text.replace("\t", " "), text + "\n", text.replace("😀", "😀\ufe0f"),
                    text.replace("尾", "尾\u200b"))
        for variant in variants:
            self.submit(variant)
        # Verify raw preservation independently of the match implementation.
        self.assertEqual(self.brain.input_get(target)["text"], text)
        result = self.duplicates(target)
        self.assertEqual(result["total"], 1)
        self.assertEqual([item["source_id"] for item in result["items"]], [exact])
        decomposed = self.submit("e\u0301")
        decomposed_match = self.submit("e\u0301")
        self.submit("é")
        self.assertEqual(self.duplicates(decomposed)["items"][0]["source_id"], decomposed_match)

    def test_historical_application_text_with_embedded_nul_compares_its_entire_body(self):
        target, match, different = self.submit(), self.submit(), self.submit()
        # New submit rejects NUL; simulate existing application text without migrating it.
        with self.brain.store._connect() as db:
            db.executemany("UPDATE sources SET body=? WHERE id=?", [
                ("historical\0same suffix", target), ("historical\0same suffix", match),
                ("historical\0different suffix", different)])
        result = self.duplicates(target)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_id"], match)

    def test_all_partitions_kinds_statuses_and_old_epochs_are_included(self):
        target = self.submit()
        expected = {}
        for partition in ("rational", "emotional", "crazy"):
            for kind in ("diary", "chat", "philosophy"):
                for status in ("pending", "agreed", "disagreed", "revoked"):
                    source = self.submit(partition=partition, kind=kind,
                                         **({"self_speaker": "synthetic speaker"} if kind == "chat" else {}))
                    if status != "pending":
                        self.result("review", source_id=source, agree=status != "disagreed")
                    if status == "revoked":
                        self.result("revoke", source_id=source)
                    expected[source] = (partition, kind, status)
        current_result = self.duplicates(target, limit=100)
        self.assertEqual(current_result["total"], 36)
        for item in current_result["items"]:
            self.assertIs(item["model_active"], item["status"] == "agreed")
        self.reset_model()
        current = self.submit(partition="crazy", exclamation=True)
        expected[current] = ("crazy", "diary", "agreed")
        result = self.duplicates(target, limit=100)
        self.assertEqual(result["model_epoch"], 1)
        self.assertEqual(result["total"], 37)
        self.assertFalse(result["truncated"])
        for item in result["items"]:
            self.assertEqual((item["partition"], item["kind"], item["status"]), expected[item["source_id"]])
            self.assertEqual(item["model_epoch"], int(item["source_id"] == current))
            self.assertIs(item["model_active"], item["source_id"] == current)

    def test_legacy_store_only_target_and_candidates_are_excluded(self):
        target = self.submit()
        match = self.submit(exclamation=True)
        legacy = self.brain.store.add_source("我重视公平。")
        legacy_candidate = self.brain.store.propose(legacy, "公平", "公平")
        self.brain.store.resolve(legacy_candidate, accept=True)
        app_candidate = self.result("candidate_propose", source_id=match, claim="公平", evidence="公平")
        self.assertTrue(app_candidate)
        for missing in (legacy, "nonexistent", "' OR 1=1 --", target + " "):
            self.assertEqual(self.call("input_duplicates", source_id=missing)["error"]["code"], "NOT_FOUND")
            with self.assertRaises(KeyError):
                self.brain.input_duplicates(missing)
        result = self.duplicates(target)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_id"], match)

    def test_current_edits_versions_deletes_revokes_and_resets(self):
        target = self.submit()
        match = self.submit(exclamation=True)
        result = self.duplicates(target)
        self.assertIs(result["items"][0]["model_active"], True)
        self.result("revoke", source_id=match)
        revoked = self.duplicates(target)
        self.assertEqual(revoked["total"], 1)
        self.assertEqual(revoked["items"][0]["status"], "revoked")
        self.assertFalse(revoked["items"][0]["model_active"])
        self.result("input_edit", source_id=match, text="我重视自由。", immediate=True)
        self.assertEqual(self.duplicates(target)["total"], 0)
        self.result("input_edit", source_id=target, text="我重视自由。", immediate=True)
        edited = self.duplicates(target)
        self.assertEqual(edited["source_version"], 0)  # Raw editing purges old versions by existing policy.
        self.assertEqual(edited["items"][0]["source_version"], 0)
        self.result("review", source_id=match, agree=True)
        self.assertTrue(self.duplicates(target)["items"][0]["model_active"])
        reset_result = self.reset_model()
        after_reset = self.duplicates(target)
        self.assertEqual(after_reset["total"], 1)
        self.assertEqual(after_reset["model_epoch"], reset_result["model_epoch"])
        self.assertFalse(after_reset["items"][0]["model_active"])
        self.result("review", source_id=match, agree=True)
        self.assertTrue(self.duplicates(target)["items"][0]["model_active"])
        self.result("input_delete", source_id=match)
        self.assertEqual(self.duplicates(target)["total"], 0)
        self.result("input_delete", source_id=target)
        self.assertEqual(self.call("input_duplicates", source_id=target)["error"]["code"], "NOT_FOUND")
        for old, new in ((result, revoked), (revoked, edited), (edited, after_reset)):
            self.assertGreater(new["input_revision"], old["input_revision"])

    def test_reopened_current_source_versions_match_once_without_searching_archives(self):
        target = self.submit(exclamation=True)
        match = self.submit(exclamation=True)
        for source in (target, match):
            self.result("correction_reopen", source_id=source, corrections=[], immediate=True, **self.guards(source))
            self.result("review_version", source_id=source, agree=True, **self.guards(source))
        result = self.duplicates(target)
        self.assertEqual(result["source_version"], 1)
        self.assertEqual(result["items"][0]["source_version"], 1)
        self.assertEqual(result["total"], 1)
        self.result("correction_reopen", source_id=match, corrections=[], immediate=False, **self.guards(match))
        self.assertEqual(self.duplicates(target)["items"][0]["source_version"], 2)
        self.assertEqual(len(self.result("correction_history", source_id=match)["version_history"]), 2)
        self.result("input_edit", source_id=match, text="Current different raw body.", immediate=True)
        self.assertEqual(self.duplicates(target)["total"], 0)

    def test_invalid_core_api_arguments_and_unknown_params_do_not_write(self):
        target = self.submit()
        before = self.dump()
        for value in (None, True, 1, 1.0, [], {}, "", " \r\n", "id\0tail", "\ud800", "\udfff"):
            with self.subTest(source_id=repr(value)):
                with self.assertRaises(ValueError):
                    self.brain.input_duplicates(value)
                self.assertEqual(self.call("input_duplicates", source_id=value)["error"]["code"], "INVALID_ARGUMENT")
        for limit in (None, True, False, -1, 0, 101, 1.0, "20", [], {}):
            with self.subTest(limit=repr(limit)):
                with self.assertRaises(ValueError):
                    self.brain.input_duplicates(target, limit=limit)
                self.assertEqual(self.call("input_duplicates", source_id=target, limit=limit)["error"]["code"],
                                 "INVALID_ARGUMENT")
        self.assertEqual(self.call("input_duplicates")["error"]["code"], "INVALID_ARGUMENT")
        with self.assertRaises(TypeError):
            self.brain.input_duplicates()
        with self.assertRaises(TypeError):
            self.brain.input_duplicates(target, 1)
        for field in ("partition", "status", "cursor", "db", "text", "params", "group_id", "group_reviewed",
                      "training_consent", "merge", "agree"):
            self.assertEqual(self.call("input_duplicates", source_id=target, **{field: None})["error"]["code"],
                             "INVALID_ARGUMENT")
        self.assertEqual(self.dump(), before)

    def test_advisory_has_no_inferred_source_review_group_or_feedback_consent(self):
        target = self.submit()
        approved = self.submit(exclamation=True)
        pending = self.submit()
        self.feedback(approved)
        self.feedback(pending, training_consent=True, group_id="explicit group", group_reviewed=True)
        before = self.dump()
        feedback = {source: self.result("choice_feedback_get", source_id=source) for source in (approved, pending)}
        result = self.duplicates(target)
        items = {item["source_id"]: item for item in result["items"]}
        self.assertTrue(items[approved]["model_active"])
        self.assertFalse(feedback[approved]["records"][0]["model_active"])
        self.assertFalse(items[pending]["model_active"])
        self.assertFalse(feedback[pending]["records"][0]["model_active"])
        self.assertEqual(self.result("choice_feedback_get", source_id=target)["records"], [])
        self.assertEqual(self.brain.input_get(target)["status"], "pending")
        for source in feedback:
            self.assertEqual(self.result("choice_feedback_get", source_id=source), feedback[source])
        self.assertEqual(self.dump(), before)

    def test_read_only_dump_tokens_model_terms_history_feedback_and_privacy(self):
        text = "synthetic-private-speaker: 我重视公平。 synthetic raw body secret 😀\r\n"
        target = self.submit(text, source_ref="synthetic-private-file.md")
        match = self.submit(text, kind="chat", self_speaker="synthetic-private-speaker")
        self.result("correction_set", source_id=match, corrections=[], expected_revision=0)
        self.result("review", source_id=match, agree=True)
        self.feedback(match, training_consent=True, group_id="synthetic-reviewed-group", group_reviewed=True)
        self.result("candidate_propose", source_id=match, claim="公平", evidence="公平")
        before = self.dump()
        state = self.result("state")
        terms = self.result("terms", partition="rational", min_documents=1)
        history = self.result("review_history", source_id=match)
        corrections = self.result("correction_history", source_id=match)
        feedback = self.result("choice_feedback_get", source_id=match)
        info = self.brain.model.reset_info()
        table_reads, selected_columns, statements = set(), [], []
        original = self.brain.store._connect

        @contextmanager
        def audited_connect():
            with original() as db:
                db.execute("PRAGMA query_only=ON")
                def row_factory(cursor, row):
                    selected_columns.append({column[0] for column in cursor.description})
                    return sqlite3.Row(cursor, row)
                db.row_factory = row_factory
                def authorize(action, table, column, _database, _trigger):
                    if action == sqlite3.SQLITE_READ:
                        table_reads.add(table)
                    return sqlite3.SQLITE_OK if action in {
                        sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
                        sqlite3.SQLITE_TRANSACTION} else sqlite3.SQLITE_DENY
                db.set_authorizer(authorize)
                db.set_trace_callback(statements.append)
                yield db

        with patch.object(self.brain.store, "_connect", audited_connect), \
                patch.object(pagination, "initialize", side_effect=AssertionError("cursor initialization")), \
                patch.object(pagination, "key", side_effect=AssertionError("cursor access")), \
                patch.object(preferences, "initialize", side_effect=AssertionError("feedback initialization")), \
                patch.object(self.brain, "input_get", side_effect=AssertionError("raw body read")), \
                patch.object(self.brain, "_input_summaries", side_effect=AssertionError("summary read")):
            result = self.duplicates(target)
            self.duplicates(target, limit=1)
        self.assertEqual(table_reads, {"sources", "brain_inputs", "brain_meta", "sqlite_sequence"})
        self.assertTrue(selected_columns)
        self.assertTrue(all(not columns & {"body", "text", "payload", "source_ref", "self_speaker"}
                            for columns in selected_columns))
        self.assertEqual(statements.count("BEGIN"), 2)
        self.assertEqual(self.dump(), before)
        self.assertEqual(result["input_revision"], info["input_revision"])
        self.assertEqual(result["model_epoch"], info["model_epoch"])
        self.assertEqual(self.brain.model.reset_info(), info)
        self.assertEqual(self.result("state"), state)
        self.assertEqual(self.result("terms", partition="rational", min_documents=1), terms)
        self.assertEqual(self.result("review_history", source_id=match), history)
        self.assertEqual(self.result("correction_history", source_id=match), corrections)
        self.assertEqual(self.result("choice_feedback_get", source_id=match), feedback)
        serialized = json.dumps(result, ensure_ascii=False)
        for private in (text, "synthetic raw body secret", "synthetic-private-file.md", "synthetic-private-speaker",
                        "synthetic private label", "synthetic private reason", "synthetic-reviewed-group",
                        feedback["records"][0]["body_digest"]):
            self.assertNotIn(private, serialized)

    def test_maximum_million_character_exact_text_keeps_response_bounded(self):
        self.assertEqual(MAX_CHARS, 1_000_000)
        text = "😀\r\n" + "x" * (MAX_CHARS - 4) + "尾"
        target = self.submit(text)
        match = self.submit(text)
        self.submit(text[:-1] + "异")
        self.submit(text.replace("\r\n", "\n") + " ")
        result = self.duplicates(target, limit=1)
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["source_id"], match)
        self.assertLess(len(json.dumps(result).encode("utf-8")), 1024)
        self.assertFalse(result["truncated"])

    def test_wal_concurrent_writer_after_target_keeps_body_version_tokens_and_epoch_snapshot(self):
        target = self.submit()
        match = self.submit(exclamation=True)
        with self.brain.store._connect() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        writer = BrainCore(self.path)
        before = self.duplicates(target)
        original_revision = pagination.revision
        with ThreadPoolExecutor(max_workers=1) as pool:
            def mutate():
                writer.input_edit(target, "我重视自由。", True)
                writer.review(target, agree=True)
                writer.correction_reopen(target, corrections=[], immediate=True, **self.guards(target, writer))
                writer.revoke(match)
                writer.input_edit(match, "我重视自由。", True)
                writer.review(match, agree=True)
                writer.correction_reopen(match, corrections=[], immediate=True, **self.guards(match, writer))
                self.reset_model(writer)
                return writer.submit("我重视自由。", partition="emotional", exclamation=True)["source_id"]
            def write_before_tokens(db):
                pool.submit(mutate).result(timeout=15)  # Real independent connection commits during the read.
                return original_revision(db)
            with patch.object(pagination, "revision", side_effect=write_before_tokens):
                snapshot = self.duplicates(target)
        self.assertEqual(snapshot, before)
        current = self.duplicates(target)
        self.assertEqual(current["source_version"], 1)
        self.assertEqual(current["model_epoch"], 1)
        self.assertGreater(current["input_revision"], before["input_revision"])
        self.assertEqual(current["total"], 2)
        self.assertEqual({item["source_version"] for item in current["items"]}, {0, 1})

    def test_wal_concurrent_delete_insert_between_count_and_rows_is_one_snapshot(self):
        target = self.submit()
        match = self.submit(exclamation=True)
        with self.brain.store._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
        writer = BrainCore(self.path)
        before = self.duplicates(target)
        original = self.brain.store._connect
        with ThreadPoolExecutor(max_workers=1) as pool:
            def mutate():
                writer.input_delete(match)
                writer.submit("我重视公平。", partition="emotional")
                writer.submit("我重视公平。", partition="crazy")
            class BetweenQueries:
                def __init__(self, db):
                    self.db = db
                def execute(self, sql, params=()):
                    cursor = self.db.execute(sql, params)
                    if sql.startswith("SELECT COUNT(*) "):
                        pool.submit(mutate).result(timeout=15)
                    return cursor
            @contextmanager
            def interleaved_connect():
                with original() as db:
                    yield BetweenQueries(db)
            with patch.object(self.brain.store, "_connect", interleaved_connect):
                snapshot = self.duplicates(target)
        self.assertEqual(snapshot, before)
        self.assertEqual(self.duplicates(target)["total"], 2)
        self.assertNotIn(match, [item["source_id"] for item in self.duplicates(target)["items"]])

    def test_authenticated_access_before_after_lock_rotation_and_operation_failure(self):
        target = self.submit()
        match = self.submit()
        password = "synthetic duplicate access password"
        setup_access(self.path, password)
        self.api = BrainAPI(self.path)
        self.assertNotIn("input_duplicates", PUBLIC_METHODS)
        self.assertIn("input_duplicates", METHODS)
        with patch("core.api.BrainCore", side_effect=AssertionError("locked database read")):
            for params in ({}, {"source_id": target}, {"source_id": "\ud800", "limit": False}):
                self.assertEqual(self.call("input_duplicates", **params)["error"]["code"], "LOCKED")
        self.result("unlock", password=password)
        self.assertEqual(self.duplicates(target)["items"][0]["source_id"], match)
        for failure in (False, True):
            self.result("unlock", password=password)
            brain = self.api.brain
            operation = brain.input_duplicates
            def lock_during_read(*args, **kwargs):
                result = operation(*args, **kwargs)
                self.api.access.lock()
                if failure:
                    raise sqlite3.OperationalError("synthetic read failure after lock")
                return result
            with patch.object(brain, "input_duplicates", side_effect=lock_during_read):
                response = self.call("input_duplicates", source_id=target)
            self.assertEqual(response["error"], {"code": "LOCKED", "message": "access is locked"})
            self.assertIsNone(self.api._brain)
            self.assertNotIn(target, json.dumps(response))
            self.assertNotIn(match, json.dumps(response))
        self.result("unlock", password=password)
        brain = self.api.brain
        operation = brain.input_duplicates
        def rotate_during_read(*args, **kwargs):
            result = operation(*args, **kwargs)
            change_password(self.path, password, "synthetic rotated duplicate password")
            return result
        with patch.object(brain, "input_duplicates", side_effect=rotate_during_read):
            response = self.call("input_duplicates", source_id=target)
        self.assertEqual(response["error"]["code"], "LOCKED")
        self.assertIsNone(self.api._brain)

    def test_locked_missing_database_does_not_create_database_or_sidecars(self):
        setup_access(self.path, "synthetic missing duplicate DB password")
        self.path.unlink()
        before = {path.name for path in self.path.parent.iterdir()}
        with patch("core.api.BrainCore", side_effect=AssertionError("locked database creation")):
            self.api = BrainAPI(self.path)
            response = self.call("input_duplicates", source_id="synthetic-missing")
            health = self.result("health")
        self.assertEqual(response["error"]["code"], "LOCKED")
        self.assertTrue(health["features"]["exact_text_duplicate_hint"])
        self.assertEqual((health["contract_revision"], len(health["methods"])), (7, 38))
        self.assertNotIn("model_epoch", health)
        self.assertFalse(self.path.exists())
        self.assertEqual({path.name for path in self.path.parent.iterdir()}, before)

    def test_jsonlines_inprocess_and_real_process_return_metadata_envelopes(self):
        target = self.submit("Synthetic wire exact text 😀\r\n")
        self.submit("Synthetic wire exact text 😀\r\n")
        request = {"schema_version": 1, "id": "duplicates-wire", "method": "input_duplicates",
                   "params": {"source_id": target, "limit": 1}}
        output = io.StringIO()
        serve(self.api, io.StringIO(json.dumps(request) + "\n"), output)
        expected = json.loads(output.getvalue())
        self.assertTrue(expected["ok"])
        self.assertEqual(set(expected["result"]), RESULT_FIELDS)
        process = subprocess.run([sys.executable, "-B", "-m", "core.api", "--db", str(self.path), "--quiet"],
                                 input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=20,
                                 cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), expected)
        self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
