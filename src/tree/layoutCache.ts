/** The one technology-tree layout of the session (deterministic; computed on first use). */

import { GRAPH } from '../fixtures/graph';
import { layoutTree, type TreeLayout } from './layout';

let cached: TreeLayout | null = null;

export function treeLayout(): TreeLayout {
  if (!cached) cached = layoutTree(GRAPH);
  return cached;
}
