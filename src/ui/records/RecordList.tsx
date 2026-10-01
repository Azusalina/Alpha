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

type Filter = 'all' | InputStatus;
const FILTERS: readonly Filter[] = ['all', 'pending', 'agreed', 'disagreed', 'revoked'];
const filterLabel = (f: Filter): string => (f === 'all' ? '全部' : STATUS_LABELS[f]);

interface Props {
  s: InputState;
  mode: BackendMode;
}

export function RecordList({ s, mode }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const counts: Record<Filter, number> = { all: s.records.length, pending: 0, agreed: 0, disagreed: 0, revoked: 0 };
  for (const r of s.records) counts[r.status]++;

  const visible = s.records.filter((r) => filter === 'all' || r.status === filter || r.source_id === s.expandedId);
  const empty = s.loaded && s.records.length === 0;

  return (
    <div className="recs" data-testid="records-list-view">
      <div className="recs__filters" role="group" aria-label="按状态筛选" data-testid="record-filters">
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

      {mode === 'unconnected' && (
        <p className="recs__empty" data-testid="records-unconnected">
          后端接通（或进入演示模式）后，过往输入会列在这里。
        </p>
      )}

      {empty && mode !== 'unconnected' && (
        <p className="recs__empty" data-testid="records-empty">
          还没有输入。在右上角写下第一份。
          <small>先点「← 收起大脑」回到输入框。</small>
        </p>
      )}

      {s.records.length > 0 && visible.length === 0 && (
        <p className="recs__empty" data-testid="records-filter-empty">
          没有「{filterLabel(filter)}」的输入。
        </p>
      )}

      {visible.length > 0 && (
        <ul className="recs__list" data-testid="records-list" aria-label="过往输入">
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
          已加载 {s.records.length} / 共 {s.total} 条
          {s.hasMore && (
            <>
              {' · '}
              <button type="button" data-testid="records-more" disabled={s.busy.refresh} onClick={() => void inputStore.loadMore()}>
                {s.busy.refresh ? '加载中…' : '加载更多'}
              </button>
              <small>筛选与计数只针对已加载的记录。</small>
            </>
          )}
        </p>
      )}
    </div>
  );
}
