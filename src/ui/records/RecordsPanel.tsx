/**
 * The RIGHT column of the drilled-in brain (round 3 part 9, D55): what has been
 * said before, and what the model holds now. Two tabs, "输入记录" (the bulleted
 * list with the second judgement, revoke, edit and delete) and "模型状态"
 * (three partitions, 13 parameters each), under the back-end banner.
 *
 * HumanPanel mounts it in `.human-panel__records`, a clipped flex column; this
 * panel scrolls its own content. It only talks to `inputStore` (rows, actions)
 * and, for the state tab, to the adapter through `useModelState`; it never
 * imports a transport. After a judgement the store re-reads the record and the
 * state tab re-reads `state()`: what is shown is what the back end holds.
 *
 * Keyboard: the tabs are a tablist (Left / Right move between them); every row
 * is a button; Escape is handled by HumanPanel's key handler, which asks
 * `inputStore.closeTopLayer` first (editor, then the open row).
 */

import { useEffect, useState } from 'react';
import type { KeyboardEvent } from 'react';

import { useBackend } from '../../backend';
import { inputStore, useInputs } from '../../app/inputStore';
import { BackendBanner } from '../shared/BackendBanner';
import { ModelStateView } from './ModelStateView';
import { RecordList } from './RecordList';
import { useModelState } from './useModelState';
import './records.css';

type Tab = 'records' | 'state';
const TABS: readonly { id: Tab; label: string }[] = [
  { id: 'records', label: '输入记录' },
  { id: 'state', label: '模型状态' },
];

export function RecordsPanel() {
  const backend = useBackend();
  const s = useInputs();
  const model = useModelState();
  const [tab, setTab] = useState<Tab>('records');

  useEffect(() => {
    void inputStore.ensureLoaded();
  }, [backend.generation]);

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const next: Tab = tab === 'records' ? 'state' : 'records';
    setTab(next);
    requestAnimationFrame(() => document.getElementById(`records-tab-${next}`)?.focus());
    e.preventDefault();
  };

  // The global T key switches the theme. A focused button here that reads like
  // "T 认可为真" must not do that: T stops at this panel, as in the entry panel
  // (the button is clicked, T is not a shortcut for it).
  const stopT = (e: KeyboardEvent) => {
    if ((e.key === 't' || e.key === 'T') && !e.ctrlKey && !e.metaKey && !e.altKey) e.stopPropagation();
  };

  // errors that belong to no row (loading the list, paging, capabilities)
  const panelError = s.error && s.error.id === null && s.error.action !== 'submit' ? s.error : null;

  return (
    <section className="records-panel" data-testid="records-panel" aria-label="过往输入与模型状态" onKeyDown={stopT}>
      <BackendBanner />
      <div className="records-panel__tabs" role="tablist" aria-label="右侧面板" onKeyDown={onKey}>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`records-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`records-tabpanel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            className={`records-panel__tab${tab === t.id ? ' is-on' : ''}`}
            data-testid={`tab-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.id === 'records' && s.total > 0 && <small>{s.total}</small>}
          </button>
        ))}
      </div>
      {panelError && (
        <p className="rec__error records-panel__error" role="alert" data-testid="records-error">
          <code>{panelError.code}</code> {panelError.message}{' '}
          <button type="button" onClick={() => void inputStore.refresh().then(() => inputStore.dismissError())}>
            重试
          </button>
        </p>
      )}
      <div
        className="records-panel__scroll"
        role="tabpanel"
        id={`records-tabpanel-${tab}`}
        aria-labelledby={`records-tab-${tab}`}
        data-testid={`tabpanel-${tab}`}
      >
        {tab === 'records' ? <RecordList s={s} mode={backend.mode} /> : <ModelStateView view={model} connected={backend.mode !== 'unconnected'} />}
      </div>
    </section>
  );
}
