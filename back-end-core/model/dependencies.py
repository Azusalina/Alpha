"""Recorded learning-input exposure and a read-only logical impact projection.

No inference, historic reconstruction, fitting, or automatic replay takes place
here. A complete graph means complete recorded coverage, not causal validation.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import deque
from itertools import islice

from . import relations, reset

CAP = 128
SCAN_CAP = 1000
_FIT = re.compile(r'[0-9a-f]{32}\Z')
_TERM = re.compile(r'[\u3400-\u9fff]{2,8}\Z')
_FIELDS = {'version', 'fit_id', 'input_revision', 'model_epoch', 'scope',
           'tokenizer_terms', 'tokenizer_terms_total', 'tokenizer_terms_truncated',
           'tokenizer_sources', 'tokenizer_sources_truncated', 'rule_sources',
           'rule_sources_truncated', 'complete'}
_REF_FIELDS = {'source_id', 'source_version', 'fit_id'}


def _invalid() -> None:
    # Never echo private stored metadata or decoder diagnostics into the API.
    raise ValueError('invalid dependency provenance')


def _source_id(value: object) -> bool:
    return (isinstance(value, str) and bool(value.strip()) and '\0' not in value
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value))


def _integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _fit_id(value: object) -> bool:
    return value is None or isinstance(value, str) and _FIT.fullmatch(value) is not None


def validate_request(source_ids: list[str], limit: int) -> None:
    if (not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 16
            or any(not _source_id(s) for s in source_ids)
            or len(set(source_ids)) != len(source_ids)):
        raise ValueError('source_ids must contain 1 to 16 unique valid source IDs')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer from 1 to 100')


def validate(value: object) -> dict:
    """Validate the closed v1 metadata, including cross-field consistency."""
    if not isinstance(value, dict) or set(value) != _FIELDS:
        _invalid()
    if (type(value['version']) is not int or value['version'] != 1
            or value['scope'] != 'available_learning_inputs'
            or not _fit_id(value['fit_id'])
            or any(not _integer(value[k]) for k in
                   ('input_revision', 'model_epoch', 'tokenizer_terms_total'))
            or any(type(value[k]) is not bool for k in
                   ('tokenizer_terms_truncated', 'tokenizer_sources_truncated',
                    'rule_sources_truncated', 'complete'))):
        _invalid()
    terms = value['tokenizer_terms']
    if (not isinstance(terms, list) or len(terms) > CAP
            or any(not isinstance(t, str) or _TERM.fullmatch(t) is None for t in terms)
            or terms != sorted(set(terms))):
        _invalid()
    total = value['tokenizer_terms_total']
    if (len(terms) != min(total, CAP)
            or value['tokenizer_terms_truncated'] != (total > CAP)):
        _invalid()
    unknown = False
    for kind in ('tokenizer', 'rule'):
        refs = value[kind + '_sources']
        if not isinstance(refs, list) or len(refs) > CAP:
            _invalid()
        for ref in refs:
            if (not isinstance(ref, dict) or set(ref) != _REF_FIELDS
                    or not _source_id(ref['source_id'])
                    or not _integer(ref['source_version']) or not _fit_id(ref['fit_id'])):
                _invalid()
            unknown |= ref['fit_id'] is None
        ids = [r['source_id'] for r in refs]
        if ids != sorted(set(ids)) or (value[kind + '_sources_truncated'] and len(refs) != CAP):
            _invalid()
    if not terms and (value['tokenizer_sources'] or value['tokenizer_sources_truncated']):
        _invalid()
    complete = not (unknown or any(value[k] for k in
                    ('tokenizer_terms_truncated', 'tokenizer_sources_truncated', 'rule_sources_truncated')))
    if value['complete'] != complete:
        _invalid()
    return value


def _context(payload: str) -> dict:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _invalid()
            result[key] = value
        return result

    try:
        context = json.loads(payload, object_pairs_hook=unique_object,
                             parse_constant=lambda _: _invalid())
    except (ValueError, TypeError, RecursionError):
        _invalid()
    if not isinstance(context, dict):
        _invalid()
    return context


def _provenance(context: dict) -> dict | None:
    # Absence alone is legacy. Present null/invalid typed metadata fails closed.
    return validate(context['dependency_provenance']) if 'dependency_provenance' in context else None


def _identity(db: sqlite3.Connection, source_id: str) -> tuple[int, str | None] | None:
    row = db.execute(
        'SELECT i.source_version, f.payload FROM brain_inputs i '
        'JOIN brain_fit_context f ON f.source_id=i.source_id AND f.source_version=i.source_version '
        'WHERE i.source_id=?', (source_id,)).fetchone()
    if row is None:
        return None
    provenance = _provenance(_context(row['payload']))
    return row['source_version'], provenance['fit_id'] if provenance else None


def _bounded_supports(rules: list[dict], *, legacy: bool = False) -> tuple[dict[str, int | None], bool]:
    """Keep only the lexicographically first 128 IDs, even for large rule pools."""
    kept, truncated = {}, False
    if not isinstance(rules, list):
        _invalid()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('support_source_ids'), list):
            _invalid()
        versions = rule.get('support_source_versions', {})
        if not isinstance(versions, dict):
            _invalid()
        for source_id in rule['support_source_ids']:
            if not _source_id(source_id):
                _invalid()
            version = versions.get(source_id)
            if not _integer(version) and not (legacy and version is None):
                _invalid()
            if source_id in kept and kept[source_id] != version:
                _invalid()
            kept[source_id] = version
            if len(kept) > CAP:
                del kept[max(kept)]
                truncated = True
    return dict(sorted(kept.items())), truncated


def capture(db: sqlite3.Connection, row: sqlite3.Row, configured: tuple[str, ...],
            rules: list[dict]) -> dict:
    """Called inside the extraction snapshot; select no source bodies."""
    terms = list(configured[:CAP])
    tokenizer_refs = []
    tokenizer_truncated = False
    if terms:
        placeholders = ','.join('?' for _ in terms)
        # <=129 bindings, DISTINCT provider IDs and one payload at a time.
        providers = db.execute(
            'SELECT i.source_id, i.source_version, f.payload FROM brain_inputs i '
            'LEFT JOIN brain_fit_context f ON f.source_id=i.source_id AND f.source_version=i.source_version '
            "WHERE i.status='agreed' AND i.partition=? AND EXISTS ("
            'SELECT 1 FROM brain_terms t WHERE t.source_id=i.source_id '
            f'AND t.source_version=i.source_version AND t.term IN ({placeholders})) '
            'ORDER BY i.source_id LIMIT 129', (row['partition'], *terms))
        for provider in providers:
            if len(tokenizer_refs) == CAP:
                tokenizer_truncated = True
                break
            provenance = _provenance(_context(provider['payload'])) if provider['payload'] is not None else None
            tokenizer_refs.append({'source_id': provider['source_id'], 'source_version': provider['source_version'],
                                   'fit_id': provenance['fit_id'] if provenance else None})
    supports, rule_truncated = _bounded_supports(rules)
    rule_refs = []
    for source_id, version in supports.items():
        identity = _identity(db, source_id)
        if identity is not None and identity[0] != version:
            _invalid()
        rule_refs.append({'source_id': source_id, 'source_version': version,
                          'fit_id': identity[1] if identity is not None else None})
    result = {'version': 1, 'fit_id': None, 'input_revision': reset.revision(db),
              'model_epoch': reset.epoch(db), 'scope': 'available_learning_inputs',
              'tokenizer_terms': terms, 'tokenizer_terms_total': len(configured),
              'tokenizer_terms_truncated': len(configured) > CAP,
              'tokenizer_sources': tokenizer_refs, 'tokenizer_sources_truncated': tokenizer_truncated,
              'rule_sources': rule_refs, 'rule_sources_truncated': rule_truncated,
              'complete': not (len(configured) > CAP or tokenizer_truncated or rule_truncated
                               or any(r['fit_id'] is None for r in tokenizer_refs + rule_refs))}
    return validate(result)


def plan(db: sqlite3.Connection, source_ids: list[str], *, limit: int) -> dict:
    """One caller-owned BEGIN snapshot; only bounded metadata survives decoding."""
    validate_request(source_ids, limit)
    for source_id in source_ids:
        if db.execute('SELECT 1 FROM brain_inputs WHERE source_id=?', (source_id,)).fetchone() is None:
            raise KeyError('brain input not found')
    revision, epoch = reset.revision(db), reset.epoch(db)
    fits = ('FROM brain_fit_context f JOIN brain_inputs i ON i.source_id=f.source_id '
            'AND i.source_version=f.source_version ')
    total = db.execute('SELECT COUNT(*) ' + fits).fetchone()[0]
    nodes, reverse, known_supports = {}, {}, {}
    untracked = incomplete = 0

    for row in db.execute('SELECT i.source_id,i.source_version,i.model_epoch,i.status,f.payload '
                          + fits + 'ORDER BY i.source_id LIMIT 1000'):
        context = _context(row['payload'])
        provenance = _provenance(context)
        fit_id = provenance['fit_id'] if provenance else None
        complete = provenance is not None and provenance['complete'] and fit_id is not None
        nodes[row['source_id']] = {
            'source_id': row['source_id'], 'source_version': row['source_version'],
            'model_epoch': row['model_epoch'], 'model_active': row['status'] == 'agreed' and row['model_epoch'] == epoch,
            'replay_eligible': row['model_epoch'] == epoch, 'fit_id': fit_id, 'provenance_complete': complete}
        if provenance is None:
            untracked += 1
            supports, _ = _bounded_supports(context.get('learned_rules', []), legacy=True)
            refs = [('rule', {'source_id': s, 'source_version': v, 'fit_id': None}) for s, v in supports.items()]
        else:
            incomplete += not complete
            refs = [(kind, ref) for kind in ('tokenizer', 'rule') for ref in provenance[kind + '_sources']]
        # Discard interpretation, terms, labels and evidence before the next row.
        child = row['source_id']
        del context, provenance, row
        for kind, ref in refs:
            parent = ref['source_id']
            reverse.setdefault(parent, {}).setdefault(child, set()).add(kind)
            # A legacy version alone is not an immutable fit identity. It
            # contributes an exposure and partial coverage, never a change.
            if ref['fit_id'] is not None:
                known_supports.setdefault(parent, set()).add((ref['source_version'], ref['fit_id']))
        del refs
    # User-reviewed edges are exact, current-version, current-epoch claims. They
    # add reachability only; they do not make the computational record partial.
    scanned = len(nodes)
    manual, manual_truncated = relations.fresh_edges(db, SCAN_CAP)
    for edge in manual:
        reverse.setdefault(edge['from_source_id'], {}).setdefault(edge['to_source_id'], set()).add(
            'manual_' + edge['kind'])
    missing = sorted({e['to_source_id'] for e in manual} - set(nodes))
    for batch in (missing[i:i + CAP] for i in range(0, len(missing), CAP)):
        for row in db.execute('SELECT source_id,source_version,model_epoch,status,ever_fitted FROM brain_inputs '
                              'WHERE source_id IN (%s)' % ','.join('?' for _ in batch), batch):
            nodes[row['source_id']] = {
                'source_id': row['source_id'], 'source_version': row['source_version'],
                'model_epoch': row['model_epoch'],
                'model_active': row['status'] == 'agreed' and row['model_epoch'] == epoch,
                'replay_eligible': bool(row['ever_fitted']) and row['model_epoch'] == epoch,
                'fit_id': None, 'provenance_complete': False}
    changed = set()
    for parent, recorded in known_supports.items():
        if parent in nodes:
            current = (nodes[parent]['source_version'], nodes[parent]['fit_id'])
            if any(support != current for support in recorded):
                changed.add(parent)
    # Never decode a second payload or exceed the fit scan budget. An existing
    # fit outside the scan has unknown fit identity; the graph cap already
    # makes coverage partial. Batch only bodyless current-version metadata for
    # missing/unscanned supporters, with at most 128 bindings/rows per query.
    unscanned = (parent for parent in known_supports if parent not in nodes)
    while batch := list(islice(unscanned, CAP)):
        placeholders = ','.join('?' for _ in batch)
        versions = {row['source_id']: row['source_version'] for row in db.execute(
            'SELECT i.source_id,i.source_version FROM brain_inputs i JOIN brain_fit_context f '
            'ON f.source_id=i.source_id AND f.source_version=i.source_version '
            f'WHERE i.source_id IN ({placeholders})', batch)}
        for parent in batch:
            if parent not in versions or any(version != versions[parent]
                                             for version, _ in known_supports[parent]):
                changed.add(parent)
    del known_supports
    distances = dict.fromkeys(source_ids, 0)
    queue = deque(sorted(source_ids))
    while queue:
        parent = queue.popleft()
        for child in sorted(reverse.get(parent, {})):
            if child not in distances:
                distances[child] = distances[parent] + 1
                queue.append(child)
    # All reachable incoming exposures, including longer paths and cycles.
    kinds = {}
    for parent in distances:
        for child, exposures in reverse.get(parent, {}).items():
            kinds.setdefault(child, set()).update(exposures)
    affected_ids = sorted((s for s in distances if distances[s] > 0), key=lambda s: (distances[s], s))
    affected = [{**nodes[s], 'distance': distances[s], 'via_kinds': sorted(kinds[s])}
                for s in affected_ids[:limit]]
    graph_truncated, truncated = total > SCAN_CAP or manual_truncated, len(affected_ids) > limit
    return {'scope': 'recorded_learning_inputs', 'source_ids': list(source_ids),
            'status': 'partial' if untracked or incomplete or changed or graph_truncated or truncated else 'complete',
            'affected': affected, 'total_affected': len(affected_ids), 'truncated': truncated,
            'scanned_sources': scanned, 'total_sources': total, 'graph_truncated': graph_truncated,
            'untracked_sources': untracked, 'incomplete_sources': incomplete, 'changed_supports': len(changed),
            'input_revision': revision, 'model_epoch': epoch}
