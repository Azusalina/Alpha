import base64
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI
from core import pagination


class InputPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.api = BrainAPI(self.path)

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "page-test", "method": method, "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response)
        return response["result"]

    def submit(self, text="今天记录一件事情。", **params):
        return self.result("submit", text=text, partition=params.pop("partition", "rational"), **params)["source_id"]

    def seed(self, count=3):
        with patch("model.engine._now", return_value="2026-10-01T00:00:00+00:00"):
            return [self.submit(text=f"记录第{i}件事情。") for i in range(count)]

    def test_summary_uses_codepoints_preserves_crlf_combining_marks_and_legacy_embedded_nul(self):
        for prefix in ("😀e\u0301\r\n", "有效\0内容\r\n"):
            text = prefix + "中😀" * 60 + "NOT-IN-THE-EXCERPT"
            source = self.submit(text=text if "\0" not in text else "旧库材料。")
            if "\0" in text:
                # New submissions reject NUL, but additive migration must not rewrite old text.
                with self.api.brain.store._connect() as db:
                    db.execute("UPDATE sources SET body=? WHERE id=?", (text, source))
            detail = self.result("input_get", source_id=source)
            row = next(row for row in self.result("input_list") if row["source_id"] == source)
            self.assertEqual(row["excerpt"], text[:80])
            self.assertEqual(row["char_count"], len(text))
            self.assertEqual(detail["excerpt"], row["excerpt"])
            self.assertEqual(detail["text"].encode("utf-8"), text.encode("utf-8"))
            self.assertIsNone(row["edited_at"])
            self.assertIs(row["immediate"], True)
            self.assertNotIn("text", row)
            self.assertNotIn("body", row)
            self.assertNotIn("NOT-IN-THE-EXCERPT", json.dumps(row))

    def test_short_and_maximum_length_inputs_return_small_summaries_without_training(self):
        for text in ("短", "字" * 1_000_000):
            source = self.submit(text=text, immediate=False)
            row = next(row for row in self.result("input_list") if row["source_id"] == source)
            self.assertEqual(row["excerpt"], text[:80])
            self.assertEqual(row["char_count"], len(text))
            self.assertLess(len(json.dumps(row, ensure_ascii=True)), 2048)
        self.assertFalse(self.result("state", partition="rational")["value.fairness"]["observed"])

    def test_empty_page_and_legacy_array_shape_remain_supported(self):
        self.assertEqual(self.result("input_list"), [])
        self.assertEqual(self.result("input_page"), {"items": [], "total": 0, "next_cursor": None, "revision": 0})
        self.assertEqual(self.result("input_page", partition=None, status=None, cursor=None, limit=100)["items"], [])

    def test_more_than_100_same_timestamp_inputs_paginate_without_duplicates_or_omissions(self):
        sources = self.seed(137)
        cursor, seen, revision = None, [], None
        while True:
            page = self.result("input_page", limit=23, cursor=cursor)
            self.assertEqual(page["total"], len(sources))
            self.assertLessEqual(len(page["items"]), 23)
            if revision is None:
                revision = page["revision"]
            self.assertEqual(page["revision"], revision)
            seen.extend(row["source_id"] for row in page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
            self.assertLessEqual(len(cursor), pagination.MAX_CURSOR_CHARS)
        self.assertEqual(seen, sorted(sources, reverse=True))
        self.assertEqual(len(set(seen)), len(sources))
        legacy_rows = self.result("input_list", limit=100)
        self.assertIsInstance(legacy_rows, list)
        self.assertEqual([row["source_id"] for row in legacy_rows], seen[:100])

    def test_filters_precede_total_and_limit_and_exclude_legacy_sources(self):
        self.api.brain.store.add_source("不属于统一入口的旧资料。")
        expected = []
        for partition in ("rational", "emotional", "crazy"):
            for immediate in (True, False):
                for _ in range(3):
                    source = self.submit(partition=partition, immediate=immediate)
                    if partition == "emotional" and not immediate:
                        expected.append(source)
        first = self.result("input_page", partition="emotional", status="disagreed", limit=2)
        self.assertEqual(first["total"], 3)
        second = self.result("input_page", partition="emotional", status="disagreed", limit=2,
                             cursor=first["next_cursor"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual({row["source_id"] for row in first["items"] + second["items"]}, set(expected))
        self.assertEqual(self.result("input_page", limit=100)["total"], 18)

    def test_cursor_restarts_persist_across_processes_and_allow_page_size_changes(self):
        sources = self.seed(7)
        first = self.result("input_page", limit=2)
        restarted = BrainAPI(self.path)
        page = restarted.brain.input_page(limit=5, cursor=first["next_cursor"])
        self.assertEqual([row["source_id"] for row in page["items"]], sorted(sources, reverse=True)[2:])
        self.assertEqual(page["revision"], first["revision"])

    def test_cursor_tampering_filter_changes_other_database_and_invalid_types_are_rejected(self):
        self.seed()
        token = self.result("input_page", limit=1)["next_cursor"]
        for bad in ("", " ", "garbage", "a" * 2049, token[:-1] + ("0" if token[-1] != "0" else "1"),
                    token + "\n", "\ud800", 1, True, [], {}):
            with self.subTest(bad=repr(bad)):
                self.assertEqual(self.call("input_page", cursor=bad)["error"]["code"], "INVALID_ARGUMENT")
        for params in ({"partition": "rational"}, {"status": "pending"}):
            self.assertEqual(self.call("input_page", cursor=token, **params)["error"]["code"], "INVALID_ARGUMENT")
        other = BrainAPI(Path(self.temp.name) / "other.sqlite3")
        response = other.handle({"schema_version": 1, "id": "other", "method": "input_page", "params": {"cursor": token}})
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")

    def test_supported_submit_review_and_revoke_changes_require_first_page_refresh(self):
        self.seed()
        for mutate in (
            lambda: self.submit(partition="crazy"),
            lambda: self.result("review", source_id=self.result("input_list")[0]["source_id"], agree=False),
            lambda: self.result("review", source_id=self.result("input_list")[0]["source_id"], agree=True),
            lambda: self.result("revoke", source_id=self.result("input_list")[0]["source_id"]),
        ):
            first = self.result("input_page", limit=1)
            mutate()
            self.assertEqual(self.call("input_page", cursor=first["next_cursor"])["error"]["code"], "STALE_CURSOR")
            refreshed = self.result("input_page", limit=1)
            self.assertGreater(refreshed["revision"], first["revision"])

    def test_corrections_invalidate_cursor_but_noop_review_and_legacy_writes_do_not(self):
        sources = self.seed()
        self.result("review", source_id=sources[0], agree=False)
        first = self.result("input_page", limit=1)
        self.result("review", source_id=sources[0], agree=False)
        self.api.brain.store.add_source("旧入口新增材料不影响统一输入列表。")
        next_page = self.result("input_page", cursor=first["next_cursor"])
        self.assertEqual(next_page["revision"], first["revision"])
        self.assertEqual(next_page["total"], 3)
        self.result("correction_set", source_id=sources[1], corrections=[], expected_revision=0)
        self.assertEqual(self.call("input_page", cursor=first["next_cursor"])["error"]["code"], "STALE_CURSOR")
        refreshed = self.result("input_page", limit=1)
        self.assertGreater(refreshed["revision"], first["revision"])
        self.assertEqual(refreshed["total"], next_page["total"])
        self.assertEqual(self.result("input_page", cursor=refreshed["next_cursor"])["revision"], refreshed["revision"])

    def test_reads_do_not_write_fit_audit_or_database_state(self):
        self.seed()
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        first = self.result("input_page", limit=1)
        self.result("input_page", cursor=first["next_cursor"])
        self.result("input_list")
        self.result("input_get", source_id=first["items"][0]["source_id"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(self.result("effects"), [])
        self.assertEqual(self.result("terms", partition="rational", min_documents=1), [])

    def test_page_metadata_total_summaries_and_revision_share_one_read_snapshot(self):
        sources = self.seed(2)
        with self.api.brain.store._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
        original = self.api.brain._input_summaries
        def write_between_metadata_and_summary(db, rows):
            self.submit(text="新提交只应在下一次列表查询出现。")
            return original(db, rows)
        with patch.object(self.api.brain, "_input_summaries", side_effect=write_between_metadata_and_summary):
            page = self.result("input_page", limit=1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(page["items"][0]["source_id"], sorted(sources, reverse=True)[0])
        self.assertEqual(self.call("input_page", cursor=page["next_cursor"])["error"]["code"], "STALE_CURSOR")
        self.assertEqual(self.result("input_page")["total"], 3)

    def test_limits_and_unknown_fields_are_rejected_without_writing(self):
        for method in ("input_list", "input_page"):
            for limit in (0, 101, -1, True, "10", None):
                self.assertEqual(self.call(method, limit=limit)["error"]["code"], "INVALID_ARGUMENT")
            for params in ({"status": "deleted"}, {"partition": "unknown"}, {"db": "/tmp/not-allowed.sqlite3"}):
                self.assertEqual(self.call(method, **params)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("input_list", cursor=None)["error"]["code"], "INVALID_ARGUMENT")

    def test_signed_malformed_payload_is_rejected_and_cursor_contains_no_raw_body_or_secret(self):
        self.seed()
        first = self.result("input_page", limit=1)
        with self.api.brain.store._connect() as db:
            secret = pagination.key(db)
        token = first["next_cursor"]
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=" * (-len(token.split(".")[0]) % 4)))
        self.assertEqual(set(payload), {"version", "revision", "partition", "status", "created_at", "source_id"})
        self.assertNotIn(secret.hex(), json.dumps(first))
        for raw in (b"not-json", b"[]", b"[" * 1001 + b"]" * 1001,
                    json.dumps(dict(payload, revision=True)).encode(),
                    json.dumps(dict(payload, source_id="\ud800")).encode()):
            body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            signed = body + "." + hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
            self.assertEqual(self.call("input_page", cursor=signed)["error"]["code"], "INVALID_ARGUMENT")

    def test_real_jsonlines_process_returns_summary_page_envelope(self):
        self.seed()
        request = {"schema_version": 1, "id": "process", "method": "input_page", "params": {"limit": 2}}
        process = subprocess.run([sys.executable, "-m", "core.api", "--db", str(self.path)],
                                 input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=20,
                                 cwd=Path(__file__).resolve().parents[1])
        self.assertEqual(process.returncode, 0, process.stderr)
        response = json.loads(process.stdout)
        self.assertTrue(response["ok"], response)
        self.assertEqual(len(response["result"]["items"]), 2)
        self.assertEqual(response["result"]["total"], 3)
        self.assertIsNotNone(response["result"]["next_cursor"])


if __name__ == "__main__":
    unittest.main()
