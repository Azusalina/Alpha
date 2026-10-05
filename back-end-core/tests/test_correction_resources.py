"""Synthetic call budgets and an independent, frozen pre-reuse validator.

Run the optional bounded benchmark with this module's --benchmark argument.
No persistent database, tokenizer, encoder, network or private fixture is used.
"""

import copy
import gc
import itertools
import json
import statistics
import sys
import time
import tracemalloc
import unittest
from unittest.mock import patch

from model.catalog import PARAMETERS
from model.corrections import validate_corrections
from translator import translate
from translator.learning import own_chat_ranges


def legacy_validate_corrections(text, kind, self_speaker, corrections):
    """Frozen old algorithm; intentionally independent of the new validator."""
    if not isinstance(corrections, list) or len(corrections) > 64:
        raise ValueError("corrections must be an array of at most 64 items")
    checked, seen = [], set()
    author_ranges = own_chat_ranges(text, self_speaker) if kind == "chat" else [(0, len(text))]
    for item in corrections:
        if isinstance(item, dict) and "type" in item:
            if set(item) != {"type", "value", "sign", "evidence", "span"}:
                raise ValueError("typed correction needs type, value, sign, evidence and span")
            family = item['type']
            span = item['span']
            if (not isinstance(item['value'], str) or not isinstance(item['evidence'], str)
                    or not isinstance(span, list) or len(span) != 2
                    or any(type(v) is not int for v in span)
                    or not 0 <= span[0] < span[1] <= len(text)
                    or text[span[0]:span[1]] != item['evidence']
                    or not any(a <= span[0] < span[1] <= b for a, b in author_ranges)):
                raise ValueError("annotation needs exact self-authored evidence span")
            if not isinstance(family, str) or family not in ('event', 'intent', 'tone', 'candidate'):
                raise ValueError("unknown annotation type")
            if type(item['sign']) is not int or item['sign'] not in (0, 1):
                raise ValueError("annotation sign must be 0 (suppress) or 1 (retain)")
            report = translate(text, kind='diary' if kind == 'philosophy' else kind,
                               self_speaker=self_speaker)
            pool = (report['cues'] if family == 'event' else report['candidates'])
            pool = [r for r in pool if (family != 'event' or r['category'] == 'event_word')
                    and (family != 'intent' or r['type'] == 'contact_intention')
                    and (family != 'tone' or r['type'] == 'textual_emotion')]
            targets = [r for r in pool
                       if all(r[k] == item[k] for k in ('value', 'evidence', 'span'))]
            if not targets:
                raise ValueError("annotation must target exact existing translator output")
            keys = {('cue' if family == 'event' else 'candidate',
                     r['category'] if family == 'event' else r['type'],
                     r['value'], r['evidence'], tuple(r['span'])) for r in targets}
            if keys & seen:
                raise ValueError("duplicate annotation target")
            seen.update(keys)
            checked.append({**item, 'span': list(item['span'])})
            continue
        if not isinstance(item, dict) or set(item) != {"parameter", "sign", "evidence", "span"}:
            raise ValueError("each correction needs parameter, sign, evidence and span")
        parameter, sign, evidence, span = (item[field] for field in ("parameter", "sign", "evidence", "span"))
        if not isinstance(parameter, str) or parameter not in PARAMETERS or parameter in seen:
            raise ValueError("correction parameter must be known and unique")
        if type(sign) is not int or sign not in (-1, 0, 1):
            raise ValueError("correction sign must be -1, 0 or 1")
        if sign == -1 and not parameter.startswith("value."):
            raise ValueError("non-value cues support only sign 0 or 1")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("correction evidence must contain text")
        if (not isinstance(span, list) or len(span) != 2 or any(type(v) is not int for v in span)
                or not 0 <= span[0] < span[1] <= len(text) or text[span[0]:span[1]] != evidence):
            raise ValueError("correction span must select its exact evidence in the source")
        if not any(start <= span[0] and span[1] <= end for start, end in author_ranges):
            raise ValueError("chat correction must belong to the self speaker")
        checked.append({"parameter": parameter, "sign": sign, "evidence": evidence,
                        "span": list(span)})
        seen.add(parameter)
    return checked


def annotation(text, family, value, evidence, sign=1, start=None):
    start = text.index(evidence) if start is None else start
    return dict(type=family, value=value, sign=sign, evidence=evidence,
                span=[start, start + len(evidence)])


def parameter(text, name='value.fairness', sign=1, evidence='我', start=None):
    start = text.index(evidence) if start is None else start
    return dict(parameter=name, sign=sign, evidence=evidence,
                span=[start, start + len(evidence)])


def long_case():
    """64 distinct tone targets in a bounded, neutral synthetic diary."""
    block = '中性记录' * 384 + '。我很开心。\n'
    text = block * 64
    batch = [annotation(text, 'tone', 'happiness', '开心', sign=i % 2,
                        start=i * len(block) + block.index('开心')) for i in range(64)]
    return text, batch


class CorrectionResourceTests(unittest.TestCase):
    def compare(self, text, batch, calls, *, kind='diary', speaker=None,
                expected=None, error=None):
        before = copy.deepcopy(batch)
        outcomes = []
        budgets = []
        for validator, target in ((legacy_validate_corrections, __name__ + '.translate'),
                                  (validate_corrections, 'model.corrections.translate')):
            with patch(target, wraps=translate) as spy:
                try:
                    outcomes.append(('ok', validator(text, kind, speaker, batch)))
                except Exception as exc:
                    outcomes.append(('error', type(exc), str(exc)))
                budgets.append(spy.call_count)
                self.assertEqual(batch, before)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(budgets[1], calls)
        # Old parsing occurred once for each typed item reached, up to the error.
        self.assertEqual(budgets[1], min(budgets[0], 1))
        if error is not None:
            self.assertEqual(outcomes[1], ('error', ValueError, error))
        else:
            self.assertEqual(outcomes[1], ('ok', batch if expected is None else expected))
        return budgets

    def test_empty_parameter_only_and_batch_gate_do_not_translate(self):
        text = '我重视公平。'
        self.compare('', [], 0)
        for sign in (-1, 0, 1):
            self.compare(text, [parameter(text, sign=sign)], 0)
        all_parameters = [parameter(text, name=name) for name in PARAMETERS]
        self.compare(text, all_parameters, 0)
        # Parameter-only validation still does not demand a translator kind.
        self.compare(text, all_parameters, 0, kind='not-a-translator-kind')
        for batch in (None, (), {}, 'bad', [parameter(text)] * 65):
            with self.subTest(batch=type(batch)):
                self.compare(text, batch, 0,
                             error='corrections must be an array of at most 64 items')
        text, typed = long_case()
        self.compare(text, typed + [typed[0]], 0,
                     error='corrections must be an array of at most 64 items')

    def test_64_distinct_targets_use_one_translation(self):
        text, batch = long_case()
        self.assertEqual(len({tuple(item['span']) for item in batch}), 64)
        self.assertEqual(self.compare(text, batch, 1), [64, 1])

    def test_all_families_signs_orders_and_mixed_parameters(self):
        text = '𠮷🙂。我取消约会。我很开心。我不再主动联系。'
        event = annotation(text, 'event', 'cancellation', '取消')
        tone = annotation(text, 'tone', 'happiness', '开心')
        intent = annotation(text, 'intent', 'less_initiative', '我不再主动联系')
        for kind in ('diary', 'philosophy'):
            for tone_family, intent_family in itertools.product(('tone', 'candidate'),
                                                               ('intent', 'candidate')):
                for signs in itertools.product((0, 1), repeat=3):
                    items = [dict(event, sign=signs[0]),
                             dict(tone, type=tone_family, sign=signs[1]),
                             dict(intent, type=intent_family, sign=signs[2])]
                    for order in itertools.permutations(items):
                        with self.subTest(kind=kind, families=(tone_family, intent_family),
                                          signs=signs, order=[i['type'] for i in order]):
                            batch = [parameter(text, sign=-1), *order,
                                     parameter(text, name='value.autonomy', sign=0)]
                            self.compare(text, batch, 1, kind=kind)
        for item in (event, tone, intent):
            self.compare(text, [item], 1)

    def test_aliases_duplicates_and_distinct_repeated_positions(self):
        text = '我很开心。我很开心。我不再主动联系。我不再主动联系。我取消约会。我取消约会。'
        for family, value, evidence in (('tone', 'happiness', '开心'),
                                        ('intent', 'less_initiative', '我不再主动联系'),
                                        ('event', 'cancellation', '取消')):
            first = annotation(text, family, value, evidence)
            aliases = (family,) if family == 'event' else (family, 'candidate')
            for families in itertools.product(aliases, repeat=2):
                for signs in itertools.product((0, 1), repeat=2):
                    with self.subTest(families=families, signs=signs):
                        self.compare(text, [dict(first, type=f, sign=s)
                                            for f, s in zip(families, signs)], 1,
                                     error='duplicate annotation target')
            later = text.index(evidence, first['span'][1])
            second = annotation(text, 'event' if family == 'event' else 'candidate',
                                value, evidence, start=later)
            self.compare(text, [first, second], 1)

    def test_cue_and_candidate_identity_remain_separate_at_same_position(self):
        text = '取消'
        # Isolate identity semantics with a deterministic synthetic report.
        report = {'cues': [dict(category='event_word', value='cancellation',
                               evidence=text, span=[0, 2])],
                  'candidates': [dict(type='contact_intention', value='cancellation',
                                     evidence=text, span=[0, 2])]}
        before = copy.deepcopy(report)
        batch = [annotation(text, 'event', 'cancellation', text),
                 annotation(text, 'candidate', 'cancellation', text, sign=0)]
        for validator, target, count in ((legacy_validate_corrections, __name__ + '.translate', 2),
                                         (validate_corrections, 'model.corrections.translate', 1)):
            with patch(target, return_value=report) as spy:
                self.assertEqual(validator(text, 'diary', None, batch), batch)
                self.assertEqual(spy.call_count, count)
            self.assertEqual(report, before)

    def test_malformed_typed_fields_preserve_pretranslation_errors(self):
        text = '我很开心。'
        good = annotation(text, 'tone', 'happiness', '开心')
        cases = []
        shape = 'typed correction needs type, value, sign, evidence and span'
        exact = 'annotation needs exact self-authored evidence span'
        for field in good:
            cases.append(({k: v for k, v in good.items() if k != field},
                          shape if field != 'type' else 'each correction needs parameter, sign, evidence and span'))
        cases.append((dict(good, extra=1), shape))
        for field in ('value', 'evidence'):
            for bad in (None, False, 1, [], {}):
                cases.append((dict(good, **{field: bad}), exact))
        for span in (None, (2, 4), '2,4', [], [2], [2, 4, 5], [True, 4], [2, 4.0],
                     [-1, 4], [4, 2], [2, 2], [2, 99], [0, 2]):
            cases.append((dict(good, span=span), exact))
        cases.append((dict(good, evidence='開心'), exact))
        for family in (None, [], {}, 1, 'unknown'):
            cases.append((dict(good, type=family), 'unknown annotation type'))
        for sign in (-1, 2, True, False, 1.0, '1', None, [], {}):
            cases.append((dict(good, sign=sign), 'annotation sign must be 0 (suppress) or 1 (retain)'))
        for item, error in cases:
            with self.subTest(item=item):
                self.compare(text, [item], 0, error=error)
                self.compare(text, [parameter(text), item], 0, error=error)
                self.compare(text, [good, item], 1, error=error)
        # Evidence errors still precede family/sign errors.
        self.compare(text, [dict(good, span=[0, 2], type='unknown', sign=-1)], 0, error=exact)

    def test_malformed_parameters_and_invalid_batch_order(self):
        text = '我很开心。'
        good = parameter(text)
        tone = annotation(text, 'tone', 'happiness', '开心')
        cases = [(None, 'each correction needs parameter, sign, evidence and span'),
                 ([], 'each correction needs parameter, sign, evidence and span'),
                 ({}, 'each correction needs parameter, sign, evidence and span'),
                 (dict(good, extra=1), 'each correction needs parameter, sign, evidence and span')]
        for name in (None, [], {}, 1, 'unknown'):
            cases.append((dict(good, parameter=name), 'correction parameter must be known and unique'))
        for sign in (True, False, 1.0, None, 2, '1', [], {}):
            cases.append((dict(good, sign=sign), 'correction sign must be -1, 0 or 1'))
        nonvalue = next(name for name in PARAMETERS if not name.startswith('value.'))
        cases.append((dict(good, parameter=nonvalue, sign=-1), 'non-value cues support only sign 0 or 1'))
        for evidence in ('', ' ', None, 1, [], {}):
            cases.append((dict(good, evidence=evidence), 'correction evidence must contain text'))
        for span in (None, (0, 1), [], [0], [0, 1, 2], [False, 1], [0, 1.0],
                     [-1, 1], [1, 0], [0, 0], [0, 99], [1, 2]):
            cases.append((dict(good, span=span), 'correction span must select its exact evidence in the source'))
        for item, error in cases:
            with self.subTest(item=item):
                self.compare(text, [item, tone], 0, error=error)
                self.compare(text, [tone, item], 1, error=error)
        self.compare(text, [good, tone, good], 1,
                     error='correction parameter must be known and unique')
        missing = dict(tone, value='invented')
        self.compare(text, [missing, {}], 1,
                     error='annotation must target exact existing translator output')
        self.compare(text, [{}, missing], 0,
                     error='each correction needs parameter, sign, evidence and span')

    def test_exact_targets_and_family_filters(self):
        text = '我很开心。我不再主动联系。'
        tone = annotation(text, 'tone', 'happiness', '开心')
        intent = annotation(text, 'intent', 'less_initiative', '我不再主动联系')
        for item in (dict(tone, value='invented'), dict(tone, type='event'),
                     dict(tone, type='intent'), dict(intent, type='tone'),
                     annotation(text, 'tone', 'happiness', '我很开心'),
                     annotation(text, 'tone', 'happiness', '开')):
            self.compare(text, [item], 1,
                         error='annotation must target exact existing translator output')

    def test_quotes_code_negation_and_source_kinds(self):
        for protected in ('“我很开心”', '「我很开心」', '"我很开心"', '`我很开心`',
                          '```我很开心```', '> 我很开心', '我不开心', '朋友说我很开心'):
            for kind in ('diary', 'philosophy'):
                text = protected + '。\n我很开心。'
                with self.subTest(text=text, kind=kind):
                    blocked = annotation(text, 'tone', 'happiness', '开心')
                    good = annotation(text, 'tone', 'happiness', '开心', start=text.rindex('开心'))
                    self.compare(text, [blocked], 1, kind=kind,
                                 error='annotation must target exact existing translator output')
                    self.compare(text, [good], 1, kind=kind)
        # Event words remain lexical cues even inside protected/nonassertive text.
        for text in ('“我取消约会”', '`我取消约会`', '我不取消约会'):
            self.compare(text, [annotation(text, 'event', 'cancellation', '取消')], 1)

    def test_chat_exact_speaker_ranges_and_crlf_unicode_offsets(self):
        text = '𠮷🙂：我很开心。\r\n我甲: 我很开心。\r\n我：我很开心。\r\n我很开心。\r\n我: 我不再主动联系。'
        own_start = text.index('开心', text.index('我：'))
        good = annotation(text, 'tone', 'happiness', '开心', start=own_start)
        intent = annotation(text, 'intent', 'less_initiative', '我不再主动联系')
        self.compare(text, [good, parameter(text, start=own_start - 2), intent], 1,
                     kind='chat', speaker='我')
        for start in (text.index('开心'), text.index('开心', text.index('我甲:')),
                      text.index('开心', text.index('\r\n我很开心'))):
            item = annotation(text, 'tone', 'happiness', '开心', start=start)
            self.compare(text, [item], 0, kind='chat', speaker='我',
                         error='annotation needs exact self-authored evidence span')
        self.compare(text, [parameter(text, start=text.index('我很开心'))], 0,
                     kind='chat', speaker='我', error='chat correction must belong to the self speaker')
        cross = annotation(text, 'candidate', 'happiness', text[own_start:text.index('我不再主动联系')])
        self.compare(text, [cross], 0, kind='chat', speaker='我',
                     error='annotation needs exact self-authored evidence span')
        self.compare(text, [good], 0, kind='chat', speaker=None,
                     error='annotation needs exact self-authored evidence span')

    def test_request_local_snapshot_arguments_and_translation_exceptions(self):
        with patch('model.corrections.translate', wraps=translate) as spy:
            for kind in ('diary', 'philosophy', 'chat'):
                text = '我: 我很开心。我很开心。' if kind == 'chat' else '我很开心。我很开心。'
                speaker = '我' if kind == 'chat' else None
                batch = [annotation(text, 'tone', 'happiness', '开心'),
                         annotation(text, 'candidate', 'happiness', '开心', start=text.rindex('开心'))]
                self.assertEqual(validate_corrections(text, kind, speaker, batch), batch)
                spy.assert_called_with(text, kind='diary' if kind == 'philosophy' else kind,
                                       self_speaker=speaker)
            self.assertEqual(spy.call_count, 3)
        text = '我很开心。'
        batch = [annotation(text, 'tone', 'happiness', '开心')]
        for kind, speaker, error in (('bad', None, 'kind must be diary or chat'),
                                      ('diary', '', 'self_speaker must contain text')):
            self.compare(text, batch, 1, kind=kind, speaker=speaker, error=error)
        for validator, target in ((legacy_validate_corrections, __name__ + '.translate'),
                                  (validate_corrections, 'model.corrections.translate')):
            failure = RuntimeError('synthetic translator failure')
            with patch(target, side_effect=failure) as spy:
                with self.assertRaises(RuntimeError) as raised:
                    validator(text, 'diary', None, batch)
                self.assertIs(raised.exception, failure)
                self.assertEqual(spy.call_count, 1)

    def test_no_input_output_or_report_alias_mutation(self):
        text = '我取消约会。我很开心。'
        shared = [8, 10]
        batch = [dict(type='tone', value='happiness', sign=0, evidence='开心', span=shared),
                 dict(parameter='value.fairness', sign=-1, evidence='开心', span=shared)]
        before = copy.deepcopy(batch)
        report = translate(text)
        report_before = copy.deepcopy(report)
        with patch('model.corrections.translate', return_value=report) as spy:
            output = validate_corrections(text, 'diary', None, batch)
            self.assertEqual(spy.call_count, 1)
        self.assertEqual(output, before)
        self.assertEqual(batch, before)
        self.assertEqual(report, report_before)
        self.assertIsNot(output, batch)
        for old, new in zip(batch, output):
            self.assertIsNot(old, new)
            self.assertIsNot(old['span'], new['span'])
        self.assertIsNot(output[0]['span'], output[1]['span'])
        output[0]['span'][0] = 999
        output[1]['sign'] = 0
        self.assertEqual(batch, before)
        self.assertEqual(report, report_before)
        shared[0] = -99
        self.assertEqual(output[1]['span'], [8, 10])


def benchmark():
    """Separate timing and Python allocation trials; no walltime assertion."""
    text, batch = long_case()
    repetitions = 3
    results = {'python': sys.version, 'characters': len(text),
               'utf8_bytes': len(text.encode('utf-8')), 'typed_targets': len(batch),
               'distinct_spans': len({tuple(item['span']) for item in batch}),
               'report_cues': len(translate(text)['cues']),
               'report_candidates': len(translate(text)['candidates']),
               'repetitions': repetitions}
    for label, validator, target in (
            ('before', legacy_validate_corrections, __name__ + '.translate'),
            ('after', validate_corrections, 'model.corrections.translate')):
        # Count calls separately so mocking/allocation tracing do not affect timing.
        with patch(target, wraps=translate) as spy:
            assert validator(text, 'diary', None, batch) == batch
            calls = spy.call_count
        validator(text, 'diary', None, batch)  # warm-up, outside measurements
        seconds, peaks = [], []
        for _ in range(repetitions):
            gc.collect()
            started = time.perf_counter()
            result = validator(text, 'diary', None, batch)
            seconds.append(time.perf_counter() - started)
            assert result == batch
            del result
        for _ in range(repetitions):
            gc.collect()
            tracemalloc.start()
            try:
                result = validator(text, 'diary', None, batch)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            assert result == batch
            peaks.append(peak)
            del result
        results[label] = {'translate_calls': calls, 'seconds': seconds,
                          'median_seconds': statistics.median(seconds),
                          'python_peak_bytes': peaks,
                          'median_python_peak_bytes': statistics.median(peaks)}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    if sys.argv[1:] == ['--benchmark']:
        benchmark()
    else:
        unittest.main()
