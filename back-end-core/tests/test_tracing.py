"""Terminal metadata tests using synthetic input and temporary SQLite only."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from core.api import BrainAPI, serve
from model import BrainModel
from model.tracing import PREFIX


class TracingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'brain.sqlite3'
        self.stderr = io.StringIO()
        with redirect_stderr(self.stderr):
            self.model = BrainModel(self.path, trace=True)

    def records(self):
        return [json.loads(line[len(PREFIX):]) for line in self.stderr.getvalue().splitlines()
                if line.startswith(PREFIX)]

    def events(self):
        return [row['event'] for row in self.records()]

    def test_saved_then_confirmed_fit_parameter_updates_without_raw_material(self):
        text = 'TRACE_PRIVATE_SENTINEL 我重视公平。'
        with redirect_stderr(self.stderr):
            source = self.model.submit(text, partition='rational', source_ref='PRIVATE_FILENAME.md')
        self.assertIn('operation_received', self.events())
        self.assertIn('data_saved', self.events())
        self.assertNotIn('fit_committed', self.events())
        self.assertEqual(self.records()[0]['db_path'], str(self.path))
        with redirect_stderr(self.stderr):
            result = self.model.review(source, agree=True)
        records = self.records()
        judgement = [r for r in records if r['event'] == 'judgement'][-1]
        self.assertTrue(judgement['immediate'] and judgement['confirm'])
        changes = [r for r in records if r['event'] == 'param_update']
        self.assertEqual(changes[0]['before'], 0)
        self.assertEqual(changes[0]['after'], result['effects'][0]['after'])
        self.assertEqual(changes[0]['support_after'], 1)
        self.assertLess(self.events().index('operation_committed'), self.events().index('param_update'))
        self.assertIn('fit_committed', self.events())
        self.assertNotIn('TRACE_PRIVATE_SENTINEL', self.stderr.getvalue())
        self.assertNotIn('PRIVATE_FILENAME', self.stderr.getvalue())
        self.assertFalse(any('evidence' in row or 'text' in row for row in records))

    def test_exclamation_zero_effect_fit_and_repeat_do_not_claim_duplicate_training(self):
        with redirect_stderr(self.stderr):
            source = self.model.submit('不含参数的合成文字', partition='emotional',
                                       immediate=False, exclamation=True)
            self.model.review(source, agree=True)
        fits = [r for r in self.records() if r['event'] == 'fit_committed']
        self.assertEqual(len(fits), 1)
        self.assertEqual(fits[0]['parameter_count'], 0)
        self.assertNotIn('param_update', self.events())
        self.assertEqual([r['reason'] for r in self.records() if r['event'] == 'fit_skipped'], ['unchanged'])

    def test_false_and_preview_never_emit_actual_fit_or_updates(self):
        with redirect_stderr(self.stderr):
            source = self.model.submit('我重视自由。', partition='rational', immediate=False)
            self.model.preview(source)
        self.assertNotIn('fit_committed', self.events())
        self.assertNotIn('param_update', self.events())
        self.assertIn('not_dual_true', [r.get('reason') for r in self.records()])

    def test_failure_after_recompute_does_not_print_rolled_back_updates(self):
        with redirect_stderr(self.stderr):
            source = self.model.submit('我重视自由。', partition='rational')
        original = self.model._recompute
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('PRIVATE_EXCEPTION_MESSAGE')
        with redirect_stderr(self.stderr), patch.object(self.model, '_recompute', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.model.review(source, agree=True)
        self.assertIn('operation_failed', self.events())
        self.assertNotIn('param_update', self.events())
        self.assertNotIn('fit_committed', self.events())
        self.assertNotIn('PRIVATE_EXCEPTION_MESSAGE', self.stderr.getvalue())
        self.assertEqual(self.model.state('rational')['value.autonomy']['support'], 0)

    def test_delete_emits_actual_removed_params_only_after_success(self):
        with redirect_stderr(self.stderr):
            source = self.model.submit('我重视自由。', partition='rational', exclamation=True)
        self.stderr.seek(0)
        self.stderr.truncate()
        with redirect_stderr(self.stderr):
            self.model.input_delete(source)
        updates = [r for r in self.records() if r['event'] == 'param_update']
        self.assertEqual(updates[0]['after'], 0)
        self.assertEqual(updates[0]['operation'], 'input_delete')
        self.assertIn('source_deleted', self.events())

    def test_reset_and_correction_logs_no_labels_or_sensitive_phrases(self):
        with redirect_stderr(self.stderr):
            source = self.model.submit('私人合成句子', partition='rational')
            self.model.correction_set(source, expected_revision=0, corrections=[{
                'parameter': 'value.autonomy', 'sign': 1, 'evidence': '私人合成句子', 'span': [0, 6]}])
            info = self.model.reset_info()
            self.model.reset_model(confirmation='RESET_MODEL', expected_epoch=info['model_epoch'],
                                   expected_revision=info['input_revision'])
        event = [r for r in self.records() if r['event'] == 'model_reset'][0]
        self.assertTrue(event['translator_preserved'])
        self.assertEqual(event['model_epoch'], 1)
        self.assertNotIn('私人合成句子', self.stderr.getvalue())

    def test_broken_stderr_cannot_change_committed_result(self):
        class Broken:
            def write(self, _):
                raise OSError('synthetic broken pipe')
            def flush(self):
                raise OSError('synthetic broken pipe')
        with redirect_stderr(Broken()):
            source = self.model.submit('我重视自由。', partition='rational', exclamation=True)
        self.assertEqual(self.model.state('rational')['value.autonomy']['support'], 1)
        self.assertEqual(self.model.store.get_source(source)['body'], '我重视自由。')

    def test_serve_stdout_is_still_exact_json_envelope(self):
        with redirect_stderr(self.stderr):
            api = BrainAPI(self.path, trace=True)
            request = dict(schema_version=1, id='trace', method='submit',
                           params=dict(text='我重视自由。', partition='rational', exclamation=True))
            output = io.StringIO()
            serve(api, io.StringIO(json.dumps(request) + '\n'), output)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])['id'], 'trace')
        self.assertIn('fit_committed', self.events())
        self.assertNotIn(PREFIX, output.getvalue())

    def test_real_cli_and_api_enabled_by_default_and_quiet_switch(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'ALPHA_BRAIN_TRACE': '1'}
        for quiet in (False, True):
            args = [sys.executable, '-m', 'model', '--db', str(self.path)]
            if quiet:
                args.append('--quiet')
            process = subprocess.run(args + ['submit', '--partition', 'rational', '--exclamation',
                                            '--text', 'SUBPROCESS_SECRET 我重视自由。'],
                                     cwd=root, env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout)['status'], 'agreed')
            self.assertEqual(PREFIX in process.stderr, not quiet)
            self.assertNotIn('SUBPROCESS_SECRET', process.stderr)
        request = dict(schema_version=1, id='real-trace', method='health', params={})
        process = subprocess.run([sys.executable, '-m', 'core.api', '--db', str(self.path)],
                                 input=json.dumps(request)+'\n', cwd=root, env=env,
                                 text=True, capture_output=True, timeout=10)
        self.assertTrue(json.loads(process.stdout)['ok'])
        self.assertIn(PREFIX, process.stderr)
        env['ALPHA_BRAIN_TRACE'] = '0'
        process = subprocess.run([sys.executable, '-m', 'core.api', '--db', str(self.path)],
                                 input=json.dumps(request)+'\n', cwd=root, env=env,
                                 text=True, capture_output=True, timeout=10)
        self.assertTrue(json.loads(process.stdout)['ok'])
        self.assertNotIn(PREFIX, process.stderr)
