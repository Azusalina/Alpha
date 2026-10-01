"""Bounded, text-free terminal telemetry; stdout remains the API channel."""

from __future__ import annotations

import json
import re
import sys
import time
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from .catalog import PARAMETERS, PARTITIONS

PREFIX = '[alpha.model] '
_pending = ContextVar('alpha_model_trace_pending', default=None)
_SOURCE = re.compile(r'[0-9a-f]{32}\Z')


class ModelTrace:
    def __init__(self, path, enabled=False):
        self.enabled = enabled
        self.path = str(Path(path).absolute())

    def emit(self, event, operation=None, **fields):
        if not self.enabled:
            return
        record = {'event': event, 'time_ms': time.time_ns() // 1_000_000}
        if operation is not None:
            record['operation'] = operation
        # Explicit field construction only: never pass a request, result, error
        # message, source_ref, evidence, phrase, speaker or correction payload.
        record.update(fields)
        try:
            sys.stderr.write(PREFIX + json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n')
            sys.stderr.flush()
        except Exception:
            pass  # A closed diagnostic sink must not turn a committed write into failure.

    def collect(self, effect):
        pending = _pending.get()
        if pending is not None and pending[0] is self:
            pending[1].append({key: effect[key] for key in (
                'source_id', 'partition', 'parameter', 'before', 'after', 'delta',
                'support_before', 'support_after', 'revision', 'model_epoch')})

    def committed(self, operation, result, effects):
        identity = {}
        source = result.get('source_id')
        if isinstance(source, str) and _SOURCE.fullmatch(source):
            identity['source_id'] = source
        if result.get('partition') in PARTITIONS:
            identity['partition'] = result['partition']
        self.emit('operation_committed', operation, **identity)
        if operation in ('submit', 'input_edit', 'correction_set'):
            self.emit('data_saved', operation, db_path=self.path, **identity)
        if 'immediate' in result:
            self.emit('judgement', operation, **identity,
                      immediate=result['immediate'], confirm=result['confirm'],
                      exclamation=result['exclamation'], status=result['status'])
        for effect in effects:
            if effect['parameter'] in PARAMETERS:
                self.emit('param_update', operation, **effect)
        if operation in ('submit', 'review'):
            if 'observed_terms' in result and result.get('status') == 'agreed':
                self.emit('fit_committed', operation, **identity, parameter_count=len(effects),
                          observed_terms=result['observed_terms'], restored_fit=result['restored_fit'])
            else:
                reason = 'unchanged' if result.get('status') == 'agreed' else 'not_dual_true'
                self.emit('fit_skipped', operation, **identity, reason=reason)
        if operation == 'input_delete':
            self.emit('source_deleted', operation, **identity)
        if operation == 'reset_model':
            self.emit('model_reset', operation, model_epoch=result['model_epoch'],
                      previous_epoch=result['previous_epoch'], translator_preserved=True)


def traced(operation):
    """Report success only after the method's SQLite context has committed."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            trace = self.trace
            if not trace.enabled:
                return function(self, *args, **kwargs)
            received = {}
            if operation != 'submit':
                source = kwargs.get('source_id', args[0] if args else None)
                if isinstance(source, str) and _SOURCE.fullmatch(source):
                    received['source_id'] = source
            if operation in ('submit', 'input_edit'):
                text = kwargs.get('text', args[0] if operation == 'submit' and args else
                                  args[1] if len(args) > 1 else None)
                if isinstance(text, str):
                    received['char_count'] = min(len(text), 1_000_001)
            trace.emit('operation_received', operation, **received)
            effects = []
            token = _pending.set((trace, effects))
            try:
                result = function(self, *args, **kwargs)
            except Exception as error:
                name = type(error).__name__
                if name not in ('ValueError', 'KeyError', 'RuntimeError', 'OSError',
                                'OperationalError', 'IntegrityError', 'DatabaseError'):
                    name = 'Exception'
                trace.emit('operation_failed', operation, error_type=name)
                raise
            finally:
                _pending.reset(token)
            try:
                trace.committed(operation, result, effects)
            except Exception:
                pass  # Telemetry formatting also must not mask a committed result.
            return result
        return wrapped
    return decorate
