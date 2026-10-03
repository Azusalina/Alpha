/** One-line descriptions of graph nodes, shared by the tree's caption and the node pages (D65). */

import type { GraphNode } from '../fixtures/graph';
import { parameterLabel, PARTITION_LABELS } from '../ui/shared/labels';
import { lazyLabels, t } from '../i18n/lang';

export const NODE_KIND_LABELS: Record<GraphNode['kind'], string> = lazyLabels(['root', 'partition', 'parameter', 'input'] as const, 'node.kind.');

const signed = (n: number): string => `${n > 0 ? '+' : ''}${(Math.round(n * 1000) / 1000).toString()}`;

/** `Input · Rational · Autonomy · change +0.2` and the like; never invents a fact the node does not carry. */
export function describeNode(n: GraphNode): string {
  const parts: string[] = [NODE_KIND_LABELS[n.kind]];
  if (n.kind !== 'root' && n.partition) parts.push(PARTITION_LABELS[n.partition]);
  if (n.kind === 'input' && n.parameter) parts.push(parameterLabel(n.parameter));
  if (n.kind === 'input' && n.delta !== undefined) parts.push(t('node.delta', { n: signed(n.delta) }));
  if (n.forkOn) parts.push(t('node.fork'));
  return parts.join(' · ');
}
