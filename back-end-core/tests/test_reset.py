"""Model-only reset tests. Synthetic text and temporary databases only."""

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
from core.pagination import StaleCursor
from model import BrainModel, reset
from model.catalog import BASELINE_PATH, PARTITIONS
from model.evaluation import read_snapshot


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'brain.sqlite3'
        self.api = BrainAPI(self.path)
        self.core = self.api.brain
        self.model = self.core.model

    def zero(self):
        info = self.model.reset_info()
        return self.model.reset_model(confirmation='RESET_MODEL', expected_epoch=info['model_epoch'],
                                      expected_revision=info['input_revision'])

    def fit(self, text='我重视公平。', partition='rational'):
        return self.core.submit(text, partition=partition, exclamation=True)['source_id']

    def assert_zero(self):
        for partition in self.model.state().values():
            for value in partition.values():
                self.assertEqual(value, {'value': 0, 'support': 0, 'observed': False})

    def test_all_partitions_restart_and_baseline_with_history_preserved(self):
        digest = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
        sources = [self.fit(partition=p) for p in PARTITIONS]
        effects = self.model.effects()
        histories = [self.model.review_history(s) for s in sources]
        snapshot = read_snapshot(self.path)
        result = self.zero()
        self.assertEqual(result['model_epoch'], 1)
        self.assertEqual(result['active_model_inputs'], 0)
        self.assertEqual(result['previous_active_model_inputs'], 3)
        self.assert_zero()
        for source, history in zip(sources, histories):
            record = self.core.input_get(source)
            self.assertEqual(record['text'], '我重视公平。')
            self.assertEqual(record['status'], 'agreed')
            self.assertTrue(record['immediate'] and record['confirm'])
            self.assertFalse(record['model_active'])
            self.assertEqual(record['model_epoch'], 0)
            self.assertEqual(self.model.review_history(source), history)
        self.assertEqual(self.model.effects(), effects)
        self.assertTrue(all(e['model_epoch'] == 0 for e in effects))
        self.assertEqual(BrainModel(self.path).state(), self.model.state())
        after = read_snapshot(self.path)
        self.assertNotEqual(after['fingerprint'], snapshot['fingerprint'])
        self.assertEqual(after['training_source_ids'], snapshot['training_source_ids'])
        self.assertEqual(hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest(), digest)
        self.assertEqual(self.model.rank_options([{'id': 'a', 'impacts': {'value.fairness': 1}},
                                                 {'id': 'b', 'impacts': {}}])['status'], 'abstain')

    def test_new_training_and_old_revoke_delete_cannot_revive_old_contributions(self):
        old = [self.fit() for _ in range(3)]
        self.zero()
        new = self.fit()
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertEqual(self.model.revoke(old[0])['effects'], [])
        self.core.input_delete(old[1])
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertTrue(self.core.input_get(new)['model_active'])
        self.assertFalse(self.core.input_get(old[2])['model_active'])

    def test_explicit_reapproval_restores_only_selected_fit_and_is_idempotent(self):
        old = [self.fit() for _ in range(2)]
        terms = self.model.learned_terms(partition='rational', min_documents=1)
        self.zero()
        with patch.object(self.model, '_observations', side_effect=AssertionError('must keep frozen fit')):
            result = self.model.review(old[0], agree=True)
        self.assertTrue(result['restored_fit'])
        self.assertEqual(result['translator_effects'], [])
        self.assertTrue(all(e['model_epoch'] == 1 for e in result['effects']))
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertEqual(self.model.learned_terms(partition='rational', min_documents=1), terms)
        self.assertFalse(self.core.input_get(old[1])['model_active'])
        self.assertEqual(self.model.review(old[0], agree=True)['effects'], [])
        self.model.revoke(old[0])
        self.assert_zero()

    def test_preserves_vocabulary_and_explicit_correction_teaching(self):
        text = '这句代表我的自由。'
        teachers = []
        for _ in range(2):
            source = self.core.submit(text, partition='rational')['source_id']
            self.core.correction_set(source, expected_revision=0, corrections=[{
                'parameter': 'value.autonomy', 'sign': 1, 'evidence': text[:-1], 'span': [0, len(text)-1]}])
            self.core.review(source, agree=True)
            teachers.append(source)
        terms = self.core.terms(partition='rational', min_documents=1)
        corrections = [self.core.correction_history(s) for s in teachers]
        self.zero()
        self.assertEqual(self.core.terms(partition='rational', min_documents=1), terms)
        self.assertEqual([self.core.correction_history(s) for s in teachers], corrections)
        pupil = self.core.submit(text, partition='rational')['source_id']
        preview = self.core.preview(pupil)
        self.assertTrue(any(e['rule_id'] == 'learned_exact_correction' for e in preview['effects']))
        self.assert_zero()
        self.core.review(pupil, agree=True)
        self.assertEqual(self.model.state('rational')['value.autonomy']['support'], 1)
        self.assertTrue(all(self.core.input_get(s)['model_active'] is False for s in teachers))

    def test_translator_revoke_and_delete_still_remove_support_after_reset(self):
        first, second = self.fit(), self.fit()
        self.zero()
        self.assertTrue(self.core.terms(partition='rational'))
        removed = self.core.revoke(first)
        self.assertEqual(removed['effects'], [])
        self.assertTrue(removed['translator_effects'])
        self.assertEqual(self.core.terms(partition='rational'), [])
        self.core.input_delete(second)
        self.assertEqual(self.core.terms(partition='rational', min_documents=1), [])
        self.assert_zero()

    def test_wrong_confirmation_epoch_revision_and_bool_never_reset(self):
        self.fit()
        info = self.model.reset_info()
        state = self.model.state()
        for overrides in ({'confirmation': 'yes'}, {'expected_epoch': True},
                          {'expected_revision': True}, {'expected_epoch': -1},
                          {'expected_epoch': 9}, {'expected_revision': 0}):
            args = dict(confirmation='RESET_MODEL', expected_epoch=info['model_epoch'],
                        expected_revision=info['input_revision'])
            args.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.model.reset_model(**args)
            self.assertEqual(self.model.state(), state)
            self.assertEqual(self.model.reset_info(), info)

    def test_revision_conflict_and_cursor_invalidation(self):
        self.fit()
        self.fit()
        page = self.core.input_page(limit=1)
        info = self.model.reset_info()
        self.fit()
        with self.assertRaises(ValueError):
            self.model.reset_model(confirmation='RESET_MODEL', expected_epoch=0,
                                  expected_revision=info['input_revision'])
        self.zero()
        with self.assertRaises(StaleCursor):
            self.core.input_page(limit=1, cursor=page['next_cursor'])
        self.assertGreater(self.core.input_page()['revision'], page['revision'])

    def test_mid_reset_rollback_keeps_epoch_state_and_cursor_generation(self):
        self.fit()
        before, info = self.model.state(), self.model.reset_info()
        with patch.object(reset.sources, 'bump_generation', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.zero()
        self.assertEqual(self.model.state(), before)
        self.assertEqual(self.model.reset_info(), info)

    def test_repeated_empty_resets_have_monotonic_epochs(self):
        for current in range(1, 4):
            self.assertEqual(self.zero()['model_epoch'], current)
            self.assert_zero()

    def test_parallel_resets_from_same_preflight_have_exactly_one_winner(self):
        self.fit()
        info = self.model.reset_info()
        def attempt(_):
            try:
                return BrainModel(self.path).reset_model(confirmation='RESET_MODEL', expected_epoch=0,
                                                        expected_revision=info['input_revision'])['reset']
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), [False, True])
        self.assert_zero()

    def test_cli_guard_and_actual_reset_process_only_on_temporary_database(self):
        root = Path(__file__).resolve().parents[1]
        def run(path, *args):
            return subprocess.run([sys.executable, '-m', 'model', '--db', str(path), *args],
                                  cwd=root, capture_output=True, text=True, timeout=10)
        missing = Path(self.temp.name) / 'missing.sqlite3'
        self.assertNotEqual(run(missing, 'reset-info').returncode, 0)
        self.assertFalse(missing.exists())
        unrelated = Path(self.temp.name) / 'unrelated.sqlite3'
        unrelated.write_bytes(b'not a database')
        self.assertNotEqual(run(unrelated, 'reset-info').returncode, 0)
        self.assertEqual(unrelated.read_bytes(), b'not a database')
        foreign = Path(self.temp.name) / 'foreign.sqlite3'
        with closing(sqlite3.connect(foreign)) as db:
            db.execute('CREATE TABLE unrelated(value TEXT)')
            db.commit()
        foreign_before = foreign.read_bytes()
        self.assertNotEqual(run(foreign, 'reset-info').returncode, 0)
        self.assertEqual(foreign.read_bytes(), foreign_before)
        self.assertNotEqual(run(Path('data/brain.sqlite3'), 'reset-info').returncode, 0)
        self.fit()
        info = json.loads(run(self.path, 'reset-info').stdout)
        result = run(self.path, 'reset', '--confirm', 'RESET_MODEL', '--expected-epoch',
                     str(info['model_epoch']), '--expected-revision', str(info['input_revision']))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['reset'])
        self.assert_zero()
        request = dict(schema_version=1, id='no-hidden-reset', method='reset_model', params={})
        self.assertEqual(self.api.handle(request)['error']['code'], 'METHOD_NOT_FOUND')

    def test_additive_epoch_migration_preserves_fit_and_is_idempotent(self):
        self.fit()
        before = self.model.state()
        with self.model.store._connect() as db:
            db.execute("DELETE FROM brain_meta WHERE key IN ('reset_schema','model_epoch')")
            db.execute('ALTER TABLE brain_inputs DROP COLUMN model_epoch')
            db.execute('ALTER TABLE brain_effects DROP COLUMN model_epoch')
        reopened = BrainModel(self.path)
        self.assertEqual(reopened.state(), before)
        self.assertEqual(reopened.reset_info()['model_epoch'], 0)
        self.assertEqual(BrainModel(self.path).reset_info(), reopened.reset_info())
