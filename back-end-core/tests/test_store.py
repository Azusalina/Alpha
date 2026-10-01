import tempfile
import unittest
from pathlib import Path

from core.store import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "brain.sqlite3"
        self.store = MemoryStore(self.path)
        self.store.initialize()

    def test_source_persists_and_is_private(self):
        source_id = self.store.add_source("我喜歡畫畫。", origin="input")
        reopened = MemoryStore(self.path)
        self.assertEqual(reopened.get_source(source_id)["body"], "我喜歡畫畫。")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_candidate_requires_exact_source_evidence(self):
        source_id = self.store.add_source("今天去看海。")
        with self.assertRaises(ValueError):
            self.store.propose(source_id, "喜歡海", "我喜歡海")
        self.assertEqual(self.store.list_candidates(), [])
        candidate_id = self.store.propose(source_id, "今天看過海", "今天去看海")
        self.assertEqual(self.store.list_candidates()[0]["id"], candidate_id)
        self.assertEqual(self.store.list_memories(), [])

    def test_resolution_is_explicit_and_once_only(self):
        source_id = self.store.add_source("我在學英文。")
        first = self.store.propose(source_id, "在學英文", "學英文")
        second = self.store.propose(source_id, "正在學習", "我在學英文")
        self.store.resolve(first, accept=True)
        self.store.resolve(second, accept=False)
        self.assertEqual([row["id"] for row in self.store.list_memories()], [first])
        with self.assertRaises(ValueError):
            self.store.resolve(first, accept=False)

    def test_resolution_requires_a_real_boolean(self):
        source_id = self.store.add_source("我在學英文。")
        candidate_id = self.store.propose(source_id, "在學英文", "學英文")
        with self.assertRaises(ValueError):
            self.store.resolve(candidate_id, accept="false")
        self.assertEqual(self.store.list_candidates()[0]["status"], "pending")

    def test_text_is_stored_as_data(self):
        body = "'); DROP TABLE sources; --"
        source_id = self.store.add_source(body)
        self.assertEqual(self.store.get_source(source_id)["body"], body)
        self.assertEqual(len(self.store.list_sources()), 1)

    def test_search_returns_only_accepted_memories_with_provenance(self):
        source_id = self.store.add_source("我在學英文，也喜歡畫畫。", origin="input")
        accepted = self.store.propose(source_id, "喜歡畫畫", "喜歡畫畫")
        self.store.resolve(accepted, accept=True)
        pending = self.store.propose(source_id, "正在學英文", "學英文")
        self.assertEqual(self.store.search_memories("英文"), [])
        results = self.store.search_memories("畫畫")
        self.assertEqual([row["id"] for row in results], [accepted])
        self.assertEqual(results[0]["source_id"], source_id)
        self.assertEqual(results[0]["evidence"], "喜歡畫畫")
        self.store.resolve(pending, accept=False)
        self.assertEqual(self.store.search_memories("英文"), [])

    def test_search_query_is_literal_and_limit_is_bounded(self):
        source_id = self.store.add_source("I like C++.")
        candidate_id = self.store.propose(source_id, "Likes C++", "C++")
        self.store.resolve(candidate_id, accept=True)
        self.assertEqual(len(self.store.search_memories("c++")), 1)
        self.assertEqual(self.store.search_memories("%"), [])
        with self.assertRaises(ValueError):
            self.store.search_memories("C++", limit=0)


if __name__ == "__main__":
    unittest.main()
