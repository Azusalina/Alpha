"""Source revision/publication/replay checks: synthetic text, temporary databases."""

import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from core.brain import BrainCore
from core.extraction import deterministic_candidates
from core.store import MemoryStore
from model import BrainModel, sources
from model.corrections import validate_corrections
from model.evaluation import read_snapshot
from translator import translate


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.sqlite3'
        self.core = BrainCore(self.path)
        self.model = self.core.model

    def fit(self, text='我重视公平。我很开心。', **kwargs):
        return self.core.submit(text, partition='rational', exclamation=True, **kwargs)['source_id']

    def guards(self, source):
        info = self.model.reset_info()
        return dict(expected_source_version=self.core.input_get(source)['source_version'],
                    expected_revision=info['input_revision'], expected_epoch=info['model_epoch'])

    def snapshot(self):
        with self.model.store._connect() as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {t: sorted([tuple(r) for r in db.execute(f'SELECT * FROM "{t}"')], key=repr)
                    for t in tables}

    def correction(self, sign=0):
        return {'parameter': 'value.fairness', 'sign': sign, 'evidence': '我重视公平', 'span': [0, 5]}

    def reopen(self, source, corrections=None, **kwargs):
        return self.core.correction_reopen(source, corrections=[self.correction()] if corrections is None else corrections,
                                           immediate=kwargs.pop('immediate', True), **self.guards(source), **kwargs)

    def zero(self):
        info = self.model.reset_info()
        return self.model.reset_model(confirmation='RESET_MODEL', expected_epoch=info['model_epoch'],
                                      expected_revision=info['input_revision'])

    def test_reopen_withdraws_only_selected_fit_and_archives_old_interpretation(self):
        source, other = self.fit(), self.fit()
        old_effects = self.model.effects(source_id=source)
        other_effects = self.model.effects(source_id=other)
        old_context = self.core.correction_history(source)['fit_context']
        result = self.reopen(source)
        self.assertEqual((result['status'], result['source_version']), ('pending', 1))
        self.assertIsNone(result['confirm'])
        self.assertFalse(result['exclamation'])
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertTrue(result['effects'])
        self.assertEqual(self.model.effects(source_id=other), other_effects)
        self.assertEqual(self.model.effects(source_id=source)[:len(old_effects)], old_effects)
        archived = self.core.correction_history(source)['version_history'][0]
        self.assertEqual(archived['fit_context'], old_context)
        self.assertEqual(archived['source_version'], 0)
        self.assertNotIn('body', archived)
        with self.assertRaises(ValueError):
            self.core.review(source, agree=True)
        approved = self.core.review_version(source, agree=True, **self.guards(source))
        self.assertFalse(approved['restored_fit'])
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertTrue(approved['confirm'])
        self.assertEqual(self.core.input_get(source)['text'], '我重视公平。我很开心。')
        self.assertIn(source, read_snapshot(self.path)['training_source_ids'])

    def test_validation_stale_guards_and_failure_rollback_leave_complete_database_unchanged(self):
        source = self.fit()
        before = self.snapshot()
        for change in ({'expected_source_version': True}, {'expected_revision': 0},
                       {'expected_epoch': 9}, {'expected_source_version': 3}):
            guards = {**self.guards(source), **change}
            with self.assertRaises(ValueError):
                self.core.correction_reopen(source, corrections=[self.correction()], immediate=True, **guards)
            self.assertEqual(self.snapshot(), before)
        with self.assertRaises(ValueError):
            self.reopen(source, [self.correction(), {'type': 'tone', 'value': 'invented', 'sign': 1,
                                                   'evidence': '开心', 'span': [8, 10]}])
        self.assertEqual(self.snapshot(), before)
        for target in ('_recompute',):
            with patch.object(self.model, target, side_effect=RuntimeError('synthetic failure')):
                with self.assertRaises(RuntimeError):
                    self.reopen(source)
            self.assertEqual(self.snapshot(), before)
        with patch('model.sources.bump_generation', side_effect=RuntimeError('late synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.reopen(source)
        self.assertEqual(self.snapshot(), before)

    def test_parallel_reopen_and_versioned_review_have_one_winner(self):
        source = self.fit()
        guards = self.guards(source)
        def reopen(_):
            try:
                return self.core.correction_reopen(source, corrections=[], immediate=True, **guards)['source_version']
            except ValueError:
                return 0
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(reopen, range(2))), [0, 1])
        guards = self.guards(source)
        def approve(_):
            try:
                return self.core.review_version(source, agree=True, **guards)['confirm']
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(approve, range(2))), [False, True])
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)

    def test_renewed_immediate_false_cannot_be_overridden_by_legacy_review(self):
        source = self.fit()
        result = self.reopen(source, immediate=False)
        self.assertEqual(result['status'], 'disagreed')
        self.assertIsNone(result['confirm'])
        for agree in (False, True):
            with self.assertRaises(ValueError):
                self.core.review(source, agree=agree)
            with self.assertRaises(ValueError):
                self.core.review_version(source, agree=agree, **self.guards(source))

    def test_automatic_memories_are_atomic_version_bound_and_idempotent(self):
        source = self.fit()
        memories = self.core.memory_list()
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['evidence'], '开心')
        self.assertEqual(memories[0]['source_version'], 0)
        self.core.review(source, agree=True)
        self.assertEqual(self.core.memory_list(), memories)
        self.reopen(source, [])
        self.assertEqual(self.core.memory_list(), [])
        self.core.review_version(source, agree=True, **self.guards(source))
        new = self.core.memory_list()
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]['source_version'], 1)
        self.assertNotEqual(new[0]['id'], memories[0]['id'])
        self.assertEqual(len(self.core.candidate_list()), 2)
        self.assertEqual(self.model.store.list_memories(), new_as_store := [
            {k: v for k, v in new[0].items() if k not in ('partition', 'source_status', 'source_ref')}])
        self.assertEqual(self.model.store.search_memories('happiness')[0]['id'], new_as_store[0]['id'])
        self.core.revoke(source)
        with self.assertRaises(ValueError):
            self.core.review(source, agree=True)
        self.core.review_version(source, agree=True, **self.guards(source))
        self.assertEqual(self.core.memory_list(), new)

    def test_assertion_author_negation_and_parameter_suppression_block_autopublication(self):
        blocked = ['“我很开心”。', '我很开心？', '如果我很开心。', '我可能很开心。',
                   '她很开心。', '开心。', '我不开心。', '我说她很开心。',
                   '> 我很开心。', '朋友说我很开心。']
        for text in blocked:
            with self.subTest(text=text):
                source = self.fit(text)
                self.assertFalse([m for m in self.core.memory_list(limit=100) if m['source_id'] == source])
        source = self.fit('他: 我很开心。\n我: 我不开心。', kind='chat', self_speaker='我')
        self.assertFalse([m for m in self.core.memory_list(limit=100) if m['source_id'] == source])
        source = self.fit('我很开心，她难过。')
        self.assertEqual([m['evidence'] for m in self.core.memory_list(limit=100) if m['source_id'] == source], ['开心'])
        text = '我重视公平而且很开心。'
        source = self.core.submit(text, partition='rational')['source_id']
        self.core.correction_set(source, corrections=[self.correction()], expected_revision=0)
        self.core.review(source, agree=True)
        self.assertFalse([m for m in self.core.memory_list(limit=100) if m['source_id'] == source])

    def test_publication_failure_rolls_back_approval_fit_and_audit(self):
        source = self.core.submit('我很开心。', partition='rational')['source_id']
        before = self.snapshot()
        original = MemoryStore.publish_deterministic
        def fail(db, source_id, version, items):
            original(db, source_id, version, items)
            raise RuntimeError('synthetic publication failure')
        with patch.object(MemoryStore, 'publish_deterministic', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.core.review(source, agree=True)
        self.assertEqual(self.snapshot(), before)

    def test_explicit_self_emotions_abstain_on_possessive_and_ambiguous_subjects(self):
        blocked = [
            '我妈妈很开心', '我爸爸很开心', '我同学很开心', '我老师很开心',
            '我室友很开心', '我邻居很开心', '我队友很开心', '我表姐很开心',
            '我媽媽很開心', '我爸爸很開心', '我同學很開心', '我老師很開心',
            '我室友很開心', '我鄰居很開心', '我隊友很開心', '我表姐很開心',
            '我的妈妈很开心', '我的室友感到开心', '我自己妈妈很开心',
            '我的媽媽很開心', '我的室友感到開心', '我的某個熟人很開心',
            '我某个熟人很开心', '我的𠮷很开心',
            '我们很开心', '我們很開心', '自己的妈妈很开心',
            "my roommate’s 很开心", "my teacher's 很开心", '妈妈说我很开心',
            '我让妈妈很开心', '我觉得妈妈很开心', '我和妈妈很开心',
            '我为妈妈开心爸爸感到开心', '我很开心妈妈也是',
            '我很开心？', '我感到不开心', '我并不很开心',
            '我可能很开心', '如果我很开心', '我说我很开心',
            '“我很开心”', '> 我很开心', '我为妈妈感到开心？',
            '“我为妈妈感到开心”', '「我為媽媽感到開心」',
            '如果我为妈妈感到开心', '我可能为妈妈感到开心',
            '妈妈说我为妈妈感到开心', '媽媽說我為媽媽感到開心',
            '朋友说，我为妈妈感到开心', '如果有好消息，我为妈妈感到开心',
            '> 我为妈妈感到开心', '我为妈妈感到不开心',
        ]
        for text in blocked:
            with self.subTest(text=text):
                report = translate(text)
                self.assertEqual(deterministic_candidates(text, 'diary', None, report, []), [])
        # Confirm the publication filter, rather than translator abstention alone,
        # covers the four reported failures and arbitrary possession prefixes.
        for text in blocked[:8]:
            self.assertTrue(translate(text)['candidates'], text)
        for text in ('我很开心', '我感到开心', '我自己很开心', '自己感到开心',
                     '我为妈妈感到开心', '我为爸爸感到开心', '我替室友感到开心',
                     '我為媽媽感到開心', '我 很 开心'):
            with self.subTest(text=text):
                items = deterministic_candidates(text, 'diary', None, translate(text), [])
                self.assertEqual(len(items), 1)
                self.assertEqual(items[0]['claim'], 'textual_emotion: happiness')
                self.assertEqual(text[slice(*items[0]['span'])], items[0]['evidence'])

    def test_self_subject_publication_preserves_unicode_chat_and_clause_ownership(self):
        cases = [
            ('我妈妈很开心。我室友很开心。我为妈妈感到开心。', 'diary', None, '开心'),
            ('我爸爸很开心。我感到开心。', 'philosophy', None, '开心'),
            ('旁人：我很开心。\n本人：我老师很开心。\n本人：我為媽媽感到開心。\n'
             '本人：我室友很开心。', 'chat', '本人', '開心'),
            ('𠮷🙂。我很开心，她难过。', 'diary', None, '开心'),
            ('本人：我媽媽很開心。\n本人：我的室友感到開心。\n'
             '本人：「我為媽媽感到開心」。\n本人：如果有好消息，我為媽媽感到開心。\n'
             '旁人：我為媽媽感到開心。\n本人：我感到開心。', 'chat', '本人', '開心'),
        ]
        for text, kind, speaker, evidence in cases:
            with self.subTest(kind=kind, text=text):
                source = self.core.submit(text, partition='rational', kind=kind,
                                          self_speaker=speaker)['source_id']
                before = self.snapshot()
                memories = self.core.preview(source)['interpretation']['memories']
                self.assertEqual(self.snapshot(), before)
                self.assertEqual([m['evidence'] for m in memories], [evidence])
                self.core.review(source, agree=True)
                published = [m for m in self.core.memory_list(limit=100) if m['source_id'] == source]
                self.assertEqual([m['evidence'] for m in published], [evidence])
                self.assertEqual(text[slice(*memories[0]['span'])], evidence)

    def test_typed_target_aliases_reject_all_signs_orders_and_repeated_positions(self):
        cases = [('我很开心', 'diary', None, 'tone'),
                 ('𠮷🙂。我很开心。我很开心。', 'diary', None, 'tone'),
                 ('他：我很开心。\n我：我很开心。', 'chat', '我', 'tone'),
                 ('我不再主动联系。', 'diary', None, 'intent')]
        for text, kind, speaker, family in cases:
            targets = translate(text, kind=kind, self_speaker=speaker)['candidates']
            self.assertTrue(targets)
            for target in targets:
                for families in ((family, 'candidate'), ('candidate', family),
                                 (family, family), ('candidate', 'candidate')):
                    for first_sign in (0, 1):
                        for second_sign in (0, 1):
                            annotations = [dict(type=f, sign=s, **{k: target[k]
                                           for k in ('value', 'evidence', 'span')})
                                           for f, s in zip(families, (first_sign, second_sign))]
                            with self.subTest(text=text, span=target['span'],
                                              families=families, signs=(first_sign, second_sign)):
                                with self.assertRaisesRegex(ValueError, 'duplicate annotation target'):
                                    validate_corrections(text, kind, speaker, annotations)
        self.assertEqual(translate('我很开心')['candidates'][0]['span'], [2, 4])

    def test_duplicate_typed_alias_batches_leave_pending_and_fitted_databases_unchanged(self):
        text = '我很开心'
        pending = self.core.submit(text, partition='rational')['source_id']
        fitted = self.fit(text)
        target = translate(text)['candidates'][0]
        for families in (('tone', 'candidate'), ('candidate', 'tone')):
            for first_sign in (0, 1):
                for second_sign in (0, 1):
                    annotations = [dict(type=f, sign=s, **{k: target[k]
                                   for k in ('value', 'evidence', 'span')})
                                   for f, s in zip(families, (first_sign, second_sign))]
                    before = self.snapshot()
                    with self.assertRaisesRegex(ValueError, 'duplicate annotation target'):
                        self.core.correction_set(pending, corrections=annotations, expected_revision=0)
                    self.assertEqual(self.snapshot(), before)
                    with self.assertRaisesRegex(ValueError, 'duplicate annotation target'):
                        self.reopen(fitted, annotations)
                    self.assertEqual(self.snapshot(), before)

    def test_distinct_typed_positions_and_event_intent_targets_remain_independent(self):
        text = '我很开心。我很开心。我不再主动联系并取消约会。'
        report = translate(text)
        tones = [r for r in report['candidates'] if r['type'] == 'textual_emotion']
        intent = next(r for r in report['candidates'] if r['type'] == 'contact_intention')
        event = next(r for r in report['cues'] if r['category'] == 'event_word')
        self.assertEqual(len(tones), 2)
        annotations = [dict(type=f, sign=s, **{k: target[k]
                       for k in ('value', 'evidence', 'span')})
                       for f, s, target in [('tone', 0, tones[0]), ('candidate', 1, tones[1]),
                                            ('event', 0, event), ('intent', 1, intent)]]
        self.assertEqual(validate_corrections(text, 'diary', None, annotations), annotations)
        source = self.core.submit(text, partition='rational')['source_id']
        self.core.correction_set(source, corrections=annotations, expected_revision=0)
        preview = self.core.preview(source)
        self.assertEqual([r['span'] for r in preview['translation']['candidates']
                          if r['type'] == 'textual_emotion'], [tones[1]['span']])
        self.assertIn(intent, preview['translation']['candidates'])
        self.assertNotIn(event, preview['translation']['cues'])

    def test_typed_annotations_are_exact_local_and_do_not_invent_learning(self):
        text = '我取消约会。我很开心。我不再主动联系。'
        source = self.core.submit(text, partition='rational')['source_id']
        report = self.core.preview(source)['translation']
        event = next(c for c in report['cues'] if c['category'] == 'event_word')
        tone = next(c for c in report['candidates'] if c['type'] == 'textual_emotion')
        intent = next(c for c in report['candidates'] if c['type'] == 'contact_intention')
        corrections = [{'type': family, 'value': c['value'], 'sign': 0, 'evidence': c['evidence'],
                        'span': c['span']} for family, c in [('event', event), ('tone', tone), ('intent', intent)]]
        self.core.correction_set(source, corrections=corrections, expected_revision=0)
        preview = self.core.preview(source)
        self.assertEqual(preview['translation']['candidates'], [])
        self.assertFalse(any(c['category'] == 'event_word' for c in preview['translation']['cues']))
        self.core.review(source, agree=True)
        self.assertEqual(self.core.memory_list(), [])
        next_source = self.core.submit(text, partition='rational')['source_id']
        self.assertTrue(self.core.preview(next_source)['translation']['candidates'])
        self.assertEqual(self.core.preview(next_source)['interpretation']['learned_rules'], [])
        for change in ({'value': 'invented'}, {'span': [True, 2]}, {'sign': True}):
            with self.assertRaises(ValueError):
                self.core.correction_set(next_source, corrections=[{**corrections[0], **change}], expected_revision=0)

    def test_archives_delete_and_f6_replacement_purge_all_old_text_records(self):
        for delete in (False, True):
            source = self.fit('我重视公平。我很开心。旧隐私。')
            self.reopen(source, [])
            self.assertTrue(self.core.correction_history(source)['version_history'])
            if delete:
                self.core.input_delete(source)
            else:
                self.core.input_edit(source, '新版普通记录。', True)
                history = self.core.correction_history(source)
                self.assertEqual(history['version_history'], [])
                self.assertEqual(history['history'], [])
                self.assertEqual(self.core.input_get(source)['source_version'], 0)
                self.assertIn(source, read_snapshot(self.path)['training_source_ids'])
            with self.model.store._connect() as db:
                for table in sources.DEPENDENT_TABLES:
                    self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table} WHERE source_id=?', (source,)).fetchone()[0], 0)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_reset_exclusion_and_deliberate_versioned_frozen_reinclusion(self):
        source, other = self.fit(), self.fit()
        self.reopen(source, [])
        self.core.review_version(source, agree=True, **self.guards(source))
        context = self.core.correction_history(source)['fit_context']
        self.zero()
        preview = self.core.replay_preview([source])
        self.assertFalse(preview['items'][0]['eligible'])
        with self.assertRaises(ValueError):
            self.reopen(source, [])
        with self.assertRaises(ValueError):
            self.core.replay_reopen([source], immediate=True, expected_source_versions={source: 1},
                expected_revision=preview['input_revision'], expected_epoch=preview['model_epoch'])
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 0)
        with patch.object(self.model, '_observations', side_effect=AssertionError('must restore frozen fit')):
            restored = self.core.review_version(source, agree=True, **self.guards(source))
        self.assertTrue(restored['restored_fit'])
        self.assertEqual(self.core.correction_history(source)['fit_context'], context)
        self.assertEqual(self.model.state('rational')['value.fairness']['support'], 1)
        self.assertFalse(self.core.input_get(other)['model_active'])

    def test_replay_is_read_only_dependent_explicit_and_renewed(self):
        phrase = '我宁愿给每个人同样的机会'
        teachers = []
        for _ in range(2):
            source = self.core.submit(phrase + '。', partition='rational')['source_id']
            self.core.correction_set(source, expected_revision=0, corrections=[
                {'parameter': 'value.fairness', 'sign': 1, 'evidence': phrase, 'span': [0, len(phrase)]}])
            self.core.review(source, agree=True)
            teachers.append(source)
        pupil = self.fit(phrase + '。')
        frozen = self.model.effects(source_id=pupil)
        preview = self.core.replay_preview([teachers[0]])
        self.assertIn(pupil, preview['items'][0]['dependencies']['dependent_source_ids'])
        self.reopen(teachers[0], [])
        before = self.snapshot()
        preview = self.core.replay_preview([pupil])
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(preview['items'][0]['semantic_change'])
        self.assertTrue(preview['items'][0]['diff']['before']['contributions'])
        self.assertEqual(preview['items'][0]['diff']['after']['contributions'], [])
        self.assertEqual(self.model.effects(source_id=pupil), frozen)
        result = self.core.replay_reopen([pupil], immediate=True, expected_source_versions={pupil: 0},
            expected_revision=preview['input_revision'], expected_epoch=preview['model_epoch'])
        self.assertEqual(result['items'][0]['status'], 'pending')
        self.assertEqual(self.model.effects(source_id=pupil)[:len(frozen)], frozen)
        self.core.review_version(pupil, agree=True, **self.guards(pupil))
        self.assertEqual(self.core.correction_history(pupil)['fit_context']['memories'], [])

    def test_replay_batch_preflight_and_rollback_are_atomic(self):
        first, second = self.fit(), self.fit()
        preview = self.core.replay_preview([first, second])
        args = dict(immediate=True, expected_source_versions={first: 0, second: 0},
                    expected_revision=preview['input_revision'], expected_epoch=preview['model_epoch'])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.core.replay_reopen([first, second], **{**args, 'expected_source_versions': {first: 0, second: 99}})
        self.assertEqual(self.snapshot(), before)
        original = self.model._reopen
        def fail(db, row, corrections, immediate):
            result = original(db, row, corrections, immediate)
            if row['source_id'] == second:
                raise RuntimeError('synthetic second-source failure')
            return result
        with patch.object(self.model, '_reopen', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.core.replay_reopen([first, second], **args)
        self.assertEqual(self.snapshot(), before)
        result = self.core.replay_reopen([first, second], **args)
        self.assertTrue(all(item['input_revision'] == result['input_revision'] for item in result['items']))
        for ids in ([], [first, first], [str(i) for i in range(17)]):
            with self.assertRaises(ValueError):
                self.core.replay_preview(ids)

    def test_candidate_proposal_new_policy_and_legacy_pending_rejected_remain(self):
        source = self.fit()
        with self.model.store._connect() as db:
            for candidate, status in [('legacy-pending', 'pending'), ('legacy-rejected', 'rejected')]:
                db.execute('INSERT INTO candidates(id,source_id,claim,evidence,status,created_at) VALUES (?,?,?,?,?,?)',
                           (candidate, source, '旧候选', '公平', status, 'legacy'))
        before = self.core.candidate_list()
        BrainCore(self.path)
        self.core.revoke(source)
        self.core.review(source, agree=True)
        self.assertEqual(self.core.candidate_list(), before)
        self.core.candidate_review('legacy-pending', accept=True)
        proposed = self.core.candidate_propose(source, '公平', '公平')
        self.assertEqual(proposed['status'], 'accepted')
        with self.assertRaises(ValueError):
            self.core.candidate_review(proposed['candidate_id'], accept=True)
        with self.model.store._connect() as db:
            db.execute('INSERT INTO candidates(id,source_id,claim,evidence,created_at) VALUES (?,?,?,?,?)',
                       ('stale-pending', source, '旧候选', '公平', 'legacy'))
        self.reopen(source, [])
        self.core.review_version(source, agree=True, **self.guards(source))
        with self.assertRaises(ValueError):
            self.core.candidate_review('stale-pending', accept=True)

    def test_version_migration_is_additive_idempotent_and_does_not_publish(self):
        source = self.fit()
        self.core.revoke(source)
        with self.model.store._connect() as db:
            db.execute("DELETE FROM brain_meta WHERE key='version_schema'")
            db.execute('DROP TABLE brain_source_versions')
            for table in ('brain_inputs', 'candidates', 'brain_contributions', 'brain_terms',
                          'brain_fit_context', 'brain_corrections', 'brain_effects'):
                db.execute(f'ALTER TABLE {table} DROP COLUMN source_version')
        with patch('model.sources.initialize_versions', side_effect=RuntimeError('migration failure')):
            with self.assertRaises(RuntimeError):
                BrainModel(self.path)
        reopened = BrainCore(self.path)
        self.assertEqual(reopened.input_get(source)['source_version'], 0)
        before = self.snapshot()
        BrainCore(self.path)
        self.assertEqual(self.snapshot(), before)
        with patch.object(reopened.model, '_observations', side_effect=AssertionError('frozen restore only')):
            reopened.review(source, agree=True)

    def test_versioned_training_trace_collects_effects_without_source_text(self):
        output = io.StringIO()
        with redirect_stderr(output):
            model = BrainModel(self.path, trace=True)
            source = model.submit('我重视公平。我很开心。', partition='rational', exclamation=True)
            model.correction_reopen(source, corrections=[], immediate=True, **self.guards(source))
            model.review_version(source, agree=True, **self.guards(source))
        records = [json.loads(line.split(' ', 1)[1]) for line in output.getvalue().splitlines()
                   if line.startswith('[alpha.model] ')]
        for operation in ('correction_reopen', 'review_version'):
            self.assertTrue(any(r['event'] == 'param_update' and r['operation'] == operation for r in records))
        self.assertNotIn('公平', output.getvalue())
        self.assertNotIn('开心', output.getvalue())


if __name__ == '__main__':
    unittest.main()
