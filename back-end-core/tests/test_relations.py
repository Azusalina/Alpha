"""User-reviewed semantic/causal relations: bound, stale-aware, never inferred."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.api import BrainAPI


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.api = BrainAPI(self.path)
        self.model = self.api.brain.model

    def call(self, method, **params):
        return self.api.handle({"schema_version": 1, "id": "relation-test", "method": method, "params": params})

    def result(self, method, **params):
        response = self.call(method, **params)
        self.assertTrue(response["ok"], response.get("error"))
        return response["result"]

    def source(self, text="我重视公平。"):
        return self.result("submit", text=text, partition="rational")["source_id"]

    def edge(self, source, target, **changes):
        info = self.model.reset_info()
        params = dict(from_source_id=source, to_source_id=target, kind="causal", reviewed=True,
                      note="user judged", expected_revision=info["input_revision"],
                      expected_epoch=info["model_epoch"],
                      expected_from_source_version=self.result("input_get", source_id=source)["source_version"],
                      expected_to_source_version=self.result("input_get", source_id=target)["source_version"])
        params.update(changes)
        return params

    def test_save_list_replace_and_retract_are_explicit_and_idempotent(self):
        a, b = self.source(), self.source("我重视自由。")
        saved = self.result("relation_set", **self.edge(a, b))
        self.assertTrue(saved["changed"])
        listed = self.result("relation_list", source_id=b)
        self.assertEqual([(r["direction"], r["kind"], r["note"], r["stale"]) for r in listed["relations"]],
                         [("incoming", "causal", "user judged", False)])
        self.assertEqual(self.result("relation_list", source_id=a)["relations"][0]["direction"], "outgoing")
        self.result("relation_set", **self.edge(a, b, note="revised note"))
        self.assertEqual(self.result("relation_list", source_id=a)["relations"][0]["note"], "revised note")
        self.result("relation_set", **self.edge(a, b, kind="semantic", note=None))
        self.assertEqual(len(self.result("relation_list", source_id=a)["relations"]), 2)
        retracted = self.result("relation_set", **self.edge(a, b, reviewed=False, note=None))
        self.assertTrue(retracted["changed"])
        again = self.result("relation_set", **self.edge(a, b, reviewed=False, note=None))
        self.assertFalse(again["changed"])
        self.assertEqual([r["kind"] for r in self.result("relation_list", source_id=a)["relations"]], ["semantic"])

    def test_invalid_requests_and_stale_guards_do_not_write(self):
        a, b = self.source(), self.source("我重视自由。")
        for changes in ({"kind": "other"}, {"reviewed": 1}, {"reviewed": None}, {"to_source_id": a},
                        {"note": "x" * 1025}, {"note": 1}, {"note": "a\0b"}, {"reviewed": False},
                        {"expected_revision": -1}, {"expected_from_source_version": True},
                        {"expected_epoch": 1.0}, {"to_source_id": " "}, {"from_source_id": "x" * 129},
                        {"unknown": 1}):
            with self.subTest(changes=changes):
                self.assertFalse(self.call("relation_set", **self.edge(a, b, **changes))["ok"])
        for field in ("expected_revision", "expected_epoch", "expected_from_source_version",
                      "expected_to_source_version"):
            stale = self.edge(a, b)
            stale[field] += 1
            self.assertEqual(self.call("relation_set", **stale)["error"]["code"], "INVALID_ARGUMENT")
        self.assertEqual(self.call("relation_set", **self.edge(a, b, to_source_id="missing"))["error"]["code"],
                         "NOT_FOUND")
        self.assertEqual(self.result("relation_list", source_id=a)["relations"], [])
        for limit in (0, 101, True, "1"):
            self.assertFalse(self.call("relation_list", source_id=a, limit=limit)["ok"])

    def test_per_source_bound_and_truncated_list(self):
        hub = self.source()
        others = [self.source(f"我重视自由{i}。") for i in range(65)]
        for other in others[:64]:
            self.result("relation_set", **self.edge(hub, other))
        self.assertFalse(self.call("relation_set", **self.edge(hub, others[64]))["ok"])
        # Replacing an existing edge is not a new edge.
        self.result("relation_set", **self.edge(hub, others[0], note="same edge"))
        page = self.result("relation_list", source_id=hub, limit=10)
        self.assertEqual((len(page["relations"]), page["truncated"]), (10, True))

    def test_edits_deletes_reopened_versions_and_resets_invalidate_edges(self):
        a, b, c = self.source(), self.source("我重视自由。"), self.source("我重视成长。")
        for target in (b, c):
            self.result("relation_set", **self.edge(a, target))
        self.result("review", source_id=b, agree=True)
        info = self.model.reset_info()
        self.result("correction_reopen", source_id=b, corrections=[], immediate=True,
                    expected_source_version=0, expected_revision=info["input_revision"],
                    expected_epoch=info["model_epoch"])
        stale = {r["to_source_id"]: r["stale"] for r in self.result("relation_list", source_id=a)["relations"]}
        self.assertEqual(stale, {b: True, c: False})
        self.assertEqual(self.result("dependency_plan", source_ids=[a])["total_affected"], 1)
        self.result("input_edit", source_id=c, text="我重视成长和学习。", immediate=True)
        self.assertEqual([r["to_source_id"] for r in self.result("relation_list", source_id=a)["relations"]], [b])
        self.result("input_delete", source_id=b)
        self.assertEqual(self.result("relation_list", source_id=a)["relations"], [])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM brain_relations").fetchone()[0], 0)
        d = self.source("我重视友情。")
        self.result("relation_set", **self.edge(a, d))
        info = self.model.reset_info()
        self.model.reset_model(confirmation="RESET_MODEL", expected_epoch=info["model_epoch"],
                               expected_revision=info["input_revision"])
        self.assertTrue(self.result("relation_list", source_id=a)["relations"][0]["stale"])
        self.assertEqual(self.result("dependency_plan", source_ids=[a])["total_affected"], 0)

    def test_dependency_plan_includes_only_fresh_manual_edges_without_fitting_or_status_change(self):
        a, b, c = self.source(), self.source("我重视自由。"), self.source("我重视成长。")
        self.result("relation_set", **self.edge(a, b, kind="semantic"))
        self.result("relation_set", **self.edge(a, b))
        self.result("relation_set", **self.edge(b, c))
        before = self.result("state")
        plan = self.result("dependency_plan", source_ids=[a])
        self.assertEqual([(r["source_id"], r["distance"], r["via_kinds"], r["replay_eligible"],
                           r["model_active"], r["fit_id"], r["provenance_complete"])
                          for r in plan["affected"]],
                         [(b, 1, ["manual_causal", "manual_semantic"], False, False, None, False),
                          (c, 2, ["manual_causal"], False, False, None, False)])
        self.assertEqual((plan["status"], plan["scanned_sources"], plan["total_sources"]), ("complete", 0, 0))
        self.assertEqual(self.result("state"), before)
        self.assertEqual(self.result("effects"), [])
        self.assertEqual(self.result("input_get", source_id=b)["status"], "pending")
        # Edges are directed: a dependent does not expose its cause.
        self.assertEqual(self.result("dependency_plan", source_ids=[c])["affected"], [])

    def test_fitted_manual_target_is_replay_eligible_and_mixes_with_computational_kinds(self):
        a, b = self.source(), self.source("我重视自由。")
        self.result("review", source_id=b, agree=True)
        self.result("relation_set", **self.edge(a, b, kind="semantic"))
        plan = self.result("dependency_plan", source_ids=[a])
        item = plan["affected"][0]
        self.assertEqual((item["source_id"], item["via_kinds"], item["replay_eligible"], item["model_active"]),
                         (b, ["manual_semantic"], True, True))
        self.assertIsNotNone(item["fit_id"])

    def test_locked_database_gates_relations(self):
        from core.access import setup_access
        a, b = self.source(), self.source("我重视自由。")
        params_set = self.edge(a, b)
        setup_access(self.path, "synthetic relation password")
        api = BrainAPI(self.path)
        for method, params in (("relation_set", params_set), ("relation_list", {"source_id": a})):
            response = api.handle({"schema_version": 1, "id": "locked", "method": method, "params": params})
            self.assertEqual(response["error"]["code"], "LOCKED")


if __name__ == "__main__":
    unittest.main()
