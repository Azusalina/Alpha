import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.api import BrainAPI, METHODS, serve
from model.catalog import PARAMETERS


class BrainAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.api = BrainAPI(self.path)

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "test", "method": method,
                                "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response)
        return response["result"]

    def test_schema_catalog_matches_runtime_capabilities(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "docs/api.schema.json").read_text())
        self.assertEqual(set(schema["$defs"]["request"]["properties"]["method"]["enum"]), set(METHODS))
        self.assertEqual(set(schema["$defs"]["parameter"]["enum"]), set(PARAMETERS))
        self.assertEqual(set(self.result("health")["methods"]), set(METHODS))

    def test_submit_preserves_unicode_crlf_and_rejects_surrogates_before_storage(self):
        for bad in ("\ud800", "\udfff", "\ud83d\ude00"):
            with self.subTest(bad=repr(bad)):
                for field in ("text", "source_ref", "self_speaker"):
                    params = {"text": "我开心。", "partition": "emotional", field: bad}
                    self.assertEqual(self.call("submit", **params)["error"]["code"], "INVALID_ARGUMENT")
                with self.assertRaises(ValueError):
                    self.api.brain.model.submit(bad, partition="emotional")
        self.assertEqual(self.result("input_list"), [])
        text = "我: 😀我很失望。\r\n你: 我生气。\r\n"
        source = self.result("submit", text=text, partition="emotional", kind="chat", self_speaker="我")["source_id"]
        self.assertEqual(self.result("input_get", source_id=source)["text"].encode("utf-8"), text.encode("utf-8"))
        preview = self.result("preview", source_id=source)
        for item in preview["translation"]["cues"] + preview["effects"]:
            start, end = item["span"]
            self.assertEqual(text[start:end], item["evidence"])

    def test_one_source_flows_through_preview_model_memory_and_revocation(self):
        source = self.result("submit", text="我重视公平。", partition="rational",
                             source_ref="diary.md")["source_id"]
        preview = self.result("preview", source_id=source)
        self.assertTrue(preview["hypothetical"])
        self.assertEqual(self.result("memory_list"), [])
        self.result("review", source_id=source, agree=True)
        candidate = self.result("candidate_propose", source_id=source,
                                claim="重视公平", evidence="我重视公平")
        self.assertEqual(candidate["status"], "accepted")
        self.assertEqual(self.result("memory_list")[0]["id"], candidate["candidate_id"])
        active = self.result("memory_search", query="公平", partition="rational")
        self.assertEqual(active[0]["source_id"], source)
        self.assertEqual(active[0]["source_ref"], "diary.md")
        self.result("revoke", source_id=source)
        self.assertEqual(self.result("memory_search", query="公平"), [])
        self.assertEqual(self.result("candidate_list")[0]["source_status"], "revoked")
        self.assertEqual(self.result("input_get", source_id=source)["text"], "我重视公平。")

    def test_canonical_queries_exclude_legacy_and_filter_partition_before_limit(self):
        legacy = self.api.brain.store.add_source("我喜欢画画。")
        legacy_candidate = self.api.brain.store.propose(legacy, "喜欢画画", "喜欢画画")
        self.api.brain.store.resolve(legacy_candidate, accept=True)
        for partition in ("emotional", "rational"):
            source = self.result("submit", text="我喜欢画画。", partition=partition)["source_id"]
            self.result("review", source_id=source, agree=True)
            candidate = self.result("candidate_propose", source_id=source,
                                    claim="喜欢画画", evidence="喜欢画画")
            self.assertEqual(candidate["status"], "accepted")
        rows = self.result("memory_search", query="画画", partition="rational", limit=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["partition"], "rational")
        self.assertEqual(len(self.result("memory_list")), 2)
        self.assertEqual(len(self.result("input_list")), 2)
        self.assertEqual(self.call("input_get", source_id=legacy)["error"]["code"], "NOT_FOUND")
        self.assertEqual(self.call("candidate_review", candidate_id=legacy_candidate,
                                   accept=True)["error"]["code"], "NOT_FOUND")

    def test_invalid_payloads_cannot_mutate_review_or_choose_database(self):
        source = self.result("submit", text="我重视自由。", partition="rational")["source_id"]
        for params in ({"source_id": source, "agree": "false"},
                       {"source_id": source, "agree": True, "db": "/tmp/other.sqlite3"}):
            response = self.call("review", **params)
            self.assertEqual(response["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.result("input_get", source_id=source)["status"], "pending")
        self.assertEqual(self.result("state", partition="rational")["value.autonomy"]["support"], 0)
        self.assertEqual(self.call("__dict__")["error"]["code"], "METHOD_NOT_FOUND")

    def test_disagreed_input_stays_readable_and_never_becomes_a_memory(self):
        source = self.result("submit", text="我在学英文。", partition="rational")["source_id"]
        self.result("review", source_id=source, agree=False)
        response = self.call("candidate_propose", source_id=source, claim="学英文", evidence="学英文")
        self.assertFalse(response["ok"])
        self.assertEqual(self.result("candidate_list"), [])
        self.assertEqual(self.result("input_list", status="disagreed")[0]["source_id"], source)

    def test_chat_memory_extraction_and_proposal_use_only_self_speaker(self):
        class ModelSpy:
            prompt = None

            def generate(self, prompt):
                self.prompt = prompt
                return '{"candidates":[{"claim":"喜欢画画","evidence":"我喜欢画画"}]}'

        source = self.result("submit", text="阿明: 我住台北。\n我: 我喜欢画画。",
                             partition="rational", kind="chat", self_speaker="我")["source_id"]
        self.result("review", source_id=source, agree=True)
        spy = ModelSpy()
        candidate = self.api.brain.extract_memories(source, spy)[0]
        self.assertNotIn("台北", spy.prompt)
        self.assertEqual(self.result("candidate_list")[0]["id"], candidate)
        self.assertEqual(self.result("candidate_list")[0]["status"], "accepted")
        response = self.call("candidate_propose", source_id=source,
                             claim="住台北", evidence="我住台北")
        self.assertFalse(response["ok"])
        self.assertEqual(len(self.result("memory_list")), 1)

    def test_stream_rejects_ambiguous_json_and_continues(self):
        good = json.dumps({"schema_version": 1, "id": "health", "method": "health", "params": {}})
        input_stream = io.StringIO('not JSON\n{"id":"a","id":"b"}\n{"value":NaN}\n' + good + '\n')
        output_stream = io.StringIO()
        serve(self.api, input_stream, output_stream)
        rows = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["error"]["code"] == "INVALID_REQUEST" for row in rows[:3]))
        self.assertTrue(rows[3]["ok"])
        self.assertEqual(rows[3]["id"], "health")

    def test_real_process_returns_json_only_and_exits_on_eof(self):
        request = {"schema_version": 1, "id": "upload", "method": "submit",
                   "params": {"text": "日记：我重视自由。", "partition": "rational", "source_ref": "日记.md"}}
        process = subprocess.run(
            [sys.executable, "-m", "core.api", "--db", str(self.path)],
            input=json.dumps(request, ensure_ascii=False) + "\n", text=True,
            capture_output=True, timeout=15, cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        rows = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["id"], "upload")
        source = rows[0]["result"]["source_id"]
        self.assertEqual(self.result("input_get", source_id=source)["text"], request["params"]["text"])


if __name__ == "__main__":
    unittest.main()
