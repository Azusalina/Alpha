import tempfile
import unittest
from pathlib import Path

from core.extraction import extract_candidates
from core.store import MemoryStore


class FakeModel:
    def __init__(self, output):
        self.output = output
        self.prompt = None

    def generate(self, prompt):
        self.prompt = prompt
        return self.output


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = MemoryStore(Path(self.temp.name) / "brain.sqlite3")
        self.store.initialize()
        self.source = self.store.add_source("我住台北，也在學英文。")

    def test_valid_model_output_stays_pending(self):
        model = FakeModel('{"candidates":[{"claim":"住台北","evidence":"我住台北"}]}')
        ids = extract_candidates(self.store, self.source, model)
        self.assertEqual(len(ids), 1)
        self.assertIn("SOURCE_JSON", model.prompt)
        self.assertEqual(self.store.list_memories(), [])
        self.assertEqual(self.store.list_candidates(status="pending")[0]["id"], ids[0])

    def test_bad_evidence_rejects_whole_batch(self):
        model = FakeModel(
            '{"candidates":[{"claim":"住台北","evidence":"我住台北"},'
            '{"claim":"喜歡咖啡","evidence":"喜歡咖啡"}]}'
        )
        with self.assertRaises(ValueError):
            extract_candidates(self.store, self.source, model)
        self.assertEqual(self.store.list_candidates(), [])

    def test_malformed_or_extra_fields_are_rejected(self):
        for output in ('not JSON', '{"candidates":[],"auto_accept":true}'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                extract_candidates(self.store, self.source, FakeModel(output))
        self.assertEqual(self.store.list_candidates(), [])


if __name__ == "__main__":
    unittest.main()
