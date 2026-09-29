/**
 * A node's detail page (decision D49): opened by double-clicking a tree node.
 * A full-view glass sheet over the tree with the record's neutral example
 * content, its parent, children and cross-links (each opens that record's
 * page). × or Escape returns to the tree.
 */

import { treeStore } from '../app/treeStore';
import { GRAPH } from '../fixtures/graph';
import { regionLabel } from './NodeDetail';

export function NodePage({ id }: { id: string }) {
  const node = GRAPH.nodes.find((n) => n.id === id);
  if (!node) return null;
  const find = (x: string) => GRAPH.nodes.find((n) => n.id === x)!;
  const parent = node.parent ? find(node.parent) : null;
  const children = GRAPH.nodes.filter((n) => n.parent === node.id);
  const links = GRAPH.edges
    .filter((e) => e.kind === 'link' && (e.from === node.id || e.to === node.id))
    .map((e) => find(e.from === node.id ? e.to : e.from));
  const open = (x: string) => treeStore.set({ selected: x, opened: x });
  const group = (title: string, items: typeof children) =>
    items.length > 0 && (
      <section>
        <h3>{title}</h3>
        <div className="node-page__chips">
          {items.map((c) => (
            <button key={c.id} type="button" className="node-page__chip" onClick={() => open(c.id)}>
              {c.label}
            </button>
          ))}
        </div>
      </section>
    );

  return (
    <div className="node-page" role="dialog" aria-modal="true" aria-label={node.label} data-testid="node-page">
      <article className="node-page__sheet">
        <header>
          <span className="node-page__tag">原型演示 · 结构化记录</span>
          <button
            type="button"
            className="node-page__close"
            aria-label="返回科技树"
            onClick={() => treeStore.set({ opened: null })}
          >
            ×
          </button>
        </header>
        <h1>{node.label}</h1>
        <dl className="node-page__meta">
          <dt>编号</dt>
          <dd>{node.id}</dd>
          <dt>层级</dt>
          <dd>{node.depth}</dd>
          <dt>占位脑区</dt>
          <dd>{regionLabel(node.region)}</dd>
        </dl>
        <p className="node-page__body">
          这是一条示例记录的详情页。正式版本里，这里会显示这条记录的结构化内容（标签、来源、时间、可编辑字段），
          分类体系尚未定义，所以现在只展示它在树中的位置与关联。
        </p>
        {group('上级', parent ? [parent] : [])}
        {group('下级', children)}
        {group('关联', links)}
      </article>
    </div>
  );
}
