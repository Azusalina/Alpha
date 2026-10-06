"""Synthetic computational exposure tests; no semantic/causal inference claims."""

import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from model import dependencies, sources
from translator.learning import configured_phrases


def provenance(fit_id="a" * 32, *, tokenizer=(), rules=(), terms=()):
    return {"version": 1, "fit_id": fit_id, "input_revision": 0, "model_epoch": 0,
            "scope": "available_learning_inputs", "tokenizer_terms": list(terms),
            "tokenizer_terms_total": len(terms), "tokenizer_terms_truncated": False,
            "tokenizer_sources": list(tokenizer), "tokenizer_sources_truncated": False,
            "rule_sources": list(rules), "rule_sources_truncated": False,
            "complete": all(ref["fit_id"] is not None for ref in (*tokenizer, *rules))}


def ref(source_id, fit_id="a" * 32, version=0):
    return {"source_id": source_id, "source_version": version, "fit_id": fit_id}


class DependencyValidationTests(unittest.TestCase):
    def test_preview_null_identity_is_valid_but_unknown_provider_is_incomplete(self):
        preview = provenance(None)
        self.assertIs(dependencies.validate(preview), preview)
        self.assertTrue(preview["complete"])
        unknown = provenance(rules=[ref("legacy", None)])
        self.assertFalse(dependencies.validate(unknown)["complete"])

    def test_closed_metadata_rejects_invalid_types_ids_terms_and_cross_fields(self):
        valid = provenance(tokenizer=[ref("provider")], terms=["公平"])
        invalid = [None, [], {**valid, "private_label": "synthetic"}]
        for field in valid:
            value = copy.deepcopy(valid)
            del value[field]
            invalid.append(value)
        for field in ("version", "input_revision", "model_epoch", "tokenizer_terms_total"):
            for bad in (True, 1.0, -1, "1", None):
                invalid.append({**valid, field: bad})
        for field in ("complete", "tokenizer_terms_truncated", "tokenizer_sources_truncated", "rule_sources_truncated"):
            for bad in (1, "false", None):
                invalid.append({**valid, field: bad})
        for field, bad in (("version", 2), ("scope", "causal_usage"), ("fit_id", "A" * 32),
                           ("fit_id", "a" * 31), ("fit_id", "a" * 32 + "\n"),
                           ("tokenizer_terms", ["english"]), ("tokenizer_terms", ["公"]),
                           ("tokenizer_terms", ["公平\n"]), ("tokenizer_terms", ["公平", "公平"]),
                           ("tokenizer_terms", ["自由", "公平"]), ("tokenizer_terms_total", 2),
                           ("tokenizer_terms_truncated", True), ("tokenizer_sources_truncated", True),
                           ("rule_sources_truncated", True), ("complete", False)):
            invalid.append({**valid, field: bad})
        for bad_ref in (ref(""), ref(" "), ref("bad\0id"), ref("\ud800"),
                        ref("provider", version=True), ref("provider", version=0.0),
                        ref("provider", fit_id="X" * 32), {**ref("provider"), "text": "synthetic"},
                        {"source_id": "provider", "source_version": 0}):
            invalid.append({**valid, "tokenizer_sources": [bad_ref]})
        invalid.extend([
            {**valid, "tokenizer_sources": [ref("provider"), ref("provider")]},
            {**valid, "tokenizer_sources": [ref("z"), ref("a")]},
            {**valid, "tokenizer_sources": [ref("provider", None)]},
            {**valid, "tokenizer_terms": [], "tokenizer_terms_total": 0},
            {**valid, "rule_sources": [ref(str(i)) for i in range(129)]},
        ])
        for index, value in enumerate(invalid):
            with self.subTest(case=index), self.assertRaisesRegex(ValueError, "^invalid dependency provenance$"):
                dependencies.validate(value)

    def test_strict_request_validation_and_bounds(self):
        dependencies.validate_request(["synthetic"], 1)
        dependencies.validate_request([str(i) for i in range(16)], 100)
        for ids in (None, "a", (), [], ["a"] * 2, [str(i) for i in range(17)],
                    [None], [1], [True], [" "], ["bad\0id"], ["\udfff"]):
            with self.subTest(ids=repr(ids)), self.assertRaises(ValueError):
                dependencies.validate_request(ids, 100)
        for limit in (None, True, 1.0, "1", 0, -1, 101):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                dependencies.validate_request(["synthetic"], limit)


class DependencyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.api = BrainAPI(self.path)
        self.model = self.api.brain.model

    def result(self, method, **params):
        response = self.api.handle({"schema_version": 1, "id": "dependency-test", "method": method, "params": params})
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def guards(self, source):
        info = self.model.reset_info()
        return {"expected_source_version": self.result("input_get", source_id=source)["source_version"],
                "expected_epoch": info["model_epoch"], "expected_revision": info["input_revision"]}

    def snapshot(self):
        with closing(sqlite3.connect(self.path)) as db:
            return list(db.iterdump())

    def seed(self, entries):
        """Seed bounded graph metadata without fitting or reading a corpus."""
        with self.model.store._connect() as db:
            for source, context in entries.items():
                db.execute("INSERT INTO sources(id,body,origin,source_ref,created_at) VALUES (?,?,'diary',?,?)",
                           (source, "SYNTHETIC_PRIVATE_BODY", "SYNTHETIC_PRIVATE_REF", "synthetic-time"))
                if context is None:
                    db.execute("INSERT INTO brain_inputs(source_id,partition,kind) VALUES (?,'rational','diary')", (source,))
                else:
                    db.execute("INSERT INTO brain_inputs(source_id,partition,kind,status,immediate,confirm,confirmed_by,ever_fitted) "
                               "VALUES (?,'rational','diary','agreed',1,1,'manual',1)", (source,))
                if context is not None:
                    db.execute("INSERT INTO brain_fit_context(source_id,payload,source_version) VALUES (?,?,0)",
                               (source, json.dumps(context)))

    @staticmethod
    def context(**kwargs):
        return {"dependency_provenance": provenance(**kwargs),
                "translation": {"claim": "SYNTHETIC_PRIVATE_CLAIM"},
                "memories": [{"evidence": "SYNTHETIC_PRIVATE_EVIDENCE"}]}

    def test_fresh_preview_fit_frozen_restore_and_f6_new_identity(self):
        source = self.result("submit", text="我重视公平。", partition="rational")["source_id"]
        before = self.snapshot()
        preview = self.result("preview", source_id=source)["interpretation"]["dependency_provenance"]
        self.assertIsNone(preview["fit_id"])
        self.assertTrue(preview["complete"])
        self.assertEqual(before, self.snapshot())
        first = self.result("review", source_id=source, agree=True)
        captured = first["interpretation"]["dependency_provenance"]
        self.assertRegex(captured["fit_id"], "^[0-9a-f]{32}$")
        self.assertFalse(first["restored_fit"])
        self.result("revoke", source_id=source)
        self.assertEqual(self.result("preview", source_id=source)["interpretation"]["dependency_provenance"], captured)
        restored = self.result("review", source_id=source, agree=True)
        self.assertTrue(restored["restored_fit"])
        self.assertEqual(restored["interpretation"]["dependency_provenance"], captured)
        before = self.snapshot()
        self.result("review", source_id=source, agree=True)
        self.assertEqual(before, self.snapshot())
        self.result("correction_reopen", source_id=source, corrections=[], immediate=True, **self.guards(source))
        next_preview = self.result("preview", source_id=source)["interpretation"]["dependency_provenance"]
        self.assertIsNone(next_preview["fit_id"])
        second = self.result("review_version", source_id=source, agree=True, **self.guards(source))
        self.assertFalse(second["restored_fit"])
        self.assertNotEqual(second["interpretation"]["dependency_provenance"]["fit_id"], captured["fit_id"])

    def test_reset_preserves_old_epoch_tokenizer_and_rule_providers(self):
        providers = []
        for _ in range(2):
            source = self.result("submit", text="我重视公平。", partition="rational")["source_id"]
            self.result("correction_set", source_id=source, expected_revision=0,
                        corrections=[{"parameter": "value.fairness", "sign": 1, "evidence": "我重视公平", "span": [0, 5]}])
            context = self.result("review", source_id=source, agree=True)["interpretation"]["dependency_provenance"]
            providers.append(ref(source, context["fit_id"]))
        info = self.model.reset_info()
        self.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"], expected_revision=info["input_revision"])
        source = self.result("submit", text="我重视公平。", partition="rational")["source_id"]
        context = self.result("review", source_id=source, agree=True)["interpretation"]["dependency_provenance"]
        self.assertEqual(context["model_epoch"], 1)
        self.assertEqual(context["rule_sources"], sorted(providers, key=lambda r: r["source_id"]))
        self.assertEqual(context["tokenizer_sources"], sorted(providers, key=lambda r: r["source_id"]))
        self.assertTrue(context["complete"])
        plan = self.result("dependency_plan", source_ids=[providers[0]["source_id"]])
        affected = {row["source_id"]: row for row in plan["affected"]}
        self.assertEqual(set(affected), {source, providers[1]["source_id"]})
        self.assertEqual(affected[source]["via_kinds"], ["rule", "tokenizer"])
        self.assertTrue(affected[source]["model_active"])
        self.assertFalse(affected[providers[1]["source_id"]]["replay_eligible"])
        self.assertFalse(self.result("input_get", source_id=providers[0]["source_id"])["model_active"])

    def test_tokenizer_uses_only_configured_sorted_chinese_recurrent_terms(self):
        self.seed({"a": self.context(), "b": self.context()})
        with self.model.store._connect() as db:
            for source in ("a", "b"):
                db.executemany("INSERT INTO brain_terms(source_id,term,occurrences,source_version) VALUES (?,?,1,0)",
                               [(source, term) for term in ("公平", "自由", "alpha", "公", "一二三四五六七八九")])
            db.execute("INSERT INTO brain_terms(source_id,term,occurrences,source_version) VALUES ('a','单次',1,0)")
        source = self.result("submit", text="Synthetic unrelated text", partition="rational")["source_id"]
        captured = self.result("preview", source_id=source)["interpretation"]["dependency_provenance"]
        self.assertEqual(captured["tokenizer_terms"], ["公平", "自由"])
        self.assertEqual([r["source_id"] for r in captured["tokenizer_sources"]], ["a", "b"])
        self.assertEqual(configured_phrases(("自由", "alpha", "公平", "公")), ("自由", "公平"))

    def test_chains_cycles_shortest_distances_and_all_reachable_exposure_kinds(self):
        self.seed({"a": self.context(), "b": self.context(rules=[ref("a")], tokenizer=[ref("c")], terms=["公平"]),
                   "c": self.context(rules=[ref("b")], tokenizer=[ref("a")], terms=["公平"]),
                   "d": self.context(rules=[ref("c")]), "pending": None})
        before = self.snapshot()
        result = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual([(r["source_id"], r["distance"], r["via_kinds"]) for r in result["affected"]],
                         [("b", 1, ["rule", "tokenizer"]), ("c", 1, ["rule", "tokenizer"]), ("d", 2, ["rule"])])
        self.assertEqual(result["total_affected"], 3)
        self.assertEqual(result["total_sources"], 4)
        selected = self.result("dependency_plan", source_ids=["b", "a"])
        self.assertEqual(selected["source_ids"], ["b", "a"])
        self.assertEqual([r["source_id"] for r in selected["affected"]], ["c", "d"])
        self.assertEqual(self.result("dependency_plan", source_ids=["pending"])["affected"], [])
        self.assertEqual(before, self.snapshot())

    def test_legacy_absence_is_partial_without_inventing_metadata(self):
        legacy = {"learned_rules": [{"support_source_ids": ["a"]}]}
        self.seed({"a": self.context(), "b": legacy})
        before = self.snapshot()
        result = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual((result["status"], result["untracked_sources"], result["incomplete_sources"]), ("partial", 1, 0))
        self.assertEqual(result["changed_supports"], 0)
        self.assertEqual(result["affected"][0]["via_kinds"], ["rule"])
        self.assertIsNone(result["affected"][0]["fit_id"])
        self.assertFalse(result["affected"][0]["provenance_complete"])
        self.assertEqual(before, self.snapshot())

    def test_persisted_null_identity_is_partial_even_with_complete_preview_coverage(self):
        self.seed({"a": self.context(), "b": self.context(fit_id=None, rules=[ref("a")])})
        result = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual((result["status"], result["incomplete_sources"]), ("partial", 1))
        self.assertFalse(result["affected"][0]["provenance_complete"])

    def test_changed_support_versions_identity_and_missing_fit_are_counted_once(self):
        self.seed({"a": self.context(fit_id="b" * 32),
                   "b": self.context(rules=[ref("a")], tokenizer=[ref("a")], terms=["公平"])})
        for mutation in ("identity", "version", "missing_fit"):
            with self.subTest(mutation=mutation):
                with self.model.store._connect() as db:
                    if mutation == "version":
                        db.execute("UPDATE brain_inputs SET source_version=1 WHERE source_id='a'")
                    elif mutation == "missing_fit":
                        db.execute("DELETE FROM brain_fit_context WHERE source_id='a'")
                result = self.result("dependency_plan", source_ids=["a"])
                self.assertEqual((result["status"], result["changed_supports"]), ("partial", 1))
                self.assertEqual([r["source_id"] for r in result["affected"]], ["b"])

    def test_f6_archive_lineage_reuse_changes_fit_identity_at_same_source_version(self):
        source = self.result("submit", text="我重视公平。", partition="rational", exclamation=True)["source_id"]
        first = self.result("correction_history", source_id=source)["fit_context"]["dependency_provenance"]
        checkpoint = sqlite3.connect(":memory:")
        self.addCleanup(checkpoint.close)
        with closing(sqlite3.connect(self.path)) as db:
            db.backup(checkpoint)
        self.result("correction_reopen", source_id=source, corrections=[], immediate=True, **self.guards(source))
        self.result("review_version", source_id=source, agree=True, **self.guards(source))
        current = self.result("correction_history", source_id=source)["fit_context"]["dependency_provenance"]
        # Restore the synthetic v0 checkpoint, then F6 reuses v1; only fit_id distinguishes the v1 fits.
        with closing(sqlite3.connect(self.path)) as db:
            checkpoint.backup(db)
        self.assertEqual(self.result("correction_history", source_id=source)["fit_context"]["dependency_provenance"], first)
        self.seed({"downstream": self.context(rules=[ref(source, current["fit_id"], 1)])})
        self.result("correction_reopen", source_id=source, corrections=[], immediate=True, **self.guards(source))
        next_fit = self.result("review_version", source_id=source, agree=True, **self.guards(source))
        self.assertEqual(next_fit["source_version"], 1)
        self.assertNotEqual(next_fit["interpretation"]["dependency_provenance"]["fit_id"], current["fit_id"])
        result = self.result("dependency_plan", source_ids=[source])
        self.assertEqual(result["changed_supports"], 1)
        self.assertEqual(result["status"], "partial")

    def test_limit_and_scan_bounds_are_explicit_partial_coverage(self):
        self.seed({"a": self.context(), **{f"b{i:04}": self.context(rules=[ref("a")]) for i in range(1000)}})
        result = self.result("dependency_plan", source_ids=["a"], limit=1)
        self.assertEqual((result["scanned_sources"], result["total_sources"], result["total_affected"]), (1000, 1001, 999))
        self.assertTrue(result["graph_truncated"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual([r["source_id"] for r in result["affected"]], ["b0000"])
        self.assertEqual(len(self.result("dependency_plan", source_ids=["a"])["affected"]), 100)

    def test_exact_1000_scan_and_outside_fit_identity_remain_truthful_and_bounded(self):
        self.seed({f"n{i:04}": self.context() for i in range(1000)})
        complete = self.result("dependency_plan", source_ids=["n0999"])
        self.assertEqual((complete["status"], complete["scanned_sources"], complete["total_sources"]), ("complete", 1000, 1000))
        self.assertFalse(complete["graph_truncated"])
        with self.model.store._connect() as db:
            db.execute("UPDATE brain_fit_context SET payload=? WHERE source_id='n0000'",
                       (json.dumps(self.context(rules=[ref("zparent")])),))
        self.seed({"zparent": None})
        exact = self.result("dependency_plan", source_ids=["n0999"])
        self.assertEqual((exact["scanned_sources"], exact["total_sources"], exact["graph_truncated"]), (1000, 1000, False))
        self.assertEqual(exact["changed_supports"], 1)  # Known identity has no current fit.
        with self.model.store._connect() as db:
            db.execute("INSERT INTO brain_fit_context(source_id,payload,source_version) VALUES ('zparent',?,0)",
                       (json.dumps(self.context(fit_id="b" * 32)),))
        before = self.snapshot()
        with patch("model.dependencies._context", wraps=dependencies._context) as decode:
            outside = self.result("dependency_plan", source_ids=["zparent"])
        self.assertEqual(decode.call_count, 1000)
        self.assertEqual((outside["scanned_sources"], outside["total_sources"], outside["graph_truncated"]), (1000, 1001, True))
        self.assertEqual(outside["changed_supports"], 0)  # Same version; outside identity is unknown.
        self.assertEqual(outside["status"], "partial")
        self.assertEqual([row["source_id"] for row in outside["affected"]], ["n0000"])
        self.assertEqual(before, self.snapshot())
        with self.model.store._connect() as db:
            db.execute("UPDATE brain_inputs SET source_version=1 WHERE source_id='zparent'")
            db.execute("UPDATE brain_fit_context SET source_version=1,payload=? WHERE source_id='zparent'",
                       ("SYNTHETIC_OUTSIDE_PAYLOAD_MUST_NOT_DECODE",))
        with patch("model.dependencies._context", wraps=dependencies._context) as decode:
            changed_version = self.result("dependency_plan", source_ids=["zparent"])
        self.assertEqual(decode.call_count, 1000)
        self.assertEqual((changed_version["status"], changed_version["changed_supports"]), ("partial", 1))

    def test_missing_known_supporters_are_queried_bodylessly_in_batches_of_128(self):
        supporters = [f"s{i:03}" for i in range(257)]
        self.seed({source: None for source in supporters})
        self.seed({f"node{i}": self.context(rules=[ref(source) for source in supporters[start:start + 128]])
                   for i, start in enumerate(range(0, 257, 128))})
        before = self.snapshot()
        queries = []
        original_connect = self.model.store._connect
        @contextmanager
        def traced_connect():
            with original_connect() as db:
                db.set_trace_callback(queries.append)
                yield db
        with patch.object(self.model.store, "_connect", traced_connect), \
                patch("model.dependencies._context", wraps=dependencies._context) as decode:
            result = self.result("dependency_plan", source_ids=[supporters[0]])
        self.assertEqual(decode.call_count, 3)
        self.assertEqual((result["status"], result["changed_supports"], result["total_sources"]), ("partial", 257, 3))
        batches = [sql for sql in queries if "WHERE i.source_id IN (" in sql]
        self.assertEqual([sql.rsplit(" IN (", 1)[1].count(",") + 1 for sql in batches], [128, 128, 1])
        self.assertTrue(all("f.payload" not in sql and "source_version" in sql for sql in batches))
        self.assertEqual(before, self.snapshot())

    def test_legacy_and_incomplete_counts_are_disjoint_and_unknown_refs_are_not_changes(self):
        self.seed({"a": self.context(), "legacy": {"learned_rules": [{"support_source_ids": ["a"],
                   "support_source_versions": {"a": 99}}]},
                   "unknown": self.context(rules=[ref("a", None, 99)]),
                   "nullfit": self.context(fit_id=None)})
        result = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual((result["untracked_sources"], result["incomplete_sources"], result["changed_supports"]), (1, 2, 0))
        self.assertEqual(result["status"], "partial")
        self.assertEqual([row["source_id"] for row in result["affected"]], ["legacy", "unknown"])

    def test_missing_selected_root_is_generic_not_found_without_any_write(self):
        self.seed({"a": self.context()})
        before = self.snapshot()
        response = self.api.handle({"schema_version": 1, "id": "missing", "method": "dependency_plan",
                                    "params": {"source_ids": ["a", "SYNTHETIC_PRIVATE_MISSING"]}})
        self.assertEqual(response["error"], {"code": "NOT_FOUND", "message": "input or candidate not found"})
        self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(response))
        self.assertEqual(before, self.snapshot())

    def test_capture_caps_terms_tokenizer_and_rule_providers(self):
        entries = {f"s{i:03}": self.context() for i in range(129)}
        self.seed(entries)
        terms = tuple(chr(0x3400 + i) + "词" for i in range(129))
        with self.model.store._connect() as db:
            db.executemany("INSERT INTO brain_terms(source_id,term,occurrences,source_version) VALUES (?,?,1,0)",
                           [(source, terms[0]) for source in entries])
            row = db.execute("SELECT * FROM brain_inputs WHERE source_id='s000'").fetchone()
            captured = dependencies.capture(db, row, terms,
                [{"support_source_ids": list(reversed(entries)), "support_source_versions": dict.fromkeys(entries, 0)}])
        self.assertEqual(captured["tokenizer_terms"], list(terms[:128]))
        self.assertEqual(captured["tokenizer_terms_total"], 129)
        self.assertEqual([r["source_id"] for r in captured["tokenizer_sources"]], sorted(entries)[:128])
        self.assertEqual([r["source_id"] for r in captured["rule_sources"]], sorted(entries)[:128])
        for field in ("tokenizer_terms_truncated", "tokenizer_sources_truncated", "rule_sources_truncated"):
            self.assertIs(captured[field], True)
        self.assertFalse(captured["complete"])
        dependencies.validate(captured)

    def test_planner_cannot_write_read_source_bodies_or_invoke_fit_or_extraction(self):
        self.seed({"a": self.context(), "b": self.context(rules=[ref("a")])})
        before = self.snapshot()
        original_connect = self.model.store._connect
        statements = []
        denied_writes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                         sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_ALTER_TABLE}

        @contextmanager
        def read_only():
            with original_connect() as db:
                db.execute("PRAGMA query_only=ON")
                db.set_trace_callback(statements.append)
                def authorize(action, table, column, database, trigger):
                    if action in denied_writes or (action == sqlite3.SQLITE_READ and
                            (table in {"sources", "candidates", "brain_terms", "brain_contributions"})):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                db.set_authorizer(authorize)
                yield db

        with patch.object(self.model.store, "_connect", read_only), \
                patch.object(self.model, "_observations", side_effect=AssertionError("extraction")), \
                patch.object(self.model, "_review", side_effect=AssertionError("fitting")), \
                patch.object(self.model, "replay_reopen", side_effect=AssertionError("replay")):
            self.assertEqual(self.result("dependency_plan", source_ids=["a"])["total_affected"], 1)
        self.assertTrue(any(sql == "BEGIN" for sql in statements))
        self.assertEqual(before, self.snapshot())

    def test_one_read_snapshot_survives_concurrent_support_change(self):
        self.seed({"a": self.context(), "b": self.context(rules=[ref("a")])})
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
        before = self.result("dependency_plan", source_ids=["a"])
        original_revision = dependencies.reset.revision
        committed = []
        def race(db):
            value = original_revision(db)  # First read fixes the caller's BEGIN snapshot.
            with closing(sqlite3.connect(self.path)) as writer, writer:
                writer.execute("UPDATE brain_fit_context SET payload=? WHERE source_id='a'",
                               (json.dumps(self.context(fit_id="b" * 32)),))
                writer.execute("UPDATE brain_meta SET value=CAST(value AS INTEGER)+1 WHERE key=?", (sources.GENERATION_KEY,))
            committed.append(True)
            return value
        with patch("model.dependencies.reset.revision", side_effect=race):
            during = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual(committed, [True])
        self.assertEqual(during, before)
        after = self.result("dependency_plan", source_ids=["a"])
        self.assertEqual((after["status"], after["changed_supports"]), ("partial", 1))
        self.assertEqual(after["input_revision"], before["input_revision"] + 1)

    def test_invalid_present_metadata_fails_closed_and_hides_decoder_details(self):
        self.seed({"a": self.context(), "b": self.context(rules=[ref("a")])})
        for payload in ('SYNTHETIC_PRIVATE_DECODER', '[]', '{"dependency_provenance":null}',
                        json.dumps({"dependency_provenance": {"private": "SYNTHETIC_PRIVATE_LABEL"}})):
            with self.subTest(payload=payload):
                with self.model.store._connect() as db:
                    db.execute("UPDATE brain_fit_context SET payload=? WHERE source_id='b'", (payload,))
                before = self.snapshot()
                response = self.api.handle({"schema_version": 1, "id": "bad", "method": "dependency_plan", "params": {"source_ids": ["a"]}})
                self.assertEqual(response["error"], {"code": "INVALID_ARGUMENT", "message": "invalid dependency provenance"})
                self.assertNotIn("result", response)
                self.assertNotIn("SYNTHETIC_PRIVATE", json.dumps(response))
                self.assertEqual(before, self.snapshot())

    def test_epoch_activity_and_replay_eligibility_are_separate(self):
        self.seed({"a": self.context(), "old": self.context(rules=[ref("a")]),
                   "revoked": self.context(rules=[ref("a")])})
        with self.model.store._connect() as db:
            db.execute("UPDATE brain_meta SET value='1' WHERE key='model_epoch'")
            db.execute("UPDATE brain_inputs SET model_epoch=1,status='revoked',confirm=0,reason='user_revoked' WHERE source_id='revoked'")
        rows = {r["source_id"]: r for r in self.result("dependency_plan", source_ids=["a"])["affected"]}
        self.assertEqual((rows["old"]["model_active"], rows["old"]["replay_eligible"]), (False, False))
        self.assertEqual((rows["revoked"]["model_active"], rows["revoked"]["replay_eligible"]), (False, True))


if __name__ == "__main__":
    unittest.main()
