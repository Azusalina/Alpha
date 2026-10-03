/**
 * Detail of one GraphData node, shared by the brain drill-in and the
 * technology tree (spec 4: the same records seen two ways): what the node is,
 * where it hangs, what hangs from it (D65).
 */

import { useState } from 'react';

import { inputStore, useInputs } from '../app/inputStore';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';
import { lazyLabels, t } from '../i18n/lang';

/** Placeholder region names (the reference brain model's), shown as such (D36). */
export const REGIONS = [
  'semantic',
  'episodic',
  'process',
  'analytic',
  'affective',
  'amygdala',
  'cerebellum',
  'brainstem',
  'bridge',
] as const;

export const REGION_LABEL: Record<string, string> = lazyLabels(REGIONS, 'region.');

export const regionLabel = (i: number) => REGION_LABEL[REGIONS[i]] ?? '—';

interface Props {
  id: string;
  onSelect: (id: string | null) => void;
  /** Offer the model reset on the main node (the brain page's drill-in only, not the tree). */
  resettable?: boolean;
}

/**
 * Reset the personalised model and clean its history. Two steps, because it cannot be undone; greyed
 * out, with the reason, when the back end does not offer it.
 */
function ModelReset() {
  const s = useInputs();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const offered = inputStore.can('modelReset');
  const run = async () => {
    setBusy(true);
    const err = await inputStore.resetModel();
    setBusy(false);
    if (!err) setAsking(false);
  };
  return (
    <section className="node-detail__reset" data-testid="model-reset">
      {!asking ? (
        <button type="button" data-testid="model-reset-open" disabled={!offered} onClick={() => setAsking(true)}>
          {t('reset.open')}
        </button>
      ) : (
        <>
          <p>{t('reset.ask')}</p>
          <div>
            <button type="button" data-testid="model-reset-confirm" disabled={busy} onClick={() => void run()}>
              {busy ? t('reset.busy') : t('reset.confirm')}
            </button>
            <button type="button" disabled={busy} onClick={() => setAsking(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </>
      )}
      {!offered && <p className="node-detail__quiet">{t('reset.unavailable')}</p>}
      {s.error?.action === 'refresh' && asking && <p className="node-detail__quiet" role="alert">{s.error.message}</p>}
    </section>
  );
}

export function NodeDetail({ id, onSelect, resettable }: Props) {
  const graph = useGraph();
  const selected = graph.nodes.find((n) => n.id === id);
  if (!selected) return null;
  const find = (x: string) => graph.nodes.find((n) => n.id === x)!;
  const parent = selected.parent ? find(selected.parent) : null;
  const children = graph.nodes.filter((n) => n.parent === selected.id);

  const list = (items: typeof children) =>
    items.map((c) => (
      <button key={c.id} type="button" onClick={() => onSelect(c.id)}>
        {c.label}
      </button>
    ));

  return (
    <aside className="node-detail" data-testid="node-detail" aria-label={t('node.detail.aria')}>
      <header>
        <span className="node-detail__tag">{describeNode(selected)}</span>
        <button type="button" aria-label={t('node.detail.close')} onClick={() => onSelect(null)}>
          ×
        </button>
      </header>
      <h2>{selected.label}</h2>
      <dl>
        <dt>{t('node.level')}</dt>
        <dd>{selected.depth}</dd>
        {parent && (
          <>
            <dt>{t('node.parent')}</dt>
            <dd>{list([parent])}</dd>
          </>
        )}
        {children.length > 0 && (
          <>
            <dt>{t('node.children')}</dt>
            <dd>{list(children)}</dd>
          </>
        )}
      </dl>
      {resettable && selected.kind === 'root' && <ModelReset />}
      <p className="node-detail__note">{t('node.detail.note')}</p>
    </aside>
  );
}
