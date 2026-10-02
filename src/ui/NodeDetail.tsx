/**
 * Detail of one GraphData node, shared by the brain drill-in and the
 * technology tree (spec 4: the same records seen two ways): what the node is,
 * where it hangs, what hangs from it (D65).
 */

import { useState } from 'react';

import { inputStore, useInputs } from '../app/inputStore';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';

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

export const REGION_LABEL: Record<string, string> = {
  semantic: '语义',
  episodic: '情景',
  process: '程序',
  analytic: '分析',
  affective: '情感',
  amygdala: '杏仁核',
  cerebellum: '小脑',
  brainstem: '脑干',
  bridge: '脑桥',
};

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
          重置模型并清空历史
        </button>
      ) : (
        <>
          <p>三个状态回到 0，所有效应历史一并清空，无法恢复。确定吗？</p>
          <div>
            <button type="button" data-testid="model-reset-confirm" disabled={busy} onClick={() => void run()}>
              {busy ? '重置中…' : '确认重置'}
            </button>
            <button type="button" disabled={busy} onClick={() => setAsking(false)}>
              取消
            </button>
          </div>
        </>
      )}
      {!offered && <p className="node-detail__quiet">当前后端没有提供模型重置，按钮暂不可用。</p>}
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
    <aside className="node-detail" data-testid="node-detail" aria-label="节点详情">
      <header>
        <span className="node-detail__tag">{describeNode(selected)}</span>
        <button type="button" aria-label="关闭详情" onClick={() => onSelect(null)}>
          ×
        </button>
      </header>
      <h2>{selected.label}</h2>
      <dl>
        <dt>层级</dt>
        <dd>{selected.depth}</dd>
        {parent && (
          <>
            <dt>上级</dt>
            <dd>{list([parent])}</dd>
          </>
        )}
        {children.length > 0 && (
          <>
            <dt>下级</dt>
            <dd>{list(children)}</dd>
          </>
        )}
      </dl>
      {resettable && selected.kind === 'root' && <ModelReset />}
      <p className="node-detail__note">脑区只是占位的分组，不代表这条内容在大脑里的位置。</p>
    </aside>
  );
}
