/**
 * Detail of one GraphData node, shared by the brain drill-in and the
 * technology tree (spec 4: the same records seen two ways). Neutral example
 * content, labelled as a prototype demonstration.
 */

import { GRAPH } from '../fixtures/graph';

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
}

export function NodeDetail({ id, onSelect }: Props) {
  const selected = GRAPH.nodes.find((n) => n.id === id);
  if (!selected) return null;
  const find = (x: string) => GRAPH.nodes.find((n) => n.id === x)!;
  const parent = selected.parent ? find(selected.parent) : null;
  const children = GRAPH.nodes.filter((n) => n.parent === selected.id);
  const links = GRAPH.edges
    .filter((e) => e.kind === 'link' && (e.from === selected.id || e.to === selected.id))
    .map((e) => find(e.from === selected.id ? e.to : e.from));

  const list = (items: typeof children) =>
    items.map((c) => (
      <button key={c.id} type="button" onClick={() => onSelect(c.id)}>
        {c.label}
      </button>
    ));

  return (
    <aside className="node-detail" data-testid="node-detail" aria-label="节点详情">
      <header>
        <span className="node-detail__tag">原型演示</span>
        <button type="button" aria-label="关闭详情" onClick={() => onSelect(null)}>
          ×
        </button>
      </header>
      <h2>{selected.label}</h2>
      <dl>
        <dt>编号</dt>
        <dd>{selected.id}</dd>
        <dt>层级</dt>
        <dd>{selected.depth}</dd>
        <dt>占位脑区</dt>
        <dd>{regionLabel(selected.region)}</dd>
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
        {links.length > 0 && (
          <>
            <dt>关联</dt>
            <dd>{list(links)}</dd>
          </>
        )}
      </dl>
      <p className="node-detail__note">示例记录，不代表真实记忆；分类体系尚未定义。</p>
    </aside>
  );
}
