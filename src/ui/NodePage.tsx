/**
 * A node's detail page (decision D49, D65): opened by double-clicking a tree
 * node. A full-view glass sheet over the tree: what the node is, its parent and
 * children (each opens that node's page), and for an input its original text,
 * read from the back end. × or Escape returns to the tree.
 */

import { useEffect, useState } from 'react';

import { treeStore } from '../app/treeStore';
import { getAdapter } from '../backend';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';

export function NodePage({ id }: { id: string }) {
  const graph = useGraph();
  const node = graph.nodes.find((n) => n.id === id);
  const sourceId = node?.sourceId;
  const [text, setText] = useState<{ id: string; value: string } | { id: string; error: string } | null>(null);

  useEffect(() => {
    if (!sourceId) return;
    let live = true;
    getAdapter()
      .inputGet(sourceId)
      .then((d) => live && setText({ id: sourceId, value: d.text }))
      .catch(() => live && setText({ id: sourceId, error: '读取不到原文（输入可能已被编辑或删除）' }));
    return () => {
      live = false;
    };
  }, [sourceId]);

  if (!node) return null;
  const find = (x: string) => graph.nodes.find((n) => n.id === x)!;
  const parent = node.parent ? find(node.parent) : null;
  const children = graph.nodes.filter((n) => n.parent === node.id);
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
  const shown = text && sourceId && text.id === sourceId ? text : null;

  return (
    <div className="node-page" role="dialog" aria-modal="true" aria-label={node.label} data-testid="node-page">
      <article className="node-page__sheet">
        <header>
          <span className="node-page__tag">{describeNode(node)}</span>
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
          <dt>层级</dt>
          <dd>{node.depth}</dd>
          {node.parameter && (
            <>
              <dt>参数</dt>
              <dd>{node.parameter}</dd>
            </>
          )}
        </dl>
        {sourceId && (
          <p className="node-page__body" data-testid="node-page-text" style={{ whiteSpace: 'pre-wrap' }}>
            {shown ? ('value' in shown ? shown.value : shown.error) : '读取原文中…'}
          </p>
        )}
        {group('上级', parent ? [parent] : [])}
        {group('下级', children)}
      </article>
    </div>
  );
}
