/**
 * "输入记录": filter chips with counts, then the bulleted list (ul / li, newest
 * first, every row a real button so the keyboard reaches it), one row open at a
 * time. Filters and counts are over the records LOADED so far (a page is 50);
 * the footer says so and loads the next page. A row the current filter no
 * longer matches but that is open (a pending one just agreed, say) stays in
 * the list until it is closed, so the user keeps seeing what their own click did.
 */

import { useState } from 'react';

import { inputStore } from '../../app/inputStore';
import type { InputState } from '../../app/inputStore';
import type { BackendMode, InputStatus } from '../../backend';
import { STATUS_LABELS } from '../shared/labels';
import { RecordRow } from './RecordRow';
import { t } from '../../i18n/lang';

type Filter = 'all' | InputStatus;
const FILTERS: readonly Filter[] = ['all', 'pending', 'agreed', 'disagreed', 'revoked'];
const filterLabel = (f: Filter): string => (f === 'all' ? t('rec.filter.all') : STATUS_LABELS[f]);

interface Props {
  s: InputState;
  mode: BackendMode;
}

export function RecordList({ s, mode }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const counts: Record<Filter, number> = { all: s.records.length, pending: 0, agreed: 0, disagreed: 0, revoked: 0 };
  for (const r of s.records) counts[r.status]++;

  const visible = s.records.filter((r) => filter === 'all' || r.status === filter || r.source_id === s.expandedId);

  return (
    <div className="recs" data-testid="records-list-view">
      <div className="recs__filters" role="group" aria-label={t('rec.filter.aria')} data-testid="record-filters">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`recs__chip${filter === f ? ' is-on' : ''}`}
            data-testid={`filter-${f}`}
            data-count={counts[f]}
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {filterLabel(f)} <span data-testid={`filter-count-${f}`}>{counts[f]}</span>
          </button>
        ))}
      </div>


      {visible.length > 0 && (
        <ul className="recs__list" data-testid="records-list" aria-label={t('rec.list.aria')}>
          {visible.map((r) => (
            <RecordRow
              key={r.source_id}
              rec={r}
              s={s}
              mode={mode}
              open={s.expandedId === r.source_id}
              sticky={s.expandedId === r.source_id && filter !== 'all' && r.status !== filter}
            />
          ))}
        </ul>
      )}

      {s.records.length > 0 && (
        <p className="recs__foot" data-testid="records-foot">
          {t('rec.list.loaded', { n: s.records.length, total: s.total })}
          {s.hasMore && (
            <>
              {' · '}
              <button type="button" data-testid="records-more" disabled={s.busy.refresh} onClick={() => void inputStore.loadMore()}>
                {s.busy.refresh ? t('rec.list.loading') : t('rec.list.more')}
              </button>
            </>
          )}
        </p>
      )}
    </div>
  );
}
